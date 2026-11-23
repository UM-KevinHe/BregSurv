#!/usr/bin/env Rscript
# restyle_figure.R - change how a figure the harness drew looks, never what it shows (V4).
#
#   Rscript restyle_figure.R <in.json> <out.json>
#
# HARNESS-INVOKED. The language model wrote the code; this script decides whether it is used. The
# model never writes statistical code: it adds terms to a figure the harness already built from the
# fitted analysis ("p + theme_minimal() + scale_colour_manual(values = ...)"), and the terms are
# accepted only when nothing the figure shows has changed.
#
# Three gates, in order; the first that fails rejects the code, and the problems go back to the
# model by name (at most three attempts in all, then the figure stays as it was):
#
#   1. what the code may say (read, not run). It must be `p` followed by `+` terms, each a call to one
#      of the style functions below, with the arguments listed for it; inside them only the helper
#      calls below, strings, numbers and TRUE/FALSE. No geom, stat, annotation, coordinate, facet,
#      axis scale, limit or data; no `::`, `$`, assignment, function or formula. A colour must be a
#      colour R knows and opaque; a manual scale's names must be the figure's groups; a number in a
#      title or label must be one the analyst wrote in the message that asked for the change.
#   2. it runs, in an environment holding only those functions and the figure (`p`).
#   3. what the figure shows (the restyled figure is built and compared with the harness's): every
#      layer's data (positions, groups, labels), the axes' ranges and the legend's labels are
#      unchanged; the axes' text and titles and, when there is one, the legend are still shown; text
#      is at least 6 points; the groups still look different from each other; a curve is not drawn in
#      the colour of the panel behind it.
#
# input.json: {figure_rds, steps: [{code, message}], out_base, render}
#   steps  every restyle of this figure accepted before, in order, and the new one last; `message` is
#          the analyst's message that asked for that step
# output.json: {status: "ok", changes, png, pdf, style_r} | {status: "rejected", problems: [{code,
#              detail}], step} | {status: "error", reason}

suppressPackageStartupMessages({ library(jsonlite); library(ggplot2) })
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("Usage: Rscript restyle_figure.R <in.json> <out.json>")
input_path <- args[1]; output_path <- args[2]
script_dir <- local({
  a <- commandArgs(trailingOnly = FALSE)
  f <- sub("^--file=", "", a[grepl("^--file=", a)])
  if (length(f)) dirname(normalizePath(f[1])) else getwd()
})
LIB <- file.path(script_dir, "figure_lib.R")
source(LIB)
grDevices::pdf(NULL)   # building a gtable needs a device; never write Rplots.pdf

# ---- gate 1: the style vocabulary ---------------------------------------------------------------
# top-level terms: the arguments each may take ("*": any argument, every value still checked)
THEMES <- c("theme_grey", "theme_gray", "theme_bw", "theme_linedraw", "theme_light", "theme_dark",
            "theme_minimal", "theme_classic")
# a whole theme takes these (base_size positionally too); theme() takes the theme's own elements
THEME_FUN_ARGS <- c("base_size", "base_family", "base_line_size", "base_rect_size")
THEME_ELEMENTS <- tryCatch(names(ggplot2::get_element_tree()), error = function(e) NULL)
STYLE_ARGS <- c(
  list(theme = "*"),
  stats::setNames(rep(list(THEME_FUN_ARGS), length(THEMES)), THEMES),
  list(labs = c("title", "subtitle", "caption", "x", "y", "colour", "color", "fill", "linetype"),
       ggtitle = c("label", "subtitle"), xlab = "label", ylab = "label",
       scale_colour_manual = c("values", "name"), scale_color_manual = c("values", "name"),
       scale_fill_manual = c("values", "name"), scale_linetype_manual = c("values", "name"),
       scale_colour_brewer = c("palette", "direction", "type", "name"),
       scale_color_brewer = c("palette", "direction", "type", "name"),
       scale_fill_brewer = c("palette", "direction", "type", "name"),
       scale_colour_viridis_d = c("option", "begin", "end", "direction", "name"),
       scale_color_viridis_d = c("option", "begin", "end", "direction", "name"),
       scale_fill_viridis_d = c("option", "begin", "end", "direction", "name"),
       scale_colour_grey = c("start", "end", "name"), scale_color_grey = c("start", "end", "name"),
       scale_fill_grey = c("start", "end", "name"),
       guides = c("colour", "color", "fill", "linetype"),
       line_width = "x", point_size = "x"))
