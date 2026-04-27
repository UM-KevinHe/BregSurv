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


tuple<arma::vec, arma::vec, double, double, int> KL_Cox_highdim_fit(const arma::mat &Z, const arma::vec &delta, const arma::vec& delta_tilde, arma::vec beta, const double &eta, 
                                                                    const arma::vec &ind_start, const arma::vec &n_each_stratum, arma::vec LinPred, const int &K0, const arma::vec &K1, 
                                                                    const double &lambda, const double &alpha, int &total_iter, const int &max_total_iter, const int &max_each_iter, 
                                                                    const arma::vec &group_multiplier, const arma::uword S, const double &tol, arma::vec &active_group, 
                                                                    const int &n_obs, const int &n_group, const bool &actSet, const int &actIter, const int &activeGroupNum, const bool &actSetRemove){

  arma::vec old_beta = beta, r(n_obs), r_shift;
  arma::vec haz(n_obs), rsk(n_obs), h(n_obs); // (1) haz: exp(LinPred); (2) rsk: sum(haz); (3) h: sum(delta/sum(haz));
  double loss = 0, df = 0, MaxChange_beta = 0, shift = 0;
  double s = 0, v = 1.0; // (1) s: l'(LinPred); (2) v: -l''(LinPred) approximate to 1
  int iter = 0; 

  double lam1_g, lam2_g;

  while (total_iter < max_total_iter) {
    int inner_loop_iter = -1;
    inner_loop_iter = inner_loop_iter +1; //just for removing unused warning.
    R_CheckUserInterrupt();
    while (total_iter < max_total_iter && iter < max_each_iter) {
      R_CheckUserInterrupt();
      df = 0;
      total_iter++;
      iter++;
      inner_loop_iter++;
      MaxChange_beta = 0;


      // calculate haz and rsk
      haz = arma::exp(LinPred);
      for (arma::uword j = 0; j < S; ++j){
        const arma::uword start = ind_start(j);
        const arma::uword len = n_each_stratum(j);
        const arma::uword end = start + len - 1;

        rsk.subvec(start, end) = rev_cumsum(haz.subvec(start, end));
        arma::vec h_i = delta.subvec(start, end) / rsk.subvec(start, end);
        h.subvec(start, end) = arma::cumsum(h_i);
      }


      loss = 0; //loss: current likelihood function (before update beta), without penalty term.
      for (int i = 0; i < n_obs; ++i){ 
        double a = haz(i) * h(i); // a: exp(LinPred) * [sum(delta/sum(exp(LinPred)))]
        double weighted_term = (delta(i) + eta * delta_tilde(i)) / (1 + eta);
        loss += weighted_term * LinPred(i) - delta(i) * log(rsk(i));

        if (a == 0){  //where delta(i) == 0 and haz(i) * h(i) == 0
          r(i) = (eta * delta_tilde(i)) / (1 + eta); // pseudo residual
        } else {
          s = weighted_term - a; // s: l'(LinPred) - l''(LinPred) * LinPred
          r(i) = s/v; 
        }
      }

      /* 1. Update unpenalized groups */
      arma::uvec update_order_unpenalized = randperm(K0); //randomly update
      for (int j = 0; j < K0; ++j){  // If K0 is zero, then the whole iteration will be skipped
        shift = mean_crossprod(Z, r, update_order_unpenalized(j), n_obs);
        if (fabs(shift) > MaxChange_beta) {
          MaxChange_beta = fabs(shift);
        }
        beta(update_order_unpenalized(j)) = old_beta(update_order_unpenalized(j)) + shift;
        arma::vec shift_LinPred = Z.col(update_order_unpenalized(j)) * shift;
        r -= shift_LinPred;
        LinPred += shift_LinPred;
        df++;
      }

      /* 2. Update penalized groups */
      // note that all groups are iterated if user choose not using the "active set method"
      for (int g = 0; g < n_group; ++g){
        if (active_group(g) == 1){
          lam1_g = lambda * alpha * group_multiplier(g);
          lam2_g = lambda * (1 - alpha) * group_multiplier(g);
          gd_KLCox_highdim(beta, Z, r, LinPred, old_beta, g, K1, n_obs, lam1_g, lam2_g, df, MaxChange_beta);
        }
      }
      old_beta = beta;

      if (MaxChange_beta < tol){
        break;
      }
    }

    if (actSet == true){
    // update active set
      if (actSetRemove == true){
        for (int g = 0; g < n_group; ++g){
          if (active_group(g) == 1) {
            if (beta(K1(g)) == 0){
              active_group(g) = 0;
            }
          }
        }
      }
      // check whether "non-active" groups can still be updated; if not, algorithm ends
      arma::vec Current_len_group(n_group, fill::zeros);
      for (int g = 0; g < n_group; ++g) {
        if (active_group(g) == 0) {
          lam1_g = lambda * alpha * group_multiplier(g);
          lam2_g = lambda * (1 - alpha) * group_multiplier(g);
          Current_len_group(g) = gd_KLCox_highdim_betaChange(Z, r, g, K1, n_obs, lam1_g, lam2_g);
        }
      }

      int if_add_new = 0; 
      arma::uvec descend_len_index = sort_index(Current_len_group, "descend");
      arma::vec descend_len_value = sort(Current_len_group, "descend");

      for (int i = 0; i < activeGroupNum; ++i){
        if (descend_len_value(i)!= 0){
          if_add_new++;
          active_group(descend_len_index(i)) = 1;
        } else { 
          break;
        }
      }

      if (if_add_new == 0){ 
        break;
      }
    } else { 
      break;
    }
  }

  return make_tuple(beta, LinPred, loss, df, iter);

}

