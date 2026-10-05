"""BregSurv agent — Cox transfer learning with a language model at two edges.

WHAT THIS PACKAGE IS, after the V2 stack was retired on 2026-08-19.

The model acts in exactly two places and is OPTIONAL in both:

  boundary 1  read which column the analyst named for which role, and ONLY when
              they wrote it in prose. A numbered answer is parsed deterministically
              and the model is never called.
  boundary 2  write the report's connective prose, in named references and not a
              single digit.

Everything else -- which methods are admissible, which one wins, every number in
the report -- is deterministic. The V2 modules that let a model choose an
estimator from 32 tool schemas were removed, because the claim this work rests on
is that it must not.

    from bregsurv_agent import pipeline, boundary
    from bregsurv_agent.declaration import render_question, parse_reply, verify
    from bregsurv_agent.rbridge import run_r
"""
from .declaration import (Declaration, DeclarationError, Verification,
                          from_dictionary, parse_reply, render_question, verify)
from .pipeline import (PipelineRefusal, RunResult, canonical_config,
                       config_hash, derive_candidate_keys, render_repro, run)
from .rbridge import DEFAULT_CV_SEED, R_SCRIPTS, find_rscript, run_r

__all__ = [
    "Declaration", "DeclarationError", "Verification",
    "render_question", "parse_reply", "verify", "from_dictionary",
    "run", "RunResult", "PipelineRefusal", "render_repro",
    "canonical_config", "config_hash", "derive_candidate_keys",
    "run_r", "find_rscript", "R_SCRIPTS", "DEFAULT_CV_SEED",
]
