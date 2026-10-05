"""The discrete-time row of the library (master memory ).

`diskd.py` is the DiSKD estimator as handed over on 2026-09-12 (a logistic-hazard
network distilled from an external Cox teacher; nested CV for the learning rate
and the borrowing weight eta), vendored unchanged. The R members of the row
(`DiscreteKL`, package source under `mcp/r_pkgs/DiscreteKL/`, driven by
`mcp/r_scripts/discretekl_cv.R`) and this Python member are fitted by the
same `run_candidates.R` branch on one shared, event-stratified partition; the
bridge that runs DiSKD from R is `mcp/py_scripts/run_diskd.py`.

Nothing here decides anything: the row is chosen by the analyst's declaration
(the internal outcome is in discrete intervals) and verified by the gate; the
members compete only inside the row by pooled held-out negative log-likelihood
per subject.
"""
