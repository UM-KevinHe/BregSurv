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
# This is a LIST, not a single filename: any private .md left at the repo root
# would otherwise be rendered and indexed. Add new ones here AND to .gitignore
# -- the two are not substitutes, since they guard different steps.
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

# Third exit: the sitemap. pkgdown lists every rendered page there, so without
# this the file is gone but the sitemap still invites crawlers to fetch it.
sitemap_path <- "docs/sitemap.xml"
if (file.exists(sitemap_path)) {
  lines <- readLines(sitemap_path, warn = FALSE)
  drop <- Reduce(`|`, lapply(private_docs, function(d) grepl(d, lines, fixed = TRUE)))
  if (any(drop)) {
    writeLines(lines[!drop], sitemap_path)
    message(sprintf("Removed %d private URLs from %s.", sum(drop), sitemap_path))
  }
}

# Fail loudly if anything private still made it through -- better to break the
# build than to publish it. Checks all three exits: rendered files, the search
# index, and the sitemap.
leaked <- list.files("docs", pattern = pattern, recursive = TRUE)
if (length(leaked)) {
  stop("Private documents still present under docs/: ",
       paste(leaked, collapse = ", "))
}
for (f in c("docs/search.json", sitemap_path)) {
  if (file.exists(f)) {
    txt <- paste(readLines(f, warn = FALSE), collapse = "\n")
    hit <- private_docs[vapply(private_docs, grepl, logical(1), x = txt, fixed = TRUE)]
    if (length(hit)) {
      stop("Private references still present in ", f, ": ",
           paste(hit, collapse = ", "))
    }
  }
}

message("docs/llms.txt successfully overridden with curated llms.txt.")