POSITIONAL_OK <- c(THEMES, "ggtitle", "xlab", "ylab", "line_width", "point_size")
# calls allowed inside a term
# Every argument is checked by name: an argument a function does not take is silently ignored by
# ggplot2, and the figure would not change while the reply said it had.
INNER_ARGS <- list(element_text = c("family", "face", "colour", "color", "size", "hjust", "vjust", "angle",
                                    "lineheight", "margin"),
                   element_line = c("colour", "color", "linewidth", "linetype", "lineend"),
                   element_rect = c("fill", "colour", "color", "linewidth", "linetype"),
                   element_blank = character(0),
                   margin = c("t", "r", "b", "l", "unit"), unit = c("x", "units"), rel = "x", c = "*",
                   guide_legend = c("title", "nrow", "ncol", "byrow", "reverse", "direction", "position"))
INNER_POSITIONAL_OK <- c("margin", "unit", "rel", "c")
TEXT_ARGS <- c("title", "subtitle", "caption", "x", "y", "label", "name")
COLOUR_ARGS <- c("colour", "color", "fill", "ink", "paper")
LINETYPES <- c("solid", "dashed", "dotted", "dotdash", "longdash", "twodash")
HELPER_RANGE <- list(line_width = c(0.2, 3), point_size = c(0.3, 6))
# why a function outside the vocabulary is refused, for the ones a model reaches for
WHY_NOT <- c(geom = "it would draw something the harness did not compute",
             stat = "it would compute something new", annotate = "it would write onto the figure",
             coord = "it would change the axes' ranges", xlim = "it would change the axes' ranges",
             ylim = "it would change the axes' ranges", lims = "it would change the axes' ranges",
             expand_limits = "it would change the axes' ranges",
             scale_x = "it would change an axis", scale_y = "it would change an axis",
             facet = "it would rearrange the data", aes = "it would change what is mapped to what")

problems <- list()
add <- function(code, detail) problems[[length(problems) + 1L]] <<- list(code = code, detail = detail)
oneline <- function(x) paste(deparse(x, width.cutoff = 200L), collapse = " ")

is_colour <- function(s) isTRUE(tryCatch({ grDevices::col2rgb(s); TRUE }, error = function(e) FALSE))
opaque <- function(s) isTRUE(tryCatch(grDevices::col2rgb(s, alpha = TRUE)[4, 1] == 255, error = function(e) FALSE))

check_string <- function(s, kind, msg, where) {
  if (is.na(s)) { add("value_not_allowed", paste0(where, ": NA")); return() }
  if (kind == "colour") {
    if (!is_colour(s)) add("not_a_colour", sprintf("%s: \"%s\" is not a colour R knows", where, s))
    else if (!opaque(s)) add("transparent_colour", sprintf("%s: \"%s\" is see-through; a curve or box in it could disappear", where, s))
    return()
  }
  if (kind == "palette") {
    known <- tryCatch(rownames(RColorBrewer::brewer.pal.info), error = function(e) character(0))
    if (!s %in% known)
      add("not_a_palette", sprintf("%s: \"%s\" is not a ColorBrewer palette (for example Set1, Dark2, Paired, Blues)", where, s))
    return()
  }
  if (kind == "linetype") {
    if (!s %in% LINETYPES)
      add("not_a_line_type", sprintf("%s: \"%s\" is not one of %s", where, s, paste(LINETYPES, collapse = ", ")))
    return()
  }
  if (nchar(s) > 120L) add("text_too_long", sprintf("%s: more than 120 characters", where))
  if (kind != "text" && grepl("[0-9]", s) && is_colour(s)) return()
  runs <- regmatches(s, gregexpr("[0-9]+(\\.[0-9]+)?", s))[[1]]
  bad <- runs[!vapply(runs, function(r) grepl(r, msg, fixed = TRUE), logical(1))]
  if (length(bad))
    add("number_in_text", sprintf("%s: \"%s\" contains %s, which the analyst did not write; a figure's text may carry no number of its own",
                                  where, s, paste(unique(bad), collapse = ", ")))
}

