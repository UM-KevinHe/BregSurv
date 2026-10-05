#!/usr/bin/env Rscript
# read_external.R -- every table an .rds / .rda / .RData file holds, as CSV.
#
# Part of M5 (external information). Python cannot read R's serialisation, so
# this script loads the file and writes each data.frame, matrix or named
# numeric vector it finds -- at the top level or one level into a list -- to a
# CSV in `out_dir`, and returns a manifest. Nothing is interpreted here: no
# column is named a coefficient, no number is changed. A matrix's row names
# become a first column `.row`; a named vector becomes `name, value`.
#
# input:  { "path": "<file>", "out_dir": "<dir>" }
# output: { "status": "ok", "tables": [ {name, kind, csv, n_rows, n_cols} ] }
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly = TRUE)
input <- fromJSON(args[1], simplifyVector = FALSE)
out_path <- args[2]

result <- tryCatch({
  path <- input$path
  out_dir <- input$out_dir
  if (!file.exists(path)) stop(sprintf("file not found: %s", path))
  dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
  ext <- tolower(tools::file_ext(path))
  e <- new.env()
  if (ext %in% c("rda", "rdata")) {
    load(path, envir = e)
    objs <- mget(ls(e), envir = e)
  } else if (ext == "rds") {
    objs <- list(readRDS(path))
    names(objs) <- make.names(tools::file_path_sans_ext(basename(path)))
  } else {
    stop(sprintf("not an R serialisation: .%s", ext))
  }

  tables <- list()
  emit <- function(obj, name) {
    df <- NULL; kind <- NULL
    if (is.data.frame(obj)) {
      df <- obj; kind <- "data.frame"
    } else if (is.matrix(obj) && is.numeric(obj)) {
      df <- as.data.frame(obj, check.names = FALSE)
      if (!is.null(rownames(obj))) df <- cbind(.row = rownames(obj), df)
      kind <- "matrix"
    } else if (is.numeric(obj) && !is.null(names(obj))) {
      df <- data.frame(name = names(obj), value = as.numeric(obj),
                       stringsAsFactors = FALSE)
      kind <- "named vector"
    }
    if (is.null(df)) return(invisible(NULL))
    f <- file.path(out_dir, paste0(gsub("[^A-Za-z0-9_.-]", "_", name), ".csv"))
    utils::write.csv(df, f, row.names = FALSE)
    tables[[length(tables) + 1L]] <<- list(name = name, kind = kind, csv = f,
                                           n_rows = nrow(df), n_cols = ncol(df))
  }
  for (nm in names(objs)) {
    obj <- objs[[nm]]
    if (is.list(obj) && !is.data.frame(obj)) {
      for (k in names(obj)) emit(obj[[k]], paste0(nm, "$", k))
    } else {
      emit(obj, nm)
    }
  }
  list(status = "ok", tables = tables)
}, error = function(err) {
  list(status = "error", message = conditionMessage(err),
       class = class(err)[1], where = "read_external.R")
})
writeLines(toJSON(result, auto_unbox = TRUE, null = "null", digits = NA), out_path)
