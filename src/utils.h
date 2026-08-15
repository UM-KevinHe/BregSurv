// shared_functions.h
#ifndef UTILS_H
#define UTILS_H

#include <RcppArmadillo.h>

arma::vec rev_cumsum(const arma::vec& X);

arma::vec calculateDeltaTilde(const arma::vec& event, 
                              const arma::vec& time, 
                              const arma::vec& theta_tilde,
                              const arma::vec& n_each_stratum);

double pl_cal_theta(const arma::vec& lp,
                    const arma::vec& delta,
                    const arma::vec& n_each_stratum);


arma::umat combn_index(int n, int r);

double mean_crossprod(const arma::mat &Z, const arma::vec &r, const int j, const int n_obs);

double Soft_thres(const double z, const double l);

void gd_KLCox_highdim(arma::vec &beta, const arma::mat &Z, arma::vec &r, arma::vec &LinPred, arma::vec &old_beta, 
                      int g, const arma::vec &K1, const int n_obs, double &lam1, double &lam2, 
                      double &df, double &MaxChange_beta);

double gd_KLCox_highdim_betaChange(const arma::mat &Z, arma::vec &r, int g, const arma::vec &K1, 
                                   const int n_obs, double &lam1, double &lam2);

#endif // UTILS_H