walk <- function(x, kind, msg, where) {
  if (is.character(x)) { for (s in x) check_string(s, kind, msg, where); return() }
  if (is.logical(x) || is.null(x)) return()
  if (is.numeric(x)) {
    if (any(!is.finite(x))) add("value_not_allowed", paste0(where, ": not a finite number"))
    return()
  }
  if (is.symbol(x)) {
    add("name_not_allowed", sprintf("%s: `%s` -- the code can use no name but `p` at its start, the functions listed and plain values",
                                    where, as.character(x)))
    return()
  }
  if (!is.call(x)) { add("value_not_allowed", sprintf("%s: %s", where, oneline(x))); return() }
  if (!is.symbol(x[[1]])) { add("function_not_allowed", sprintf("%s: %s", where, oneline(x[[1]]))); return() }
  fn <- as.character(x[[1]])
  a <- as.list(x)[-1]
  if (fn == "-" && length(a) == 1L && is.numeric(a[[1]])) return()
  if (!fn %in% names(INNER_ARGS)) { refuse_fun(fn, where); return() }
  nms <- names(a); if (is.null(nms)) nms <- rep("", length(a))
  allowed <- INNER_ARGS[[fn]]
  for (i in seq_along(a)) {
    if (!nzchar(nms[i]) && !fn %in% INNER_POSITIONAL_OK) {
      add("argument_unnamed", sprintf("%s: give every argument of %s() its name (%s)", where, fn,
                                      paste(allowed, collapse = ", ")))
      next
    }
    if (!identical(allowed, "*") && nzchar(nms[i]) && !nms[i] %in% allowed) {
      add("argument_not_allowed", sprintf("%s: %s(%s = ...) -- %s() takes only %s; anything else would be ignored and the figure would not change",
                                          where, fn, nms[i], fn, paste(allowed, collapse = ", ")))
      next
    }
    k <- if (nms[i] %in% COLOUR_ARGS) "colour" else if (fn == "c") kind else
         if (fn == "guide_legend" && nms[i] == "title") "text" else "any"
    walk(a[[i]], k, msg, paste0(where, " > ", fn, if (nzchar(nms[i])) paste0("(", nms[i], ")") else ""))
  }
}

refuse_fun <- function(fn, where) {
  hit <- names(WHY_NOT)[vapply(names(WHY_NOT), function(w) startsWith(fn, w), logical(1))]
  why <- if (length(hit)) WHY_NOT[[hit[1]]] else "it is not one of the style functions this system runs"
  add("function_not_allowed", sprintf("%s: %s() is not allowed: %s", where, fn, why))
}

# the parts of the figure a manual scale can name, by the aesthetic the groups are told apart by
mapped_aes <- function(meta) if (identical(meta$kind, "splits_boxplot")) "fill" else c("colour", "linetype")
aes_of <- function(fn) {
  if (grepl("^scale_(colour|color)_", fn)) return("colour")
  if (grepl("^scale_fill_", fn)) return("fill")
  if (grepl("^scale_linetype_", fn)) return("linetype")
  NA_character_
}

