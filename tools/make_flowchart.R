## Builds vignettes/figures/bregsurv-flowchart.svg, the overview figure of Get started.
##
##   Rscript tools/make_flowchart.R [png-preview-path]      # from the package root
##
## The objective sits on top, with the term each step sets in that step's colour, and the three
## steps below it.
library(grid)

col <- c(target = "#2F6690", release = "#A87A2A", divergence = "#C8553D", fit = "#1F3B4D",
         ink = "#22313B", muted = "#5B6A75", panel = "#F3F6F8", rule = "#D2DAE0")

draw_flowchart <- function() {
  grid.newpage()
  grid.rect(gp = gpar(fill = "white", col = NA))
  pushViewport(viewport(xscale = c(0, 12), yscale = c(3.1, 8.9)))
  nat <- function(g) convertWidth(grobWidth(g), "native", valueOnly = TRUE)

  ## the objective
  grid.roundrect(x = unit(6, "native"), y = unit(7.72, "native"), width = unit(11.5, "native"),
                 height = unit(2.05, "native"), r = unit(7, "pt"), gp = gpar(fill = col[["panel"]], col = col[["rule"]]))
  grid.text("ONE OBJECTIVE FOR EVERY ANALYSIS", x = unit(0.62, "native"), y = unit(8.42, "native"), just = "left",
            gp = gpar(fontsize = 10.5, fontface = "bold", col = col[["muted"]]))
  fs <- 23
  pieces <- list(
    list(quote(paste(italic(Q)[eta], "(", theta, ")  =  − ")), col[["ink"]]),
    list(quote(paste("ℓ", "(", theta, ")")), col[["target"]]),
    list(quote(paste("  +  ")), col[["ink"]]),
    list(quote(eta), col[["fit"]]),
    list(quote(paste(" ", italic(B)[italic(G)], "(", theta, ")")), col[["divergence"]]),
    list(quote(paste(",     ", eta >= 0)), col[["muted"]]))
  grobs <- lapply(pieces, function(p) textGrob(p[[1]], gp = gpar(fontsize = fs, col = p[[2]])))
  w <- vapply(grobs, nat, numeric(1))
  x0 <- 6 - sum(w) / 2
  for (i in seq_along(grobs)) {
    grid.text(pieces[[i]][[1]], x = unit(x0 + sum(w[seq_len(i - 1)]), "native"), y = unit(7.83, "native"),
              just = "left", gp = gpar(fontsize = fs, col = pieces[[i]][[2]]))
  }
  grid.text(quote(paste("where  ", italic(B)[italic(G)], "(", italic(u), " ‖ ", italic(v), ")  =  ",
                        italic(G), "(", italic(u), ")  −  ", italic(G), "(", italic(v), ")  −  ∇",
                        italic(G), "(", italic(v), ")"^T, "(", italic(u), " − ", italic(v), "),   ",
                        italic(G), " strictly convex")),
            x = unit(6, "native"), y = unit(7.12, "native"), gp = gpar(fontsize = 13.5, col = col[["muted"]]))

  ## the three steps
  cx <- c(2.1, 6, 9.9); top <- 6.05; bot <- 3.6; wd <- 3.65
  steps <- list(
    list(key = "target", n = "STEP 1", title = "The target model",
         q = c("What model do you fit", "to your own data?"),
         foot = quote(paste("sets the likelihood  ", "ℓ", "(", theta, ")"))),
    list(key = "release", n = "STEP 2", title = "The release",
         q = c("What did the external source", "make available?"),
         foot = quote(paste("decides which divergences apply"))),
    list(key = "divergence", n = "STEP 3", title = "The divergence",
         q = c("Through which divergence does", "the release enter?"),
         foot = quote(paste("sets  ", italic(G), "  and so  ", italic(B)[italic(G)]))))
  for (i in 1:3) {
    s <- steps[[i]]; k <- col[[s$key]]
    grid.roundrect(x = unit(cx[i], "native"), y = unit((top + bot) / 2, "native"), width = unit(wd, "native"),
                   height = unit(top - bot, "native"), r = unit(7, "pt"), gp = gpar(fill = "white", col = k, lwd = 1.8))
    left <- cx[i] - wd / 2 + 0.28
    grid.text(s$n, x = unit(left, "native"), y = unit(top - 0.38, "native"), just = "left",
              gp = gpar(fontsize = 10.5, fontface = "bold", col = k))
    grid.text(s$title, x = unit(left, "native"), y = unit(top - 0.78, "native"), just = "left",
              gp = gpar(fontsize = 16.5, fontface = "bold", col = col[["ink"]]))
    grid.text(s$q[1], x = unit(left, "native"), y = unit(top - 1.3, "native"), just = "left",
              gp = gpar(fontsize = 12.5, col = col[["muted"]]))
    grid.text(s$q[2], x = unit(left, "native"), y = unit(top - 1.62, "native"), just = "left",
              gp = gpar(fontsize = 12.5, col = col[["muted"]]))
    grid.segments(x0 = unit(left, "native"), x1 = unit(cx[i] + wd / 2 - 0.28, "native"),
                  y0 = unit(bot + 0.55, "native"), y1 = unit(bot + 0.55, "native"),
                  gp = gpar(col = col[["rule"]], lwd = 1))
    grid.text(s$foot, x = unit(left, "native"), y = unit(bot + 0.27, "native"), just = "left",
              gp = gpar(fontsize = 12, col = k, fontface = "bold"))
  }
  arrow_g <- gpar(col = "#8E9BA5", fill = "#8E9BA5", lwd = 1.6)
  arr <- arrow(length = unit(7, "pt"), type = "closed", angle = 22)
  for (i in 1:2) grid.segments(x0 = unit(cx[i] + wd / 2 + 0.06, "native"), x1 = unit(cx[i + 1] - wd / 2 - 0.06, "native"),
                               y0 = unit((top + bot) / 2, "native"), y1 = unit((top + bot) / 2, "native"),
                               arrow = arr, gp = arrow_g)

  popViewport()
}

out <- file.path("vignettes", "figures", "bregsurv-flowchart.svg")
dir.create(dirname(out), showWarnings = FALSE, recursive = TRUE)
svg(out, width = 10, height = 4.83, bg = "white")
draw_flowchart()
invisible(dev.off())
cat("wrote", out, "\n")
args <- commandArgs(trailingOnly = TRUE)
if (length(args)) {
  png(args[1], width = 10, height = 4.83, units = "in", res = 110, type = "cairo", bg = "white")
  draw_flowchart()
  invisible(dev.off())
  cat("wrote", args[1], "\n")
}
