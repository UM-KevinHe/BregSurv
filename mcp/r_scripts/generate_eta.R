#!/usr/bin/env Rscript
# generate_eta.R - dispatcher for the generate_eta MCP tool.
#
# Called by mcp/server.py as:
#   Rscript generate_eta.R <input.json> <output.json>
#
# Thin wrapper around BregSurv::generate_eta(). Useful when the user has
# only described a range / shape of eta values rather than typing out an
# explicit numeric array. The returned `etas` array is suitable for direct
# use as the `etas` argument of any fit_* tool.

suppressPackageStartupMessages({
  library(jsonlite)
  library(BregSurv)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript generate_eta.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

result <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)

  method  <- if (!is.null(input$method))  as.character(input$method) else "exponential"
  n       <- if (!is.null(input$n))       as.integer(input$n)        else 10L
  max_eta <- if (!is.null(input$max_eta)) as.numeric(input$max_eta)  else 5
  min_eta <- if (!is.null(input$min_eta)) as.numeric(input$min_eta)  else 0

  if (!(method %in% c("linear", "exponential"))) {
    stop(sprintf(
      "method must be 'linear' or 'exponential' (got '%s')", method
    ))
  }
  if (n < 1L) stop("n must be >= 1")
  if (!is.finite(max_eta) || max_eta < 0) stop("max_eta must be a finite, non-negative number")
  if (!is.finite(min_eta) || min_eta < 0) stop("min_eta must be a finite, non-negative number")
  if (max_eta < min_eta) stop("max_eta must be >= min_eta")

  etas <- generate_eta(method = method, n = n,
                       max_eta = max_eta, min_eta = min_eta)

  list(
    status  = "ok",
    method  = method,
    n       = n,
    min_eta = min_eta,
    max_eta = max_eta,
    etas    = as.numeric(etas)
  )
}, error = function(err) {
  list(
    status  = "error",
    message = conditionMessage(err),
    class   = class(err)[1],
    where   = "generate_eta.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, na = "null", null = "null", pretty = TRUE),
  con = output_path
)
