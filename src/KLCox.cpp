#include <RcppArmadillo.h>
#include "utils.h"
// [[Rcpp::depends(RcppArmadillo)]]
// [[Rcpp::plugins(cpp11)]]

using namespace Rcpp;

/*
 * Computes the log-partial likelihood for the Cox-KL model.
 *
 * Parameters:
 *   N              - Number of observations
 *   lp              - Linear predictor (n × 1), i.e. Z * beta
 *   delta           - Event indicator vector (length n)
 *   delta_eta       - Pre-computed combined event weight: (eta * delta_tilde + delta) / (1 + eta)
 *   eta             - Tuning parameter controlling KL divergence strength
 *   ind_start       - Starting indices of each stratum
 *   n_each_stratum  - Number of observations in each stratum
 *   beta            - Coefficient vector (p × 1)
 *   lambda          - Ridge Regularization parameter (≥ 0; default: 0.0)
 *
 * Returns:
 *   Scalar double: value of the stratified Cox-KL (potentially with ridge) log-partial likelihood.
 */
double coxkl_loglik(const double N,
                    const arma::vec& lp,
                    const arma::vec& delta,
                    const arma::vec& delta_eta,
                    double eta,
                    const arma::uvec& ind_start,
                    const arma::vec& n_each_stratum,
                    const arma::vec& beta,
                    const double lambda = 0.0) {

  const arma::uword S = ind_start.n_elem;
  double loglik = 0.0;

  for (arma::uword s = 0; s < S; ++s) {
    const arma::uword start = ind_start(s);
    const arma::uword len   = static_cast<arma::uword>(n_each_stratum(s));
    if (len == 0) continue;
    const arma::uword end   = start + len - 1;

    arma::vec lp_s    = lp.subvec(start, end);
    arma::vec delta_s = delta.subvec(start, end);

    arma::vec delta_eta_s = delta_eta.subvec(start, end);

    const double m = lp_s.max();
    arma::vec exp_lp_s_shift = arma::exp(lp_s - m);
    arma::vec S0_s = rev_cumsum(exp_lp_s_shift);

    for (arma::uword i = 0; i < len; ++i) {
      const double w_i = delta_eta_s(i);
      loglik += w_i * lp_s(i);
      if (delta_s(i) > 0) {
        loglik -= std::log(S0_s(i)) + m;
      }
    }
  }
  loglik /= N;

  if (lambda > 0.0) {
    loglik -= 0.5 * lambda * arma::dot(beta, beta);
  }
  return loglik;
}


/*
 * Performs one Newton–Raphson update step for β in the Cox–KL model,
 * with optional backtracking line search.
 *
 *
 * Parameters:
 *   N              - Number of observations
 *   Z              - Covariate matrix (n × p)
 *   delta          - Event indicator vector (length n, 1 = event, 0 = censored)
 *   delta_eta      - Pre-computed combined event weight: (eta * delta_tilde + delta) / (1 + eta)
 *   beta           - Current coefficient vector (p × 1)
 *   eta            - KL tuning parameter (η ≥ 0); η = 0 reduces to standard Cox
 *   ind_start      - Start indices of each stratum (length = #strata)
 *   n_each_stratum - Number of observations in each stratum
 *   lambda         - Ridge Regularization parameter (≥ 0; default: 0.0)
 *   backtrack      - If true, use a backtracking line search on the Newton step
 *
 * Returns:
 *   Newton step vector of step sizes.
 */
