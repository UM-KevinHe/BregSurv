"""Routing benchmark v2: with system prompt."""
import asyncio, json, time, sys
from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VLLM_URL = "http://localhost:8000/v1"
MCP_SERVER = "/scratch/kevinhe_root/kevinhe1/ybshao/SurvBregDiv-mcp/server.py"

SYSTEM_PROMPT = """You are SurvBregDiv-Agent, a statistical assistant for Cox proportional hazards and nested case-control (NCC) survival analysis with external data integration. You have access to ~33 tools in the SurvBregDiv suite. Your job is to ROUTE the user's natural-language query to the correct tool.

CRITICAL RULES (apply in order):

(1) inspect_data is ONLY for inspecting a data file when the user provides an EXPLICIT FILE PATH (e.g., "/data/cohort.rds"). NEVER call inspect_data when the user describes their data only verbally (e.g., "I have 100 patients"). For verbal descriptions, route directly to a fit/cv tool or start_analysis.

(2) generate_eta is a NICHE HELPER. NEVER call it unless the user explicitly asks "generate an eta sequence" or "make an eta grid". The fit_* and cv_* tools accept eta directly.

(3) start_analysis is the WIZARD. Call it when:
    - The user's query is vague (no study design specified, no external info specified)
    - The user's query is conflicting or off-topic
    - You cannot confidently identify both study design AND external info type
    NEVER respond in plain text for unclear queries — ALWAYS call start_analysis.

(4) For clear queries, route directly using this decision tree:
    Study design: "cohort" / "patients" → cox_* family | "nested case-control"/"NCC"/"cases and controls"/"matched" → ncc_* family
    External info type:
      - User mentions only β / coefficients / point estimates → fit_*kl (KL family)
      - User mentions β + covariance / vcov / Sigma / info matrix → fit_*_MDTL (Mahalanobis)
      - User mentions individual-level external data / full cohort → fit_*_indi
      - No external info → recommend coxph or start_analysis
    Ties (cohort only): "tied events" / "daily/weekly resolution" → _ties variant
    High-dim (p large vs n): "lasso/elastic net/variable selection" → _enet | "ridge" → _ridge
    Tuning: "cross-validate" / "tune eta" / "don't know eta" → cv_* prefix
    Otherwise → fit_* prefix

(5) NCC has no _ties variant (matched sets have one event by design). If user mentions both NCC and ties, IGNORE the ties part and route to fit_ncc*.

(6) cohort terms: "cohort", "patients", "subjects", "follow-up" — default to cohort unless NCC is explicit.

EXAMPLES:
- "100 patients, external beta, KL integration" → fit_coxkl
- "n=100, p=300, ridge regularization, KL" → fit_coxkl_ridge
- "Help me with survival analysis" → start_analysis (vague)
- "What is in /tmp/data.rds?" → inspect_data (explicit path)
- "NCC matched 1:4, external beta, tied events" → fit_ncckl (ignore ties for NCC)
- "Cohort, beta + vcov, lasso, p=400" → fit_cox_MDTL_enet
"""

