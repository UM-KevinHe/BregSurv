#define Check_Headers
#include <RcppArmadillo.h>
#include <iostream>
#include <cmath>
#include <omp.h>
#include <chrono>
#include "utils.h"
// [[Rcpp::depends(RcppArmadillo)]]
// [[Rcpp::plugins(cpp11)]]
// [[Rcpp::plugins(openmp)]]
using namespace Rcpp;
using namespace std;
using namespace arma;

void gd_MDTL_enet(arma::vec &beta, const arma::mat &Z, arma::vec &r, arma::vec &eta, const arma::vec &old_beta,
                  const int g, const arma::vec &K1, const int n_obs, const double lambda, const double alpha,
                  const double eta_mdtl, const arma::mat &Q, const arma::vec &Qbeta_ext, arma::vec &Qbeta,
                  double &df, double &MaxChange_beta) {
  const int K = K1(g + 1) - K1(g);
  for (int j = K1(g); j < K1(g + 1); j++) {
    const double Qpp = Q(j, j);
    const double a_p = 1.0 + eta_mdtl * Qpp + lambda * (1.0 - alpha);
    const double c_p = mean_crossprod(Z, r, j, n_obs) + old_beta(j);
    const double t_p = c_p - eta_mdtl * ((Qbeta(j) - Qpp * beta(j)) - Qbeta_ext(j));
    const double beta_new = Soft_thres(t_p, lambda * alpha) / a_p;

    const double beta_change = beta_new - beta(j);
    if (beta_change != 0.0) {
      beta(j) = beta_new;
      r -= Z.col(j) * beta_change;
      eta += Z.col(j) * beta_change;
      Qbeta += Q.col(j) * beta_change;
      if (std::abs(beta_change) > MaxChange_beta) MaxChange_beta = std::abs(beta_change);
    }
  }
  if (K > 0) {
    double norm_ratio = 0.0;
    df += K * norm_ratio;
  }

}

double gd_MDTL_BetaChange(const arma::mat &Z, const arma::vec &r, const arma::vec &old_beta,
                          const int g, const arma::vec &K1, const int n_obs, const double lambda,
                          const double alpha, const double eta_mdtl, const arma::mat &Q,
                          const arma::vec &Qbeta_ext, const arma::vec &Qbeta, const arma::vec &beta) {
  double max_len = 0.0;
  for (int j = K1(g); j < K1(g + 1); j++) {
    const double Qpp = Q(j, j);
    const double a_p = 1.0 + eta_mdtl * Qpp + lambda * (1.0 - alpha);
    const double m_j = mean_crossprod(Z, r, j, n_obs) + old_beta(j);
    const double t_p = m_j - eta_mdtl * ((Qbeta(j) - Qpp * beta(j)) - Qbeta_ext(j));
    const double beta_new = Soft_thres(t_p, lambda * alpha) / a_p;
    const double absv = std::abs(beta_new);
    if (absv > max_len) max_len = absv;
  }
  return max_len;
}