arma::vec BetaUpdate(const double N,
                     const arma::mat& Z,
                     const arma::vec& delta,
                     const arma::vec& delta_eta,
                     const arma::vec& beta,
                     const double eta,
                     const arma::uvec& ind_start,
                     const arma::vec& n_each_stratum,
                     const double lambda = 0.0,
                     bool backtrack = false) {

  const arma::uword p = Z.n_cols;
  const arma::uword S = n_each_stratum.n_elem;


  // arma::vec exp_theta = arma::exp(theta);
  arma::vec L1(p, arma::fill::zeros);
  arma::mat L2(p, p, arma::fill::zeros);

  arma::vec theta = Z * beta;

  for (arma::uword s = 0; s < S; ++s) {
    const arma::uword start = ind_start(s);
    const arma::uword len = n_each_stratum(s);
    if (len == 0) continue;
    const arma::uword end = start + len - 1;

    arma::vec delta_s = delta.subvec(start, end);
    arma::vec delta_eta_s = delta_eta.subvec(start, end);
    arma::mat Z_s = Z.rows(start, end);
    arma::vec theta_s = theta.subvec(start, end);

    const double m = theta_s.max();
    arma::vec exp_theta_s = arma::exp(theta_s - m);
    arma::vec S0_s = rev_cumsum(exp_theta_s);

    arma::mat S1_s(len, p, arma::fill::zeros);
    arma::cube S2_s(len, p, p, arma::fill::zeros);

    for (arma::uword j = 0; j < p; ++j) {
      arma::vec Zj_s = Z_s.col(j);
      S1_s.col(j) = rev_cumsum(Zj_s % exp_theta_s);
      for (arma::uword k = 0; k < p; ++k) {
        arma::vec Zk_s = Z_s.col(k);
        S2_s.slice(j).col(k) = rev_cumsum(Zj_s % Zk_s % exp_theta_s);
      }
    }

    for (arma::uword i = 0; i < len; ++i) {
      const double d_i = delta_s(i);
      const double deta_i = delta_eta_s(i);
      const double s0_i = S0_s(i);

      arma::rowvec z_i = Z_s.row(i);
      arma::rowvec s1_i = S1_s.row(i);

      L1 += deta_i * z_i.t() - d_i * (s1_i / s0_i).t();

      if (d_i > 0) {
        arma::mat s2_i(p, p);
        for (arma::uword j = 0; j < p; ++j) {
          s2_i.col(j) = S2_s.slice(j).row(i).t();
        }
        arma::vec s1_div_s0 = s1_i.t() / s0_i;
        arma::mat outer = s1_div_s0 * s1_div_s0.t();
        L2 += d_i * (s2_i / s0_i - outer);
      }
    }
  }

  L1 /= N;
  L2 /= N;

  arma::vec L1_pen = L1 - lambda * beta;
  arma::mat L2_pen = L2;
  L2_pen.diag() += lambda;

  // Small numerical ridge (independent of lambda)
  L2_pen.diag() += 1e-8;

  arma::vec d_beta;
  bool ok = arma::solve(d_beta, L2_pen, L1_pen, arma::solve_opts::likely_sympd);

  if (!ok) {
    arma::mat L2_reg = L2_pen;
    L2_reg.diag() += 1e-4;
    ok = arma::solve(d_beta, L2_reg, L1_pen, arma::solve_opts::likely_sympd);
    if (!ok) Rcpp::stop("Hessian solve failed.");
  }

  if (backtrack) {
    const double armijo_s = 0.01;
    const double shrink_t = 0.60;
    const int max_bt = 10;
    double step_size = 1.0;

    double f0 = coxkl_loglik(N, theta, delta, delta_eta, eta, ind_start, n_each_stratum, beta, lambda);
    double slope = arma::dot(L1_pen, d_beta);
    for (int bt = 0; bt < max_bt; ++bt) {
      arma::vec beta_try = beta + step_size * d_beta;
      arma::vec theta_try = Z * beta_try;

      double f_try = coxkl_loglik(N, theta_try, delta, delta_eta, eta, ind_start, n_each_stratum, beta_try, lambda);
      if (f_try >= f0 + armijo_s * step_size * slope) break;
      step_size *= shrink_t;
    }
    d_beta *= step_size;
  }

  return d_beta;
}



 /*
 * Estimates Cox-KL model coefficients using Newton-Raphson iteration.
 *
 * Parameters:
 *   N              - Number of observations
 *   z              - Internal covariate matrix (n × p)
 *   delta          - Event indicator vector (length n), 1 = event, 0 = censored
 *   delta_eta      - Pre-computed combined event weight: (eta * delta_tilde + delta) / (1 + eta)
 *   n_each_stratum - Number of observations in each stratum (length S)
 *   eta            - Integration weight for KL penalty
 *   tol            - Convergence tolerance for Newton-Raphson updates (default: 1e-7)
 *   Mstop          - Maximum number of iterations (default: 50)
 *   lambda         - Regularization parameter (default: 0.0)
 *   backtrack      - Whether to use backtracking line search (default: false)
 *
 * Returns:
 *   Estimated coefficient vector (β̂) for the Cox-KL model
 */
