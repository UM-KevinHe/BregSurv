#!/usr/bin/env Rscript
# fit_cox_MDTL.R - dispatcher for the fit_cox_MDTL MCP tool.
#
# Called by mcp/server.py as:
#   Rscript fit_cox_MDTL.R <input.json> <output.json>
#
# Reads JSON parameters, loads the user's data file, resolves R expressions,
# calls BregSurv::cox_MDTL with external beta and optional precision matrix
# Q, writes results as JSON. On any error, writes a structured
# {status:"error",...} payload.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript fit_cox_MDTL.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

eval_in <- function(expr_str, env) {
  if (is.null(expr_str) || !is.character(expr_str) || !nzchar(expr_str)) {
    return(NULL)
  }
  eval(parse(text = expr_str), envir = env)
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

  # --- Required: data_path ---
  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) stop("data_path is required")
  if (!file.exists(data_path)) stop(sprintf("File not found: %s", data_path))

  # --- Load data into an isolated environment ---
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

  # --- Required: z / time / delta ---
  z <- eval_in(input$z_expr, e)
  if (is.null(z)) stop("z_expr is required and must resolve to a matrix or data.frame")
  z <- as.matrix(z)
  storage.mode(z) <- "double"

  time <- eval_in(input$time_expr, e)
  if (is.null(time)) stop("time_expr is required")
  time <- as.numeric(time)

  delta <- eval_in(input$delta_expr, e)
  if (is.null(delta)) stop("delta_expr is required")
  delta <- as.numeric(delta)

  # --- Required: etas ---
  if (is.null(input$etas)) stop("etas is required (a numeric array)")
  etas <- as.numeric(unlist(input$etas))
  if (length(etas) == 0) stop("etas must be a non-empty numeric array")

  # --- Required: external beta (exactly one of beta_expr / beta_inline) ---
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
    stop(sprintf(
      "Provide only one of: beta_expr, beta_inline (got %d: %s)",
      length(beta_sources), paste(beta_sources, collapse = ", ")
    ))
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

  # --- Optional: Q (weighting / precision matrix for the Mahalanobis penalty) ---
  Q <- NULL
  Q_sources <- character(0)
  if (!is.null(input$Q_expr) && nzchar(input$Q_expr)) {
    Q <- as.matrix(eval_in(input$Q_expr, e))
    storage.mode(Q) <- "double"
    Q_sources <- c(Q_sources, "Q_expr")
  }
  if (!is.null(input$Q_inline)) {
    # Q_inline expected as a list of rows (list-of-lists in JSON).
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

  # --- Other optional parameters ---
  stratum      <- eval_in(input$stratum_expr, e)
  beta_initial <- eval_in(input$beta_initial_expr, e)
  tol          <- if (!is.null(input$tol))       as.numeric(input$tol)       else 1e-4
  Mstop        <- if (!is.null(input$Mstop))     as.integer(input$Mstop)     else 50L
  backtrack    <- if (!is.null(input$backtrack)) as.logical(input$backtrack) else FALSE

  # --- Call cox_MDTL ---
  .lk  <- link_external(z, beta, Q)
  beta <- .lk$beta
  Q    <- .lk$Q

  fit <- cox_MDTL(
    z            = z,
    delta        = delta,
    time         = time,
    stratum      = stratum,
    beta         = beta,
    Q            = Q,
    etas         = etas,
    tol          = tol,
    Mstop        = Mstop,
    backtrack    = backtrack,
    message      = FALSE,
    beta_initial = beta_initial
  )

  # --- Shape the return payload ---
  # Drops `linear.predictors` (n x n_etas, large) and `data` (echoes inputs).
  list(
    status        = "ok",
    linkage       = .lk$linkage,
    eta           = as.numeric(fit$eta),
    beta          = fit$beta,
    likelihood    = as.numeric(fit$likelihood),
    n_obs         = nrow(z),
    n_covariates  = ncol(z),
    n_etas        = length(fit$eta),
    Q_used     = if (length(Q_sources) == 0L) "masked_identity" else Q_sources
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "fit_cox_MDTL.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, matrix = "rowmajor", na = "null",
         null = "null", pretty = TRUE),
  con = output_path
)
