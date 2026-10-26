"""Fixed-B DP-SGD implementation following the MTNet Algorithm 1 update.

Unlike the audited Poisson prototype, this file follows the paper's stated
fixed-size uniformly sampled minibatch.  C and sigma are required because the
paper reports neither value. A local budget is therefore an audit of this
implementation, not a numerical reproduction of undisclosed author settings.
"""
from __future__ import annotations

import argparse
import hashlib
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_loss_curve(history, destination: Path) -> None:
    """Write an internal training diagnostic, never a released DP statistic."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    points = [(entry['epoch'] + 1, entry.get('route_nll_probe')) for entry in history
              if entry.get('route_nll_probe') is not None]
    if not points:
        return
    epoch, value = zip(*points)
    fig, ax = plt.subplots(figsize=(6.2, 3.6), constrained_layout=True)
    ax.plot(epoch, value, color='#0077a8', marker='o', markersize=3.5, linewidth=1.7)
    ax.set(xlabel='DP-SGD epoch', ylabel='Route NLL on fixed private probe',
           title='Private diagnostic only (not a released DP utility result)')
    ax.grid(alpha=0.25)
    fig.savefig(destination, dpi=220)
    plt.close(fig)


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
    p.add_argument('--accountant-delta', type=float, default=1e-5,
                   help='Delta used to report a bound when --sigma is supplied directly')
    p.add_argument('--adjacency', choices=['replace'], default='replace',
                   help='Dataset adjacency. This fixed-B=N implementation preserves cardinality, so replacement is the supported relation.')
    p.add_argument('--dataset-size-public', action='store_true',
                   help='Required: certify that the fixed population size and B are public protocol constants.')
    p.add_argument('--release-condition-policy', choices=['not_releasing', 'public_fixed', 'separately_dp'],
                   default='not_releasing',
                   help='How generation conditions will be obtained; private raw conditions are forbidden.')
    p.add_argument('--steps-per-epoch', type=int, default=None,
                   help='Default floor(N/B), so every update has exactly B samples')
    p.add_argument('--progress-every', type=int, default=25,
                   help='Report trajectory-level progress while accumulating a fixed batch')
    p.add_argument('--gradient-engine', choices=['sequential', 'vmap'], default='vmap',
                   help='vmap uses an algebraically identical LSTMCell expansion for exact per-trajectory gradients.')
    p.add_argument('--expected-mtnet-sha256',
                   help='Optional source lock. Abort if mtnet.py differs from this SHA256.')
    p.add_argument('--source-lock', type=Path,
                   default=Path(__file__).with_name('canonical_mtnet_source_lock.json'),
                   help='Canonical author-source lock JSON. Set to an explicit audited lock for strict runs.')
    p.add_argument('--dp-domain-scope', choices=['prepared_aligned', 'raw_recordwise'], default='prepared_aligned',
                   help='prepared_aligned follows the paper input domain; raw_recordwise is a strengthened extension.')
    p.add_argument('--dp-domain-manifest', type=Path,
                   help='Required only for raw_recordwise mode, which proves fixed-cardinality preprocessing.')
    p.add_argument('--microbatch-size', type=int, default=4,
                   help='Per-sample-gradient vectorization chunk for --gradient-engine vmap')
    p.add_argument('--resume', action='store_true',
                   help='Resume an interrupted run from the epoch-boundary checkpoint')
    p.add_argument('--loss-probe-size', type=int, default=128,
                   help='Fixed private training probe used only for the local diagnostic loss curve')
    p.add_argument('--split-per', type=float, default=1.0,
                   help='Training fraction from the author-format corpus. Use <1 only for fixed held-out diagnostics; it never selects a checkpoint.')
    p.add_argument('--heldout-probe-size', type=int, default=0,
                   help='If positive and --split-per < 1, record route NLL on this fixed held-out private probe outside the DP release.')
    p.add_argument('--seed', type=int, default=20260712)
    p.add_argument('--data-split-seed', type=int, default=None,
                   help='Public fixed seed for the author-loader partition; defaults to --seed.')
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
    if (a.target_epsilon is None) != (a.target_delta is None):
        p.error('--target-epsilon and --target-delta must be supplied together')
    if a.sigma is not None and a.target_epsilon is not None:
        p.error('supply either --sigma or a target privacy budget, not both')
    if not a.dataset_size_public:
        p.error('--dataset-size-public is required for fixed-B replacement-adjacency accounting')
    domain = None
    declared_raw_count = None
    if a.dp_domain_scope == 'raw_recordwise':
        if a.dp_domain_manifest is None:
            p.error('--raw_recordwise requires --dp-domain-manifest')
        domain = json.loads(a.dp_domain_manifest.read_text(encoding='utf-8'))
        if not domain.get('recordwise_preprocessing'):
            raise RuntimeError('Retained-only FMM input is diagnostic only and cannot certify raw-trajectory DP.')
        if domain.get('privacy_unit') != 'one raw trajectory before public record-wise map matching':
            raise RuntimeError('The DP domain manifest does not bind one raw trajectory to one fixed training row.')
        declared_raw_count = int(domain['selected_raw_train_records'])
        if declared_raw_count != int(domain['mtnet_training_rows']):
            raise RuntimeError('Strict raw-trajectory DP requires exactly one output row per raw input trajectory.')
    domain_manifest_path = str(a.dp_domain_manifest.resolve()) if a.dp_domain_manifest is not None else None
    root = a.mtnet_root.resolve(); os.chdir(root); sys.path.insert(0, str(root))
    from util import config
    from util.dataloader import GenDataset, load_edgeadjs, load_trajs_raw
    import mtnet
    source_files = {name: root / relative for name, relative in {
        'mtnet.py': 'mtnet.py', 'train.py': 'train.py', 'util/config.py': 'util/config.py'}.items()}
    source_fingerprint = {name: sha256_file(path) for name, path in source_files.items()}
    lock = json.loads(a.source_lock.read_text(encoding='utf-8'))
    expected_files = lock.get('files_sha256', {})
    normalized_expected = {name: str(value).lower() for name, value in expected_files.items()}
    if source_fingerprint != normalized_expected:
        mismatch = {name: {'expected': normalized_expected.get(name), 'observed': source_fingerprint.get(name)}
                    for name in source_files if normalized_expected.get(name) != source_fingerprint.get(name)}
        raise RuntimeError(f'MTNet source tree does not match canonical source lock: {mismatch}')
    if a.expected_mtnet_sha256 and source_fingerprint['mtnet.py'].lower() != a.expected_mtnet_sha256.lower():
        raise RuntimeError('mtnet.py SHA256 differs from --expected-mtnet-sha256')
    source_defaults = {
        'BATCH_SIZE': config.BATCH_SIZE, 'EPOCHS': config.EPOCHS,
        'USE_TGRAPH': config.USE_TGRAPH, 'TRAJ_FIX_LEN': config.TRAJ_FIX_LEN,
        'LAMBDA': config.LAMBDA, 'LSTMS_NUM': config.LSTMS_NUM, 'L2_NUM': config.L2_NUM,
    }
    if source_defaults != lock.get('source_defaults'):
        raise RuntimeError('Imported MTNet defaults do not match the canonical source lock')
    if a.gradient_engine == 'vmap':
        install_vmap_step_compatibility(mtnet, config)
    config.DATA_BASE = str(a.data_parent.resolve()) + os.sep
    config.CITY = a.city
    config.TRAJ_FIX_LEN = a.max_route_edges + 1
    if not (0.0 < a.split_per <= 1.0):
        p.error('--split-per must lie in (0, 1]')
    if a.heldout_probe_size and a.split_per >= 1.0:
        p.error('--heldout-probe-size requires --split-per < 1')
    config.SPLIT_PER = a.split_per
    data_split_seed = a.seed if a.data_split_seed is None else a.data_split_seed
    # The author loader uses NumPy shuffling to construct its train/test split.
    random.seed(data_split_seed); np.random.seed(data_split_seed); torch.manual_seed(data_split_seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(data_split_seed)
    adjs = load_edgeadjs()
    train_set, heldout_set = load_trajs_raw()
    dataset = GenDataset(adjs, *train_set)
    heldout_dataset = GenDataset(adjs, *heldout_set) if a.heldout_probe_size else None
    n = len(dataset)
    if declared_raw_count is not None and n != declared_raw_count:
        raise RuntimeError(f'Loaded dataset has {n} rows but the strict DP domain declares {declared_raw_count}.')
    if a.batch_size > n:
        raise ValueError('B cannot exceed the full training population')
    # Reset only after the public split is fixed, so repeated training seeds
    # share exactly one held-out population.
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(a.seed)
    steps_per_epoch = a.steps_per_epoch or (n // a.batch_size)
    total_steps = a.epochs * steps_per_epoch
    accountant_delta = a.target_delta if a.target_delta is not None else a.accountant_delta
    # Conservative RDP composition for the Gaussian mechanism. It ignores
    # sampling amplification and is consequently valid for fixed-B updates.
    orders = np.concatenate([np.arange(1.1, 32.0, 0.1), np.arange(32, 513)])
    def epsilon_for(sigma):
        if total_steps == 0:
            return 0.0
        # Replacement changes a clipped sum by at most 2C. With Gaussian
        # standard deviation sigma*C, per-step RDP is 2*alpha/sigma^2.
        values = total_steps * (2.0 * orders) / (sigma * sigma) + np.log(1.0 / accountant_delta) / (orders - 1.0)
        return float(values.min())
    if a.sigma is None:
        if a.target_epsilon is None:
            p.error('supply --sigma or (--target-epsilon, --target-delta)')
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
                   'requested_target_epsilon': a.target_epsilon, 'delta': accountant_delta,
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
    parameter_count = sum(parameter.numel() for parameter in params)
    expected_noise_l2 = a.sigma * a.clip_C * math.sqrt(parameter_count)
    maximum_clipped_sum_l2 = a.batch_size * a.clip_C
    utility_preflight = {
        'trainable_parameter_count': parameter_count,
        'expected_noise_l2_before_averaging': expected_noise_l2,
        'maximum_possible_clipped_sum_l2_before_averaging': maximum_clipped_sum_l2,
        'noise_to_maximum_signal_ratio': expected_noise_l2 / maximum_clipped_sum_l2,
        'status': 'unverified: requires independent-seed and held-out utility evaluation',
    }
    history = []
    # Training curves, clipping summaries, and resume state are private
    # diagnostics. Keep them outside the release directory because they are
    # direct functions of the private training corpus, not DP releases.
    diagnostic_dir = Path(str(a.out) + '_private_training_state')
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = diagnostic_dir / 'epoch_boundary_checkpoint.pt'
    progress_path = diagnostic_dir / 'training_progress.json'
    start_epoch = 0
    if a.resume:
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f'--resume requested but {checkpoint_path} is absent')
        # This checkpoint is generated locally by this script and contains
        # Python/NumPy RNG states required for an exact epoch-boundary resume.
        saved = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        # ``microbatch_size`` changes only how independent per-trajectory
        # gradients are evaluated; it is not a DP mechanism parameter.
        expected = {'n_trajectories': n, 'B': a.batch_size, 'dataset_size_public': a.dataset_size_public,
                    'dp_domain_manifest': domain_manifest_path,
                    'release_condition_policy': a.release_condition_policy, 'clip_C': a.clip_C,
                    'sigma': a.sigma, 'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch,
                    'gradient_engine': a.gradient_engine, 'split_per': a.split_per,
                    'data_split_seed': data_split_seed, 'training_seed': a.seed,
                    'heldout_probe_size': min(a.heldout_probe_size, len(heldout_dataset)) if heldout_dataset else 0}
        saved_protocol = {key: saved.get('protocol', {}).get(key) for key in expected}
        if saved_protocol != expected:
            raise RuntimeError('checkpoint protocol differs from the requested run')
        model.load_state_dict(saved['state_dict']); optimizer.load_state_dict(saved['optimizer_state_dict'])
        for optimizer_state in optimizer.state.values():
            for key, value in optimizer_state.items():
                if torch.is_tensor(value):
                    optimizer_state[key] = value.to(config.device)
        history = list(saved['history']); start_epoch = int(saved['next_epoch'])
        random.setstate(saved['python_random_state']); np.random.set_state(saved['numpy_random_state'])
        torch.set_rng_state(saved['torch_random_state'].cpu())
        if torch.cuda.is_available() and saved.get('cuda_random_state') is not None:
            torch.cuda.set_rng_state(saved['cuda_random_state'].cpu())
        print(json.dumps({'resumed_from_epoch': start_epoch, 'completed_epochs': len(history)}), flush=True)
    protocol = {'n_trajectories': n, 'B': a.batch_size, 'dataset_size_public': a.dataset_size_public,
                'dp_domain_manifest': domain_manifest_path,
                'release_condition_policy': a.release_condition_policy, 'clip_C': a.clip_C,
                'sigma': a.sigma, 'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch,
                'gradient_engine': a.gradient_engine, 'microbatch_size': a.microbatch_size,
                'loss_probe_size': min(a.loss_probe_size, n), 'split_per': a.split_per,
                'data_split_seed': data_split_seed, 'training_seed': a.seed,
                'heldout_probe_size': min(a.heldout_probe_size, len(heldout_dataset)) if heldout_dataset else 0}
    loss_probe = [dataset[index] for index in range(protocol['loss_probe_size'])]
    px = torch.stack([item[0] for item in loss_probe]).to(config.device)
    pdpt = torch.stack([item[1] for item in loss_probe]).to(config.device)
    py = torch.stack([item[3] for item in loss_probe]).to(config.device)
    if heldout_dataset:
        heldout_probe = [heldout_dataset[index] for index in range(protocol['heldout_probe_size'])]
        hpx = torch.stack([item[0] for item in heldout_probe]).to(config.device)
        hpdpt = torch.stack([item[1] for item in heldout_probe]).to(config.device)
        hpy = torch.stack([item[3] for item in heldout_probe]).to(config.device)
    for epoch in range(start_epoch, a.epochs):
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
            signal_sq, noise_sq = 0.0, 0.0
            for total, parameter in zip(accumulated, params):
                noise = torch.randn_like(total) * (a.sigma * a.clip_C)
                signal_sq += float(total.pow(2).sum().item())
                noise_sq += float(noise.pow(2).sum().item())
                parameter.grad = (total + noise) / a.batch_size
            optimizer.step()
        with torch.no_grad():
            route_log_prob, _ = model(px, pdpt)
            labels = py.reshape(-1)
            route_nll_probe = float((-route_log_prob[torch.arange(labels.numel(), device=config.device), labels]).mean().item())
            valid_labels = labels != 0
            valid_route_nll_probe = float((-route_log_prob[
                torch.arange(labels.numel(), device=config.device)[valid_labels], labels[valid_labels]]).mean().item())
            heldout_route_nll_probe = None
            heldout_valid_route_nll_probe = None
            if heldout_dataset:
                heldout_log_prob, _ = model(hpx, hpdpt)
                heldout_labels = hpy.reshape(-1)
                heldout_route_nll_probe = float((-heldout_log_prob[
                    torch.arange(heldout_labels.numel(), device=config.device), heldout_labels]).mean().item())
                heldout_valid = heldout_labels != 0
                heldout_valid_route_nll_probe = float((-heldout_log_prob[
                    torch.arange(heldout_labels.numel(), device=config.device)[heldout_valid],
                    heldout_labels[heldout_valid]]).mean().item())
        record = {'epoch': epoch, 'steps': steps_per_epoch,
                  'mean_loss': float(np.mean(losses)) if losses else None,
                  'mean_unclipped_norm': float(np.mean(norms)), 'clip_fraction': clipped / len(norms),
                  'clipped_sum_l2_before_average': math.sqrt(signal_sq),
                  'gaussian_noise_l2_before_average': math.sqrt(noise_sq),
                  'noise_to_clipped_sum_l2_ratio': math.sqrt(noise_sq / max(signal_sq, 1e-30)),
                  'route_nll_probe': route_nll_probe,
                  'valid_route_nll_probe': valid_route_nll_probe,
                  'heldout_route_nll_probe': heldout_route_nll_probe,
                  'heldout_valid_route_nll_probe': heldout_valid_route_nll_probe}
        history.append(record); print(json.dumps(record), flush=True)
        # Persist only at an update boundary, so an interrupted process can
        # resume without repeating or silently omitting a DP mechanism call.
        boundary = {'state_dict': model.state_dict(), 'optimizer_state_dict': optimizer.state_dict(),
                    'history': history, 'next_epoch': epoch + 1, 'protocol': protocol,
                    'python_random_state': random.getstate(), 'numpy_random_state': np.random.get_state(),
                    'torch_random_state': torch.get_rng_state(),
                    'cuda_random_state': torch.cuda.get_rng_state() if torch.cuda.is_available() else None}
        temporary = checkpoint_path.with_suffix('.tmp')
        torch.save(boundary, temporary); temporary.replace(checkpoint_path)
        progress_path.write_text(json.dumps({'completed_epochs': epoch + 1, 'total_epochs': a.epochs,
                                             'last_record': record, 'protocol': protocol}, indent=2), encoding='utf-8')
        write_loss_curve(history, diagnostic_dir / 'training_loss_curve.png')
    torch.save({'state_dict': model.state_dict(),
                'privacy_unit': 'one raw trajectory before public record-wise map matching',
                'fixed_batch_B': a.batch_size, 'clip_C': a.clip_C, 'sigma': a.sigma,
                'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch}, a.out / 'model.pt')
    manifest = {'implementation': 'MTNet Algorithm 1 fixed-B DP-SGD',
                'sampling': 'uniform fixed-size B each update',
                'privacy_unit': 'one raw trajectory before public record-wise map matching',
                'n_trajectories': n, 'B': a.batch_size, 'C': a.clip_C, 'sigma': a.sigma,
                'data_split_seed': data_split_seed, 'training_seed': a.seed,
                'dp_domain_scope': a.dp_domain_scope,
                'dp_domain_manifest': domain_manifest_path, 'dp_domain': domain,
                'dataset_size_public': a.dataset_size_public,
                'release_condition_policy': a.release_condition_policy,
                'release_boundary': ('Only the trained model is released by this command. Any trajectory release must '
                                     'use public_fixed or separately_dp conditions; raw private conditions are outside this DP ledger.'),
                'epochs': a.epochs, 'steps_per_epoch': steps_per_epoch,
                'gradient_engine': a.gradient_engine, 'microbatch_size': a.microbatch_size,
                'privacy_accountant': accountant,
                'utility_preflight': utility_preflight,
                'utility_evaluation': {'split_per': a.split_per,
                                       'heldout_probe_size': protocol['heldout_probe_size'],
                                       'checkpoint_selection': 'disabled; fixed final epoch only',
                                       'release_status': 'private diagnostic only'},
                'private_training_diagnostics': {
                    'release_status': 'not part of the DP release',
                    'location': str(diagnostic_dir.resolve()),
                    'contains': ['raw training loss summaries', 'clipping summaries', 'resume state'],
                },
                'paper_reported_protocol': {
                    'epsilon': 1.0, 'delta': 1e-5, 'max_epochs': 30,
                    'early_stop': 'route-JSD, patience 5', 'default_L': 20,
                    'lambda': 0.1, 'LSTM_layers': 2, 'feedforward_layers': 1,
                },
                'source_defaults_at_import': source_defaults,
                'source_fingerprint_sha256': source_fingerprint,
                'source_lock': str(a.source_lock.resolve()),
                'compatibility_adapter': 'Current PyTorch requires integer embedding indices. The sequential backend casts only time-slot dtype to long. The vmap backend additionally replaces the identical boolean-index assignment with masked_fill because vmap forbids dynamic-shape boolean indexing.',
                'run_status': 'Algorithm-1 execution under a local, recorded DP-SGD configuration; not an author-hyperparameter numerical reproduction.',
                'numerical_privacy_limit': 'The accountant certifies this implementation and recorded configuration only. The paper does not disclose C, sigma, or cross-step accountant parameters, so this run must not be described as reproducing the paper\'s epsilon=1 configuration or numerical utility.'}
    (a.out / 'paper_algorithm_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
