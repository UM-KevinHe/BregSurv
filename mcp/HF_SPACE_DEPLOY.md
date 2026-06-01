# Deploying the agent on HuggingFace Space (with local Qwen 7B AWQ)

This guide is for the **maintainer-side** workflow of putting the
BregSurv agent on HuggingFace Space with a locally served Qwen 7B AWQ
model. Reviewers and end users do not need to follow this — they just
open the Space URL.

If you want to *run* the agent without deploying it, see:

- `mcp/INSTALL.md` — Claude Desktop extension (no GPU, no Docker)
- `mcp/DEPLOY.md` — Docker self-host on your own GPU machine

---

## Why this exists

The HF Space serves the public, reviewer-facing demo. Earlier (Stage
4c) it called OpenAI gpt-4o-mini as the routing LLM, which conflicted
with the paper's central claim that **Qwen 2.5-7B-AWQ routes correctly
without fine-tuning**. Stage 4f migrates the Space to run vLLM-served
Qwen locally inside the container — same weights, same routing logic,
same benchmark numbers as the Docker self-host.

Cost: ~\$20-50/month on HF L4 24 GB with 15-minute sleep timeout
during the review period. Drops to \$0 the moment you downgrade back
to "CPU basic" after acceptance.

---

## One-time setup (do this in order)

### 1. HF account billing

1. Log in to <https://huggingface.co/settings/billing> on the
   `anon-bregsurv` account (or whichever anonymous account hosts the
   Space).
2. Bind a payment method (credit / debit card). HF stores the billing
   info privately; Space visitors never see it. **Anonymity is
   preserved.**
3. Set a **monthly spending limit** of \$50 (or your preferred ceiling).
   This is the safety net — if anything goes wrong (runaway loop,
   sudden viral traffic), HF cuts the Space off rather than billing
   you indefinitely.

### 2. HF Space Secrets

In `https://huggingface.co/spaces/anon-bregsurv/BregSurv/settings`, go
to **Variables and secrets** and configure:

| Variable / Secret | Value | Notes |
|---|---|---|
| `SURVBREGDIV_MODEL_ENDPOINT` | `http://127.0.0.1:8000/v1` | Points the agent at the in-container vLLM |
| `SURVBREGDIV_MODEL_NAME` | `qwen2.5-7b-awq` | Must match `--served-model-name` in entrypoint |
| `OPENAI_API_KEY` | `EMPTY` (or delete entirely) | vLLM ignores this; OpenAI client rejects truly empty strings |
| `BREGSURV_AUTH_USER` | `reviewer` (your choice) | Login username — write this in the paper submission footnote |
| `BREGSURV_AUTH_PASS` | (pick something memorable, e.g. `bregsurv-2026`) | Login password — same |
| `VLLM_GPU_MEM_UTIL` | `0.5` (optional) | Override if vLLM warns about OOM |

**`BREGSURV_AUTH_USER` and `BREGSURV_AUTH_PASS` MUST be set as
"Secrets" (not "Variables")** so they are not exposed in the build
log or to anyone who can inspect the Space's settings without write
access.

If you leave the auth pair unset, Gradio launches WITHOUT a login
page — the Space becomes fully public. Don't do this for a public
demo unless you have a separate reason.

### 3. Hardware tier

In **Settings → Hardware**, change from the current free CPU tier to:

| Tier | VRAM | Cost | Recommendation |
|---|---|---|---|
| T4 small | 16 GB | ~\$0.40/h | Tight — AWQ INT4 + KV cache barely fits |
| **L4** | **24 GB** | **~\$0.80/h** | **Pick this** |
| A10G small | 24 GB | ~\$1.05/h | No advantage over L4 for this workload |

### 4. Sleep timeout

In **Settings → Sleep time**, set **15 minutes**.

A shorter sleep means the Space pauses faster after a reviewer
closes the tab, lowering wasted compute. The tradeoff is each new
reviewer waits ~90 s for a cold start (container restart + vLLM
kernel JIT). For paper-review traffic patterns, 15 min is the
sweet spot.