check_term <- function(term, msg, meta, where) {
  if (!is.call(term) || !is.symbol(term[[1]])) {
    add("not_a_style_term", sprintf("%s: %s is not a call to a style function", where, oneline(term)))
    return()
  }
  fn <- as.character(term[[1]])
  if (!fn %in% names(STYLE_ARGS)) { refuse_fun(fn, where); return() }
  a <- as.list(term)[-1]
  nms <- names(a); if (is.null(nms)) nms <- rep("", length(a))
  allowed <- STYLE_ARGS[[fn]]
  ae <- aes_of(fn)
  if (!is.na(ae) && !ae %in% mapped_aes(meta))
    add("no_such_scale", sprintf("%s: %s() changes the %s, but this figure tells its groups apart by %s",
                                 where, fn, ae, paste(mapped_aes(meta), collapse = " and ")))
  groups <- unlist(meta$groups)
  for (i in seq_along(a)) {
    nm <- nms[i]
    if (!nzchar(nm) && !fn %in% POSITIONAL_OK) {
      add("argument_unnamed", sprintf("%s: give every argument of %s() its name (for example values = ...)", where, fn))
      next
    }
    if (!identical(allowed, "*") && nzchar(nm) && !nm %in% allowed) {
      add("argument_not_allowed", sprintf("%s: %s(%s = ...) -- %s() takes only %s here", where, fn, nm, fn,
                                          paste(allowed, collapse = ", ")))
      next
    }
    if (fn == "theme" && length(THEME_ELEMENTS) && !nm %in% THEME_ELEMENTS) {
      add("argument_not_allowed", sprintf(paste0(
        "%s: theme(%s = ...) -- %s is not a part of the theme, so it would be ignored. The font size of ",
        "everything is theme_bw(base_size = 14) or theme(text = element_text(size = 14)); the font is ",
        "theme(text = element_text(family = 'serif')); the legend's title is labs(colour = '...')"), where, nm, nm))
      next
    }
    if (fn %in% names(HELPER_RANGE)) {
      v <- a[[i]]
      r <- HELPER_RANGE[[fn]]
      if (!is.numeric(v) || length(v) != 1L || !is.finite(v) || v < r[1] || v > r[2])
        add("value_not_allowed", sprintf("%s: %s() takes one number from %s to %s", where, fn, r[1], r[2]))
      next
    }
    if (fn == "guides") {
      v <- a[[i]]
      if (is.character(v)) {
        if (!all(v %in% c("legend", "none")))
          add("value_not_allowed", sprintf("%s: guides(%s = ...) takes \"legend\", \"none\" or guide_legend(...)", where, nm))
      } else walk(v, "any", msg, paste0(where, " > guides(", nm, ")"))
      next
    }
    kind <- if (fn %in% c("labs", "ggtitle", "xlab", "ylab") || nm %in% c("name")) "text" else
            if (nm == "palette") "palette" else
            if (nm == "values" && identical(ae, "linetype")) "linetype" else
            if (nm == "values") "colour" else
            if (nm %in% COLOUR_ARGS) "colour" else "any"
    if (nm == "values") {
      v <- a[[i]]
      vals <- if (is.call(v) && identical(v[[1]], as.name("c"))) as.list(v)[-1] else list(v)
      vn <- names(vals)
      if (!is.null(vn) && any(nzchar(vn))) {
        unknown <- setdiff(vn[nzchar(vn)], groups)
        if (length(unknown))
          add("unknown_group", sprintf("%s: %s names %s, but the figure's groups are %s", where, fn,
                                       paste0("\"", unknown, "\"", collapse = ", "),
                                       paste0("\"", groups, "\"", collapse = ", ")))
        missing <- setdiff(groups, vn)
        if (length(missing))
          add("group_left_out", sprintf("%s: %s leaves out %s; name a value for every group", where, fn,
                                        paste0("\"", missing, "\"", collapse = ", ")))
      } else if (length(vals) < length(groups)) {
        add("too_few_values", sprintf("%s: %s has %d value(s) for %d groups", where, fn, length(vals), length(groups)))
      }
    }
    walk(a[[i]], kind, msg, paste0(where, " > ", fn, if (nzchar(nm)) paste0("(", nm, ")") else ""))
  }
}

