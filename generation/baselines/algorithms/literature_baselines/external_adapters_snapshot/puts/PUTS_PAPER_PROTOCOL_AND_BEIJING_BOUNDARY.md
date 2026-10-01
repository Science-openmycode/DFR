# PUTS paper-protocol audit and Beijing boundary

## Paper-faithful check

The bundled UCAR experiment is the only supplied original PUTS protocol in
this artifact: 1,000 matched trajectories, six regions, `safeValue=1.5`, and
an epsilon split of `(0.33, 0.34, 0.33)`.  The accompanying audit reports a
real median length of 3475 m and a PUTS median length of 3637 m.  Thus the
unmodified implementation is operational on its original matched-road input.

## Why no Beijing PUTS figure is paper-faithful

The original algorithm explicitly materializes a dense `R x R` Markov matrix
for every step up to the maximum matched-path length, in addition to an
all-pairs shortest-path matrix.  A Beijing full public-OSM matching produces
many more road states than the UCAR protocol.  Reducing the state set to a
top-K subset changes the graph on which PUTS samples source/destination roads
and path lengths; it is a scalability diagnostic, not a reproduction of the
published method.

The public runner therefore rejects reduced supports unless
`--allow-reduced-support` is supplied. Such outputs must never enter paper
tables, figures, or claims as native PUTS results.

## Permitted paper usage

1. Report the UCAR original-protocol audit as a baseline-reproduction sanity
   check.
2. State that native PUTS is excluded from Beijing full-city comparisons for
   computational/protocol mismatch, rather than presenting a degraded top-K
   output.
3. If a Beijing comparison is required, label any sparse/on-demand or
   coarsened-graph implementation as a new scalability variant, not PUTS.