// [[Rcpp::export]]
arma::vec KL_Cox_Estimate_cpp(const double N,
                              const arma::mat& Z,
                              const arma::vec& delta,
                              const arma::vec& delta_eta,
                              const arma::vec& n_each_stratum,
                              const double eta,
                              arma::vec beta_initial,
                              const double tol = 1.0e-7,
                              const int maxit = 50,
                              const double lambda = 0.0,
                              bool backtrack = false,
                              bool message = false){
  arma::vec beta = beta_initial;

  const arma::uword S = n_each_stratum.n_elem;
  arma::uvec ind_start(S);
  ind_start(0) = 0;
  for (arma::uword i = 1; i < S; ++i) {
    ind_start(i) = ind_start(i - 1) + n_each_stratum(i - 1);
  }

  for (int iter = 0; iter < maxit; ++iter) {
    arma::vec d_beta = BetaUpdate(N, Z, delta, delta_eta, beta, eta, ind_start, n_each_stratum, lambda, backtrack);

    double step_size = 1.0;
    if (!backtrack && arma::abs(d_beta).max() > 1.0) {
      step_size = 1.0 / arma::abs(d_beta).max();
    }
    beta += step_size * d_beta;


    if (arma::max(arma::abs(d_beta)) < tol) {
      if (message){
        if (lambda == 0.0) {
          Rcpp::Rcout << "CoxKL converged after " << iter + 1 << " iterations." << std::endl;
        } else {
          Rcpp::Rcout << "CoxKL with ridge penalty (lambda=" << lambda << ") converged after " << iter + 1 << " iterations." << std::endl;
        }
      }
      break;
    }
  }
  return beta;
}



/* ========================================================================== */
/* TIES HANDLING FUNCTIONS                           */
/* ========================================================================== */

// [[Rcpp::export]]
double pl_cal_exact(const arma::vec& lp,
                    const arma::vec& delta,
                    const arma::vec& time,
                    const arma::vec& n_each_stratum,
                    const double comb_max = 200000.0) {
  const int n = lp.n_elem;
  if ((int)delta.n_elem != n || (int)time.n_elem != n) {
    Rcpp::stop("Lengths of lp, delta, and time must match.");
  }
  const int S = n_each_stratum.n_elem;

  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s) {
    ind_start(s) = ind_start(s - 1) + (unsigned int)n_each_stratum(s - 1);
  }

  double loglik = 0.0;

  // loop over strata
  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    int end   = start + len - 1;
    if (len <= 0) continue;

    arma::vec lp_s    = lp.subvec(start, end);
    arma::vec delta_s = delta.subvec(start, end);
    arma::vec time_s  = time.subvec(start, end);

    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      int d_k = 0;
      double num_sum = 0.0;
      for (int r = b; r <= e; ++r) {
        if (delta_s(r) == 1.0) {
          ++d_k;
          num_sum += lp_s(r);
        }
      }
      if (d_k == 0) continue;

      int n_risk = len - b;
      double ncomb_dbl = R::choose((double)n_risk, (double)d_k);
      if (ncomb_dbl > comb_max) {
        Rcpp::stop("pl_cal_exact: C(%d,%d)=%.4g > comb_max(%.4g) at stratum %d, t=%.6g",
                   n_risk, d_k, ncomb_dbl, comb_max, s+1, tk);
      }

      arma::vec lp_risk = lp_s.subvec(b, len - 1);
      arma::umat combs  = combn_index(n_risk, d_k);
      const int n_comb  = combs.n_cols;

      double max_sum = -std::numeric_limits<double>::infinity();
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        double ssum = arma::sum(lp_risk.elem(idx));
        if (ssum > max_sum) max_sum = ssum;
      }

      double S0 = 0.0;
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        double ssum = arma::sum(lp_risk.elem(idx));
        S0 += std::exp(ssum - max_sum);
      }
      double denom_log = max_sum + std::log(S0);

      loglik += num_sum - denom_log;
    }
  }

  return loglik;
}

