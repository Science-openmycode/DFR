"""Plot the checked-in DFR algorithm-level ablation table."""
from pathlib import Path
import argparse
import matplotlib.pyplot as plt
import pandas as pd


METRICS = ["DemandFid", "BTF", "RC-CPC", "EdgeCPC", "TurnCPC", "FamilyCPC", "EdgeIoU", "TurnIoU", "BranchCPC", "ExitAcc"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("experiment_results/ablation/results.csv"))
    p.add_argument("--output", type=Path, default=Path("experiment_results/ablation/ablation_metrics.png"))
    a = p.parse_args()
    df = pd.read_csv(a.input).set_index("Ablation arm")
    fig, axes = plt.subplots(2, 5, figsize=(15, 6), constrained_layout=True)
    for ax, metric in zip(axes.flat, METRICS):
        ax.bar(df.index, df[metric], color="#2f6b9a")
        ax.set_title(metric)
        ax.set_ylim(0, 1.02)
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("DFR algorithm-level ablation")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()