std::tuple<arma::vec, arma::vec, double, double, int>
Cox_MDTL_enet_fit(const arma::vec &delta, const arma::mat &Z, const arma::vec &n_each_prov,
                  arma::vec beta, arma::vec eta, const int K0, const arma::vec &K1,
                  const double lambda, const double alpha, const double eta_mdtl,
                  const arma::mat &Q, const arma::vec &Qbeta_ext,
                  int &tol_iter, const int max_total_iter, const int max_each_iter,
                  const arma::vec &group_multiplier, const int count_stratum,
                  const double tol, const arma::vec &ind_start, arma::vec &active_group,
                  const int n_obs, const int n_group, const bool actSet, const int actIter,
                  const int activeGroupNum, const bool actSetRemove,
                  const arma::uvec &tf, const arma::uvec &tl, const bool use_ties) {

  arma::vec old_beta = beta, r(n_obs), rsk(n_obs), h(n_obs);
  arma::vec Qbeta = Q * beta;
  double loss = 0.0, df = 0.0, MaxChange_beta = 0.0, lambda_g = 0.0, s, v = 1.0;
  int iter = 0;


  while (tol_iter < max_total_iter) {
    int inner_loop_iter = -1;
    inner_loop_iter = inner_loop_iter + 1;
    R_CheckUserInterrupt();

    while (tol_iter < max_total_iter && iter < max_each_iter) {
      R_CheckUserInterrupt();
      df = 0.0;
      tol_iter++;
      iter++;
      inner_loop_iter++;
      MaxChange_beta = 0.0;

      arma::vec haz = arma::exp(eta);
      for (int j = 0; j < count_stratum; j++) {
        rsk(ind_start(j) + n_each_prov(j) - 1) = haz(ind_start(j) + n_each_prov(j) - 1);
        for (int i = ind_start(j) + n_each_prov(j) - 2; i >= ind_start(j); i--) {
          rsk(i) = rsk(i + 1) + haz(i);
        }
      }
      if (use_ties) rsk = rsk.elem(tf);   // Breslow (1.3.0): the tie group's risk set
      for (int j = 0; j < count_stratum; j++) {
        h(ind_start(j)) = delta(ind_start(j)) / rsk(ind_start(j));
        for (int i = ind_start(j) + 1; i < ind_start(j) + n_each_prov(j); i++) {
          h(i) = h(i - 1) + delta(i) / rsk(i);
        }
      }
      if (use_ties) h = h.elem(tl);       // a row's cumulative hazard to the end of its tie group

      double a;
      for (int i = 0; i < n_obs; i++) {
        a = haz(i) * h(i);
        if (a == 0){
          r(i) = 0;
        } else {
          s =  delta(i) - a;
          r(i) = s/v;
        }
      }


      loss = 0.0;
      for (int i = 0; i < n_obs; i++) {
        loss += delta(i) * (eta(i) - std::log(rsk(i)));
      }

      if (K0 > 0) {
        arma::uvec update_order_unpenalized = arma::randperm(K0);
        for (int j = 0; j < K0; j++) {
          const int col = update_order_unpenalized(j);
          const double Qpp = Q(col, col);
          const double a_p = 1.0 + eta_mdtl * Qpp;
          const double c_p = mean_crossprod(Z, r, col, n_obs) + old_beta(col);
          const double t_p = c_p - eta_mdtl * ((Qbeta(col) - Qpp * beta(col)) - Qbeta_ext(col));
          const double beta_new = t_p / a_p;
          const double diff = beta_new - beta(col);
          if (diff != 0.0) {
            beta(col) = beta_new;
            r -= Z.col(col) * diff;
            eta += Z.col(col) * diff;
            Qbeta += Q.col(col) * diff;
            if (std::abs(diff) > MaxChange_beta) MaxChange_beta = std::abs(diff);
            df += 1.0;
          }
        }
      }

      for (int g = 0; g < n_group; g++) {
        if (active_group(g) == 1) {
          lambda_g = lambda * group_multiplier(g);
          gd_MDTL_enet(beta, Z, r, eta, old_beta, g, K1, n_obs, lambda_g, alpha,
                       eta_mdtl, Q, Qbeta_ext, Qbeta, df, MaxChange_beta);
        }
      }
      
      old_beta = beta;
      
     

      if (MaxChange_beta < tol) break;
    }

    if (actSet == true) {
      if (actSetRemove == true) {
        for (int g = 0; g < n_group; g++) {
          if (active_group(g) == 1) {
            if (beta(K1(g)) == 0) active_group(g) = 0;
          }
        }
      }
      arma::vec Current_len_group(n_group, arma::fill::zeros);
      for (int g = 0; g < n_group; g++) {
        if (active_group(g) == 0) {
          const double lambda_g2 = lambda * group_multiplier(g);
          Current_len_group(g) = gd_MDTL_BetaChange(Z, r, old_beta, g, K1, n_obs,
                                                    lambda_g2, alpha, eta_mdtl,
                                                    Q, Qbeta_ext, Qbeta, beta);
        }
      }
      int if_add_new = 0;
      const arma::uvec descend_len_index = arma::sort_index(Current_len_group, "descend");
      const arma::vec descend_len_value = arma::sort(Current_len_group, "descend");
      for (int i = 0; i < activeGroupNum; i++) {
        if (descend_len_value(i) != 0) {
          if_add_new++;
          active_group(descend_len_index(i)) = 1;
        } else break;
      }
      if (if_add_new == 0) break;
    } else break;
  }

  return std::make_tuple(beta, eta, loss, df, iter);
}


