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

# Remove any rendered CLAUDE.* files pkgdown may have produced from CLAUDE.md.
# CLAUDE.md is private maintainer documentation and must never be published.
claude_artifacts <- list.files("docs", pattern = "^CLAUDE\\.", full.names = TRUE)
if (length(claude_artifacts)) {
  file.remove(claude_artifacts)
  message("Removed private CLAUDE artifacts from docs/: ",
          paste(basename(claude_artifacts), collapse = ", "))
}

# Scrub CLAUDE.md-derived entries from docs/search.json. pkgdown indexes
# CLAUDE.md into the site-wide search before we remove the rendered file,
# so without this step the site search box would still surface CLAUDE
# snippets even though clicking them 404s.
search_path <- "docs/search.json"
if (requireNamespace("jsonlite", quietly = TRUE) && file.exists(search_path)) {
  idx <- jsonlite::fromJSON(search_path, simplifyVector = FALSE)
  has_claude <- function(entry) {
    fields <- unlist(entry[c("title", "path")], use.names = FALSE)
    any(grepl("CLAUDE", fields, fixed = TRUE))
  }
  cleaned <- Filter(Negate(has_claude), idx)
  removed <- length(idx) - length(cleaned)
  if (removed > 0L) {
    jsonlite::write_json(cleaned, search_path, auto_unbox = TRUE)
    message(sprintf("Removed %d CLAUDE entries from %s.", removed, search_path))
  }
}

message("docs/llms.txt successfully overridden with curated llms.txt.")
