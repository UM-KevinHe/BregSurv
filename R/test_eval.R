#' Evaluate Survival Model Performance
#'
#' Computes predictive performance metrics for stratified or unstratified Cox models.
#' Supports Loss, C-index, Integrated Brier Score (IBS), and Time-Dependent AUC (tdAUC).
#'
#' @param test_z Matrix of predictors for the test set.
#' @param test_delta Numeric vector of event indicators (1 for event, 0 for censored).
#' @param test_time Numeric vector of observed times.
#' @param betahat Numeric vector of estimated coefficients.
#' @param test_stratum Vector indicating strata for test subjects. Defaults to NULL (single stratum).
#' @param train_baseline_obj A list containing the baseline hazard function (typically from \code{get_baseline_hazard}).
#' Required only when \code{criteria = "IBS"}.
#' @param criteria Metric to calculate: "loss" (Log-Partial Likelihood), "CIndex" (Concordance Index),
#' "IBS" (Integrated Brier Score), or "tdAUC" (Integrated Time-Dependent AUC).
#'
#' @details
#' For "IBS", the function predicts survival probabilities and converts them to risk (1 - S).
#' If \code{riskRegression} fails to provide a pre-computed IBS, the function manually integrates
#' the Brier score using the trapezoidal rule.
#'
#' @return A numeric value representing the performance metric.
#' Returns \code{NA} if the metric cannot be computed (e.g., no events in test set).
#'
#' @importFrom riskRegression Score
#' @importFrom survival Surv
#' @importFrom stats approxfun plnorm plogis pnorm qnorm rbinom relevel rexp rlnorm rnorm rpois runif rweibull
#' @importFrom utils head tail
#'
#' @keywords internal
#' @export
test_eval <- function(test_z, test_delta, test_time,
                      betahat, test_stratum = NULL,
                      train_baseline_obj = NULL,
                      criteria = c("loss", "CIndex", "IBS", "tdAUC")) {

  criteria <- match.arg(criteria)

  test_RS <- as.vector(as.matrix(test_z) %*% as.matrix(betahat))
  d_test <- data.frame(time = as.numeric(test_time), status = as.numeric(test_delta))
  n <- nrow(d_test)
  if (is.null(test_stratum)) test_stratum <- rep(1, n)

  if (criteria == "loss") {
    ord <- order(test_stratum, d_test$time)
    return(-2 * pl_cal_theta(test_RS[ord], d_test$status[ord], as.numeric(table(test_stratum))) / n)
  }

  if (criteria == "CIndex") {
    return(c_stat_stratcox(d_test$time, test_RS, test_stratum, d_test$status)$c_statistic)
  }

  eval_times_all <- sort(unique(d_test$time[d_test$status == 1]))
  if (length(eval_times_all) < 2L) return(NA_real_)

  if (criteria == "IBS") {
    if (is.null(train_baseline_obj)) return(NA_real_)

    S_mat <- predict_surv_prob(
      test_RS = test_RS,
      eval_times = eval_times_all,
      train_baseline_obj = train_baseline_obj,
      test_stratum = test_stratum
    )
    risk_mat <- 1 - S_mat
    risk_mat <- as.matrix(risk_mat)
    colnames(risk_mat) <- as.character(eval_times_all)

    unique_strata <- sort(unique(test_stratum))
    ibs_vals <- numeric(length(unique_strata))
    weights <- numeric(length(unique_strata))

    for (k in seq_along(unique_strata)) {
      s <- unique_strata[k]
      idx <- which(test_stratum == s)

      if (length(idx) < 2L || all(d_test$status[idx] == 0)) {
        ibs_vals[k] <- NA_real_
        weights[k] <- 0
        next
      }

      d_s <- d_test[idx, , drop = FALSE]

      ev_times_s <- d_s$time[d_s$status == 1]
      if (length(ev_times_s) == 0L) {
        ibs_vals[k] <- NA_real_
        weights[k] <- 0
        next
      }

      min_ev_s <- min(ev_times_s, na.rm = TRUE)
      max_t_s <- max(d_s$time, na.rm = TRUE)

      times_s <- eval_times_all[eval_times_all >= min_ev_s & eval_times_all <= max_t_s]
      if (length(times_s) < 2L) {
        ibs_vals[k] <- NA_real_
        weights[k] <- 0
        next
      }

      col_idx <- match(as.character(times_s), colnames(risk_mat))
      if (any(is.na(col_idx))) {
        ibs_vals[k] <- NA_real_
        weights[k] <- 0
        next
      }

      risk_s <- risk_mat[idx, col_idx, drop = FALSE]
      risk_s <- as.matrix(risk_s)
      colnames(risk_s) <- as.character(times_s)

      keep <- is.finite(d_s$time) & !is.na(d_s$status) & apply(is.finite(risk_s), 1, all)
      if (sum(keep) < 2L || all(d_s$status[keep] == 0)) {
        ibs_vals[k] <- NA_real_
        weights[k] <- 0
        next
      }

      d_s2 <- d_s[keep, , drop = FALSE]
      risk_s2 <- risk_s[keep, , drop = FALSE]

      score_res_s <- riskRegression::Score(
        object  = list(MyModel = risk_s2),
        formula = Surv(time, status) ~ 1,
        data    = d_s2,
        times   = times_s,
        metrics = "brier",
        summary = "ibs"
      )

      bsum <- as.data.frame(score_res_s$Brier$summary)
      if (nrow(bsum) > 0 && "IBS" %in% colnames(bsum)) {
        ibs_vals[k] <- bsum[bsum$model == "MyModel", "IBS"]
        weights[k] <- nrow(d_s2)
      } else {
        bsc <- as.data.frame(score_res_s$Brier$score)
        bsc <- bsc[bsc$model == "MyModel", , drop = FALSE]
        if (nrow(bsc) >= 2) {
          tcol <- if ("times" %in% names(bsc)) "times" else if ("time" %in% names(bsc)) "time" else NA_character_
          if (is.na(tcol) || !"Brier" %in% names(bsc)) {
            ibs_vals[k] <- NA_real_
            weights[k] <- 0
          } else {
            x <- as.numeric(bsc[[tcol]])
            y <- as.numeric(bsc[["Brier"]])
            ord <- order(x)
            x <- x[ord]; y <- y[ord]
            if (length(x) >= 2 && max(x) > min(x)) {
              ibs_vals[k] <- sum(diff(x) * (head(y, -1) + tail(y, -1)) / 2) / (max(x) - min(x))
              weights[k] <- nrow(d_s2)
            } else {
              ibs_vals[k] <- NA_real_
              weights[k] <- 0
            }
          }
        } else {
          ibs_vals[k] <- NA_real_
          weights[k] <- 0
        }
      }
    }

    if (sum(weights) == 0) return(NA_real_)
    ibs_val <- sum(ibs_vals * weights, na.rm = TRUE) / sum(weights)
    return(as.numeric(ibs_val))
  }

  if (criteria == "tdAUC") {
    unique_strata <- sort(unique(test_stratum))
    n_strata <- length(unique_strata)
    n_times <- length(eval_times_all)

    dN_mat <- matrix(0, nrow = n_strata, ncol = n_times)
    AUC_mat <- matrix(NA_real_, nrow = n_strata, ncol = n_times)

    for (k in seq_along(unique_strata)) {
      s <- unique_strata[k]
      idx <- which(test_stratum == s)

      if (length(idx) < 2L || all(d_test$status[idx] == 0)) next

      d_s <- d_test[idx, , drop = FALSE]
      rs <- test_RS[idx]

      ev_times_s <- d_s$time[d_s$status == 1]
      if (length(ev_times_s) == 0L) next

      min_ev_s <- min(ev_times_s, na.rm = TRUE)
      max_t_s <- max(d_s$time, na.rm = TRUE)

      times_s <- eval_times_all[eval_times_all >= min_ev_s & eval_times_all <= max_t_s]
      if (length(times_s) < 2L) next

      for (j in seq_along(eval_times_all)) {
        t <- eval_times_all[j]
        dN_mat[k, j] <- sum(d_s$time == t & d_s$status == 1)
      }

      keep <- is.finite(d_s$time) & !is.na(d_s$status) & is.finite(rs)
      if (sum(keep) < 2L || all(d_s$status[keep] == 0)) next

      d_s2 <- d_s[keep, , drop = FALSE]
      rs2 <- rs[keep]

      score_res_s <- riskRegression::Score(
        object  = list(MyModel = rs2),
        formula = Surv(time, status) ~ 1,
        data    = d_s2,
        times   = times_s,
        metrics = "auc"
      )

      auc_df <- as.data.frame(score_res_s$AUC$score)
      auc_df <- auc_df[auc_df$model == "MyModel", , drop = FALSE]
      if (nrow(auc_df) == 0) next

      tcol <- if ("times" %in% names(auc_df)) "times" else if ("time" %in% names(auc_df)) "time" else NA_character_
      acol <- if ("AUC" %in% names(auc_df)) "AUC" else NA_character_
      if (is.na(tcol) || is.na(acol)) next

      tt <- as.numeric(auc_df[[tcol]])
      aa <- as.numeric(auc_df[[acol]])

      AUC_vec <- rep(NA_real_, n_times)
      m <- match(eval_times_all, tt)
      ok <- !is.na(m)
      AUC_vec[ok] <- aa[m[ok]]

      AUC_mat[k, ] <- AUC_vec
    }

    numer_t <- colSums(dN_mat * AUC_mat, na.rm = TRUE)
    denom_t <- colSums(dN_mat, na.rm = TRUE)
    AUC_t <- ifelse(denom_t > 0, numer_t / denom_t, NA_real_)

    valid <- is.finite(AUC_t)
    if (sum(valid) < 2L) return(mean(AUC_t, na.rm = TRUE))

    x <- eval_times_all[valid]
    y <- AUC_t[valid]
    if (max(x) <= min(x)) return(mean(y, na.rm = TRUE))

    iauc <- sum(diff(x) * (head(y, -1) + tail(y, -1)) / 2) / (max(x) - min(x))
    return(as.numeric(iauc))
  }

  NA_real_
}

