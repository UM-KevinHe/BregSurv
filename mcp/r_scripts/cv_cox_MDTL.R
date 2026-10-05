#!/usr/bin/env Rscript
# cv_cox_MDTL.R - dispatcher for the cv_cox_MDTL MCP tool.
#
# Cross-validates BregSurv::cox_MDTL over a candidate `etas` grid.
# Mirrors fit_cox_MDTL's parameter style: external `beta` is required,
# optional precision matrix `Q` either as expression or inline list-of-rows.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript cv_cox_MDTL.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
}

extract_metric <- function(internal_stat) {
  cn <- setdiff(colnames(internal_stat), "eta")
  if (length(cn) != 1L) {
    stop(sprintf("Unexpected internal_stat columns: %s",
                 paste(colnames(internal_stat), collapse = ", ")))
  }
  list(name = cn, values = as.numeric(internal_stat[[cn]]))
}

# --- External-coefficient linkage (requirement R2) ---------------------------
# The external coefficient vector is matched to the internal covariates BY NAME.
# `as.numeric` used to strip those names here, which disabled the package's
# aligner and silently reintroduced POSITIONAL borrowing whenever the two
# lengths happened to agree. Keep the names.
as_named_numeric <- function(x) {
  if (is.null(x)) return(NULL)
  nm <- names(x)
  if (is.null(nm) && is.matrix(x) && ncol(x) == 1L) nm <- rownames(x)
  v <- as.numeric(unlist(x, use.names = FALSE))
  if (!is.null(nm) && length(nm) == length(v)) names(v) <- nm
  v
}

