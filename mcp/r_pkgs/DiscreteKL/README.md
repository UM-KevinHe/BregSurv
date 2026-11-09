# DiscreteKL

Kullback-Leibler-based discrete failure time models, by Di Wang, distributed here unchanged
under its own licence, GPL (>= 2) (see `DESCRIPTION`). The agent's discrete-time row installs it
to fit the `internal_discrete` and `discretekl` members.

Reference: Wang, D., Ye, W., Sung, R., Jiang, H., Taylor, J. M. G., Ly, L. and He, K. (2025).
Kullback-Leibler-based discrete failure time models for integration of published prediction models
with new time-to-event dataset. *The Annals of Applied Statistics* 19(2), 1167-1189.

The BregSurv R package (version 2.0.0 and later) has its own grouped-time engine,
`cv.bregsurv(target_discrete(...), release_model(...))`, which agrees with this package to about
1e-8 on the coefficients.