// [[Rcpp::export]]
List KL_Cox_highdim(const arma::mat& Z, const arma::vec& delta, const arma::vec& delta_tilde, const double &eta,
                    const arma::vec& n_each_stratum, arma::vec &beta, const arma::vec& K1, const int &K0,
                    const arma::vec &lambda_seq, const double &alpha, bool lambda_early_stop, double stop_loss_ratio, 
                    const arma::vec &group_multiplier, const int &max_total_iter, const int &max_each_iter, const double &tol, 
                    const int &initial_active_group, const double &nvar_max, const double &group_max, const bool &trace_lambda, 
                    const bool &actSet, const int &actIter, const int &activeGroupNum, const bool &actSetRemove) {
  int n_obs = delta.n_elem, n_beta = Z.n_cols, n_lambda = lambda_seq.n_elem, n_group = K1.n_elem - 1;
  int total_iter = 0;
  const arma::uword S = n_each_stratum.n_elem; // number of strata (i.e., number of providers)

  arma::mat beta_matrix(n_beta, n_lambda, fill::zeros); 
  arma::mat LinPred_matrix(n_obs, n_lambda, fill::zeros); // linear predictor
  arma::vec iter_vec(n_lambda, fill::zeros);  // number of iterations for each lambda
  arma::vec df_vec(n_lambda, fill::zeros); 
  arma::vec loss_vec(n_lambda, fill::zeros); //loss: likelihood function (without penalty)
  arma::vec active_group(n_group, fill::zeros);

  if (actSet == true){
    if (K0 == 0){ 
      active_group(initial_active_group) = 1;
    }
  } else {
    active_group.ones();
  }

  arma::vec ind_start(S); // index of the first observation within each provider
  ind_start(0) = 0;
  for (arma::uword i = 1; i < S; ++i) {
    ind_start(i) = ind_start(i - 1) + n_each_stratum(i - 1);
  }
 
  // initialize LinPred
  arma::vec LinPred = Z * beta;

  for (int l = 0; l < n_lambda; l++){
    R_CheckUserInterrupt();
    if (trace_lambda == true){
      Rcpp::Rcout << "processing lambda: " << l + 1 << " (total: " << l + 1 << "/" << n_lambda << ")..." << endl;
    }
    double lambda = lambda_seq(l);

    auto fit = KL_Cox_highdim_fit(
      Z, delta, delta_tilde, beta, eta, 
      ind_start, n_each_stratum, LinPred, K0, K1, 
      lambda, alpha, total_iter, max_total_iter, max_each_iter, 
      group_multiplier, S, tol, active_group, 
      n_obs, n_group, actSet, actIter, activeGroupNum, actSetRemove);

    double loss_l, df_l;
    int iter_l;
    tie(beta, LinPred, loss_l, df_l, iter_l) = fit;
    beta_matrix.col(l) = beta;
    LinPred_matrix.col(l) = LinPred;
    loss_vec(l) = loss_l;
    df_vec(l) = df_l;
    iter_vec(l) = iter_l;

    // check whether the iteration number for the current lambda has reached the maximum
    if (iter_l == max_each_iter) {
      if (trace_lambda == true){
        Rcpp::Rcout << "Warning: lambda " << l + 1 << "/" << n_lambda << " failed to converge within " << max_each_iter << " iterations!" << endl;
      }
    }

    // check dfmax, gmax; (note, "nv" doesn't equal "df")
    int ng = 0, nv = 0;
    for (int g = 0; g < n_group; ++g){
      if (beta(K1(g)) != 0){
         ng++;
         nv += (K1(g + 1) - K1(g));
      }
    }
    if (ng > group_max || nv > nvar_max || total_iter == max_total_iter) {
      if (total_iter == max_total_iter) {
        Rcpp::Rcout << "Algorithm has reached the maximum number of total iterations, stops..." << endl;
      } else if (ng > group_max) {
        Rcpp::Rcout << "Algorithm has selected the maximum number of groups, stops..." << endl;
      } else {
        Rcpp::Rcout << "Algorithm has selected the maximum number of variables, stops..." << endl;
      }

      for (int ll = (l + 1); ll < n_lambda; ll++){
        iter_vec(ll) = NA_REAL;
      }
      break;
    }

    if (lambda_early_stop == true){
      if (l != 0){
        double null_lkd = loss_vec(0);
        double loss_ratio = fabs((loss_vec(l) - loss_vec(l - 1))/(loss_vec(l) - null_lkd));
        if (loss_ratio < stop_loss_ratio){
          for (int ll = (l + 1); ll < n_lambda; ll++){
            iter_vec(ll) = NA_REAL;
          }
        break;
        }
      }
    }
  }

  List result = List::create(_["beta"] = beta_matrix, _["loss"] = loss_vec, _["LinPred"] = LinPred_matrix, _["Df"] = df_vec, _["iter"] = iter_vec);
  return result;
}