# BregSurv zero-pads internal covariates the external model does not cover, but
# HARD-ERRORS on external names with no internal counterpart. R2 calls for those
# to be dropped, so drop them here and report exactly what was dropped.
link_external <- function(z, beta, Q = NULL) {
  zn <- colnames(z)
  bn <- names(beta)
  if (is.null(beta) || is.null(bn) || is.null(zn)) {
    return(list(beta = beta, Q = Q, linkage = list(
      matched_by = "position", n_internal = ncol(z),
      n_external = length(beta),
      covered = list(), zero_padded = list(), dropped = list())))
  }
  keep    <- bn %in% zn
  dropped <- bn[!keep]
  beta    <- beta[keep]
  if (!is.null(Q) && !is.null(rownames(Q))) {
    qk <- rownames(Q) %in% zn
    Q  <- Q[qk, qk, drop = FALSE]
  }
  list(beta = beta, Q = Q, linkage = list(
    matched_by  = "name",
    n_internal  = ncol(z),
    n_external  = length(bn),
    covered     = as.list(intersect(zn, bn)),
    zero_padded = as.list(setdiff(zn, bn)),
    dropped     = as.list(dropped)))
}

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)

  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))

  ext <- tolower(tools::file_ext(data_path))
  e <- new.env()
  if (ext %in% c("rda", "rdata")) {
    load(data_path, envir = e)
  } else if (ext == "rds") {
    obj_name <- tools::file_path_sans_ext(basename(data_path))
    assign(obj_name, readRDS(data_path), envir = e)
  } else {
    stop(sprintf("Unsupported file extension: .%s", ext))
  }

  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required")
  z <- as.matrix(z)
  storage.mode(z) <- "double"

  time  <- as.numeric(eval_in(input$time_expr, e))
  delta <- as.numeric(eval_in(input$delta_expr, e))
  if (is.null(time))  stop("time_expr is required")
  if (is.null(delta)) stop("delta_expr is required")

  if (is.null(input$etas)) stop("etas is required")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # External beta (required)
  beta <- NULL
  beta_sources <- character(0)
  if (!is.null(input$beta_expr) && nzchar(input$beta_expr)) {
    beta <- as_named_numeric(eval_in(input$beta_expr, e))
    beta_sources <- c(beta_sources, "beta_expr")
  }
  if (!is.null(input$beta_inline)) {
    beta <- as_named_numeric(input$beta_inline)
    beta_sources <- c(beta_sources, "beta_inline")
  }
  if (length(beta_sources) == 0L) {
    stop("Must provide exactly one of: beta_expr, beta_inline")
  }
  if (length(beta_sources) > 1L) {
    stop("Provide only one of: beta_expr, beta_inline")
  }
  # A NAMED beta may cover only a subset of the internal covariates: the package
  # aligns it by name and zero-pads the rest. Only an UNNAMED beta, which is
  # borrowed positionally, has to match ncol(z) exactly.
  if (!is.null(beta) && is.null(names(beta)) && length(beta) != ncol(z)) {
    stop(sprintf(
      paste0("Length of external beta (%d) does not match number of covariates ",
             "in z (%d). Supply a NAMED beta, with names matching the covariate ",
             "columns, to align a partial external model automatically."),
      length(beta), ncol(z)
    ))
  }

  # Optional Q (weighting / precision matrix)
  Q <- NULL
  Q_sources <- character(0)
  if (!is.null(input$Q_expr) && nzchar(input$Q_expr)) {
    Q <- as.matrix(eval_in(input$Q_expr, e))
    storage.mode(Q) <- "double"
    Q_sources <- c(Q_sources, "Q_expr")
  }
  if (!is.null(input$Q_inline)) {
    raw <- input$Q_inline
    mat <- do.call(rbind, lapply(raw, function(row) as.numeric(unlist(row))))
    Q <- as.matrix(mat)
    storage.mode(Q) <- "double"
    Q_sources <- c(Q_sources, "Q_inline")
  }
  if (length(Q_sources) > 1L) {
    stop("Provide only one of: Q_expr, Q_inline")
  }
  # Shape / symmetry / PSD / name validation is delegated to the package's
  # align_beta_Q: a NAMED Q may cover a subset of colnames(z) and is
  # zero-padded; only an UNNAMED Q must be exactly ncol(z) x ncol(z).
  # Do not re-check it here -- the bridge cannot express that contract.

  cv_criteria <- if (!is.null(input$cv_criteria)) as.character(input$cv_criteria) else "V&VH"
  if (!(cv_criteria %in% c("V&VH", "LinPred", "CIndex_pooled", "CIndex_foldaverage"))) {
    stop(sprintf("cv_criteria must be one of 'V&VH', 'LinPred', 'CIndex_pooled', 'CIndex_foldaverage' (got '%s')",
                 cv_criteria))
  }

  stratum         <- eval_in(input$stratum_expr, e)
  c_index_stratum <- eval_in(input$c_index_stratum_expr, e)
  tol    <- if (!is.null(input$tol))    as.numeric(input$tol)    else 1e-4
  Mstop  <- if (!is.null(input$Mstop))  as.integer(input$Mstop)  else 100L
  nfolds <- if (!is.null(input$nfolds)) as.integer(input$nfolds) else 5L
  # A4: the seed is never NULL. Fold assignment is drawn with sample, so an
  # absent seed hands the cross-validated loss -- and therefore the choice
  # between candidates -- to the ambient RNG. over 30
  # unseeded rounds the recommended estimator flipped 8 times out of 30,
  # because the run-to-run wobble in the loss was four times the gap between
  # the candidates. A fixed documented default costs nothing statistically
  # (the partition is arbitrary) and makes the run repeatable by default.
  DEFAULT_CV_SEED <- 20260818L
  seed   <- if (!is.null(input$seed)) as.integer(input$seed) else DEFAULT_CV_SEED
  seed_source <- if (!is.null(input$seed)) "caller" else "bridge_default"

  .lk  <- link_external(z, beta, Q)
  beta <- .lk$beta
  Q    <- .lk$Q

  cv_fit <- cv.cox_MDTL(
    z = z, delta = delta, time = time, stratum = stratum,
    beta = beta, Q = Q, etas = etas,
    tol = tol, Mstop = Mstop,
    nfolds = nfolds, cv.criteria = cv_criteria,
    c_index_stratum = c_index_stratum,
    message = FALSE, seed = seed
  )

  metric <- extract_metric(cv_fit$internal_stat)

  list(
    status       = "ok",
    linkage      = .lk$linkage,
    criteria     = cv_fit$criteria,
    nfolds       = cv_fit$nfolds,
    seed         = seed,
    seed_source  = seed_source,
    rng_kind     = if (!is.null(cv_fit$rng_kind)) cv_fit$rng_kind else NA,
    folds        = if (!is.null(cv_fit$folds)) as.integer(cv_fit$folds) else NA,
    etas         = as.numeric(cv_fit$internal_stat$eta),
    cv_metric    = metric,
    best         = list(
      best_eta  = as.numeric(cv_fit$best$best_eta),
      best_beta = as.numeric(cv_fit$best$best_beta),
      criteria  = cv_fit$best$criteria
    ),
    beta_full    = cv_fit$beta_full,
    n_obs        = nrow(z),
    n_covariates = ncol(z),
    n_etas       = length(cv_fit$internal_stat$eta),
    Q_used    = if (length(Q_sources) == 0L) "masked_identity" else Q_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "cv_cox_MDTL.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
