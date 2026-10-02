# Literature algorithms

The reproduced literature baselines are kept separate from MTR-DFR.

| Method | Authoritative source |
|---|---|
| SPRT | `../../src/reproduced_papers/SPRT/` |
| PrivTrace | `../../src/reproduced_papers/PrivTrace/` |
| DPTraj-PM | `../../src/reproduced_papers/DPTrajPM/` |
| DPStd | `../../src/reproduced_papers/DPStd/` |
| Shared reproduction utilities | `../../src/reproduced_papers/common/` |

Run them through `../../generation/baselines/generate.py`. Official-code
adapters and interface audits for MTNet and PUTS remain under
`../../external_competitors/`; they are not relabeled as native statistical
baseline implementations.

For a single-folder audit, this directory contains read-only organization
snapshots:

- `source_snapshot/`: the four reproduced statistical methods and shared code;
- `entrypoints/`: the unified baseline wrapper;
- `external_adapters_snapshot/`: MTNet/PUTS adapters and interface protocols.

The established paths remain authoritative for execution. The generated
`../ALGORITHM_INDEX.json` verifies that the curated snapshots match them.
