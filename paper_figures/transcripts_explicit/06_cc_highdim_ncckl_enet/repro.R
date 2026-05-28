#!/usr/bin/env Rscript
#
# repro.R — replay of one BregSurv agent run.
# Generated:    2026-05-28T01:06:13.750174Z
# User query:   Fit an elastic-net NCC KL model (variable selection on p=20 covariates) on /gpfs/accounts/kevinhe_root/kevinhe1/ybshao/BregSurv-mcp/data/ExampleData_cc_highdim.rda. Use these EXACT R expressions ve
# Model:        qwen2.5-7b-awq @ http://localhost:8000/v1
# Prompt SHA:   d93e601dd35a4ddd
#
# Each block below dispatches one tool call against the same
# R script the agent used (mcp/r_scripts/<tool>.R). Provide the
# path to the mcp/r_scripts directory via the SURVBREGDIV_R_SCRIPTS
# environment variable, or set the default below.

suppressPackageStartupMessages({
  library(jsonlite)
})

MCP_R_SCRIPTS <- Sys.getenv(
  'SURVBREGDIV_R_SCRIPTS',
  unset = file.path(getwd(), 'mcp', 'r_scripts')
)
if (!dir.exists(MCP_R_SCRIPTS)) {
  stop(paste0(
    'mcp/r_scripts/ not found at: ', MCP_R_SCRIPTS, '\n',
    'Clone the BregSurv-mcp repo and set SURVBREGDIV_R_SCRIPTS.'
  ))
}
RSCRIPT <- Sys.which('Rscript')
if (RSCRIPT == '') stop('Rscript not found on PATH.')

run_tool <- function(tool_name, args) {
  in_file  <- tempfile(fileext = '.in.json')
  out_file <- tempfile(fileext = '.out.json')
  on.exit({ unlink(in_file); unlink(out_file) }, add = TRUE)
  writeLines(toJSON(args, auto_unbox = TRUE, null = 'null'), in_file)
  script <- file.path(MCP_R_SCRIPTS, paste0(tool_name, '.R'))
  # NOTE: system2() does not individually shell-quote `args`, so paths
  # containing spaces (common on macOS Dropbox folders) get word-split.
  # Build the command string with shQuote on every variable and use
  # system() instead.
  cmd <- paste(
    shQuote(RSCRIPT),
    '--no-save --no-restore --no-init-file',
    shQuote(script), shQuote(in_file), shQuote(out_file)
  )
  status <- system(cmd, ignore.stdout = TRUE, ignore.stderr = TRUE)
  if (!file.exists(out_file))
    stop(sprintf('%s.R produced no output (status=%d)', tool_name, status))
  fromJSON(out_file)
}

results <- list()

# Step 1: fit_ncckl_enet
cat('=== Step 1: fit_ncckl_enet ===\n')
r1_args <- list(data_path = "/gpfs/accounts/kevinhe_root/kevinhe1/ybshao/BregSurv-mcp/data/ExampleData_cc_highdim.rda", z_expr = "ExampleData_cc_highdim$train$z", y_expr = "ExampleData_cc_highdim$train$y", stratum_expr = "ExampleData_cc_highdim$train$stratum", eta = 0.5, beta_expr = "ExampleData_cc_highdim$beta_external", alpha = 1.0, lambda_ = NULL, nlambda = 100, lambda_min_ratio = NULL, tol = 0.0001, Mstop = 1000)
r1 <- run_tool('fit_ncckl_enet', r1_args)
results[['fit_ncckl_enet_step1']] <- r1
print(r1)

# All steps complete. Inspect `results` for the full set of
# replayed outputs (one named list entry per non-skipped step).
invisible(results)