# "p + a + b" -> list(a, b); NULL (and a problem) when it is not that shape
chain_terms <- function(code, where) {
  ex <- tryCatch(parse(text = code, keep.source = FALSE), error = function(e) e)
  if (inherits(ex, "error")) {
    add("not_valid_r", sprintf("%s: %s (write every string in single quotes, 'like this': a double quote can end the code early)",
                               where, gsub("\\s+", " ", conditionMessage(ex))))
    return(NULL)
  }
  if (length(ex) != 1L) {
    add("not_one_expression", sprintf("%s: write one expression, `p + ...`, and nothing else", where))
    return(NULL)
  }
  e <- ex[[1]]
  terms <- list()
  while (is.call(e) && identical(e[[1]], as.name("+")) && length(e) == 3L) {
    terms <- c(list(e[[3]]), terms)
    e <- e[[2]]
  }
  if (!identical(e, as.name("p"))) {
    add("must_start_with_p", sprintf("%s: the code must be `p` followed by `+` terms, for example p + theme_minimal()", where))
    return(NULL)
  }
  if (!length(terms)) {
    add("no_change", sprintf("%s: `p` alone changes nothing", where))
    return(NULL)
  }
  terms
}

# ---- gate 2: run it, with nothing in reach but the style functions --------------------------------
sandbox <- local({
  env <- new.env(parent = emptyenv())
  for (f in setdiff(c(names(STYLE_ARGS), names(INNER_ARGS)), c("line_width", "point_size", "unit", "c")))
    assign(f, getExportedValue("ggplot2", f), envir = env)
  assign("unit", grid::unit, envir = env)
  assign("c", base::c, envir = env)
  assign("-", base::`-`, envir = env)
  env
})

apply_terms <- function(p, terms, roles, where) {
  for (t in terms) {
    fn <- as.character(t[[1]])
    r <- tryCatch({
      if (fn %in% c("line_width", "point_size")) fig_set_size(p, roles, fn, eval(t[[2]], sandbox))
      else p + eval(t, envir = sandbox)
    }, error = function(e) e)
    if (inherits(r, "error")) {
      add("did_not_run", sprintf("%s: %s gave the error: %s", where, oneline(t), gsub("\\s+", " ", conditionMessage(r))))
      return(NULL)
    }
    p <- r
  }
  p
}

# ---- gate 3: what the figure shows -------------------------------------------------------------
POS <- FIG_POS_COLS_CHECK <- c("x", "y", "ymin", "ymax", "xmin", "xmax", "xend", "yend", "xintercept",
                               "yintercept", "lower", "upper", "middle", "xlower", "xupper", "xmiddle",
                               "group", "PANEL", "label", "outliers", "flipped_aes")
shown <- function(p) {
  b <- ggplot_build(p)
  list(b = b,
       data = lapply(b$data, function(d) { d <- as.data.frame(d)[, intersect(POS, names(d)), drop = FALSE]; rownames(d) <- NULL; d }),
       ranges = lapply(b$layout$panel_params, function(pp) list(x = pp$x.range, y = pp$y.range)),
       geoms = vapply(p$layers, function(l) class(l$geom)[1], ""))
}
legend_labels <- function(b, ae) {
  sc <- b$plot$scales$get_scales(ae)
  if (is.null(sc)) return(NULL)
  as.character(unlist(sc$get_labels()))
}
has_legend <- function(p) {
  g <- ggplotGrob(p)
  i <- grep("^guide-box", g$layout$name)
  length(i) > 0L && any(!vapply(g$grobs[i], function(x) inherits(x, "zeroGrob"), logical(1)))
}
luminance <- function(col) {
  v <- grDevices::col2rgb(col)[, 1] / 255
  v <- ifelse(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055)^2.4)
  sum(c(0.2126, 0.7152, 0.0722) * v)
}
contrast <- function(a, b) { la <- luminance(a); lb <- luminance(b); (max(la, lb) + 0.05) / (min(la, lb) + 0.05) }

