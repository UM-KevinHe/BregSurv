# Paper Figures & Transcripts

This directory holds the reproducibility artefacts referenced from the
"Verification-Backed Agent" section of the paper. Each transcript is a
real end-to-end agent run — a natural-language user query routed by
Qwen 2.5-7B-AWQ through the MCP tool layer, against R running `BregSurv`
in a subprocess — captured verbatim with the trace, the reproducer
script, and the rendered report.

## Layout

```
paper_figures/
├── transcripts/          # natural-query baseline (user describes data in words)
│   ├── 01_lowdim_coxkl/
│   ├── 02_indi_cox_indi/
│   ├── 03_highdim_coxkl_enet/
│   ├── 04_cc_lowdim_ncckl/
│   ├── 05_cc_indi_ncc_indi/
│   ├── 06_cc_highdim_ncckl_enet/
│   └── manifest.json
└── transcripts_explicit/ # explicit-paths baseline (user gives R *_expr strings)
    └── (same 6 subdirs + manifest.json)
```

Each per-dataset subdirectory contains:

| File | Contents |
|---|---|
| `transcript.txt` | Verbatim user query + agent's plain-text reply |
| `trace.json` | Per-tool-call log: name, args, status, R-side output |
| `repro.R` | Standalone R script that reproduces the final result bit-for-bit, no LLM in the loop |
| `report.md` | Rendered Markdown report (the artefact a paper reviewer sees) |

## Coverage matrix

Six transcripts cover the full Cox / NCC × KL / individual-external ×
base / enet decision space (cells where the package defines a method):

| # | Dataset | Expected tool | Family axes exercised |
|---|---|---|---|
| 01 | `ExampleData_lowdim` | `fit_coxkl` | Cox + KL + base + low-dim |
| 02 | `ExampleData_indi` | `fit_cox_indi` | Cox + individual-level external + base |
| 03 | `ExampleData_highdim` | `fit_coxkl_enet` | Cox + KL + enet + p = 50 |
| 04 | `ExampleData_cc_lowdim` | `fit_ncckl` | NCC + KL + base |
| 05 | `ExampleData_cc_indi` | `fit_ncc_indi` | NCC + individual-level external + base |
| 06 | `ExampleData_cc_highdim` | `fit_ncckl_enet` | NCC + KL + enet + p = 20 |

## Why two corpora — the paper narrative

Both corpora use the same six datasets, expected tools, and Qwen
2.5-7B-AWQ + system prompt v2. The only axis that changes is whether
the user's query contains literal R `*_expr` strings or describes the
data in words.

The two-axis result, from `manifest.json`:

| Query style | Routed correctly | One-shot success | Eventual success | Mean wall-clock |
|---|---|---|---|---|
| Natural | 6 / 6 | 2 / 6 | 4 / 6 | ~35 s |
| Explicit | **6 / 6** | **6 / 6** | 6 / 6 | ~15 s |

**Routing is solved at 7B without fine-tuning** (100% on both axes).
The remaining gap is R-syntax construction on `*_expr` arguments — at
7B, Qwen produces three persistent failure modes on natural queries
(template-bracket wrapping like `'<ExampleData_lowdim$train$z>'`,
dropping a nested level, dropping the dataset prefix). With explicit
paths supplied, all three vanish.

When the natural-query run does fail on the first attempt, the trace
shows self-recovery — `inspect_data` → updated `*_expr` → success in
1-5 turns. **`trace.json` IS the verification artefact**: it shows
exactly which estimator library entries the agent picked and which
arguments it constructed, and `repro.R` proves the result is
deterministic and replicable without an LLM.

## Mapping to paper sections

- **Section 4 (Verification-Backed Agent)** — cites `trace.json` and
  `repro.R` as concrete examples of the audit-trail + reproducibility
  pillars.
- **Section 5.3 (End-to-end demo)** — Figure 2 inlines
  `01_lowdim_coxkl/transcript.txt` and the corresponding coefficient
  matrix.
- **Supplement** — full set of 6 transcripts (natural + explicit) so
  reviewers can replay every routing decision the paper claims.

## Regenerating

To recreate these artefacts from scratch (e.g. after a `bregsurv_agent`
update), use `generate_transcripts.py` at the repo root. See its
`--help` and the relevant section in `CLAUDE.md` ("Stage 4a transcript
results") for the invocation and the canonical system prompt path.

## Provenance

Both corpora were generated 2026-05-27 on Great Lakes (`spgpu` A40 node
gl1511) against the BregSurv `main` branch immediately after the rename
from `SurvBregDiv`. Model: `Qwen/Qwen2.5-7B-Instruct-AWQ`, vLLM 0.6.x,
system prompt v2 (`prompt_v2.txt`, 2632 chars, SHA prefix `d93e601d`).