// [[Rcpp::export]]
List cox_MDTL_enet_cpp(const arma::vec &delta, const arma::mat &Z, const arma::vec &n_each_prov,
                       arma::vec &beta, const int K0, const arma::vec &K1,
                       const arma::vec &lambda_seq, const bool lambda_early_stop, const double stop_loss_ratio,
                       const arma::vec &group_multiplier, const int max_total_iter, const int max_each_iter,
                       const double tol, const int initial_active_group, const double nvar_max,
                       const double group_max, const bool trace_lambda, const bool actSet, const int actIter,
                       const int activeGroupNum, const bool actSetRemove, const double alpha, const double eta_mdtl,
                       const arma::mat &vcov, const arma::vec &Qbeta_ext,
                       Rcpp::Nullable<Rcpp::IntegerVector> tie_first = R_NilValue,
                       Rcpp::Nullable<Rcpp::IntegerVector> tie_last = R_NilValue) {
  const bool use_ties = tie_first.isNotNull() && tie_last.isNotNull();
  const arma::uvec tf = tie_index(tie_first, Z.n_rows), tl = tie_index(tie_last, Z.n_rows);

  const int n_obs = Z.n_rows, n_beta = Z.n_cols, n_lambda = lambda_seq.n_elem, n_group = K1.n_elem - 1;
  int tol_iter = 0;
  const int count_stratum = n_each_prov.n_elem;

  arma::mat beta_matrix(n_beta, n_lambda, arma::fill::zeros);
  arma::mat eta_matrix(n_obs, n_lambda, arma::fill::zeros);
  arma::vec iter_vec(n_lambda, arma::fill::zeros);
  arma::vec df_vec(n_lambda, arma::fill::zeros);
  arma::vec loss_vec(n_lambda, arma::fill::zeros);
  arma::vec active_group(n_group, arma::fill::zeros);

  if (actSet == true) {
    if (K0 == 0) {
      if (initial_active_group >= 0 && initial_active_group < n_group) active_group(initial_active_group) = 1;
      else active_group(0) = 1;
    }
  } else {
    active_group.ones();
  }

  arma::vec ind_start(count_stratum);
  ind_start(0) = 0;
  for (int i = 1; i < count_stratum; i++) {
    ind_start(i) = ind_start(i - 1) + n_each_prov(i - 1);
  }

  arma::vec eta = Z * beta;

  for (int l = 0; l < n_lambda; l++) {
    R_CheckUserInterrupt();
    if (trace_lambda == true) {
      Rcout << "processing lambda: " << l + 1 << " (total: " << l + 1 << "/" << n_lambda << ")..." << std::endl;
    }
    const double lambda = lambda_seq(l);

    arma::vec beta_l = beta, eta_l = eta;
    double loss_l, df_l;
    int iter_l;

    std::tie(beta_l, eta_l, loss_l, df_l, iter_l) =
      Cox_MDTL_enet_fit(delta, Z, n_each_prov, beta_l, eta_l, K0, K1, lambda, alpha, eta_mdtl,
                        vcov, Qbeta_ext, tol_iter, max_total_iter, max_each_iter, group_multiplier,
                        count_stratum, tol, ind_start, active_group, n_obs, n_group,
                        actSet, actIter, activeGroupNum, actSetRemove, tf, tl, use_ties);

    beta = beta_l;
    eta = eta_l;
    beta_matrix.col(l) = beta_l;
    eta_matrix.col(l) = eta_l;
    loss_vec(l) = loss_l;
    df_vec(l) = df_l;
    iter_vec(l) = iter_l;

    if (iter_l == max_each_iter) {
      if (trace_lambda == true){
        Rcout << "Warning: lambda " << l + 1 << "/" << n_lambda << " failed to converge within "
              << max_each_iter << " iterations!" << std::endl;
      }
    }

    int ng = 0, nv = 0;
    for (int g = 0; g < n_group; g++) {
      if (beta(K1(g)) != 0) {
        ng++;
        nv += (K1(g + 1) - K1(g));
      }
    }
    if (ng > group_max || nv > nvar_max || tol_iter == max_total_iter) {
      for (int ll = (l + 1); ll < n_lambda; ll++) {
        iter_vec(ll) = NA_REAL;
      }
      break;
    }

    if (lambda_early_stop == true && l != 0) {
      const double null_lkd = loss_vec(0);
      const double loss_ratio = std::fabs((loss_vec(l) - loss_vec(l - 1)) / (loss_vec(l) - null_lkd));
      if (loss_ratio < stop_loss_ratio) {
        for (int ll = (l + 1); ll < n_lambda; ll++) {
          iter_vec(ll) = NA_REAL;
        }
        break;
      }
    }
  }

  return List::create(_["beta"] = beta_matrix, _["loss"] = loss_vec,
                      _["LinPred"] = eta_matrix, _["Df"] = df_vec,
                      _["iter"] = iter_vec);
}