#' Predict Survival Probabilities From a Baseline-Hazard Object
#'
#' @description
#' Given a per-subject linear predictor (risk score) and a baseline cumulative
#' hazard object as returned by \code{\link{get_baseline_hazard}}, returns the
#' predicted survival probability matrix at the supplied evaluation times.
#' Used internally by \code{\link{test_eval}} for IBS computation.
#'
#' @param test_RS Numeric vector of risk scores (\eqn{Z\beta}) for the test subjects.
#' @param eval_times Numeric vector of times at which to evaluate \eqn{S(t)}.
#' @param train_baseline_obj A list with element \code{predict_baseline}, as
#'   returned by \code{\link{get_baseline_hazard}}.
#' @param test_stratum Optional stratum vector for the test subjects. Defaults
#'   to a single stratum.
#'
#' @return A numeric matrix of dimension \code{length(test_RS) x length(eval_times)}
#'   of predicted survival probabilities \eqn{\exp(-e^{Z\beta}\,\hat\Lambda_0(t))}.
#'
#' @keywords internal
#' @export
predict_surv_prob <- function(test_RS, eval_times, train_baseline_obj, test_stratum = NULL) {
  n <- length(test_RS)
  if (is.null(test_stratum)) test_stratum <- rep(1, n)

  S_pred <- matrix(0, nrow = n, ncol = length(eval_times))
  unique_strata <- unique(test_stratum)

  for (s in unique_strata) {
    idx <- which(test_stratum == s)
    Lambda0_t <- train_baseline_obj$predict_baseline(eval_times, strat_id = s)
    S_pred[idx, ] <- exp(-exp(test_RS[idx]) %o% Lambda0_t)
  }
  S_pred
}