UNITS <- c("second", "minute", "hour", "day", "week", "month", "year")
units_in <- function(s) UNITS[vapply(UNITS, function(u) grepl(u, tolower(s %||% ""), fixed = TRUE), logical(1))]

# An axis title says what the axis shows. Time keeps its units: a title in years over follow-up in
# days mislabels every number on the axis. The y axis shows the proportion without the event, never
# its complement.
check_titles <- function(p0, p1, msg) {
  l0 <- fig_labels(p0); l1 <- fig_labels(p1)
  u0 <- units_in(l0$x); u1 <- units_in(l1$x)
  if (length(u1) && !identical(l1$x, l0$x)) {
    if (length(u0) && !all(u1 %in% u0))
      add("axis_title_unit", sprintf("the x axis title \"%s\" speaks of %s, but the follow-up is in the units of the column it was drawn from (\"%s\"); a title cannot change the units of the numbers on the axis",
                                     l1$x, paste0(u1, "s", collapse = " and "), l0$x))
    else if (!length(u0) && !all(vapply(u1, function(u) grepl(u, tolower(msg), fixed = TRUE), logical(1))))
      add("axis_title_unit", sprintf("the x axis title \"%s\" names a unit of time the analyst did not write", l1$x))
  }
  y1 <- tolower(l1$y %||% "")
  if (!identical(l1$y, l0$y) && grepl("mortality|incidence|hazard|death rate|risk of death|probability of death|cumulative risk|probability of the event", y1))
    add("axis_title_meaning", sprintf("the y axis shows the proportion without the event; \"%s\" would describe something else", l1$y))
}

# whether two figures would look exactly the same (drawn small and compared byte for byte)
same_look <- function(a, b) {
  fa <- tempfile(fileext = ".png"); fb <- tempfile(fileext = ".png")
  draw <- function(p, f) {
    grDevices::png(f, width = 5, height = 4, units = "in", res = 60,
                   type = if (isTRUE(capabilities("cairo"))) "cairo" else getOption("bitmapType"))
    print(p); invisible(grDevices::dev.off())
  }
  suppressWarnings({ draw(a, fa); draw(b, fb) })
  identical(unname(tools::md5sum(fa)), unname(tools::md5sum(fb)))
}

compare <- function(p0, p1, meta) {
  s0 <- shown(p0); s1 <- shown(p1)
  if (!identical(s0$geoms, s1$geoms)) {
    add("layers_changed", "the figure's layers are not the ones the harness drew")
  } else {
    for (i in seq_along(s0$data)) {
      d0 <- s0$data[[i]]; d1 <- s1$data[[i]]
      same <- identical(names(d0), names(d1)) && nrow(d0) == nrow(d1) &&
        isTRUE(all.equal(d0, d1, check.attributes = FALSE, tolerance = 1e-12))
      if (!same) add("data_changed", sprintf("what layer %d (%s) draws has changed", i, meta$layers[[i]]))
    }
  }
  if (!isTRUE(all.equal(s0$ranges, s1$ranges, tolerance = 1e-12)))
    add("axis_range_changed", "the range of an axis has changed")
  for (ae in mapped_aes(meta)) {
    l0 <- legend_labels(s0$b, ae); l1 <- legend_labels(s1$b, ae)
    if (!identical(l0, l1))
      add("legend_labels_changed", sprintf("the legend's labels for the %s are no longer the figure's groups", ae))
  }
  th <- complete_theme(p1$theme)
  blank <- function(el) inherits(calc_element(el, th), "element_blank")
  for (el in c("axis.text.x.bottom", "axis.text.y.left"))
    if (blank(el)) add("axis_hidden", sprintf("%s is blank: the axis would have no numbers on it", el))
  for (el in c("axis.title.x.bottom", "axis.title.y.left"))
    if (blank(el)) add("axis_hidden", sprintf("%s is blank: the axis would not say what it measures", el))
  legend0 <- has_legend(p0)
  if (legend0 && !has_legend(p1)) add("legend_removed", "the legend that tells the groups apart is gone")
  if (legend0 && blank("legend.text")) add("legend_removed", "the legend's labels are blank")
  for (el in c("axis.text.x.bottom", "axis.text.y.left", "axis.title.x.bottom", "axis.title.y.left",
               if (legend0) "legend.text")) {
    e <- calc_element(el, th)
    if (!inherits(e, "element_blank") && is.numeric(e$size) && e$size < 6)
      add("text_too_small", sprintf("%s would be %.1f points; the smallest is 6", el, e$size))
  }
  groups <- unlist(meta$groups)
  if (identical(meta$kind, "splits_boxplot")) {
    f <- fig_colours(p1, groups, "fill")
    if (length(unique(tolower(f))) < length(groups))
      add("groups_look_the_same", "the CV-selected box would no longer stand out from the others")
  } else {
    cols <- fig_colours(p1, groups, "colour")
    lts <- fig_colours(p1, groups, "linetype")
    if (length(groups) > 1L && anyDuplicated(paste(tolower(cols), lts)))
      add("groups_look_the_same", "two groups would be drawn in the same colour and line type")
    bg <- calc_element("panel.background", th)
    bgc <- if (inherits(bg, "element_blank") || is.null(bg$fill) || is.na(bg$fill)) {
      pb <- calc_element("plot.background", th)
      if (inherits(pb, "element_blank") || is.null(pb$fill) || is.na(pb$fill)) "white" else pb$fill
    } else bg$fill
    for (g in groups) if (is_colour(cols[[g]]) && is_colour(bgc) && contrast(cols[[g]], bgc) < 1.5)
      add("curve_invisible", sprintf("the curve of \"%s\" (%s) would hardly show against the background (%s)", g, cols[[g]], bgc))
  }
}