// [[Rcpp::export]]
arma::mat calculateWTilde_exact(const arma::mat& Z,
                                const arma::vec& delta,
                                const arma::vec& time,
                                const arma::vec& n_each_stratum,
                                const arma::vec& external_beta,
                                const double comb_max = 200000.0) {
  const int p = Z.n_cols;

  const int S = n_each_stratum.n_elem;

  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s)
    ind_start(s) = ind_start(s-1) + (unsigned int)n_each_stratum(s-1);

  std::vector< arma::rowvec > out_tildeW;

  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    if (len <= 0) continue;

    arma::mat Z_s     = Z.rows(start, start + len - 1);
    arma::vec delta_s = delta.subvec(start, start + len - 1);
    arma::vec time_s  = time.subvec(start, start + len - 1);

    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      // failures at tk
      int d_k = 0;
      for (int r = b; r <= e; ++r)
        if (delta_s(r) == 1.0) ++d_k;
      if (d_k == 0) continue;

      // risk set
      int n_risk = len - b;
      double ncomb_dbl = R::choose((double)n_risk, (double)d_k);
      if (ncomb_dbl > comb_max) {
        Rcpp::stop("calculateWTilde: C(%d,%d)=%.4g > comb_max(%.4g) at stratum %d, t=%.6g",
                   n_risk, d_k, ncomb_dbl, comb_max, s+1, tk);
      }

      arma::mat Z_risk = Z_s.rows(b, len - 1);
      arma::umat combs = combn_index(n_risk, d_k);
      const int n_comb = combs.n_cols;

      double rmax = -std::numeric_limits<double>::infinity();
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        arma::rowvec w = arma::sum(Z_risk.rows(idx), 0);
        double r = arma::dot(w, external_beta);
        if (r > rmax) rmax = r;
      }

      double S0t = 0.0;
      arma::rowvec S1t(p, arma::fill::zeros);
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        arma::rowvec w = arma::sum(Z_risk.rows(idx), 0);
        double r = arma::dot(w, external_beta);
        double wgt = std::exp(r - rmax);
        S0t += wgt;
        S1t += wgt * w;
      }
      arma::rowvec tilde_w = S1t / S0t;

      out_tildeW.push_back(tilde_w);
    }
  }

  // assemble into matrix
  const int K = (int)out_tildeW.size();
  arma::mat tildeW(K, p, arma::fill::zeros);
  for (int k = 0; k < K; ++k) tildeW.row(k) = out_tildeW[k];

  return tildeW; //return a matrix: each time k is a row
}

