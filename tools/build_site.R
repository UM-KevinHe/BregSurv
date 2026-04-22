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
if (!identical(first_line, "# SurvBregDiv")) {
  stop("docs/llms.txt does not start with the expected '# SurvBregDiv' header. ",
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

message("docs/llms.txt successfully overridden with curated llms.txt.")
