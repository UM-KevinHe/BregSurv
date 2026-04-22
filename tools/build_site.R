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

file.copy("llms.txt", "docs/llms.txt", overwrite = TRUE)

first_line <- readLines("docs/llms.txt", n = 1)
if (!identical(first_line, "# SurvBregDiv")) {
  stop("docs/llms.txt does not start with the expected '# SurvBregDiv' header. ",
       "Check that llms.txt at the repo root is the curated version.")
}

message("docs/llms.txt successfully overridden with curated llms.txt.")
