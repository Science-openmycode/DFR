# External Road-Network Competitors

This directory keeps external competitors separate from the paper's reproduced
statistical baseline family.

## MTNet

`mtnet/` contains the audited fixed-batch Algorithm-1 DP-SGD trainer and the
public-seed generator. The Figure-2-compatible release uses only public OSM
start-edge/time seeds at generation time; it must not reuse private trajectory
origins. Its local Beijing run is a conservative `(epsilon=1, delta=1e-5)`
implementation, not an author-hyperparameter numerical reproduction.

## PUTS

`puts/run_puts_beijing_full_release.py` is a documented Beijing-scale local
adapter. It inherits the existing on-demand shortest-path/BFS adaptation needed
because PUTS's original dense road-transition construction does not fit the full
Beijing graph. The current adapter failed to produce 17,123 drawable records in
one bounded run, so PUTS must not be inserted into the strict Figure-2 panel set
until a single documented release contains exactly that many valid trajectories.

Do not report either external comparator as an author-code-certified or
equal-protocol quantitative leaderboard row without a separate audit.
