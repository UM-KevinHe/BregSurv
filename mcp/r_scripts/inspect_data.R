#!/usr/bin/env Rscript
# inspect_data.R — describe the structure of an R data file.
#
# Called by mcp/server.py as:
#   Rscript inspect_data.R <input.json> <output.json>
#
# input.json : {"data_path": "..."}
# output.json: {"status": "ok", "data_path": "...", "structure": {...}}
#          or {"status": "error", "message": "...", "class": "...", "where": "..."}
#
# Only metadata (class, dim, length) is reported — values are never read.
# Safe on very large files.

suppressPackageStartupMessages({
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript inspect_data.R <input.json> <output.json>")
}
input_path  <- args[1]
output_path <- args[2]

describe <- function(obj) {
  if (is.matrix(obj)) {
    sprintf("matrix %dx%d (%s)", nrow(obj), ncol(obj), typeof(obj))
  } else if (is.data.frame(obj)) {
    cols <- vapply(obj, function(x) class(x)[1], character(1))
    list(
      ".kind" = sprintf("data.frame %dx%d", nrow(obj), ncol(obj)),
      ".columns" = as.list(cols)
    )
  } else if (is.list(obj) && !is.null(names(obj)) && all(nzchar(names(obj)))) {
    lapply(obj, describe)
  } else if (is.list(obj)) {
    sprintf("unnamed list (length %d)", length(obj))
  } else if (is.factor(obj)) {
    sprintf("factor (length %d, %d levels)", length(obj), nlevels(obj))
  } else if (is.numeric(obj)) {
    sprintf("numeric (length %d)", length(obj))
  } else if (is.integer(obj)) {
    sprintf("integer (length %d)", length(obj))
  } else if (is.character(obj)) {
    sprintf("character (length %d)", length(obj))
  } else if (is.logical(obj)) {
    sprintf("logical (length %d)", length(obj))
  } else {
    class(obj)[1]
  }
}

result <- tryCatch({
  input <- fromJSON(input_path)
  data_path <- input$data_path
  if (is.null(data_path) || !nzchar(data_path)) {
    stop("data_path is required")
  }
  if (!file.exists(data_path)) {
    stop(sprintf("File not found: %s", data_path))
  }

  ext <- tolower(tools::file_ext(data_path))
  e <- new.env()

  if (ext %in% c("rda", "rdata")) {
    load(data_path, envir = e)
  } else if (ext == "rds") {
    # readRDS returns one object; give it a name based on the filename.
    obj_name <- tools::file_path_sans_ext(basename(data_path))
    assign(obj_name, readRDS(data_path), envir = e)
  } else {
    stop(sprintf("Unsupported file extension: .%s (supported: .rda .RData .rds)", ext))
  }

  structure_desc <- lapply(as.list(e), describe)

  list(
    status = "ok",
    data_path = data_path,
    top_level_names = names(structure_desc),
    structure = structure_desc
  )
}, error = function(err) {
  list(
    status = "error",
    message = conditionMessage(err),
    class = class(err)[1],
    where = "inspect_data.R"
  )
})

writeLines(
  toJSON(result, auto_unbox = TRUE, pretty = TRUE, null = "null"),
  con = output_path
)
