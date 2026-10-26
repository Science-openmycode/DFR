from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# The evaluator keeps its descriptive names (for example
# ``grid_density_jsd``), while the frozen appendix uses the shorter names
# ``Grid``/``Trip``/``Len``.  These are representation aliases only: values
# are copied unchanged and their original direction/definition is not
# inverted.  Do not add a mapping unless the two names are the same metric.
METRIC_ALIASES = {
    "Grid": "grid_density_jsd",
    "Trip": "trip_error",
    "Len": "path_length_jsd",
    "DirValid": "directed_road_validity",
}


def retain_numeric_cells(table):
    """A measured zero is a value, never a missing observation."""
    table = table.copy()
    table['value'] = pd.to_numeric(table['value'], errors='coerce')
    table.loc[~table['status'].isin(('VALID', 'ZERO')), 'value'] = float('nan')
    return table


def metric_display_name(name):
    retention_tasks = {'NextCellHit1','NextCellMRR','DestinationHit5','DestinationMRR',
                       'RoadContinuationHit1','RoadContinuationMRR','RouteRetrievalNDCG5'}
    if name in retention_tasks:
        return name + ' [relative retention, clipped]'
    return {'DirValid':'DirValid [road object only in audit-v2]',
            'RC-CPC':'RC-CPC [physical junction]',
            'Len':'Len [JS divergence; lower is better]'}.get(name,name)


def add_metric_aliases(table: pd.DataFrame) -> pd.DataFrame:
    """Expose frozen appendix labels without inventing or transforming data."""
    if "metric" not in table.columns:
        return table
    existing = set(table["metric"].astype(str))
    additions = []
    for canonical, source in METRIC_ALIASES.items():
        if canonical in existing or source not in existing:
            continue
        extra = table[table["metric"].eq(source)].copy()
        extra["metric"] = canonical
        if "column" in extra.columns:
            extra["column"] = canonical
        additions.append(extra)
    return pd.concat([table, *additions], ignore_index=True) if additions else table


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot a configurable M×R metric heatmap.")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--metric", default="ALL", help="one metric, or ALL for the frozen row×metric matrix")
    parser.add_argument("--drop-row", action="append", default=[])
    parser.add_argument("--drop-col", action="append", default=[])
    parser.add_argument("--keep-row", action="append")
    parser.add_argument("--keep-col", action="append")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if not spec.get("rows") or not spec.get("columns"):
        raise SystemExit("full_27x48.json must contain frozen rows and columns; refusing to invent experiment cells")
    table = pd.read_csv(args.results)
    if {"M", "R"}.issubset(table.columns) and "row" not in table.columns:
        native = set(spec.get("native_rows", []))
        table["row"] = table.apply(lambda item: str(item["M"]) if str(item["M"]) in native else f"{item['M']} + {item['R']}", axis=1)
        table["column"] = table["metric"]
    table = add_metric_aliases(table)
    required = {"row", "column", "metric", "value", "status"}
    missing = required.difference(table.columns)
    if missing:
        raise SystemExit(f"result table lacks columns: {sorted(missing)}")
    rows = list(args.keep_row or spec["rows"])
    cols = list(args.keep_col or spec["columns"])
    rows = [x for x in rows if x not in args.drop_row]
    cols = [x for x in cols if x not in args.drop_col]
    if args.metric != "ALL":
        if args.metric not in spec["columns"]:
            raise SystemExit(f"unknown metric {args.metric!r}; choose one of the frozen columns or ALL")
        if args.metric not in cols:
            raise SystemExit(f"metric {args.metric!r} was removed by --drop-col/--keep-col")
        cols = [args.metric]
        table = table[table["metric"].eq(args.metric)].copy()
    else:
        table = table[table["metric"].isin(cols)].copy()
    table = retain_numeric_cells(table)
    frame = table.pivot_table(index="row", columns="column", values="value", aggfunc="first").reindex(index=rows, columns=cols)
    status_frame = table.pivot_table(index="row", columns="column", values="status", aggfunc="first").reindex(index=rows, columns=cols)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(max(10, len(cols) * 0.42), max(5, len(rows) * 0.34)))
    finite = frame.to_numpy(dtype=float)
    finite = finite[~pd.isna(finite)]
    if len(finite) and float(finite.min()) >= 0.0 and float(finite.max()) <= 1.0:
        vmin, vmax = 0.0, 1.0
    elif len(finite):
        vmin, vmax = float(finite.min()), float(finite.max())
        if vmin == vmax:
            vmax = vmin + 1.0
    else:
        vmin, vmax = 0.0, 1.0
    image = ax.imshow(frame.to_numpy(dtype=float), vmin=vmin, vmax=vmax, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(cols)), [metric_display_name(c) for c in cols], rotation=55, ha="right", fontsize=8)
    ax.set_yticks(range(len(rows)), rows, fontsize=8)
    for i in range(len(rows)):
        for j in range(len(cols)):
            value = frame.iloc[i, j]
            status = status_frame.iloc[i, j]
            if pd.isna(value):
                label = str(status) if isinstance(status, str) else "MISSING"
            else:
                label = f"{value:.2f}"
            ax.text(j, i, label, ha="center", va="center", fontsize=7)
    ax.set_title(f"M×R metric matrix — {args.metric}\nRaw values: directions differ; structural retention targets 1")
    fig.colorbar(image, ax=ax, label=args.metric)
    fig.tight_layout()
    fig.savefig(args.out_dir / f"mr_{args.metric}.png", dpi=240)
    fig.savefig(args.out_dir / f"mr_{args.metric}.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
