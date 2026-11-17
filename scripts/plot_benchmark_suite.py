"""Render saved suite contrasts; no fitting or cloud calls."""

import argparse
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(output, destination):
    result = json.loads((output / "summary.json").read_text())["response"]["result"]
    labels = ["Selected fixed", "Ridge sequential", "Tree myopic"]
    keys = ["H1_deployability", "H2_capacity", "H3_credit"]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True, layout="constrained")
    for ax, task, title in zip(
        axes,
        [None, "packing26", "packing32", "autoconvolution64"],
        ["Equal-task mean", "26 circles", "32 circles", "Autoconvolution (64 bins)"],
    ):
        for i, key in enumerate(keys):
            r = result["comparisons"][key]
            if task is None:
                mean, ci = r["equal_task_mean"], r["ci98_333"]
            else:
                mean, ci = (
                    r["tasks"][task]["mean"],
                    r["tasks"][task]["ci95_descriptive"],
                )
            ax.plot([ci[0], ci[1]], [i, i], color="#315f89", lw=2)
            ax.plot(mean, i, "o", color="#182f46", ms=5)
        ax.axvline(0, color="#777777", lw=0.8, ls="--")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Normalized utility difference", fontsize=9)
        ax.grid(axis="x", alpha=0.2)
        ax.ticklabel_format(axis="x", style="sci", scilimits=(-2, 2))
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(2.6, -0.6)
    axes[0].set_yticks(range(3), labels)
    axes[0].set_ylabel("Tree sequential minus comparator")
    fig.suptitle(
        "Matched controller comparisons: 48 fresh paired seeds per task", fontsize=13
    )
    fig.supxlabel(
        "Aggregate: adjusted 98.333% intervals. Individual tasks: descriptive 95% intervals. Positive favors tree sequential.",
        fontsize=9,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--figure",
        type=Path,
        default=Path("papers/metacontrol/benchmark-suite-results.svg"),
    )
    a = p.parse_args()
    plot(a.output, a.figure)