// [[Rcpp::export]]
Rcpp::List ddloglik_exact_KL(const arma::mat& Z,
                             const arma::vec& delta,
                             const arma::vec& time,
                             const arma::vec& beta,
                             const arma::vec& n_each_stratum,
                             const arma::mat& tildeW,   // K x p, in scan order
                             const double eta,
                             const double comb_max = 200000.0) {
  const int n = Z.n_rows;
  const int p = Z.n_cols;
  if ((int)delta.n_elem != n || (int)time.n_elem != n)
    Rcpp::stop("Lengths of Z, delta, and time must match.");
  if ((int)beta.n_elem != p)
    Rcpp::stop("beta length must equal ncol(Z).");
  if (tildeW.n_cols != (unsigned)p)
    Rcpp::stop("tildeW must have p columns.");

  const int S = n_each_stratum.n_elem;

  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s)
    ind_start(s) = ind_start(s-1) + (unsigned int)n_each_stratum(s-1);

  arma::vec L1(p, arma::fill::zeros);
  arma::mat L2(p, p, arma::fill::zeros);

  int block_idx = 0; // row index into tildeW

  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    if (len <= 0) continue;

    arma::mat Z_s     = Z.rows(start, start + len - 1);
    arma::vec delta_s = delta.subvec(start, start + len - 1);
    arma::vec time_s  = time.subvec(start, start + len - 1);

    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      int d_k = 0;
      arma::rowvec w_k(p, arma::fill::zeros);
      for (int r = b; r <= e; ++r) {
        if (delta_s(r) == 1.0) {
          ++d_k;
          w_k += Z_s.row(r);
        }
      }
      if (d_k == 0) continue;

      if (block_idx >= (int)tildeW.n_rows)
        Rcpp::stop("tildeW has fewer rows than time blocks encountered.");

      arma::rowvec w_bar = (w_k + eta * tildeW.row(block_idx)) / (1.0 + eta);

      // risk set at t_k is {b, ..., len-1}
      int n_risk = len - b;
      double ncomb_dbl = R::choose((double)n_risk, (double)d_k);
      if (ncomb_dbl > comb_max) {
        Rcpp::stop("KL exact: C(%d,%d)=%.4g > comb_max(%.4g) at stratum %d, t=%.6g",
                   n_risk, d_k, ncomb_dbl, comb_max, s+1, tk);
      }

      arma::mat Z_risk = Z_s.rows(b, len - 1);
      arma::umat combs = combn_index(n_risk, d_k);
      const int n_comb = combs.n_cols;

      // pass 1: eta_max (for current beta)
      double eta_max = -std::numeric_limits<double>::infinity();
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        arma::rowvec w = arma::sum(Z_risk.rows(idx), 0);
        double eta_j = arma::dot(w, beta);
        if (eta_j > eta_max) eta_max = eta_j;
      }

      // pass 2: S0,S1,S2 (stabilized)
      double S0 = 0.0;
      arma::rowvec S1(p, arma::fill::zeros);
      arma::mat S2(p, p, arma::fill::zeros);
      for (int j = 0; j < n_comb; ++j) {
        arma::uvec idx = combs.col(j);
        arma::rowvec w = arma::sum(Z_risk.rows(idx), 0);
        double eta_j = arma::dot(w, beta);
        double wgt = std::exp(eta_j - eta_max);
        S0 += wgt;
        S1 += wgt * w;
        S2 += wgt * (w.t() * w);
      }

      // gradient & Hessian contributions
      L1 += (w_bar - (S1 / S0)).t();
      arma::mat mean_outer = (S1.t() * S1) / (S0 * S0);
      L2 += (S2 / S0) - mean_outer;   // negative semidefinite

      ++block_idx;
    }
  }

  if (block_idx != (int)tildeW.n_rows)
    Rcpp::stop("tildeW rows (%d) != time blocks encountered (%d).",
               tildeW.n_rows, block_idx);

  return Rcpp::List::create(
    Rcpp::Named("L1") = L1,
    Rcpp::Named("L2") = L2
  );
}

// [[Rcpp::export]]
arma::vec CoxKL_NR_exact(const arma::mat& Z,
                         const arma::vec& delta,
                         const arma::vec& time,
                         const arma::vec& n_each_stratum,
                         const arma::mat& tildeW,  // K x p from PrecomputeTildeW_exact
                         double eta,
                         arma::vec beta,           // init (length p)
                         double tol,
                         int max_iter,
                         double comb_max = 200000.0) {
  arma::vec update(beta.n_elem);
  arma::vec L1;
  arma::mat L2;
  Rcpp::List diff;

  for (int iter = 0; iter < max_iter; ++iter) {
    diff = ddloglik_exact_KL(Z, delta, time, beta, n_each_stratum, tildeW, eta, comb_max);
    L1 = Rcpp::as<arma::vec>(diff["L1"]);
    L2 = Rcpp::as<arma::mat>(diff["L2"]);

    update = arma::solve(L2, L1);
    beta  += update;

    if (arma::max(arma::abs(update)) < tol) break;
  }

  return beta;
}

