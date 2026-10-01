"""Audit a fixed-size MTNet DP-SGD checkpoint's DP accountant."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def epsilon(sigma: float, steps: int, delta: float, sensitivity_factor: float) -> tuple[float, float]:
    """Return a Gaussian-RDP epsilon upper bound and optimizing order."""
    orders = np.concatenate([np.arange(1.1, 32.0, 0.1), np.arange(32, 513)])
    rdp = steps * sensitivity_factor * orders / (2.0 * sigma * sigma)
    values = rdp + np.log(1.0 / delta) / (orders - 1.0)
    index = int(np.argmin(values))
    return float(values[index]), float(orders[index])


def calibrate(target: float, steps: int, delta: float, sensitivity_factor: float) -> float:
    low, high = 1e-8, 1.0
    while epsilon(high, steps, delta, sensitivity_factor)[0] > target:
        high *= 2.0
    for _ in range(100):
        mid = (low + high) / 2.0
        if epsilon(mid, steps, delta, sensitivity_factor)[0] <= target:
            high = mid
        else:
            low = mid
    return high


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--delta', type=float, default=1e-5)
    parser.add_argument('--target-epsilon', type=float, default=1.0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    sigma = float(manifest['sigma'])
    steps = int(manifest['epochs']) * int(manifest['steps_per_epoch'])
    add_eps, add_order = epsilon(sigma, steps, args.delta, 1.0)
    replace_eps, replace_order = epsilon(sigma, steps, args.delta, 4.0)
    corrected_sigma = calibrate(args.target_epsilon, steps, args.delta, 4.0)
    corrected_eps, corrected_order = epsilon(corrected_sigma, steps, args.delta, 4.0)
    report = {
        'scope': 'fixed-B MTNet DP-SGD accountant audit',
        'checkpoint_manifest': str(args.manifest.resolve()),
        'input': {'sigma': sigma, 'steps': steps, 'delta': args.delta},
        'add_remove_counterfactual': {
            'sensitivity_of_clipped_sum': 'C',
            'epsilon_upper_bound': add_eps,
            'optimizing_rdp_order': add_order,
            'status': 'not the natural relation for B=N without a canonical null slot',
        },
        'replacement_accounting': {
            'adjacency': 'replace one complete trajectory while keeping N fixed',
            'sensitivity_of_clipped_sum': '2C',
            'per_step_rdp': '2 alpha / sigma^2',
            'epsilon_upper_bound': replace_eps,
            'optimizing_rdp_order': replace_order,
            'status': 'applicable to the fixed-cardinality execution path',
        },
        'corrected_epsilon_calibration': {
            'target_epsilon': args.target_epsilon,
            'required_sigma': corrected_sigma,
            'certified_epsilon_upper_bound': corrected_eps,
            'optimizing_rdp_order': corrected_order,
            'required_retraining': True,
        },
        'artifact_policy': {
            'historical_checkpoint_status': 'diagnostic only',
            'forbidden_claim': 'epsilon=1 fixed-B replacement-DP release',
            'rerun_required_for': ['generation', 'visualization', 'utility metrics', 'membership attacks'],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
