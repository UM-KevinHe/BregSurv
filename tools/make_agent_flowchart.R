## Builds assets/agent-flowchart.svg, the "How it works" figure of the README (the GitHub front page).
##
##   Rscript tools/make_agent_flowchart.R [png-preview-path]      # from the repository root
library(grid)

col <- c(you = "#55636D", model = "#2F6690", core = "#1F3B4D", external = "#A87A2A", stop = "#C8553D",
         ink = "#22313B", muted = "#5B6A75", panel = "#F3F6F8", rule = "#C9D3DA", arrow = "#7F8E99")

draw_agent_flowchart <- function() {
  grid.newpage()
  grid.rect(gp = gpar(fill = "white", col = NA))
  pushViewport(viewport(xscale = c(0, 13), yscale = c(0.3, 6.2)))
  u <- function(v) unit(v, "native")
  arr <- arrow(length = unit(6.5, "pt"), type = "closed", angle = 22)
  arr2 <- arrow(length = unit(6.5, "pt"), type = "closed", angle = 22, ends = "both")
  seg <- function(x0, y0, x1, y1, colour = col[["arrow"]], a = arr, lwd = 1.6)
    grid.segments(u(x0), u(y0), u(x1), u(y1), arrow = a, gp = gpar(col = colour, fill = colour, lwd = lwd))
  txt <- function(label, x, y, size = 11, colour = col[["ink"]], face = "plain", just = "centre")
    grid.text(label, u(x), u(y), just = just, gp = gpar(fontsize = size, col = colour, fontface = face))
  box <- function(x0, x1, y0, y1, border, fill = "white", lwd = 1.6)
    grid.roundrect(u((x0 + x1) / 2), u((y0 + y1) / 2), u(x1 - x0), u(y1 - y0), r = unit(6, "pt"),
                   gp = gpar(col = border, fill = fill, lwd = lwd))

  ## the frame: everything inside runs on your machine
  box(0.3, 10.6, 0.5, 5.9, col[["core"]], fill = "#FBFCFD", lwd = 2)
  txt("YOUR MACHINE OR YOUR INSTITUTION", 0.6, 5.58, size = 10.5, colour = col[["core"]], face = "bold", just = "left")

  ## checks in code, over the model and the package
  box(3.55, 10.3, 4.62, 5.2, col[["rule"]], fill = col[["panel"]], lwd = 1.2)
  txt("Checks in code", 6.925, 4.91, size = 11, colour = col[["muted"]], face = "bold")
  seg(5.1, 4.6, 5.1, 4.4); seg(8.75, 4.6, 8.75, 4.4)

  ## you, the language model, the R package
  box(0.6, 2.9, 2.6, 4.35, col[["you"]])
  txt("You", 1.75, 3.85, size = 14, face = "bold")
  txt("Describe the analysis", 1.75, 3.3, size = 10.5, colour = col[["muted"]])
  txt("Review the result", 1.75, 2.98, size = 10.5, colour = col[["muted"]])

  box(3.55, 6.65, 2.6, 4.35, col[["model"]])
  txt("Language model", 5.1, 3.85, size = 14, face = "bold", colour = col[["model"]])
  txt("Qwen3-8B, on your machine", 5.1, 3.45, size = 10, colour = col[["model"]], face = "italic")
  txt("Reads and plans", 5.1, 3.0, size = 10.5, colour = col[["muted"]])

  box(7.2, 10.3, 2.6, 4.35, col[["core"]], fill = "#EEF2F5")
  txt("BregSurv R package", 8.75, 3.85, size = 14, face = "bold", colour = col[["core"]])
  txt("Fits the models", 8.75, 3.3, size = 10.5, colour = col[["muted"]])
  txt("and picks the best", 8.75, 2.98, size = 10.5, colour = col[["muted"]])

  seg(2.95, 3.47, 3.5, 3.47, a = arr2); txt("chat", 3.225, 3.69, size = 9.5, colour = col[["muted"]])
  seg(6.7, 3.75, 7.15, 3.75); txt("plan", 6.925, 3.97, size = 9.5, colour = col[["muted"]])
  seg(7.15, 3.15, 6.7, 3.15); txt("results", 6.925, 2.93, size = 9.5, colour = col[["muted"]])

  ## your data
  box(7.75, 9.75, 0.85, 1.85, col[["you"]])
  txt("Your data", 8.75, 1.35, size = 12.5, face = "bold")
  seg(8.75, 1.9, 8.75, 2.55)

  ## external information comes in
  seg(12.8, 3.47, 10.35, 3.47, colour = col[["external"]], lwd = 1.8)
  txt("External information", 11.6, 3.75, size = 11, colour = col[["external"]], face = "bold")
  popViewport()
}

out <- file.path("assets", "agent-flowchart.svg")
svg(out, width = 11, height = 4.99, bg = "white")
draw_agent_flowchart()
invisible(dev.off())
cat("wrote", out, "\n")
args <- commandArgs(trailingOnly = TRUE)
if (length(args)) {
  png(args[1], width = 11, height = 4.99, units = "in", res = 100, type = "cairo", bg = "white")
  draw_agent_flowchart()
  invisible(dev.off())
  cat("wrote", args[1], "\n")
}
