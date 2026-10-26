# Beijing 3,000-Parent Appendix Protocol: MTR, DPMM, and PUTS

## Frozen Parent Corpus

The appendix starts by freezing **one 3,000-trajectory central-Beijing parent
corpus** in `parent_beijing_central_3000.pkl`, using the declared bbox
`[39.96, 40.03] x [116.28, 116.38]`. Its source indices and preprocessing
manifest are stored alongside the file. The parent corpus is the common raw
input for every method; it is never reconstructed from a method output.

## Two Reporting Strata

The mechanisms have different published input interfaces, so one artificial
86-record three-way leaderboard would be misleading. The appendix therefore
uses two explicitly separated strata.

1. **Population-release stratum (N=3,000).** MTR/DP-GSRT is fitted on all
   3,000 parent records and emits 3,000 fixed public slots. Official DPMM is
   independently invoked on all 3,000 raw GPS records. The report preserves
   DPMM's successful-output count rather than silently truncating MTR.
2. **PUTS eligible stratum (m=86).** The upstream PUTS prerequisite is run on
   the same frozen 3,000-record parent. FMM-valid records are counted before
   any cap; the first 86 valid records in source order form the documented
   PUTS input. The upstream PUTS sampler is then run unchanged. The report
   compares PUTS to its *own eligible real records*. An optional DPMM run on
   those 86 raw GPS records is an interface diagnostic only.

MTR is not retrained on the 86 records for the principal comparison. Doing so
would erase the published-interface asymmetry and turn PUTS eligibility into
a hidden training filter for a population synthesizer.

## Rendering and Metrics

The full-parent figure contains `Real N=3,000`, `MTR N=3,000`, and
`DPMM N=successful outputs`, with each count printed in its panel title. The
PUTS figure contains `Real FMM-eligible m=86` and `PUTS m=86`; no plotting
utility may call `min(n)` to manufacture count matching across strata.

Each stratum has its own grid-density JSD, trip/path-length distributions,
road proximity, long-jump rate, and route-compatible yield. Cross-stratum
numbers are descriptive rather than a common-data leaderboard.

## Complexity Boundary

PUTS explicitly materializes `tbR[L+1, R, R]` and repeatedly computes dense
Markov powers. Its memory is `Theta(L R^2)` and its dense recurrence is
`Theta(L R^3)`. On the full Beijing graph (`R=76,366`, `L=50`, float64), the
transition tensor alone has lower bound `8 * 51 * R^2 = 2.38 TB`; a strict
full-city PUTS run is not practically supported by the released dense method.

DPMM has a different bottleneck. For every private input trajectory it runs
two map-matching passes. With `w_i` RDP waypoints and local candidate-node
sets `A_ij`, `B_ij`, its routing work is

```
sum_i sum_j [T_buffer(i,j) + sum_(u,v) in A_ij x B_ij T_G(u,v)].
```

It is finite but can have a substantial road-density and waypoint tail. Its
successful-output count and wall-clock time are therefore recorded rather
than hidden by a count-matched display.
