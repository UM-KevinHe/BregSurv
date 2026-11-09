#' Composite-Likelihood Cox Model with a Ridge Penalty (Individual-Level External Data)
#'
#' @description
#' Fits the composite-likelihood Cox model of \code{\link{cox_indi}}, in which the
#' internal rows carry weight 1 and the rows of an external individual-level cohort
#' carry weight \eqn{\eta}, with a ridge (L2) penalty on the coefficients, over a path
#' of penalty values for each \eqn{\eta}.
#'
#' @details
#' For each \eqn{\eta} the function maximises
#' on the per-observation scale of the ridge family, i.e.
#' \eqn{[\ell_{int}(\beta) + \eta\,\ell_{ext}(\beta)] / n_{eff} - \tfrac{1}{2}\lambda\|\beta\|_2^2}
#' with \eqn{n_{eff}} the larger of the total weight and the number of rows (the denominator
#' of \code{\link{cox_indi_enet}}), by Newton--Raphson with step halving, along a decreasing \eqn{\lambda} path with warm
#' starts. The two cohorts sit in strata of their own, so no risk set mixes them. The
#' penalty is applied on the scale of the standardised design when
#' \code{standardize = TRUE} (scaling by the standard deviation of the stacked design,
#' no centering), and the coefficients are returned on the original scale. At
#' \eqn{\lambda = 0} the fit is the one of \code{\link{cox_indi}}.
#'
#' @param z_int,delta_int,time_int,stratum_int Internal covariate matrix, event
#'   indicator, observed times and optional strata.
#' @param z_ext,delta_ext,time_ext,stratum_ext The same for the external cohort, with
#'   the same covariates in the same column order.
#' @param etas Non-negative weights of the external rows.
#' @param lambda Optional ridge penalty values. If \code{NULL}, a path of
#'   \code{nlambda} values is generated for each \eqn{\eta}, ending at 0.
#' @param nlambda Number of penalty values when \code{lambda} is \code{NULL}. Default 100.
#' @param penalty.factor Numeric in \code{[0, 1)}; the largest penalty of the generated
#'   path is the null-model score divided by \code{1 - penalty.factor}, as for
#'   \code{\link{coxkl_ridge}}. Default 0.999.
#' @param standardize Logical. Scale the stacked design to unit standard deviation
#'   before penalising. Default \code{TRUE}.
#' @param tol,max_iter Convergence tolerance on the Newton step and the iteration limit.
#' @param message Logical. Print a progress bar.
#' @param ties \code{"none"} or \code{"breslow"}, as in \code{\link{cox_indi}}.
#'
#' @return An object of class \code{"cox_indi_ridge"}: \code{eta} (the weights),
#'   \code{lambda} (a list, one penalty path per \eqn{\eta}), \code{beta} (a list of
#'   \eqn{p \times L} coefficient matrices on the original scale),
#'   \code{linear.predictors_int} (a list of \eqn{n_{int} \times L} matrices in the
#'   caller's row order), \code{ties} and \code{data}.
#'
#' @examples
#' \dontrun{
#' data(ExampleData_indi)
#' fit <- cox_indi_ridge(
#'   z_int = ExampleData_indi$internal$z, delta_int = ExampleData_indi$internal$status,
#'   time_int = ExampleData_indi$internal$time,
#'   z_ext = ExampleData_indi$external$z, delta_ext = ExampleData_indi$external$status,
#'   time_ext = ExampleData_indi$external$time,
#'   etas = c(0, 0.5, 1))
#' }
#' @export
cox_indi_ridge <- function(z_int, delta_int, time_int, stratum_int = NULL,
                           z_ext, delta_ext, time_ext, stratum_ext = NULL,
                           etas, lambda = NULL, nlambda = 100, penalty.factor = 0.999,
                           standardize = TRUE, tol = 1.0e-7, max_iter = 100,
                           message = FALSE, ties = c("none", "breslow")) {
  ties <- .check_ties(match.arg(ties))

  z_int <- as.matrix(z_int); z_ext <- as.matrix(z_ext)
  delta_int <- .check_event(delta_int, "delta_int")
  delta_ext <- .check_event(delta_ext, "delta_ext")
  time_int <- as.numeric(time_int); time_ext <- as.numeric(time_ext)
  n_int <- nrow(z_int); n_ext <- nrow(z_ext); p <- ncol(z_int)
  if (ncol(z_ext) != p)
    stop("Internal and external datasets must have the same number of covariates (columns).", call. = FALSE)
  if (is.null(etas)) stop("etas must be provided.", call. = FALSE)
  etas <- sort(as.numeric(etas)); check_etas(etas)
  if (penalty.factor < 0 || penalty.factor >= 1) stop("penalty.factor must be in [0, 1).", call. = FALSE)
  if (is.null(lambda) && (nlambda < 2 || nlambda != round(nlambda)))
    stop("nlambda must be an integer of at least 2.", call. = FALSE)
  if (!is.null(lambda) && any(!is.finite(lambda) | lambda < 0))
    stop("lambda must be finite and non-negative.", call. = FALSE)

  if (is.null(stratum_int)) stratum_int <- rep(1, n_int)
  if (is.null(stratum_ext)) stratum_ext <- rep(1, n_ext)
  s_int <- as.numeric(match(as.vector(stratum_int), unique(as.vector(stratum_int))))
  s_ext <- as.numeric(match(as.vector(stratum_ext), unique(as.vector(stratum_ext)))) + max(s_int)
  ord_int <- order(s_int, time_int); ord_ext <- order(s_ext, time_ext)

  z_all <- rbind(z_int[ord_int, , drop = FALSE], z_ext[ord_ext, , drop = FALSE])
  delta_all <- c(delta_int[ord_int], delta_ext[ord_ext])
  time_all <- c(time_int[ord_int], time_ext[ord_ext])
  stratum_all <- c(s_int[ord_int], s_ext[ord_ext])
  n_each <- as.numeric(table(stratum_all))
  tm <- .tie_maps(time_all, n_each, ties)
  tf <- if (is.null(tm)) NULL else tm$first

  ## scaling only, no centering (the 1.2.0 rule of the ridge family)
  std_scale <- rep(1, p)
  if (isTRUE(standardize)) {
    std_scale <- apply(z_all, 2, function(v) sqrt(sum((v - mean(v))^2) / length(v)))
    std_scale[!is.finite(std_scale) | std_scale <= 1e-6] <- 1
  }
  z_fit <- sweep(z_all, 2, std_scale, "/")

  ends <- cumsum(n_each); starts <- ends - n_each + 1
  pen_loglik <- function(b, w, lam) {
    ne <- max(sum(w), nrow(z_fit))
    th <- as.numeric(z_fit %*% b); ex <- exp(th); S0 <- numeric(length(th))
    for (s in seq_along(n_each)) { idx <- starts[s]:ends[s]; S0[idx] <- rev(cumsum(rev(ex[idx]))) }
    if (!is.null(tf)) S0 <- S0[tf + 1L]
    sum(w * delta_all * (th - log(S0))) / ne - 0.5 * lam * sum(b^2)
  }
  newton <- function(b, w, lam) {
    f0 <- pen_loglik(b, w, lam)
    ne <- max(sum(w), nrow(z_fit))   # the per-observation scale of the ridge family
    for (it in seq_len(max_iter)) {
      d <- ddloglik_indi(z_fit, delta_all, b, w, n_each, tie_first = tf)
      g <- as.numeric(d$L1) / ne - lam * b
      H <- d$L2 / ne; diag(H) <- diag(H) + lam
      step <- tryCatch(as.numeric(solve(H, g)), error = function(e) NULL)
      if (is.null(step) || any(!is.finite(step))) stop("Hessian solve failed.", call. = FALSE)
      ## step halving: the penalised log-likelihood must not fall
      a <- 1; b_new <- b + step; f_new <- pen_loglik(b_new, w, lam)
      while ((!is.finite(f_new) || f_new < f0 - 1e-10) && a > 1e-4) {
        a <- a / 2; b_new <- b + a * step; f_new <- pen_loglik(b_new, w, lam)
      }
      b <- b_new; f0 <- f_new
      if (max(abs(a * step)) < tol) break
    }
    b
  }

  n_eta <- length(etas)
  beta_list <- lambda_list <- lp_list <- vector("list", n_eta)
  names(beta_list) <- names(lambda_list) <- names(lp_list) <- round(etas, 6)
  if (message) pb <- utils::txtProgressBar(min = 0, max = n_eta, style = 3, width = 30)

  for (i in seq_along(etas)) {
    w <- c(rep(1, n_int), rep(etas[i], n_ext))
    if (is.null(lambda)) {
      g0 <- as.numeric(ddloglik_indi(z_fit, delta_all, rep(0, p), w, n_each, tie_first = tf)$L1)
      lmax <- max(abs(g0)) / max(sum(w), nrow(z_fit)) / (1 - penalty.factor)
      lam_seq <- c(exp(seq(log(lmax), log(1e-7 * lmax), length.out = nlambda - 1)), 0)
    } else {
      lam_seq <- sort(as.numeric(lambda), decreasing = TRUE)
    }
    B <- matrix(NA_real_, p, length(lam_seq))
    b <- rep(0, p)
    for (j in seq_along(lam_seq)) {
      b <- newton(b, w, lam_seq[j])
      B[, j] <- b
    }
    B <- B / std_scale
    rownames(B) <- colnames(z_int); colnames(B) <- round(lam_seq, 6)
    lp_s <- z_int[ord_int, , drop = FALSE] %*% B
    lp <- matrix(NA_real_, n_int, length(lam_seq)); lp[ord_int, ] <- lp_s
    beta_list[[i]] <- B; lambda_list[[i]] <- lam_seq; lp_list[[i]] <- lp
    if (message) utils::setTxtProgressBar(pb, i)
  }
  if (message) close(pb)

  structure(list(
    eta = etas, lambda = lambda_list, beta = beta_list,
    linear.predictors_int = lp_list, ties = ties,
    data = list(z_int = z_int, delta_int = delta_int, time_int = time_int, stratum_int = stratum_int,
                z_ext = z_ext, delta_ext = delta_ext, time_ext = time_ext, stratum_ext = stratum_ext)
  ), class = "cox_indi_ridge")
}
