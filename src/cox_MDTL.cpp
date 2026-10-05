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
 *   delta_tilde     - Augmented failure indicator for KL divergence penalty
 *   eta             - Tuning parameter controlling KL divergence strength
 *   ind_start       - Starting indices of each stratum
 *   n_each_stratum  - Number of observations in each stratum
 *   external_beta  - External covariate coefficients (length p)
 *   Q  -  External variance-covariance matrix (p × p)
 *   beta            - Coefficient vector (p × 1)
 *   lambda          - Ridge Regularization parameter (≥ 0; default: 0.0)
 *
 * Returns:
 *   Scalar double: value of the stratified Cox-KL (potentially with ridge) log-partial likelihood.
 */
double MDTL_loglik(const double N, 
                    const arma::vec& lp,      
                    const arma::vec& delta,
                    const double eta,
                    const arma::uvec& ind_start,
                    const arma::vec& n_each_stratum,
                    const arma::vec& external_beta,
                    const arma::mat& Q,
                    const arma::vec& beta,
                    const double lambda,
                    const arma::uvec& tf,
                    const bool use_ties) {
  const arma::uword S = ind_start.n_elem;
  double loglik = 0.0;

  for (arma::uword s = 0; s < S; ++s) {
    const arma::uword start = ind_start(s);
    const arma::uword len   = static_cast<arma::uword>(n_each_stratum(s));
    if (len == 0) continue;
    const arma::uword end   = start + len - 1;

    arma::vec lp_s    = lp.subvec(start, end);
    arma::vec delta_s = delta.subvec(start, end);

    const double m = lp_s.max();
    arma::vec exp_lp_s_shift = arma::exp(lp_s - m);
    arma::vec S0_s = rev_cumsum(exp_lp_s_shift);
    if (use_ties) S0_s = S0_s.elem(tf.subvec(start, end) - start);   // Breslow: the tie group's risk set

    loglik += arma::accu(delta_s % (lp_s - arma::log(S0_s)));
    loglik -= m * arma::sum(delta_s);
  }
  loglik /= N;
  double quad = arma::as_scalar((beta - external_beta).t() * Q * (beta - external_beta));
  loglik -= 0.5 * eta * quad + 0.5 * lambda * arma::dot(beta, beta);

  return loglik;
}

/*
 * Computes the log-partial likelihood, first-order derivative (score), 
 * and second-order derivative (Hessian) for the stratified Cox proportional hazards model.
 *
 * Parameters:
 *   Z     - Internal covariate matrix (n × p)
 *   delta - Event indicator vector (length n), 1 = event, 0 = censored
 *   beta  - Coefficient vector (length p)
 *   n_each_stratum - Number of observations in each stratum
 *   external_beta - External covariate coefficients (length p)
 *   Q  -  External variance-covariance matrix (p × p)
 *   lambda - Ridge Regularization parameter (≥ 0; default: 0.0)
 *   eta - Integration weight for Mahalanobis distance penalty
 *
 * Returns:
 *   A List containing:
 *     - loglik: log-partial likelihood
 *     - L1: first-order derivative (score vector)
 *     - L2: second-order derivative (Hessian matrix)
 *     - S0
 */
