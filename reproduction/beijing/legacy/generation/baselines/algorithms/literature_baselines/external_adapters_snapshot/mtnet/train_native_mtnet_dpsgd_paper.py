"""Literal fixed-B implementation of MTNet paper Algorithm 1.

Unlike the audited Poisson prototype, this file follows the paper's stated
fixed-size uniformly sampled minibatch.  C and sigma are required because the
paper reports neither value.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.func import functional_call, grad, vmap


def single_trajectory_loss(model, x, dpt, tcost, y, balance: float):
    pred_x, pred_t = model(x, dpt)
    labels = y.reshape(-1)
    rows = torch.arange(labels.numel(), device=labels.device)
    route_loss = -pred_x[rows, labels].sum()
    time_residual = pred_t[rows, labels] - tcost.reshape(-1)
    time_residual[labels == 0] = 0.0
    return route_loss + balance * time_residual.abs().sum()


def vectorized_clipped_sum(model, params, buffers, x, dpt, tcost, y, bound: float,
                           microbatch_size: int, progress, balance: float):
    """Exact per-trajectory clipping, evaluated in vectorized microbatches.

    A microbatch is only a computational container. ``vmap(grad(...))`` retains
    a separate full-parameter gradient and clipping factor for every trajectory
    before their clipped gradients are summed, exactly as Algorithm 1 requires.
    """
    def loss_for_one(parameters, module_buffers, one_x, one_dpt, one_tcost, one_y):
        pred_x, pred_t = functional_call(
            model, (parameters, module_buffers),
            (one_x.unsqueeze(0), one_dpt.unsqueeze(0)))
        labels = one_y.reshape(-1)
        rows = torch.arange(labels.numel(), device=labels.device)
        route_loss = -pred_x[rows, labels].sum()
        residual = pred_t[rows, labels] - one_tcost.reshape(-1)
        residual = residual.masked_fill(labels == 0, 0.0)
        return route_loss + balance * residual.abs().sum()

    one_grad = grad(loss_for_one)
    per_sample_grad = vmap(one_grad, in_dims=(None, None, 0, 0, 0, 0), randomness='different')
    totals = {name: torch.zeros_like(parameter) for name, parameter in params.items()}
    norms, losses, clipped = [], [], 0
    n = x.size(0)
    for start in range(0, n, microbatch_size):
        stop = min(n, start + microbatch_size)
        gradients = per_sample_grad(params, buffers, x[start:stop], dpt[start:stop],
                                    tcost[start:stop], y[start:stop])
        sq = torch.zeros(stop - start, device=x.device)
        for value in gradients.values():
            sq.add_(value.reshape(stop - start, -1).pow(2).sum(dim=1))
        norm = sq.sqrt()
        scale = (bound / (norm + 1e-12)).clamp(max=1.0)
        for name, value in gradients.items():
            # This is the clipped-gradient accumulator, not part of a higher
            # order derivative graph. Detach each microbatch before retaining it.
            totals[name].add_((value * scale.view(-1, *([1] * (value.ndim - 1)))).sum(dim=0).detach())
        norms.extend(norm.detach().cpu().tolist())
        clipped += int((scale < 1.0).sum().item())
        # Do not retain a per-sample-gradient tensor across microbatches.
        del gradients, sq, norm, scale
        progress(stop, n)
    return totals, losses, norms, clipped


def install_vmap_step_compatibility(mtnet, config):
    """Install a mathematically identical, vmap-compatible official step."""
    def functional_lstm_cell(cell, value, state):
        """LSTMCell equations expressed with tensor primitives supported by vmap."""
        hidden, memory = state
        gates = (F.linear(value, cell.weight_ih, cell.bias_ih) +
                 F.linear(hidden, cell.weight_hh, cell.bias_hh))
        input_gate, forget_gate, candidate, output_gate = gates.chunk(4, dim=1)
        input_gate = torch.sigmoid(input_gate)
        forget_gate = torch.sigmoid(forget_gate)
        candidate = torch.tanh(candidate)
        output_gate = torch.sigmoid(output_gate)
        memory = forget_gate * memory + input_gate * candidate
        hidden = output_gate * torch.tanh(memory)
        return hidden, memory

    def step(self, xt, dptslot, hs, cs):
        B = xt.size(0)
        zt = torch.randn(B, self.z_dim, device=xt.device)
        xt_emb = self.x_emb(xt)
        tt_emb = self.t_emb(dptslot.long())
        xt_eprop = self.eprop[xt]
        hidden = torch.cat([zt, xt_emb, tt_emb, xt_eprop], dim=-1)
        for i, lstm in enumerate(self.lstms):
            hs[i], cs[i] = functional_lstm_cell(lstm, hidden, (hs[i], cs[i]))
            hidden = hs[i]
        afterx = self.linear_afterx(hidden)
        adjs = self.adj[xt]
        tt_emb = tt_emb.unsqueeze(1).expand(-1, self.adj.size(1), -1)
        aftert = self.linear_aftert(torch.cat([self.tcost_emb(adjs), tt_emb], dim=-1))
        props = self.eprop[adjs]
        mk = torch.cat([self.x_emb(adjs), tt_emb, props], -1)
        softmax_w = self.mlp_meta_x(mk); sigmoid_w = self.mlp_meta_t(mk)
        pred_xnext = afterx.view(B, 1, 1, -1).matmul(
            softmax_w.view(B, self.adj.size(1), -1, 1)).view(B, -1)
        invalid = adjs == self.adj.size(0) + config.ADJ_MASK
        pred_xnext = pred_xnext.masked_fill(invalid, float('-inf'))
        pred_tnext = aftert.unsqueeze(2).matmul(sigmoid_w.unsqueeze(-1)).view(B, self.adj.size(1))
        return (pred_xnext, pred_tnext), hs, cs
    mtnet.Model.step = step


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--mtnet-root', type=Path, required=True)
    p.add_argument('--data-parent', type=Path, required=True)
    p.add_argument('--city', required=True)
    p.add_argument('--max-route-edges', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=30)
    p.add_argument('--batch-size', type=int, default=8192,
                   help='Author official demo config default B; every update uses exactly B samples')
    p.add_argument('--clip-C', type=float, required=True, help='Algorithm 1 gradient bound C')
    p.add_argument('--sigma', type=float, default=None, help='Algorithm 1 noise multiplier sigma')
    p.add_argument('--target-epsilon', type=float, default=None,
                   help='Calibrate sigma for this total fixed-B training run')
    p.add_argument('--target-delta', type=float, default=None,
                   help='Required with --target-epsilon')
    p.add_argument('--adjacency', choices=['replace'], default='replace',
                   help='Dataset adjacency. This fixed-B=N implementation preserves cardinality, so replacement is the supported relation.')
    p.add_argument('--steps-per-epoch', type=int, default=None,
                   help='Default floor(N/B), so every update has exactly B samples')
    p.add_argument('--progress-every', type=int, default=25,
                   help='Report trajectory-level progress while accumulating a fixed batch')
    p.add_argument('--gradient-engine', choices=['sequential', 'vmap'], default='vmap',
                   help='vmap uses an algebraically identical LSTMCell expansion for exact per-trajectory gradients.')
    p.add_argument('--microbatch-size', type=int, default=4,
                   help='Per-sample-gradient vectorization chunk for --gradient-engine vmap')
    p.add_argument('--seed', type=int, default=20260712)
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    if (a.target_epsilon is None) != (a.target_delta is None):
        p.error('--target-epsilon and --target-delta must be supplied together')
    if a.sigma is not None and a.target_epsilon is not None:
        p.error('supply either --sigma or a target privacy budget, not both')
    root = a.mtnet_root.resolve(); os.chdir(root); sys.path.insert(0, str(root))
    from util import config
    from util.dataloader import GenDataset, load_edgeadjs, load_trajs_raw
    import mtnet
    if a.gradient_engine == 'vmap':
        install_vmap_step_compatibility(mtnet, config)
    config.DATA_BASE = str(a.data_parent.resolve()) + os.sep
    config.CITY = a.city
    config.TRAJ_FIX_LEN = a.max_route_edges + 1
    config.SPLIT_PER = 1.0
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(a.seed)
    adjs = load_edgeadjs()
    train_set, _ = load_trajs_raw()
    dataset = GenDataset(adjs, *train_set)
    n = len(dataset)
    if a.batch_size > n:
        raise ValueError('B cannot exceed the full training population')
    steps_per_epoch = a.steps_per_epoch or (n // a.batch_size)
    total_steps = a.epochs * steps_per_epoch
    accountant = None
    if a.sigma is None:
        if a.target_epsilon is None:
            p.error('supply --sigma or (--target-epsilon, --target-delta)')
        # Conservative RDP composition for the Gaussian mechanism.  It ignores
        # subsampling amplification, hence remains valid for fixed-B sampling.
        orders = np.concatenate([np.arange(1.1, 32.0, 0.1), np.arange(32, 513)])
        def epsilon_for(sigma):
            # Replacing one record changes a clipped sum by at most 2C.
            # With noise sigma*C, the Gaussian RDP term is therefore four
            # times the add/remove term C^2/(2 sigma^2).
            values = total_steps * (4.0 * orders) / (2.0 * sigma * sigma) + np.log(1.0 / a.target_delta) / (orders - 1.0)
            return float(values.min())
        low, high = 1e-6, 1.0
        while epsilon_for(high) > a.target_epsilon:
            high *= 2.0
        for _ in range(80):
            mid = (low + high) / 2.0
            if epsilon_for(mid) <= a.target_epsilon: high = mid
            else: low = mid
        a.sigma = high
        accountant = {'type': 'conservative Gaussian RDP composition without subsampling amplification',
                       'adjacency': 'replace one complete trajectory', 'sensitivity': '2C',
                       'target_epsilon': a.target_epsilon, 'target_delta': a.target_delta,
                       'certified_epsilon_upper_bound': epsilon_for(a.sigma), 'total_steps': total_steps}
    model = mtnet.Model()
    if a.gradient_engine == 'sequential':
        # Current PyTorch promotes the official integral time slots to float.
        official_step = model.step
        def pytorch_dtype_compatibility_step(xt, dptslot, hs, cs):
            return official_step(xt, dptslot.long(), hs, cs)
        model.step = pytorch_dtype_compatibility_step
    optimizer = torch.optim.Adam(model.parameters())  # same optimizer as source train.py
    params = [parameter for parameter in model.parameters() if parameter.requires_grad]
    history = []
    for epoch in range(a.epochs):
        losses, norms, clipped = [], [], 0
        for step in range(steps_per_epoch):
            # Algorithm 1 line 4: uniform fixed-size B minibatch.
            indices = random.sample(range(n), a.batch_size)
            accumulated = [torch.zeros_like(parameter) for parameter in params]
            t_step = time.time()
            if a.gradient_engine == 'vmap':
                selected = [dataset[index] for index in indices]
                bx = torch.stack([item[0] for item in selected]).to(config.device)
                bdpt = torch.stack([item[1] for item in selected]).to(config.device)
                btcost = torch.stack([item[2] for item in selected]).to(config.device)
                by = torch.stack([item[3] for item in selected]).to(config.device)
                parameter_map = dict(model.named_parameters())
                buffer_map = dict(model.named_buffers())
                def report(position, total):
                    if a.progress_every and (position % a.progress_every == 0 or position == total):
                        print(json.dumps({'epoch': epoch, 'step': step + 1,
                                          'trajectory_progress': f'{position}/{total}',
                                          'elapsed_seconds': round(time.time() - t_step, 1),
                                          'gradient_engine': 'vmap'}), flush=True)
                summed, batch_losses, batch_norms, batch_clipped = vectorized_clipped_sum(
                    model, parameter_map, buffer_map, bx, bdpt, btcost, by, a.clip_C,
                    a.microbatch_size, report, config.LAMBDA)
                losses.extend(batch_losses); norms.extend(batch_norms); clipped += batch_clipped
                accumulated = [summed[name] for name, _ in model.named_parameters()]
            else:
                for position, index in enumerate(indices, start=1):
                    x, dpt, tcost, y = dataset[index]
                    optimizer.zero_grad(set_to_none=True)
                    loss = single_trajectory_loss(model, x.unsqueeze(0).to(config.device),
                        dpt.unsqueeze(0).to(config.device), tcost.unsqueeze(0).to(config.device),
                        y.unsqueeze(0).to(config.device), config.LAMBDA)
                    loss.backward()
                    sq_norm = sum((parameter.grad.detach().pow(2).sum() for parameter in params if parameter.grad is not None),
                                  torch.zeros((), device=config.device))
                    norm = float(torch.sqrt(sq_norm).item())
                    scale = min(1.0, a.clip_C / (norm + 1e-12))
                    clipped += int(scale < 1.0); norms.append(norm); losses.append(float(loss.item()))
                    for total, parameter in zip(accumulated, params):
                        if parameter.grad is not None:
                            total.add_(parameter.grad.detach(), alpha=scale)
                    if a.progress_every and (position % a.progress_every == 0 or position == a.batch_size):
                        print(json.dumps({'epoch': epoch, 'step': step + 1,
                                          'trajectory_progress': f'{position}/{a.batch_size}',
                                          'elapsed_seconds': round(time.time() - t_step,
                                          1), 'gradient_engine': 'sequential'}), flush=True)
            # Algorithm 1 lines 9-10: N(0, sigma^2 C^2 I), then divide by B.
            optimizer.zero_grad(set_to_none=True)
            for total, parameter in zip(accumulated, params):
                parameter.grad = (total + torch.randn_like(total) * (a.sigma * a.clip_C)) / a.batch_size
            optimizer.step()
        record = {'epoch': epoch, 'steps': steps_per_epoch,
                  'mean_loss': float(np.mean(losses)) if losses else None,
                  'mean_unclipped_norm': float(np.mean(norms)), 'clip_fraction': clipped / len(norms)}
        history.append(record); print(json.dumps(record), flush=True)
    torch.save({'state_dict': model.state_dict(), 'privacy_unit': 'one complete trajectory',
                'fixed_batch_B': a.batch_size, 'clip_C': a.clip_C, 'sigma': a.sigma,
                'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch}, a.out / 'model.pt')
    manifest = {'implementation': 'MTNet Algorithm 1 fixed-B DP-SGD',
                'sampling': 'uniform fixed-size B each update', 'privacy_unit': 'one complete trajectory',
                'n_trajectories': n, 'B': a.batch_size, 'C': a.clip_C, 'sigma': a.sigma,
                'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch,
                'gradient_engine': a.gradient_engine, 'microbatch_size': a.microbatch_size,
                'privacy_accountant': accountant,
                'private_training_diagnostics': {
                    'release_status': 'no raw training aggregates are written to this release directory',
                },
                'paper_reported_protocol': {
                    'epsilon': 1.0, 'delta': 1e-5, 'max_epochs': 30,
                    'early_stop': 'route-JSD, patience 5', 'default_L': 20,
                    'lambda': 0.1, 'LSTM_layers': 2, 'feedforward_layers': 1,
                },
                'author_source_defaults': {
                    'BATCH_SIZE': 8192, 'EPOCHS': 3, 'USE_TGRAPH': True,
                    'source': 'util/config.py in the author-provided core repository',
                },
                'compatibility_adapter': 'Current PyTorch requires integer embedding indices. The sequential backend casts only time-slot dtype to long. The vmap backend additionally replaces the identical boolean-index assignment with masked_fill because vmap forbids dynamic-shape boolean indexing.',
                'run_status': 'Algorithm-1 execution smoke test or local variant; not an author-hyperparameter numerical reproduction.',
                'numerical_privacy_limit': 'Paper does not disclose C, sigma, or the cross-step accountant parameters; this run must not be labelled epsilon=1 unless those author settings are supplied and audited.'}
    (a.out / 'paper_algorithm_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
