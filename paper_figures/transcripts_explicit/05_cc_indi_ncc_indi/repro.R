#!/usr/bin/env Rscript
#
# repro.R — replay of one BregSurv agent run.
# Generated:    2026-05-28T01:06:05.031802Z
# User query:   Fit an individual-data NCC transfer-learning model on /gpfs/accounts/kevinhe_root/kevinhe1/ybshao/BregSurv-mcp/data/ExampleData_cc_indi.rda. Use these EXACT R expressions verbatim (keep the full Ex
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

# Step 1: fit_ncc_indi
cat('=== Step 1: fit_ncc_indi ===\n')
r1_args <- list(data_path = "/gpfs/accounts/kevinhe_root/kevinhe1/ybshao/BregSurv-mcp/data/ExampleData_cc_indi.rda", z_int_expr = "ExampleData_cc_indi$internal$z", y_int_expr = "ExampleData_cc_indi$internal$y", stratum_int_expr = "ExampleData_cc_indi$internal$stratum", z_ext_expr = "ExampleData_cc_indi$external$z", y_ext_expr = "ExampleData_cc_indi$external$y", stratum_ext_expr = "ExampleData_cc_indi$external$stratum", etas = c(0, 0.5, 1), max_iter = 100, tol = 1e-07)
r1 <- run_tool('fit_ncc_indi', r1_args)
results[['fit_ncc_indi_step1']] <- r1
print(r1)

# All steps complete. Inspect `results` for the full set of
# replayed outputs (one named list entry per non-skipped step).
invisible(results)