arma::vec BetaUpdate_MDTL(const double N, 
                          const arma::mat& Z, 
                          const arma::vec& delta,
                          const arma::vec& beta,
                          const arma::uvec& ind_start,
                          const arma::vec& n_each_stratum,
                          const arma::vec& external_beta,
                          const arma::mat& Q,
                          const double lambda,
                          const double eta,
                          bool backtrack,
                          const arma::uvec& tf,
                          const bool use_ties) {

  const arma::uword p = Z.n_cols;       
  const arma::uword S = n_each_stratum.n_elem;

  // double loglik = 0.0;
  arma::vec L1(p, arma::fill::zeros);
  arma::mat L2(p, p, arma::fill::zeros);

  arma::vec theta = Z * beta;
  // arma::vec exp_theta = arma::exp(theta);

  for (arma::uword s = 0; s < S; ++s) {
    const arma::uword start = ind_start(s);
    const arma::uword len = n_each_stratum(s);
    if (len == 0) continue;
    const arma::uword end = start + len - 1;

    arma::vec delta_s = delta.subvec(start, end);
    arma::mat Z_s = Z.rows(start, end);
    // arma::vec weight_s = weight.subvec(start, end);
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
      const arma::uword k = use_ties ? tf(start + i) - start : i;   // Breslow: the tie group's risk set
      const double s0_i = S0_s(k);

      arma::rowvec z_i = Z_s.row(i);
      arma::rowvec s1_i = S1_s.row(k);
      L1 += d_i * (z_i.t() - (s1_i / s0_i).t());

      if (d_i > 0) {
        arma::mat s2_i(p, p);
        for (arma::uword j = 0; j < p; ++j) {
          s2_i.col(j) = S2_s.slice(j).row(k).t();
        }
        arma::vec s1_div_s0 = s1_i.t() / s0_i;
        arma::mat outer = s1_div_s0 * s1_div_s0.t();
        L2 += d_i * (s2_i / s0_i - outer);
      }
    }
  }

  L1 /= N;
  L2 /= N;

  arma::vec diff_beta = beta - external_beta;
  L1 -= eta * (Q * diff_beta) + lambda * beta;
  L2 += eta * Q + lambda * arma::eye<arma::mat>(p, p);

  L2.diag() += 1e-8;
  arma::vec d_beta;
  bool ok = arma::solve(d_beta, L2, L1, arma::solve_opts::likely_sympd);
  if (!ok) {
    arma::mat L2_reg = L2;
    L2_reg.diag() += 1e-4;
    ok = arma::solve(d_beta, L2_reg, L1, arma::solve_opts::likely_sympd);
    if (!ok) Rcpp::stop("Hessian solve failed.");
  }

  if (backtrack) {
    const double armijo_s = 0.01;
    const double shrink_t = 0.60;
    const int max_bt = 10;
    double step_size = 1.0;

    double f0 = MDTL_loglik(N, theta, delta, eta, ind_start, n_each_stratum,
                            external_beta, Q, beta, lambda, tf, use_ties);
    double slope = arma::dot(L1, d_beta);

    for (int bt = 0; bt < max_bt; ++bt) {
      arma::vec beta_try = beta + step_size * d_beta;
      arma::vec theta_try = Z * beta_try;

      double f_try = MDTL_loglik(N, theta_try, delta, eta, ind_start, n_each_stratum,
                                 external_beta, Q, beta_try, lambda, tf, use_ties);
      if (f_try >= f0 + armijo_s * step_size * slope) break;
      step_size *= shrink_t;
    }
    d_beta *= step_size;
  }
  return d_beta;
}




/*
 * Performs Newton-Raphson iteration to estimate beta in the Cox model.
 *
 * Parameters:
 *   N     - Number of observations 
 *   Z     - Covariate matrix (n × p)
 *   delta - Event indicator vector (length n)
 *   n_each_stratum - Number of observations in each stratum
 *   external_beta - External risk score coefficients (length q)
 *   Q  -  External variance-covariance matrix (q × q)
 *   eta - Integration weight for Mahalanobis distance penalty
 *   lambda - Ridge Regularization parameter (≥ 0; default: 0.0)
 *   beta_initial - Initial coefficient vector (p × 1)
 *   tol   - Convergence tolerance (scalar)
 *   max_iter - Maximum number of iterations (default 100)
 *
 * Returns:
 *   Estimated coefficient vector (β̂)
 */
// [[Rcpp::export]]
arma::vec Cox_MDTL_cpp(const double N,
                      const arma::mat& Z, 
                      const arma::vec& delta, 
                      const arma::vec& n_each_stratum,
                      const double eta,
                      const arma::vec& external_beta,
                      const arma::mat& Q,
                      const arma::vec& beta_initial,
                      const double lambda = 0.0,
                      const double tol = 1.0e-7,
                      const int max_iter = 100,
                      bool backtrack = false,
                      bool message = false,
                      Rcpp::Nullable<Rcpp::IntegerVector> tie_first = R_NilValue) {
  
  arma::vec beta = beta_initial;
  const bool use_ties = tie_first.isNotNull();
  const arma::uvec tf = tie_index(tie_first, Z.n_rows);


  const arma::uword S = n_each_stratum.n_elem;
  arma::uvec ind_start(S); 
  ind_start(0) = 0;
  for (arma::uword i = 1; i < S; ++i) {
    ind_start(i) = ind_start(i - 1) + n_each_stratum(i - 1);
  }

  for (int iter = 0; iter < max_iter; ++iter) {
    arma::vec d_beta = BetaUpdate_MDTL(N, Z, delta, beta, ind_start, n_each_stratum,
                                       external_beta, Q, lambda, eta, backtrack, tf, use_ties);
    
    double step_size = 1.0;
    if (!backtrack && arma::abs(d_beta).max() > 1.0) {
      step_size = 1.0 / arma::abs(d_beta).max();
    }
    beta += step_size * d_beta;

    if (arma::max(arma::abs(d_beta)) < tol) {
      if (message) {
        Rcpp::Rcout << "Converged in " << iter + 1 << " iterations." << std::endl;
      }
      break;
    }
  }
  return beta;
}