# what changed, in words, for the reply
CHANGE_WORDS <- function(fn) {
  if (fn %in% THEMES) return(sprintf("the overall look (%s)", fn))
  if (fn == "theme") return("details of the look (fonts, legend, background)")
  if (fn %in% c("labs", "ggtitle", "xlab", "ylab")) return("titles and labels")
  if (grepl("^scale_linetype", fn)) return("the line types")
  if (grepl("^scale_", fn)) return("the colours")
  if (fn == "guides") return("the legend")
  if (fn == "line_width") return("the line width")
  if (fn == "point_size") return("the size of the censoring marks")
  fn
}

style_script <- function(fig, steps, terms_by_step, rds, out_base) {
  head <- c("#!/usr/bin/env Rscript",
            sprintf("# %s.style.R - redraws \"%s\" with the changes the analyst asked for.", basename(out_base), fig$meta$title),
            "#",
            "# Written by the BregSurv agent. The language model wrote the restyle lines below; the harness checked",
            "# them before they were used: every curve, mark and box, the axes' ranges and the legend's labels are",
            "# exactly as the harness drew them, so only the look has changed. Run it in the folder that holds",
            sprintf("# %s; it needs R with ggplot2 and cowplot, and writes %s.png and %s.pdf.", basename(rds), basename(out_base), basename(out_base)),
            "", "## ---- the harness's figure code (figure_lib.R, copied) ----")
  body <- c("", "## ---- the restyles, in order ----",
            sprintf("fig <- readRDS(\"%s\")", basename(rds)), "p <- fig$main")
  for (j in seq_along(steps)) {
    m <- gsub("[\r\n]+", " ", substr(as.character(steps[[j]]$message %||% ""), 1L, 200L))
    body <- c(body, sprintf("# restyle %d, asked for in: \"%s\"", j, m))
    for (t in terms_by_step[[j]]) {
      fn <- as.character(t[[1]])
      body <- c(body, if (fn %in% c("line_width", "point_size"))
        sprintf("p <- fig_set_size(p, fig$meta$layers, \"%s\", %s)", fn, oneline(t[[2]])) else
        sprintf("p <- p + %s", oneline(t)))
    }
  }
  if (!identical(fig$meta$kind, "splits_boxplot"))
    body <- c(body, "p <- fig_sync_legends(fig$main, p)   # colour and line type keep one legend")
  body <- c(body, "fig$main <- p", sprintf("fig_render(fig, \"%s\")", basename(out_base)))
  c(head, readLines(LIB), body)
}