/*
 * 2. Breslow approximation
 */

// [[Rcpp::export]]
arma::mat calculateWTilde_breslow(const arma::mat& Z,
                                  const arma::vec& delta,
                                  const arma::vec& time,
                                  const arma::vec& risk_score_ext,
                                  const arma::vec& n_each_stratum) {

  const int p = Z.n_cols;
  const int S = n_each_stratum.n_elem;

  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s) {
    ind_start(s) = ind_start(s - 1) + (unsigned int)n_each_stratum(s - 1);
  }

  std::vector<arma::rowvec> wtilde_list;

  // loop over strata
  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    int end   = start + len - 1;

    arma::mat Z_s = Z.rows(start, end);
    arma::vec delta_s = delta.subvec(start, end);
    arma::vec time_s  = time.subvec(start, end);
    arma::vec r_s     = risk_score_ext.subvec(start, end);

    arma::vec exp_r = arma::exp(r_s);
    arma::vec S0_s = rev_cumsum(exp_r);

    // S1: risk set numerator
    arma::mat S1_s(len, p, arma::fill::zeros);
    for (int j = 0; j < p; ++j) {
      arma::vec pre = Z_s.col(j) % exp_r;
      S1_s.col(j) = rev_cumsum(pre);
    }

    // find unique time points
    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      int d_k = 0;
      for (int r = b; r <= e; ++r) {
        if (delta_s(r) == 1.0) ++d_k;
      }
      if (d_k == 0) continue;

      double S0 = S0_s(b);
      arma::rowvec S1 = S1_s.row(b);

      arma::rowvec wtilde_k = d_k * (S1 / S0);
      wtilde_list.push_back(wtilde_k);
    }
  }

  int K = (int)wtilde_list.size();
  arma::mat Wtilde(K, p);
  for (int k = 0; k < K; ++k) {
    Wtilde.row(k) = wtilde_list[k];
  }

  return Wtilde;
}

// [[Rcpp::export]]
double pl_cal_breslow(const arma::vec& lp,
                      const arma::vec& delta,
                      const arma::vec& time,
                      const arma::vec& n_each_stratum) {
  const int n = lp.n_elem;
  if ((int)delta.n_elem != n || (int)time.n_elem != n) {
    Rcpp::stop("Lengths of lp, delta, and time must match.");
  }
  const int S = n_each_stratum.n_elem;

  // stratum start indices (0-based)
  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s) {
    ind_start(s) = ind_start(s - 1) + (unsigned int)n_each_stratum(s - 1);
  }

  double loglik = 0.0;

  // loop over strata
  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    int end   = start + len - 1;
    if (len <= 0) continue;

    arma::vec lp_s    = lp.subvec(start, end);
    arma::vec delta_s = delta.subvec(start, end);
    arma::vec time_s  = time.subvec(start, end);

    arma::vec exp_lp  = arma::exp(lp_s);
    arma::vec S0_s    = rev_cumsum(exp_lp);

    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      int d_k = 0;
      double num_sum = 0.0;
      for (int r = b; r <= e; ++r) {
        if (delta_s(r) == 1.0) {
          ++d_k;
          num_sum += lp_s(r);
        }
      }
      if (d_k == 0) continue;

      double denom = S0_s(b);
      loglik += num_sum - d_k * std::log(denom);
    }
  }

  return loglik;
}