#' Estimate the Baseline Cumulative Hazard for a Cox Fit
#'
#' @description
#' Computes the Breslow estimator of the baseline cumulative hazard
#' \eqn{\hat\Lambda_0(t)} corresponding to a coefficient vector \code{beta},
#' optionally stratified, by fitting an offset-only Cox model on the supplied
#' training data. Returns a closure that evaluates \eqn{\hat\Lambda_0(t)} at
#' arbitrary times. Used internally by \code{\link{test_eval}} (criterion
#' \code{"IBS"}).
#'
#' @param z Numeric matrix of training covariates.
#' @param delta Numeric event-indicator vector (1 = event, 0 = censored).
#' @param time Numeric vector of observed event/censoring times.
#' @param beta Numeric vector of estimated coefficients.
#' @param stratum Optional stratum vector. If supplied, a separate baseline
#'   hazard is estimated within each stratum.
#'
#' @return A list with one element, \code{predict_baseline}, a function with
#'   signature \code{function(times, strat_id = NULL)} returning
#'   \eqn{\hat\Lambda_0(\text{times})} for the requested stratum.
#'
#' @keywords internal
#' @export
get_baseline_hazard <- function(z, delta, time, beta, stratum = NULL) {
  lp <- drop(as.matrix(z) %*% as.matrix(beta))

  if (is.null(stratum)) {
    df <- data.frame(time = as.numeric(time), status = as.numeric(delta))
    fit_fixed <- survival::coxph(Surv(time, status) ~ offset(lp), data = df)
    bh <- survival::basehaz(fit_fixed, centered = FALSE)

    fun <- approxfun(
      x = bh$time,
      y = bh$hazard,
      method = "constant",
      yleft = 0,
      rule = 2
    )

    predict_baseline <- function(times, strat_id = NULL) {
      fun(times)
    }

    return(list(predict_baseline = predict_baseline))
  }

  str_raw <- stratum
  u <- sort(unique(str_raw))

  baseline_funs <- vector("list", length(u))
  names(baseline_funs) <- as.character(u)

  for (s in u) {
    idx <- which(str_raw == s)
    df_s <- data.frame(time = as.numeric(time[idx]), status = as.numeric(delta[idx]))

    fit_s <- survival::coxph(
      Surv(time, status) ~ offset(lp[idx]),
      data = df_s
    )
    bh_s <- survival::basehaz(fit_s, centered = FALSE)

    baseline_funs[[as.character(s)]] <- approxfun(
      x = bh_s$time,
      y = bh_s$hazard,
      method = "constant",
      yleft = 0,
      rule = 2
    )
  }

  predict_baseline <- function(times, strat_id = NULL) {
    sid <- as.character(strat_id)
    if (!sid %in% names(baseline_funs)) {
      stop("Stratum ", strat_id, " not present in training data.")
    }
    baseline_funs[[sid]](times)
  }

  list(predict_baseline = predict_baseline)
}




