QUERIES = [
    # === A. Cohort vs NCC family selection ===
    {"id": "A01", "axis": "cohort_no_external",
     "query": "I have 200 cancer patients, follow-up times and death indicators, plus 5 baseline covariates. I want to fit a standard Cox model. No external data available.",
     "expect_family": ["start_analysis", "cox_no_external", "fit_cox_indi"]},
    {"id": "A02", "axis": "ncc_matched_basic",
     "query": "Nested case-control study with 100 cases and 400 matched controls (1:4 matching by age and sex). I have 6 covariates and want to integrate external Cox coefficients via KL divergence.",
     "expect_family": ["fit_ncckl", "start_analysis"]},
    {"id": "A03", "axis": "ncc_with_strata",
     "query": "NCC design with 80 cases, 320 controls, stratum_id column for matching. External regression coefficients available. Want KL integration.",
     "expect_family": ["fit_ncckl", "start_analysis"]},
    {"id": "A04", "axis": "cohort_full_individual",
     "query": "Internal cohort of 150 patients, full individual-level data from external cohort of 5000 patients with same covariates. Want to leverage external data fully.",
     "expect_family": ["fit_cox_indi", "start_analysis"]},
    {"id": "B01", "axis": "kl_external_beta_only",
     "query": "I have 100 internal patients survival data. External study published only their estimated Cox regression coefficients (a vector of beta values). Use KL divergence to integrate.",
     "expect_family": ["fit_coxkl", "start_analysis"]},
    {"id": "B02", "axis": "mdtl_beta_plus_vcov",
     "query": "Internal cohort of 80 patients. External study provides both estimated coefficients AND the covariance matrix (vcov) of those estimates. Want Mahalanobis-distance based integration.",
     "expect_family": ["fit_cox_MDTL", "start_analysis"]},
    {"id": "B03", "axis": "indi_full_external",
     "query": "I have internal cohort of 200 patients and the FULL individual-level external dataset (covariates + outcomes) from another study. Want weighted pseudo-likelihood integration.",
     "expect_family": ["fit_cox_indi", "start_analysis"]},
    {"id": "B04", "axis": "no_external_info",
     "query": "Cox proportional hazards model on my single-cohort survival data. n=300, p=8 covariates. No external information available.",
     "expect_family": ["cox_no_external_recommended", "start_analysis", "fit_cox_indi"]},
    {"id": "B05", "axis": "beta_with_se_only",
     "query": "Internal cohort 120 patients. External study reports point estimates and standard errors for each coefficient (no full vcov). Want to use this for integration.",
     "expect_family": ["fit_cox_MDTL", "fit_coxkl", "start_analysis"]},
    {"id": "C01", "axis": "explicit_ties",
     "query": "150 patients with survival data recorded daily, so many tied event times. External Cox coefficients available. Want KL-divergence integration with proper ties handling.",
     "expect_family": ["fit_coxkl_ties", "start_analysis"]},
    {"id": "C02", "axis": "ties_with_breslow",
     "query": "Internal 200 transplant patients, follow-up resolved to weeks (many ties). External beta from registry. KL integration with Breslow approximation for ties.",
     "expect_family": ["fit_coxkl_ties", "start_analysis"]},
    {"id": "C03", "axis": "implicit_no_ties",
     "query": "100 patients, continuous-time survival data (event times measured in hours, essentially unique), KL borrowing from external beta. Standard Cox.",
     "expect_family": ["fit_coxkl", "start_analysis"]},
    {"id": "D01", "axis": "highdim_enet_kl",
     "query": "Gene expression survival study: p=500 genes, n=80 patients. External Cox model from larger study (n=2000) provides external coefficients. Want KL integration with elastic net variable selection.",
     "expect_family": ["fit_coxkl_enet", "cv_coxkl_enet", "start_analysis"]},
    {"id": "D02", "axis": "highdim_ridge",
     "query": "Internal n=100, p=300 covariates (no strict variable selection needed). External beta available. KL borrowing with ridge regularization for stability.",
     "expect_family": ["fit_coxkl_ridge", "cv_coxkl_ridge", "start_analysis"]},
    {"id": "D03", "axis": "highdim_mdtl_enet",
     "query": "Cohort of n=120 patients with p=400 features. External study provides both coefficients and covariance matrix. Want Mahalanobis integration with lasso-style sparsity.",
     "expect_family": ["fit_cox_MDTL_enet", "cv_cox_MDTL_enet", "start_analysis"]},
    {"id": "D04", "axis": "variable_selection_request",
     "query": "Cohort survival study with 50 patients and 80 candidate predictors. External coefficient vector available. I want to integrate external info AND select variables via lasso.",
     "expect_family": ["fit_coxkl_enet", "cv_coxkl_enet", "start_analysis"]},
    {"id": "D05", "axis": "low_dim_no_reg_needed",
     "query": "Cohort of 500 patients, only 6 well-established covariates. External KL borrowing. No need for variable selection or regularization.",
     "expect_family": ["fit_coxkl", "start_analysis"]},
    {"id": "E01", "axis": "ncc_mdtl",
     "query": "Nested case-control 60 cases : 240 controls. External coefficients AND covariance matrix available. Want Mahalanobis integration.",
     "expect_family": ["fit_ncc_MDTL", "start_analysis"]},
    {"id": "E02", "axis": "ncc_indi",
     "query": "Internal NCC sample (50 cases, 200 controls) plus full individual-level external dataset from a registry. Want individual-level integration.",
     "expect_family": ["fit_ncc_indi", "start_analysis"]},
    {"id": "E03", "axis": "ncc_highdim_enet",
     "query": "NCC genomic study: 40 cases, 160 controls, 800 SNP covariates. External beta from a EUR-ancestry GWAS. Want KL + elastic net.",
     "expect_family": ["fit_ncckl_enet", "cv_ncckl_enet", "start_analysis"]},
    {"id": "E04", "axis": "ncc_no_external",
     "query": "Standalone NCC analysis, 70 cases and 280 controls matched 1:4, 5 covariates. No external info.",
     "expect_family": ["ncc_no_external_recommended", "start_analysis"]},
    {"id": "F01", "axis": "want_cv_tuning",
     "query": "I have internal cohort 80 patients with external Cox coefficients. I do NOT know what eta to use. Please cross-validate over a range of eta and pick the best.",
     "expect_family": ["cv_coxkl", "start_analysis"]},
    {"id": "F02", "axis": "explicit_fit_no_cv",
     "query": "Internal 200 patients, external beta, KL integration with eta=0.5 (I have already decided eta). Just fit, no cross-validation needed.",
     "expect_family": ["fit_coxkl", "start_analysis"]},
    {"id": "F03", "axis": "cv_highdim",
     "query": "Cohort, p=300, n=100, KL with elastic net. I need both eta and lambda tuned via 5-fold cross-validation.",
     "expect_family": ["cv_coxkl_enet", "start_analysis"]},
    {"id": "G01", "axis": "vague_no_specifics",
     "query": "Help me do survival analysis with some external information.",
     "expect_family": ["start_analysis"]},
    {"id": "G02", "axis": "naive_language",
     "query": "I have some patients, some died and some didn't, and I want to use info from another study to make my model better. Some of my patients died on the same day.",
     "expect_family": ["start_analysis", "fit_coxkl_ties", "fit_coxkl"]},
    {"id": "G03", "axis": "conflicting_info",
     "query": "I have a nested case-control study with tied event times. External beta available. Want KL integration.",
     "expect_family": ["fit_ncckl", "start_analysis"]},
    {"id": "G04", "axis": "off_topic_meta_analysis",
     "query": "I want to do a meta-analysis of 5 published Cox regression studies. Each gives hazard ratios and confidence intervals.",
     "expect_family": ["start_analysis", "fit_cox_MDTL"]},
    {"id": "G05", "axis": "ambiguous_design",
     "query": "Survival study with 100 patients, want external info integration.",
     "expect_family": ["start_analysis"]},
    {"id": "G06", "axis": "inspect_first_request",
     "query": "I have a data file at /data/cohort.rds, can you tell me what's in it and recommend an analysis approach?",
     "expect_family": ["inspect_data", "start_analysis"]},
]

