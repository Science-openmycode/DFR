"""Render the current MTR-versus-four-statistical-method paper tables.

The renderer deliberately excludes public-routing controls and differently
interfaced road-native diagnostics.  Those belong to ablation/interface audits.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROAD_AGGREGATE = ROOT / "results" / "road_route_metrics" / "current" / "beijing" / "metrics.json"
METHOD_INPUTS = {
    "SPRT-native": ROOT / "results" / "multicity_current" / "beijing" / "sprt_current_eval_v3" / "metrics.json",
    "PrivTrace-native": ROOT / "results" / "multicity_current" / "beijing" / "privtrace_current_eval_v3" / "metrics.json",
    "DPTrajPM-native": ROOT / "results" / "multicity_current" / "beijing" / "dptraj_pm_current_eval_v3" / "metrics.json",
    "DPStd-native": ROOT / "results" / "multicity_current" / "beijing" / "dpstd_current_eval_v3" / "metrics.json",
    "MTR-GSRT": ROOT / "results" / "multicity_current" / "beijing" / "mtr_gsrt_current_eval_v3" / "metrics.json",
}
MAIN_KEYS = ("grid_density_jsd", "trip_error", "path_length_jsd")
TASK_KEYS = (
    "road_route_top1",
    "road_route_top5",
    "road_route_mrr",
    "road_route_best5_edge_f1",
)
ROAD_NAMES = {
    "SPRT-native": "SPRT",
    "PrivTrace-native": "PrivTrace",
    "DPTrajPM-native": "DPTraj-PM",
    "DPStd-native": "DPStd",
    "MTR-GSRT": "MTR-GSRT",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def metric_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    protocol = payload["protocol"]
    if int(protocol["synthetic_count"]) != 17123:
        raise RuntimeError(f"not a count-matched 17,123-record evaluation: {path}")
    return payload["metrics"]


def number(value: float) -> str:
    rendered = f"{float(value):.3f}"
    return rendered[1:] if rendered.startswith("0.") else rendered


def real_calibration() -> dict:
    source = ROOT / "outputs" / "kdd_revised" / "main_statistics_refrozen_v3_20260717" / "main_statistics.csv"
    with source.open(encoding="utf-8", newline="") as handle:
        row = next(row for row in csv.DictReader(handle) if row["method"] == "Real-vs-real calibration")
    return {key: float(row[key]) for key in MAIN_KEYS}


def main_table(methods: dict[str, dict], *, chinese: bool) -> str:
    header = "方法" if chinese else "Method"
    lines = [
        r"\begin{tabular}{lrrrrr}", r"\toprule",
        header + r" & Grid$\downarrow$ & Trip$\downarrow$ & Len$\downarrow$ & WitnessValid$\uparrow$ & $\mathrm{RouteF1}_5\uparrow$\\",
        r"\midrule",
    ]
    best_low = {key: min(methods[name][key] for name in methods) for key in MAIN_KEYS}
    best_nav = max(methods[name]["road_route_best5_edge_f1"] for name in methods)
    for name, values in methods.items():
        cells = []
        for key in MAIN_KEYS:
            value = number(values[key])
            if values[key] == best_low[key]:
                value = rf"\textbf{{{value}}}"
            cells.append(value)
        witness = (
            rf"\textbf{{{number(values['witness_valid'])}}}"
            if name == "MTR-GSRT"
            else "--"
        )
        nav = number(values["road_route_best5_edge_f1"])
        if values["road_route_best5_edge_f1"] == best_nav:
            nav = rf"\textbf{{{nav}}}"
        cells.extend([witness, nav])
        lines.append(name + " & " + " & ".join(cells) + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines) + "\n"


def task_table(methods: dict[str, dict], *, chinese: bool) -> str:
    header = "方法" if chinese else "Method"
    labels = (
        r"Route@1$\uparrow$",
        r"Route@5$\uparrow$",
        r"MRR$\uparrow$",
        r"Best-$\kroute$ edge F1$\uparrow$",
    )
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule", header + " & " + " & ".join(labels) + r"\\", r"\midrule"]
    best = {key: max(values[key] for values in methods.values()) for key in TASK_KEYS}
    for name, values in methods.items():
        cells = []
        for key in TASK_KEYS:
            value = number(values[key])
            if values[key] == best[key]:
                value = rf"\textbf{{{value}}}"
            cells.append(value)
        lines.append(name + " & " + " & ".join(cells) + r"\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines) + "\n"


def main() -> None:
    methods = {name: metric_payload(path) for name, path in METHOD_INPUTS.items()}
    road_payload = json.loads(ROAD_AGGREGATE.read_text(encoding="utf-8"))
    for name, metrics in methods.items():
        metrics.update(road_payload["results"][ROAD_NAMES[name]])
    out = ROOT / "outputs" / "kdd_revised" / "current_statistical_comparison_20260720"
    out.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for language in ("en", "zh"):
        table_dir = out / "tables" / language
        table_dir.mkdir(parents=True, exist_ok=True)
        rendered = {
            "tables_kdd_revised_main_statistics.tex": main_table(methods, chinese=language == "zh"),
            "tables_kdd_revised_task_utility.tex": task_table(methods, chinese=language == "zh"),
        }
        for filename, content in rendered.items():
            path = table_dir / filename
            path.write_text(content, encoding="utf-8")
            outputs[str(path.relative_to(ROOT)).replace("\\", "/")] = sha256(path)
    manifest = {
        "schema_version": 1,
        "classification": "CURRENT_PAPER_STATISTICAL_COMPARISON",
        "methods": list(METHOD_INPUTS),
        "excluded_from_main_comparison": ["public-routing controls", "differently interfaced road-native diagnostics"],
        "inputs": {
            **{str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in METHOD_INPUTS.values()},
            str(ROAD_AGGREGATE.relative_to(ROOT)).replace("\\", "/"): sha256(ROAD_AGGREGATE),
            str(ROAD_AGGREGATE.with_name("manifest.json").relative_to(ROOT)).replace("\\", "/"):
                sha256(ROAD_AGGREGATE.with_name("manifest.json")),
        },
        "renderer": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
        "renderer_sha256": sha256(Path(__file__)),
        "outputs": outputs,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote current statistical tables and {out / 'manifest.json'}")


if __name__ == "__main__":
    main()
