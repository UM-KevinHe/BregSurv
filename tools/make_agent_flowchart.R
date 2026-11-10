## Builds assets/agent-flowchart.svg, the "How it works" figure of the README (the GitHub front page).
##
##   Rscript tools/make_agent_flowchart.R [png-preview-path]      # from the repository root
library(grid)

col <- c(you = "#55636D", model = "#2F6690", core = "#1F3B4D", external = "#A87A2A", stop = "#C8553D",
         ink = "#22313B", muted = "#5B6A75", panel = "#F3F6F8", rule = "#C9D3DA", arrow = "#7F8E99")

draw_agent_flowchart <- function() {
  grid.newpage()
  grid.rect(gp = gpar(fill = "white", col = NA))
  pushViewport(viewport(xscale = c(0, 14), yscale = c(0.3, 7.8)))
  u <- function(v) unit(v, "native")
  arr <- arrow(length = unit(6.5, "pt"), type = "closed", angle = 22)
  arr2 <- arrow(length = unit(6.5, "pt"), type = "closed", angle = 22, ends = "both")
  seg <- function(x0, y0, x1, y1, colour = col[["arrow"]], a = arr, lty = 1, lwd = 1.6)
    grid.segments(u(x0), u(y0), u(x1), u(y1), arrow = a, gp = gpar(col = colour, fill = colour, lwd = lwd, lty = lty))
  txt <- function(label, x, y, size = 11, colour = col[["ink"]], face = "plain", just = "centre")
    grid.text(label, u(x), u(y), just = just, gp = gpar(fontsize = size, col = colour, fontface = face))
  box <- function(x0, x1, y0, y1, border, fill = "white", lwd = 1.6)
    grid.roundrect(u((x0 + x1) / 2), u((y0 + y1) / 2), u(x1 - x0), u(y1 - y0), r = unit(6, "pt"),
                   gp = gpar(col = border, fill = fill, lwd = lwd))

  ## the frame: everything inside runs on your machine
  box(0.3, 10.7, 0.5, 7.6, col[["core"]], fill = "#FBFCFD", lwd = 2)
  txt("YOUR MACHINE OR YOUR INSTITUTION", 0.6, 7.28, size = 10.5, colour = col[["core"]], face = "bold", just = "left")

  ## checks in code, over the model and the package
  box(3.55, 10.4, 6.25, 6.95, col[["rule"]], fill = col[["panel"]], lwd = 1.2)
  txt("Checks in code: readings verified  ·  only admissible analyses  ·  a fixed budget",
      6.975, 6.6, size = 10, colour = col[["muted"]], face = "bold")
  seg(5.1, 6.22, 5.1, 5.95); seg(8.85, 6.22, 8.85, 5.95)

  ## you, the language model, the R package
  box(0.6, 2.9, 3.65, 5.9, col[["you"]])
  txt("You", 1.75, 5.42, size = 14, face = "bold")
  txt("Describe the analysis", 1.75, 4.88, size = 10.5, colour = col[["muted"]])
  txt("in your own words", 1.75, 4.58, size = 10.5, colour = col[["muted"]])
  txt("Review the result", 1.75, 4.12, size = 10.5, colour = col[["muted"]])

  box(3.55, 6.65, 3.65, 5.9, col[["model"]])
  txt("Language model", 5.1, 5.42, size = 14, face = "bold", colour = col[["model"]])
  txt("Qwen3-8B, on your machine", 5.1, 5.08, size = 10, colour = col[["model"]], face = "italic")
  txt("Reads your request", 5.1, 4.62, size = 10.5, colour = col[["muted"]])
  txt("Plans the analysis", 5.1, 4.32, size = 10.5, colour = col[["muted"]])
  txt("Writes the summary", 5.1, 4.02, size = 10.5, colour = col[["muted"]])

  box(7.3, 10.4, 3.65, 5.9, col[["core"]], fill = "#EEF2F5")
  txt("BregSurv R package", 8.85, 5.42, size = 14, face = "bold", colour = col[["core"]])
  txt("Fits every planned model", 8.85, 4.75, size = 10.5, colour = col[["muted"]])
  txt("Cross-validation picks", 8.85, 4.38, size = 10.5, colour = col[["muted"]])
  txt("the best", 8.85, 4.08, size = 10.5, colour = col[["muted"]])

  seg(2.95, 4.78, 3.5, 4.78, a = arr2); txt("chat", 3.225, 5.0, size = 9.5, colour = col[["muted"]])
  seg(6.7, 5.15, 7.25, 5.15); txt("plan", 6.975, 5.37, size = 9.5, colour = col[["muted"]])
  seg(7.25, 4.35, 6.7, 4.35); txt("fits", 6.975, 4.13, size = 9.5, colour = col[["muted"]])

  ## what you get: words from the model, numbers from the fits
  box(0.6, 5.6, 0.95, 2.6, col[["you"]])
  txt("Chat answer  ·  PDF report  ·  replay script", 3.1, 2.08, size = 11.5, face = "bold")
  txt("words from the model, every number from the fits", 3.1, 1.6, size = 10, colour = col[["muted"]], face = "italic")
  txt("the replay script reruns it in R, without the model", 3.1, 1.25, size = 10, colour = col[["muted"]], face = "italic")
  seg(4.6, 3.6, 4.6, 2.65); txt("words", 4.95, 3.12, size = 9.5, colour = col[["muted"]])
  seg(7.6, 3.6, 5.65, 2.3); txt("numbers", 6.95, 2.6, size = 9.5, colour = col[["muted"]])
  seg(1.75, 2.65, 1.75, 3.6)

  ## your data stay here
  box(7.6, 10.1, 0.95, 2.6, col[["you"]])
  txt("Your data", 8.85, 2.05, size = 12.5, face = "bold")
  txt("patient records", 8.85, 1.6, size = 10, colour = col[["muted"]], face = "italic")
  seg(8.85, 2.65, 8.85, 3.6)
  seg(10.15, 1.78, 13.6, 1.78, colour = col[["stop"]], lty = 2, lwd = 1.5)
  txt("✕", 11.75, 1.78, size = 15, colour = col[["stop"]], face = "bold")
  txt("Data and results never", 12.15, 1.32, size = 10.5, colour = col[["stop"]], face = "bold")
  txt("leave your machine", 12.15, 1.02, size = 10.5, colour = col[["stop"]], face = "bold")

  ## external information comes in
  seg(13.6, 4.78, 10.45, 4.78, colour = col[["external"]], lwd = 1.8)
  txt("External information", 12.1, 5.42, size = 11.5, colour = col[["external"]], face = "bold")
  txt("a published model, a risk score,", 12.1, 4.4, size = 9.5, colour = col[["external"]])
  txt("another cohort's records", 12.1, 4.13, size = 9.5, colour = col[["external"]])
  popViewport()
}

out <- file.path("assets", "agent-flowchart.svg")
svg(out, width = 11, height = 5.89, bg = "white")
draw_agent_flowchart()
invisible(dev.off())
cat("wrote", out, "\n")
args <- commandArgs(trailingOnly = TRUE)
if (length(args)) {
  png(args[1], width = 11, height = 5.89, units = "in", res = 100, type = "cairo", bg = "white")
  draw_agent_flowchart()
  invisible(dev.off())
  cat("wrote", args[1], "\n")
}
