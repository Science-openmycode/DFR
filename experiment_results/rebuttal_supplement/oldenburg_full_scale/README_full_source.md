# Oldenburg full-source MTR-GSRT evaluation

This experiment uses all 500,000 trajectories in `oldenburg.dat` as the source corpus, fixes the public slot count to 500,000 before private access, generates 500,000 synthetic trajectories, and evaluates the synthetic release against all 500,000 source trajectories. It is therefore a full-source replacement experiment, not a train/sample diagnostic.

The release uses normalized coordinates and a normalized public road graph with 6,105 nodes and 7,029 directed ways. The MTR-GSRT transcript uses ε=7/5, δ=0, 384 quotient regions, six portals per fine edge, and fixed research seeds. All 500,000 output slots have a directed road witness; no fallback was emitted.

Full metrics are in `metrics/metrics_full.json` and `metrics/metrics_full.csv`. The main values are: grid occupancy JSD 0.0769, OD JSD 0.4398, length JSD 0.0099, step JSD 0.0785, road_200m 1.000, and mean road distance 0.0206 km.

## Beijing-level metric contract

The same-level evaluator reports GridJSD 0.0673, TripError 0.2364, LengthJSD 0.0079, OD JSD 0.2789, OD NDCG@20 0.7388, Grid-route Top1 0.5310, Grid-route MRR 0.6445, Next-region Accuracy 0.7421, and Next-region NLL 1.2618. The edge-projection route evaluator reports RouteYield 1.000, WitnessValid 1.000, BTF 0.5936, RC-CPC 0.5935, EdgeCPC 0.6015, TurnCPC 0.5457, EdgeCount-IoU 0.4301, TurnCount-IoU 0.3752, EdgeRecall 0.8664, EdgeJaccard 0.8657, OD-PF96 0.3879, and OD-PF384 0.1739.

The edge-projection evaluator is used because Oldenburg trajectory points lie inside road edges; a nearest-node continuity shortcut underestimates RouteYield even for the real identity.
