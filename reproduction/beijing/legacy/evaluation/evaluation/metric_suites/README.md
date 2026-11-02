# Metric suite bindings

The paper uses three evidence layers.

1. Statistical controls: Grid, Trip, and Length.
2. Road objects: WitnessValid plus witness-coordinate distance and ordering.
3. Real mobility characteristics: OD-conditioned road-transition divergence
   and route recommendation on actual directed public-road edge IDs.

`evaluation/evaluate_all.py` evaluates coordinate statistics and shared count/OD
distribution diagnostics. It does not train predictive downstream models.
The four road applications run through `evaluate_applications.py` in README
section 05, directly answering fixed real-data questions from saved road releases.

The corrected road implementation is `metric_suites/road_route.py`:

- `evaluation/evaluate_witness_coordinates.py` validates the complete MTR
  coordinate/witness release without a map matcher;
- `evaluation/prepare_road_evaluation_network.py` builds one directed edge per
  consecutive OSM-node pair, preserving intersections inside an OSM way;
- `evaluation/evaluate_road_route.py` runs STMatch on the same frozen network
  and parameters for all methods, counts failed matches in the invalid outcome,
  and evaluates actual directed-road edge sequences;
- `evaluation/aggregate_road_route_chunks.py` rejects missing or incompatible
  method chunks and writes the complete method-by-metric and ranking ledgers.

The public route workflow uses STMatch and therefore has no UBODT size
dependency.  `RoadRealizable` is outside the current comparison scope.