// [[Rcpp::export]]
Rcpp::List ddloglik_breslow_KL(const arma::mat& Z,
                               const arma::vec& delta,
                               const arma::vec& time,
                               const arma::vec& beta,
                               const arma::vec& n_each_stratum,
                               const arma::mat& Wtilde,
                               const double eta) {

  const int p = Z.n_cols;
  const int S = n_each_stratum.n_elem;

  arma::uvec ind_start(S);
  ind_start(0) = 0u;
  for (int s = 1; s < S; ++s) {
    ind_start(s) = ind_start(s - 1) + (unsigned int)n_each_stratum(s - 1);
  }

  arma::vec L1(p, arma::fill::zeros);
  arma::mat L2(p, p, arma::fill::zeros);

  int global_k = 0;

  for (int s = 0; s < S; ++s) {
    int start = (int)ind_start(s);
    int len   = (int)n_each_stratum(s);
    int end   = start + len - 1;
    if (len <= 0) continue;

    arma::mat Z_s     = Z.rows(start, end);
    arma::vec delta_s = delta.subvec(start, end);
    arma::vec time_s  = time.subvec(start, end);

    arma::vec theta_s     = Z_s * beta;
    arma::vec exp_theta_s = arma::exp(theta_s);
    arma::vec S0_s        = rev_cumsum(exp_theta_s);

    arma::mat S1_s(len, p, arma::fill::zeros);
    for (int j = 0; j < p; ++j) {
      arma::vec pre = Z_s.col(j) % exp_theta_s;
      S1_s.col(j) = rev_cumsum(pre);
    }

    std::vector<int> b_idx;
    std::vector<int> d_vals;
    std::vector<arma::rowvec> wk_list;

    int i = 0;
    while (i < len) {
      double tk = time_s(i);
      int b = i;
      while (i < len && time_s(i) == tk) ++i;
      int e = i - 1;

      int d_k = 0;
      arma::rowvec w_k(p, arma::fill::zeros);
      for (int r = b; r <= e; ++r) {
        if (delta_s(r) == 1.0) {
          ++d_k;
          w_k += Z_s.row(r);
        }
      }
      if (d_k == 0) continue;

      b_idx.push_back(b);
      d_vals.push_back(d_k);
      wk_list.push_back(w_k);
    }

    const int K_local = (int)b_idx.size();
    for (int k = 0; k < K_local; ++k, ++global_k) {
      int b = b_idx[k];
      int d_k = d_vals[k];
      const arma::rowvec& w_k = wk_list[k];

      const arma::rowvec& wtilde_k = Wtilde.row(global_k);
      arma::rowvec w_aug = (w_k + eta * wtilde_k) / (1.0 + eta);

      double S0 = S0_s(b);
      arma::rowvec S1 = S1_s.row(b);

      arma::rowvec score_k = w_aug - d_k * (S1 / S0);
      L1 += score_k.t();
    }

    for (int a = 0; a < p; ++a) {
      for (int bcol = 0; bcol < p; ++bcol) {
        arma::vec S2_vec = rev_cumsum(Z_s.col(a) % exp_theta_s % Z_s.col(bcol));
        double acc = 0.0;
        for (int k = 0; k < K_local; ++k) {
          int b = b_idx[k];
          int d_k = d_vals[k];

          double S0 = S0_s(b);
          double S2 = S2_vec(b);
          double S1a = S1_s(b, a);
          double S1b = S1_s(b, bcol);

          double Vij = (S2 / S0) - (S1a * S1b) / (S0 * S0);
          acc += d_k * Vij;
        }
        L2(a, bcol) += acc;
      }
    }
  }

  return Rcpp::List::create(
    Rcpp::Named("L1") = L1,
    Rcpp::Named("L2") = L2
  );
}

// [[Rcpp::export]]
arma::vec CoxKL_NR_breslow(const arma::mat& Z,
                           const arma::vec& delta,
                           const arma::vec& time,
                           const arma::vec& n_each_stratum,
                           const arma::mat& Wtilde,
                           const double eta,
                           arma::vec beta,
                           double tol,
                           int max_iter) {

  arma::vec update(beta.n_elem);
  arma::vec L1;
  arma::mat L2;
  Rcpp::List diff;

  for (int iter = 0; iter < max_iter; ++iter) {
    diff = ddloglik_breslow_KL(Z, delta, time, beta, n_each_stratum, Wtilde, eta);
    L1 = Rcpp::as<arma::vec>(diff["L1"]);
    L2 = Rcpp::as<arma::mat>(diff["L2"]);

    update = arma::solve(L2, L1);
    beta += update;

    if (arma::max(arma::abs(update)) < tol) break;
  }

  return beta;
}
