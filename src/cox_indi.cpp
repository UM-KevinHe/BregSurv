#include <RcppArmadillo.h>
#include "utils.h"
#include <Rmath.h>
// [[Rcpp::depends(RcppArmadillo)]]
// [[Rcpp::plugins(cpp11)]]

using namespace Rcpp;


// [[Rcpp::export]]
Rcpp::List ddloglik_indi(const arma::mat& Z,
                         const arma::vec& delta,
                         const arma::vec& beta,
                         const arma::vec& weight,
                         const arma::vec& n_each_stratum,
                         Rcpp::Nullable<Rcpp::IntegerVector> tie_first = R_NilValue) {

  const bool use_ties = tie_first.isNotNull();
  const arma::uvec tf = tie_index(tie_first, Z.n_rows);
  int count_stratum = n_each_stratum.n_elem;
  int p = beta.n_rows;

  arma::vec L1(p, arma::fill::zeros);
  arma::mat L2(p, p, arma::fill::zeros);

  arma::vec theta = Z * beta;
  arma::vec exp_theta = arma::exp(theta);

  // Compute start index for each stratum
  arma::vec ind_start(count_stratum);
  ind_start(0) = 0;
  for (int i = 1; i < count_stratum; i++) {
    ind_start(i) = ind_start(i - 1) + n_each_stratum(i - 1);
  }

  // Loop over strata
  for (int s = 0; s < count_stratum; s++) {
    int start = ind_start(s);
    int len = n_each_stratum(s);
    int end = start + len - 1;

    // Extract stratum-specific data
    arma::mat Z_s = Z.rows(start, end);
    arma::vec delta_s = delta.subvec(start, end);
    arma::vec weight_s = weight.subvec(start, end);
    arma::vec theta_s = theta.subvec(start, end);
    arma::vec exp_theta_s = exp_theta.subvec(start, end);

    arma::vec S0_s = rev_cumsum(exp_theta_s);

    arma::mat S1_s(len, p, arma::fill::zeros);
    for (int j = 0; j < p; ++j) {
      arma::vec Zj = Z_s.col(j);
      S1_s.col(j) = rev_cumsum(Zj % exp_theta_s);
    }
    // Breslow (1.3.0): every risk-set sum taken at the first row of the row's tie group
    arma::uvec loc;
    if (use_ties) {
      loc = tf.subvec(start, end) - (arma::uword) start;
      S0_s = S0_s.elem(loc);
      S1_s = S1_s.rows(loc);
    }

    // Compute gradient (score)
    arma::vec L1_s(p, arma::fill::zeros);
    for (int j = 0; j < p; ++j) {
      arma::vec Zj = Z_s.col(j);
      arma::vec S1j = S1_s.col(j);
      L1_s(j) = arma::sum(weight_s % delta_s % (Zj - S1j / S0_s));
    }
    L1 += L1_s;

    for (int i = 0; i < p; ++i) {
      for (int j = 0; j < p; ++j) {
        arma::vec S2_s = rev_cumsum(Z_s.col(i) % exp_theta_s % Z_s.col(j));
        if (use_ties) S2_s = S2_s.elem(loc);
        arma::vec V = (S2_s / S0_s) -
                      (S1_s.col(i) % S1_s.col(j)) / arma::square(S0_s);
        L2(i, j) += arma::sum(weight_s % delta_s % V);
      }
    }
  }

  return Rcpp::List::create(
    Rcpp::Named("L1") = L1,
    Rcpp::Named("L2") = L2
  );
}




// [[Rcpp::export]]
Rcpp::List Cox_indi(const arma::mat& Z,
                    const arma::vec& delta,
                    const arma::vec& weight,
                    const arma::vec &n_each_stratum,  // stratification info
                    arma::vec beta,                   // initial values
                    double tol = 1e-6,
                    int max_iter = 100,
                    Rcpp::Nullable<Rcpp::IntegerVector> tie_first = R_NilValue) {
  arma::vec update(beta.n_elem);
  Rcpp::List diff;
  arma::vec L1;
  arma::mat L2;

  for (int iter = 0; iter < max_iter; ++iter) {

    diff = ddloglik_indi(Z, delta, beta, weight, n_each_stratum, tie_first);
    L1 = Rcpp::as<arma::vec>(diff["L1"]);
    L2 = Rcpp::as<arma::mat>(diff["L2"]);

    update = arma::solve(L2, L1);
    beta += update;

    if (arma::max(arma::abs(update)) < tol) break;
  }

  return Rcpp::List::create(
    Rcpp::Named("beta") = beta
  );
}
