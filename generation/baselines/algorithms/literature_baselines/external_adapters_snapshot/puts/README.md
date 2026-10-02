# PUTS Appendix Reproduction

This directory keeps the upstream PUTS reproduction separate from the main
population-synthesis benchmark. PUTS begins after an FMM map-matching
prerequisite and materializes a dense road-state transition object; MTR and
DPMM have different input interfaces. The paper appendix therefore uses the
auditable **3,000-parent two-stratum protocol** documented in
[`DPMM_PUTS_MTR_APPENDIX_PROTOCOL.md`](DPMM_PUTS_MTR_APPENDIX_PROTOCOL.md).

Run the complete appendix pipeline from `public_release`:

```powershell
powershell -ExecutionPolicy Bypass -File external_competitors\puts\run_dpmm_puts_mtr_appendix.ps1
```

It creates the following artifacts under
`outputs/external_competitors/puts_dpmm_mtr_parent3000/`. The frozen parent is
the declared central-Beijing bbox `[39.96, 40.03] x [116.28, 116.38]`:

- `parent_beijing_central_3000.pkl`: frozen common 3,000-record parent corpus;
- `parent_beijing_central_3000_source_indices.json`: its deterministic source map;
- `puts_fmm_eligible86/prepare_manifest.json`: FMM-valid count before capping
  and the deterministic 86-record PUTS branch;
- an official DPMM release on the 3,000-record parent, retaining its actual
  successful-output count;
- an unmodified upstream PUTS release on its FMM-eligible branch;
- two separate figures and a two-stratum metrics CSV.

The evaluator and renderer intentionally never use `min(n)` across methods.
MTR is not retrained on the 86 PUTS-eligible trajectories for the principal
comparison.

## Legacy files

`run_puts_same_train_subset.py`,
and the `*_native_graph_*` utilities are retained as historical adapter
diagnostics. They constrain MTR to a PUTS-derived road graph or use an
implementation-specific selected support, so they are not valid sources for
the appendix claims or paper figures.

## Complexity boundary

The released PUTS method explicitly materializes an `(L+1) x R x R` dense
transition tensor and performs dense transition recurrences. Its memory is
`Theta(L R^2)` and its dense recurrence is `Theta(L R^3)`. The full Beijing
road graph has `R=76,366`; at `L=50`, the float64 tensor alone has a lower
bound of 2.38 TB. The executable branch is consequently an eligibility-bound
small-subset diagnostic, not a full-city PUTS release.
