#!/usr/bin/env Rscript
# start_analysis.R - dispatcher for the start_analysis MCP wizard tool.
#
# Pure R decision logic — no BregSurv calls. Stateless state machine:
# the AI calls this with whatever it has accumulated; the wizard either
# returns the next-question payload (so AI can ask the user) or a final
# recommendation (so AI can proceed to inspect_data + the actual fit/cv tool).
#
# Wizard parameters (all optional so the wizard supports skip-ahead):
#   study_design   : "cohort" | "ncc"
#   has_ties       : TRUE | FALSE  (only relevant for cohort)
#   external_info  : "beta_only" | "beta_and_vcov" | "individual_data" | "none"
#   regularization : "none" | "enet" | "ridge"
#   output_type    : "fit" | "cv"
#   user_language  : "en" | "zh"  (default "en"; AI passes "zh" for Chinese
#                    conversations so wizard returns Chinese strings)
#
# Final recommendation INTENTIONALLY exposes recommended_mcp_tool only as
# data for the AI; never tell the end-user the literal MCP tool name.

suppressPackageStartupMessages({
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript start_analysis.R <input.json> <output.json>")
input_path  <- args[1]
output_path <- args[2]

# --------------------------------------------------------------------------
# i18n strings (English / Chinese). Single source of truth for user-facing
# wording. AI relays these as-is to the user; do NOT let AI editorialize on
# top of these (keeps voice consistent).
# --------------------------------------------------------------------------

LOC <- list(
  # Q1 — study design
  q1 = list(
    en = "What kind of study data do you have?",
    zh = "你的数据是什么形态？"
  ),
  q1_cohort = list(
    en = "Standard cohort: each row is one patient, with a follow-up time and an event/censoring indicator",
    zh = "标准 cohort：一行一个病人，有'随访时间'和'是否发生事件'两列"
  ),
  q1_ncc = list(
    en = "Matched case-control: data is organized in matched sets (each set has one case and a few controls)",
    zh = "配对 case-control：数据按组组织，每组里有 1 个发病的 + 几个对照"
  ),

  # Q2 — ties (cohort only)
  q2 = list(
    en = "Do many of your event times repeat (i.e. multiple events at the same time)?",
    zh = "你的事件发生时间是否高度重复？（不少于 10% 的事件和别的事件在同一时间发生）"
  ),
  q2_yes = list(
    en = "Yes, more than ~10% of events share a time with another event",
    zh = "是，相同时间发生的事件超过 10%"
  ),
  q2_no = list(
    en = "No, or only a handful of ties",
    zh = "几乎没有"
  ),

  # Q3 — external info
  q3 = list(
    en = "What kind of external information do you have to borrow from?",
    zh = "你手上有什么样的外部信息可以借用？"
  ),
  q3_beta_only = list(
    en = "Just regression coefficients from a published study (a vector of beta values)",
    zh = "只有别人发表的回归系数（一组 beta 值）"
  ),
  q3_beta_and_vcov = list(
    en = "Coefficients PLUS their covariance / precision matrix from the published study",
    zh = "系数 + 系数的协方差/精度矩阵"
  ),
  q3_individual = list(
    en = "Full individual-level data from an external cohort (subject-level variables and outcomes)",
    zh = "完整的外部 cohort 原始数据（病人级别的变量和 outcome）"
  ),
  q3_none = list(
    en = "I have no external information",
    zh = "什么都没有"
  ),

  # Q4 — regularization (analyst preference, not data-driven)
  q4 = list(
    en = "How would you like the model to handle the variables?",
    zh = "你希望模型怎么处理这些变量？"
  ),
  q4_none = list(
    en = "Standard fit — no extra penalty, just estimate each variable's effect",
    zh = "标准拟合——不加任何额外正则，直接估每个变量的效应"
  ),
  q4_enet = list(
    en = "Variable selection (lasso / elastic net) — let the model push some coefficients exactly to zero",
    zh = "变量筛选（lasso / 弹性网）——让模型把某些不重要的变量的系数压到 0"
  ),
  q4_ridge = list(
    en = "Ridge shrinkage — keep all variables but pull each coefficient toward zero (no exact zeros)",
    zh = "Ridge 收缩——保留所有变量但每个系数都向 0 收缩（系数不会变成 0）"
  ),

  # Q5 — output
  q5 = list(
    en = "What do you want as the output?",
    zh = "你想要的输出是什么？"
  ),
  q5_fit = list(
    en = "A point estimate at one specific borrowing strength (eta) — for example, eta=0.5",
    zh = "在指定的某一个 borrowing 强度（eta）下做一次拟合，得到点估计"
  ),
  q5_cv = list(
    en = "Use cross-validation to automatically pick the best borrowing strength (eta)",
    zh = "用交叉验证自动挑选最优的 borrowing 强度（eta）"
  ),

  # Fallbacks
  fallback_ncc_ridge = list(
    en = "Ridge shrinkage is not implemented for matched case-control data in this package — only standard fit and variable selection are available. Please pick one of those instead.",
    zh = "配对 case-control 数据的 ridge 收缩在这个 package 里没实现——只有'标准拟合'和'变量筛选'两种选项。请改选这两个之一。"
  ),
  fallback_indi_ridge = list(
    en = "Ridge shrinkage is not available when borrowing from a full external cohort (individual-level data) — only standard fit and variable selection are. Please pick one of those instead.",
    zh = "用整套外部 cohort 数据借用时，ridge 收缩不可用——只有'标准拟合'和'变量筛选'两种选项。请改选这两个之一。"
  ),
  fallback_ties_regularized = list(
    en = "Heavy event-time ties require a special tie-aware fit, which is only available in the standard (non-regularized) form. The variable-selection and ridge variants do not support ties. Please pick standard fit, or revisit whether your ties are really that heavy.",
    zh = "事件时间高度重复需要一个特殊的 tie-aware 拟合方法，目前只有'标准拟合'版本支持，变量筛选和 ridge 版本都不支持。请改选'标准拟合'，或重新评估一下时间重复是不是真的那么严重。"
  ),
  fallback_no_external = list(
    en = "This package is specifically for borrowing external information into your survival/case-control model. If you genuinely have no external information, you don't need this package — use the standard `survival` package directly: `survival::coxph()` for cohort data, `survival::clogit()` for matched case-control. Come back when you have an external study to borrow from.",
    zh = "这个 package 的核心功能是把外部信息借用进你的生存/case-control 模型。如果你真的没有任何外部信息，就不需要这个 package——直接用标准的 `survival` 包就好：cohort 数据用 `survival::coxph()`，配对 case-control 用 `survival::clogit()`。等你有外部研究信息可以借用时再回来。"
  ),

  # Final recommendation strings
  done_intro = list(
    en = "Based on what you told me, here's the model that fits your situation:",
    zh = "根据你提供的信息，最适合你这个场景的模型是："
  ),
  done_next_step_user = list(
    en = "To proceed, I'll need to look at your data file to figure out which columns hold the variables, the time / outcome, and the matched-set ID (if applicable). Could you share the path to your data file?",
    zh = "接下来我需要看一下你的数据文件，确定哪些列是变量、哪些是时间/事件、哪些是配对组 ID（如果适用）。能告诉我数据文件的路径吗？"
  )
)

l <- function(key, lang) {
  if (is.null(LOC[[key]])) stop(sprintf("Missing i18n key: %s", key))
  txt <- LOC[[key]][[lang]]
  if (is.null(txt)) txt <- LOC[[key]][["en"]]   # fallback to English
  txt
}

# --------------------------------------------------------------------------
# Tool-name lookup table (internal — never shown to user).
# Keys: study_design + has_ties + external_info + regularization + output_type.
# --------------------------------------------------------------------------

resolve_tool <- function(state) {
  sd  <- state$study_design
  ti  <- isTRUE(state$has_ties)
  ei  <- state$external_info
  rg  <- state$regularization
  ot  <- state$output_type

  # Cohort with heavy ties → only base ties-aware tool
  if (sd == "cohort" && ti) {
    if (rg != "none") return(NULL)   # caller should have routed to fallback_ties_regularized
    if (ei == "beta_only") return(if (ot == "cv") "cv_coxkl_ties" else "fit_coxkl_ties")
    return(NULL)   # ties + non-KL external info: no tool covers this; let caller handle
  }

  # Cohort no ties
  if (sd == "cohort") {
    fam_prefix <- switch(ei,
      "beta_only"       = "coxkl",
      "beta_and_vcov"   = "cox_MDTL",
      "individual_data" = "cox_indi"
    )
    if (is.null(fam_prefix)) return(NULL)

    suffix <- switch(rg,
      "none"  = "",
      "enet"  = "_enet",
      "ridge" = "_ridge"
    )
    # cox_indi has no ridge variant
    if (fam_prefix == "cox_indi" && rg == "ridge") return(NULL)

    return(sprintf("%s_%s%s", if (ot == "cv") "cv" else "fit", fam_prefix, suffix))
  }

  # NCC
  if (sd == "ncc") {
    fam_prefix <- switch(ei,
      "beta_only"       = "ncckl",
      "beta_and_vcov"   = "ncc_MDTL",
      "individual_data" = "ncc_indi"
    )
    if (is.null(fam_prefix)) return(NULL)

    # NCC has no ridge by design
    if (rg == "ridge") return(NULL)

    suffix <- if (rg == "enet") "_enet" else ""
    return(sprintf("%s_%s%s", if (ot == "cv") "cv" else "fit", fam_prefix, suffix))
  }

  NULL
}

# Human-readable model description (user-facing). Built from state, never
# uses the literal MCP tool name.
human_readable <- function(state, lang) {
  parts <- character(0)

  parts <- c(parts, switch(state$study_design,
    "cohort" = if (lang == "zh") "Cox 比例风险模型" else "Cox proportional-hazards model",
    "ncc"    = if (lang == "zh") "条件 logistic 回归（配对 case-control）" else "conditional logistic regression for matched case-control"
  ))

  if (state$study_design == "cohort" && isTRUE(state$has_ties)) {
    parts <- c(parts, if (lang == "zh") "（带 tie 处理）" else "(with tie handling)")
  }

  parts <- c(parts, switch(state$regularization,
    "none"  = "",
    "enet"  = if (lang == "zh") "+ 弹性网变量筛选" else "+ elastic-net variable selection",
    "ridge" = if (lang == "zh") "+ ridge 系数收缩" else "+ ridge coefficient shrinkage"
  ))

  parts <- c(parts, switch(state$external_info,
    "beta_only"       = if (lang == "zh") "+ 通过 KL 散度集成你提供的外部 β 系数" else "+ KL-divergence integration of your external β coefficients",
    "beta_and_vcov"   = if (lang == "zh") "+ 通过 Mahalanobis 距离集成外部 β 和它的协方差矩阵" else "+ Mahalanobis-distance integration of external β plus its covariance matrix",
    "individual_data" = if (lang == "zh") "+ 通过双 cohort 加权似然集成外部研究的原始数据" else "+ dual-cohort composite-likelihood integration of the full external dataset"
  ))

  if (state$output_type == "cv") {
    parts <- c(parts, if (lang == "zh") "，并通过交叉验证自动挑选最优借用强度 (eta)" else ", with cross-validation to automatically pick the optimal borrowing strength (eta)")
  } else {
    parts <- c(parts, if (lang == "zh") "，在你指定的一个 eta 上拟合" else ", at a single user-specified eta")
  }

  paste(Filter(nzchar, parts), collapse = " ")
}

# Required args based on the resolved tool name. Used so AI knows what to
# ask the user / read from inspect_data after the recommendation.
required_args_for <- function(tool_name) {
  if (is.null(tool_name)) return(NULL)

  base <- c("data_path")

  # study_design layer
  if (grepl("indi", tool_name)) {
    base <- c(base,
              "z_int_expr", "z_ext_expr",
              if (grepl("ncc", tool_name)) c("y_int_expr", "y_ext_expr") else c("time_int_expr", "delta_int_expr", "time_ext_expr", "delta_ext_expr"),
              if (grepl("ncc", tool_name)) c("stratum_int_expr", "stratum_ext_expr") else NULL)
  } else if (grepl("ncc", tool_name)) {
    base <- c(base, "z_expr", "y_expr", "stratum_expr")
  } else {
    base <- c(base, "z_expr", "time_expr", "delta_expr")
  }

  # external info (no extra arg for indi — external info IS the second cohort)
  if (!grepl("indi", tool_name)) {
    if (grepl("MDTL", tool_name)) {
      base <- c(base, "beta_expr_or_inline", "(optional) vcov_expr_or_inline")
    } else {
      # KL family — accepts beta or RS
      base <- c(base, "beta_expr_or_inline_or_RS_expr_or_RS_inline")
    }
  }

  # eta vs etas
  is_cv <- startsWith(tool_name, "cv_")
  is_indi_enet <- grepl("indi_enet", tool_name)
  if (is_cv || is_indi_enet) {
    base <- c(base, "etas (numeric array)")
  } else if (grepl("_enet$|_ridge$", tool_name)) {
    base <- c(base, "eta (single scalar; defaults to 0 with notice)")
  } else {
    base <- c(base, "etas (numeric array)")
  }

  base
}

# --------------------------------------------------------------------------
# State machine — wrapped in a function so `return()` works correctly.
# (At top-level of an Rscript, `return()` has no enclosing function to
# return from, so early returns inside tryCatch's `{}` block silently
# fail — we hit this on first run.)
# --------------------------------------------------------------------------

build_response <- function(input) {
  state <- list(
    study_design   = if (is.null(input$study_design)   || identical(input$study_design,   "")) NULL else as.character(input$study_design),
    has_ties       = if (is.null(input$has_ties))       NULL else as.logical(input$has_ties),
    external_info  = if (is.null(input$external_info)  || identical(input$external_info,  "")) NULL else as.character(input$external_info),
    regularization = if (is.null(input$regularization) || identical(input$regularization, "")) NULL else as.character(input$regularization),
    output_type    = if (is.null(input$output_type)    || identical(input$output_type,    "")) NULL else as.character(input$output_type)
  )
  lang <- if (is.null(input$user_language) || identical(input$user_language, "")) "en" else as.character(input$user_language)
  if (!(lang %in% c("en", "zh"))) lang <- "en"

  # Validate enum values eagerly so AI gets clear feedback on bad input
  if (!is.null(state$study_design) && !(state$study_design %in% c("cohort", "ncc"))) {
    stop(sprintf("study_design must be 'cohort' or 'ncc' (got '%s')", state$study_design))
  }
  if (!is.null(state$external_info) && !(state$external_info %in% c("beta_only", "beta_and_vcov", "individual_data", "none"))) {
    stop(sprintf("external_info must be one of beta_only/beta_and_vcov/individual_data/none (got '%s')", state$external_info))
  }
  if (!is.null(state$regularization) && !(state$regularization %in% c("none", "enet", "ridge"))) {
    stop(sprintf("regularization must be one of none/enet/ridge (got '%s')", state$regularization))
  }
  if (!is.null(state$output_type) && !(state$output_type %in% c("fit", "cv"))) {
    stop(sprintf("output_type must be 'fit' or 'cv' (got '%s')", state$output_type))
  }

  # === Q1: study_design ===
  if (is.null(state$study_design)) {
    return(list(
      status         = "ok",
      step           = "Q1_study_design",
      progress       = "1 of up to 5",
      question       = l("q1", lang),
      options        = list(
        list(key = "cohort", label = l("q1_cohort", lang)),
        list(key = "ncc",    label = l("q1_ncc",    lang))
      ),
      next_param     = "study_design",
      ai_instruction = "Relay the question + options to the user as numbered choices. After they pick, call start_analysis again with the user's choice in `study_design` AND all previously collected answers."
    ))
  }

  # === Q2: has_ties (cohort only) ===
  if (state$study_design == "cohort" && is.null(state$has_ties)) {
    return(list(
      status         = "ok",
      step           = "Q2_has_ties",
      progress       = "2 of up to 5",
      question       = l("q2", lang),
      options        = list(
        list(key = "true",  label = l("q2_yes", lang)),
        list(key = "false", label = l("q2_no",  lang))
      ),
      next_param     = "has_ties",
      ai_instruction = "Relay the question. Pass back as `has_ties=true` or `has_ties=false`."
    ))
  }
  # NCC implicitly has no ties (each matched set has exactly one case by construction)
  if (state$study_design == "ncc" && is.null(state$has_ties)) state$has_ties <- FALSE

  # === Q3: external_info ===
  if (is.null(state$external_info)) {
    return(list(
      status         = "ok",
      step           = "Q3_external_info",
      progress       = "3 of up to 5",
      question       = l("q3", lang),
      options        = list(
        list(key = "beta_only",       label = l("q3_beta_only",       lang)),
        list(key = "beta_and_vcov",   label = l("q3_beta_and_vcov",   lang)),
        list(key = "individual_data", label = l("q3_individual",      lang)),
        list(key = "none",            label = l("q3_none",            lang))
      ),
      next_param     = "external_info",
      ai_instruction = "Relay the four options. The user's mental model probably doesn't include 'beta + vcov' as a standard concept — explain in plain language if asked."
    ))
  }

  # Hard-stop: no external info -> recommend standard survival package
  if (state$external_info == "none") {
    return(list(
      status               = "ok",
      step                 = "DONE_no_external_info",
      recommendation_type  = "out_of_scope",
      user_facing_message  = l("fallback_no_external", lang),
      ai_instruction       = "Relay the user_facing_message as-is. Do NOT recommend any MCP tool from this server — they don't need this package. Suggest survival::coxph() (for cohort) or survival::clogit() (for matched case-control) directly."
    ))
  }

  # === Q4: regularization ===
  if (is.null(state$regularization)) {
    return(list(
      status         = "ok",
      step           = "Q4_regularization",
      progress       = "4 of up to 5",
      question       = l("q4", lang),
      options        = list(
        list(key = "none",  label = l("q4_none",  lang)),
        list(key = "enet",  label = l("q4_enet",  lang)),
        list(key = "ridge", label = l("q4_ridge", lang))
      ),
      next_param     = "regularization",
      ai_instruction = "Frame this as the user's analytical preference, NOT as a data-shape question. Don't ask 'is your data high-dimensional' — ask what they want the model to do."
    ))
  }

  # Fallback: ridge unavailable for NCC family
  if (state$study_design == "ncc" && state$regularization == "ridge") {
    return(list(
      status               = "ok",
      step                 = "Q4_NCC_ridge_unavailable",
      recommendation_type  = "fallback_required",
      user_facing_message  = l("fallback_ncc_ridge", lang),
      next_param           = "regularization",
      options              = list(
        list(key = "none", label = l("q4_none", lang)),
        list(key = "enet", label = l("q4_enet", lang))
      ),
      ai_instruction       = "Inform the user ridge isn't supported for their data type, then ask them to pick between standard fit and variable selection. Re-call start_analysis with the new regularization choice."
    ))
  }

  # Fallback: ridge unavailable for indi (Cox indi has no ridge variant)
  if (state$external_info == "individual_data" && state$regularization == "ridge") {
    return(list(
      status               = "ok",
      step                 = "Q4_indi_ridge_unavailable",
      recommendation_type  = "fallback_required",
      user_facing_message  = l("fallback_indi_ridge", lang),
      next_param           = "regularization",
      options              = list(
        list(key = "none", label = l("q4_none", lang)),
        list(key = "enet", label = l("q4_enet", lang))
      ),
      ai_instruction       = "Inform the user ridge isn't available with full external cohort data, then re-ask the regularization question."
    ))
  }

  # Fallback: ties + regularization is unsupported (no _enet/_ridge for ties)
  if (isTRUE(state$has_ties) && state$regularization != "none") {
    return(list(
      status               = "ok",
      step                 = "Q4_ties_regularized_unavailable",
      recommendation_type  = "fallback_required",
      user_facing_message  = l("fallback_ties_regularized", lang),
      next_param           = "regularization",
      options              = list(
        list(key = "none", label = l("q4_none", lang))
      ),
      ai_instruction       = "Tell the user the combination of heavy ties + regularization is not implemented; offer standard fit only."
    ))
  }

  # === Q5: output_type ===
  if (is.null(state$output_type)) {
    return(list(
      status         = "ok",
      step           = "Q5_output_type",
      progress       = "5 of up to 5",
      question       = l("q5", lang),
      options        = list(
        list(key = "fit", label = l("q5_fit", lang)),
        list(key = "cv",  label = l("q5_cv",  lang))
      ),
      next_param     = "output_type",
      ai_instruction = "Last question. After this, the wizard returns the final recommendation."
    ))
  }

  # === All info collected — build final recommendation ===
  tool_name <- resolve_tool(state)
  if (is.null(tool_name)) {
    stop(sprintf(
      "Could not resolve a tool for state: study_design=%s has_ties=%s external_info=%s regularization=%s output_type=%s",
      state$study_design, state$has_ties, state$external_info, state$regularization, state$output_type
    ))
  }

  human_desc <- human_readable(state, lang)
  req_args   <- required_args_for(tool_name)

  list(
    status                = "ok",
    step                  = "DONE",
    recommendation_type   = "tool_recommended",
    # Internal-only — AI uses but does NOT show to user
    recommended_mcp_tool  = tool_name,
    required_args         = req_args,
    # User-facing
    user_facing_intro     = l("done_intro", lang),
    user_facing_model     = human_desc,
    user_facing_next_step = l("done_next_step_user", lang),
    # AI-only behavioral hints (data, not commands)
    ai_instruction = paste(
      "1. Relay user_facing_intro + user_facing_model + user_facing_next_step to the user.",
      "2. NEVER show the literal recommended_mcp_tool string to the user — it's an internal handle.",
      "3. When the user provides a data file path, silently call inspect_data on it (do not announce the tool name) and use the returned structure to propose the column expressions in required_args.",
      "4. Once you have all required_args resolved, call recommended_mcp_tool to actually run the analysis.",
      "5. If the user asks 'what function are you running' or similar, describe it as the model from user_facing_model — not the literal MCP tool name.",
      sep = " "
    ),
    state_collected = state
  )
}

result <- tryCatch(
  build_response(fromJSON(input_path, simplifyVector = TRUE)),
  error = function(err) {
    list(
      status  = "error",
      message = conditionMessage(err),
      class   = class(err)[1],
      where   = "start_analysis.R"
    )
  }
)

writeLines(
  toJSON(result, auto_unbox = TRUE, na = "null", null = "null", pretty = TRUE),
  con = output_path
)