---

## Build & deploy

The Space repo and the GitHub repo currently share the same files
(`Dockerfile`, `app.py`, `mcp/`, `bregsurv_agent/`, R package
sources). To push an updated build:

```
# From the project root, push to the HF Space (NOT to GitHub).
# `git push hf-space main` works in principle but HF over HTTPS has
# been flaky for mid-size pushes; use `hf upload` instead:
hf upload spaces/anon-bregsurv/BregSurv \
    Dockerfile mcp/entrypoint.sh app.py requirements.txt \
    --repo-type=space

# For larger changes (Python agent, R package), upload subtrees:
hf upload spaces/anon-bregsurv/BregSurv \
    bregsurv_agent/ \
    --repo-type=space
```

The Space will start building automatically after the upload. First
build takes **~25 minutes** (R compile + Qwen weights download +
vLLM install). Subsequent builds with only `app.py` / `mcp/` changes
take **~30 s** thanks to layer caching.

Watch the build log at
`https://huggingface.co/spaces/anon-bregsurv/BregSurv/logs/build`.

When the build finishes, the Space goes into "Running" state on
your chosen GPU tier and starts being billed.

---

## Verifying the deployment

Open the Space URL. You should see:

1. A **Gradio login page** with the auth message
   "Reviewer access only. Credentials are provided in the paper
   submission..."
2. After entering the credentials, the normal BregSurv agent UI.
3. Submit a query like:
   > "Fit a KL Cox model on /app/data/ExampleData_lowdim.rda at eta = 0, 0.5, 1"

4. In the response, expand the trace.json download. It should
   contain `"model": "qwen2.5-7b-awq"` somewhere — NOT
   `gpt-4o-mini`. This is how you confirm the migration succeeded.

5. Check **Settings → Logs → Container** for vLLM startup:
   ```
   [entrypoint HH:MM:SS] starting vLLM serve  model=/opt/qwen-awq
   [entrypoint HH:MM:SS] vLLM ready after Ns
   [entrypoint HH:MM:SS] launching Gradio app
   ```

If the trace shows `gpt-4o-mini`, the env vars are still set incorrectly
— recheck Secrets in step 2 above.

---

## Cost monitoring during review

Watch your usage at <https://huggingface.co/settings/billing>. The
dashboard updates roughly hourly.

If you see unexpected spikes:

1. Check the Space's **Settings → Logs → Container** for evidence of
   repeated wakes from unknown IPs (rare but possible from search
   crawlers).
2. Tighten the sleep timeout (15 min → 10 min).
3. Rotate `BREGSURV_AUTH_PASS` if you suspect the password leaked.
4. Worst case: temporarily downgrade to CPU basic until you can
   investigate. The Space stays alive; only billing pauses.

---

## After paper acceptance

1. **Settings → Hardware → CPU basic** (free) — billing stops the
   moment you save.
2. The Space stays up at \$0/month, but Qwen no longer runs (CPU can't
   serve the 7B model). The Gradio UI will load but tool calls will
   time out.
3. Either:
   - **Delete the Space** if you no longer need it.
   - **Switch back to gpt-4o-mini** (revert the Secrets) and run on
     CPU basic for free, accepting the original "GPT-4o, not Qwen"
     limitation — but now after acceptance, the paper narrative is
     locked.
   - **Re-publish under your real account** with the same Qwen setup
     on the GPU tier (de-anonymize).
4. Either way, remove `BREGSURV_AUTH_USER` / `BREGSURV_AUTH_PASS` to
   drop the password gate.

---

## Cross-references

- `Dockerfile` — what gets built on HF Space.
- `mcp/entrypoint.sh` — boots vLLM + Gradio inside the container.
- `app.py` — `_resolve_auth()` reads the env vars; full UI assembly.
- `Dockerfile.selfhost` — parallel file for users running on their
  own GPU; same R/BregSurv install pattern but downloads weights at
  runtime instead of baking.
