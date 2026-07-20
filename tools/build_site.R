# tools/build_site.R
#
# Wrapper around pkgdown::build_site() that preserves the hand-written
# llms.txt. pkgdown >= 2.1 auto-generates docs/llms.txt from the README +
# package index and overwrites whatever is in pkgdown/assets/. We rebuild
# the site, then overwrite docs/llms.txt with our curated version.
#
# Run this INSTEAD of pkgdown::build_site() whenever you publish the site.
#
#   source("tools/build_site.R")

stopifnot(file.exists("llms.txt"))

pkgdown::build_site()

# Override pkgdown's auto-generated llms.txt with our curated version
file.copy("llms.txt", "docs/llms.txt", overwrite = TRUE)

first_line <- readLines("docs/llms.txt", n = 1)
if (!identical(first_line, "# BregSurv")) {
  stop("docs/llms.txt does not start with the expected '# BregSurv' header. ",
       "Check that llms.txt at the repo root is the curated version.")
}

# ---------------------------------------------------------------------------
# Private-document scrub.
#
# pkgdown renders EVERY top-level .md it finds into the site and indexes it
# into the search box. .gitignore does not help: it stops git, not pkgdown.
#
# This bit the project twice. CLAUDE.md leaked into a published search.json
# for ~3 weeks in 2026-04/05. Then on 2026-07-15 a REPO_CLEANUP.md written
# during a repo tidy-up was rendered to docs/REPO_CLEANUP.html and 15 search
# entries, exposing internal notes, before the same rebuild caught it.
#
# So this is a LIST, not a single filename. Any new private .md at the repo
# root must be added here AND to .gitignore -- the two are not substitutes.
# ---------------------------------------------------------------------------
private_docs <- c("CLAUDE", "REPO_CLEANUP", "AGENT_NOTES", "INTERNAL_NOTES")

pattern <- paste0("^(", paste(private_docs, collapse = "|"), ")\\.")
artifacts <- list.files("docs", pattern = pattern, full.names = TRUE)
if (length(artifacts)) {
  file.remove(artifacts)
  message("Removed private artifacts from docs/: ",
          paste(basename(artifacts), collapse = ", "))
}

# Same documents must also be scrubbed from the site-wide search index:
# pkgdown indexes them BEFORE we delete the rendered files, so without this
# the search box would still surface their text even though the links 404.
search_path <- "docs/search.json"
if (requireNamespace("jsonlite", quietly = TRUE) && file.exists(search_path)) {
  idx <- jsonlite::fromJSON(search_path, simplifyVector = FALSE)
  is_private <- function(entry) {
    fields <- unlist(entry[c("title", "path")], use.names = FALSE)
    any(vapply(private_docs,
               function(d) any(grepl(d, fields, fixed = TRUE)),
               logical(1)))
  }
  cleaned <- Filter(Negate(is_private), idx)
  removed <- length(idx) - length(cleaned)
  if (removed > 0L) {
    jsonlite::write_json(cleaned, search_path, auto_unbox = TRUE)
    message(sprintf("Removed %d private entries from %s.", removed, search_path))
  }
}

# Fail loudly if anything private still made it through -- better to break the
# build than to publish it.
leaked <- list.files("docs", pattern = pattern, recursive = TRUE)
if (length(leaked)) {
  stop("Private documents still present under docs/: ",
       paste(leaked, collapse = ", "))
}

message("docs/llms.txt successfully overridden with curated llms.txt.")