`%||%` <- function(a, b) if (is.null(a)) b else a

res <- tryCatch({
  input <- fromJSON(input_path, simplifyVector = FALSE)
  fig <- readRDS(input$figure_rds)
  meta <- fig$meta
  steps <- input$steps
  if (!length(steps)) stop("no restyle to apply")
  p0 <- fig$main
  terms_by_step <- vector("list", length(steps))
  for (j in seq_along(steps)) {
    where <- if (j == length(steps)) "the new code" else sprintf("restyle %d", j)
    tt <- chain_terms(as.character(steps[[j]]$code), where)
    if (is.null(tt)) next
    for (t in tt) check_term(t, as.character(steps[[j]]$message %||% ""), meta, where)
    terms_by_step[[j]] <- tt
  }
  p1 <- NULL; p_prev <- NULL
  survival_fig <- !identical(meta$kind, "splits_boxplot")
  # every version is built from its own copy of the figure: a layer is an environment, and a change
  # to one copy's layer must not reach the figure it is compared with
  fresh <- function() readRDS(input$figure_rds)$main
  p0 <- fresh()
  if (!length(problems)) {
    n <- length(steps)
    p_prev <- fresh()
    for (j in seq_len(n - 1L)) {
      p_prev <- apply_terms(p_prev, terms_by_step[[j]], unlist(meta$layers), sprintf("restyle %d", j))
      if (is.null(p_prev)) break
    }
    if (!is.null(p_prev)) {
      p1 <- fresh()
      for (j in seq_len(n)) {
        p1 <- apply_terms(p1, terms_by_step[[j]], unlist(meta$layers),
                          if (j == n) "the new code" else sprintf("restyle %d", j))
        if (is.null(p1)) break
      }
    }
  }
  if (!length(problems) && !is.null(p1) && survival_fig) {
    p1 <- fig_sync_legends(p0, p1); p_prev <- fig_sync_legends(p0, p_prev)
  }
  if (!length(problems) && !is.null(p1)) compare(p0, p1, meta)
  if (!length(problems) && !is.null(p1) && survival_fig)
    check_titles(p0, p1, as.character(steps[[length(steps)]]$message %||% ""))
  if (!length(problems) && !is.null(p1) && same_look(p_prev, p1))
    add("no_effect", paste0("the new code leaves the figure looking exactly as it is now: either the figure ",
                            "already looks the way the code sets it (then the request needs no change: write ",
                            "an empty code), or the code sets something this figure does not show; a change ",
                            "already made needs no repeating"))
  if (length(problems)) {
    list(status = "rejected", problems = problems)
  } else {
    changes <- unique(vapply(terms_by_step[[length(steps)]], function(t) CHANGE_WORDS(as.character(t[[1]])), ""))
    groups <- unlist(meta$groups)
    main_aes <- if (identical(meta$kind, "splits_boxplot")) "fill" else "colour"
    current <- list(colours = as.list(fig_colours(p1, groups, main_aes)), labels = fig_labels(p1))
    if (!identical(meta$kind, "splits_boxplot"))
      current$linetypes <- as.list(fig_colours(p1, groups, "linetype"))
    out <- list(status = "ok", changes = as.list(changes), current = current)
    if (isTRUE(input$render)) {
      fig$main <- p1
      files <- fig_render(fig, input$out_base)
      style_r <- paste0(input$out_base, ".style.R")
      writeLines(style_script(fig, steps, terms_by_step, input$figure_rds, input$out_base), style_r)
      out <- c(out, list(png = files$png, pdf = files$pdf, style_r = style_r))
    }
    out
  }
}, error = function(err) list(status = "error", reason = conditionMessage(err)))
writeLines(toJSON(res, auto_unbox = TRUE, null = "null", digits = NA), output_path)
