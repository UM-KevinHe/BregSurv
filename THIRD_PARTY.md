# Third-party code in this repository

| component | where | authors | licence | used for |
|---|---|---|---|---|
| DiscreteKL | `mcp/r_pkgs/DiscreteKL/` | Di Wang | GPL (>= 2) | the agent's discrete-time members `internal_discrete` and `discretekl` |
| DiSKD | `bregsurv_agent/discrete/diskd.py` | after the reference implementation of Deng et al. (2026) | distributed with the authors' permission | the agent's network members `internal_nn` and `diskd` |

References

- Wang, D., Ye, W., Sung, R., Jiang, H., Taylor, J. M. G., Ly, L. and He, K. (2025). Kullback-Leibler-based
  discrete failure time models for integration of published prediction models with new time-to-event
  dataset. *The Annals of Applied Statistics* 19(2), 1167-1189.
- Deng, F., Luo, L., Wang, D., Li, Q., Kong, L. and He, K. (2026). Discrete Survival Knowledge
  Distillation for Competing Risks Analysis. *Proceedings of the 43rd International Conference on
  Machine Learning*, PMLR 306.

The language models the agent downloads at build time (Qwen3-8B-AWQ, Qwen3-Embedding-0.6B and
Qwen3-Reranker-0.6B) are released by their authors under the Apache License 2.0 and are not
distributed in this repository.