async def run_one(session, llm, openai_tools, model, q, max_turns=2):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": q["query"]},
    ]
    trace = {"id": q["id"], "axis": q["axis"], "model": model,
             "first_tool": None, "n_tools_called": 0, "all_tools": [],
             "error": None, "latency_s": None}
    t0 = time.time()
    try:
        resp = await llm.chat.completions.create(
            model=model, messages=messages, tools=openai_tools,
            tool_choice="auto", temperature=0.0, timeout=60,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            trace["n_tools_called"] = len(msg.tool_calls)
            trace["all_tools"] = [tc.function.name for tc in msg.tool_calls]
            trace["first_tool"] = msg.tool_calls[0].function.name
    except Exception as e:
        trace["error"] = str(e)[:300]
    trace["latency_s"] = round(time.time() - t0, 2)
    return trace

async def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-7b-awq"
    output = f"/scratch/kevinhe_root/kevinhe1/ybshao/benchmark_v2_{model.replace('.','_').replace('-','_')}.json"
    params = StdioServerParameters(command="python", args=[MCP_SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            openai_tools = [{"type": "function",
                             "function": {"name": t.name,
                                          "description": t.description or "",
                                          "parameters": t.inputSchema}}
                            for t in tools_result.tools]
            llm = AsyncOpenAI(base_url=VLLM_URL, api_key="dummy")
            results = []
            print(f"=== Running {len(QUERIES)} queries against {model} (with system prompt v2) ===\n")
            for i, q in enumerate(QUERIES, 1):
                trace = await run_one(session, llm, openai_tools, model, q)
                trace["query"] = q["query"]
                trace["expect_family"] = q["expect_family"]
                hit = "✓" if (trace["first_tool"] in q["expect_family"]) else "✗"
                print(f"[{i:2d}/{len(QUERIES)}] {q['id']} ({q['axis'][:30]:30s})  "
                      f"→ {trace['first_tool'] or 'NO_TOOL':28s} {hit}  ({trace['latency_s']}s)")
                results.append(trace)
            with open(output, "w") as f:
                json.dump(results, f, indent=2)
            expect_map = {q["id"]: q["expect_family"] for q in QUERIES}
            n_hit = sum(1 for r in results if r["first_tool"] in expect_map[r["id"]])
            print(f"\n=== Summary (v2 with system prompt) ===")
            print(f"Routing accuracy: {n_hit}/{len(QUERIES)} = {100*n_hit/len(QUERIES):.1f}%")
            print(f"Saved: {output}")

asyncio.run(main())
