#include <Rcpp.h>
#include <RcppEigen.h>
#include <math.h>
//[[Rcpp::depends(RcppEigen)]]

using namespace Rcpp;
using Eigen::MatrixXd;

// all the input must be sorted according to t, large->small.  
  
// [[Rcpp::export]]
List Update_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v, int max_t, int c, int r){
  double loglik=0;
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  Eigen::MatrixXd info_t(max_t,1);
  info_t.setZero(max_t,1);
  Eigen::MatrixXd info_v(c,c);
  info_v.setZero(c,c);
  Eigen::MatrixXd info_tv(max_t,c);
  info_tv.setZero(max_t,c);
  
  
  for (int i = 0 ; i < r ; i++){
    for (int s = 1 ; s <= t(i,0) ; s++){
        double lambda=1/(1+exp(-beta_t(s-1,0)-(X.row(i)*beta_v)(0,0)));
        score_t(s-1,0)=score_t(s-1,0)-lambda;
        score_v=score_v-lambda*X.row(i).transpose();
        info_t(s-1,0)=info_t(s-1,0)+lambda*(1-lambda);
        info_v=info_v+(lambda*(1-lambda))*(X.row(i).transpose()*X.row(i));
        info_tv.row(s-1)=info_tv.row(s-1)+(lambda*(1-lambda))*X.row(i);
        if (t(i,0) == s and ind(i,0) == 1){
          loglik=loglik+log(lambda);
          score_t(s-1,0)=score_t(s-1,0)+1;
          score_v=score_v+X.row(i).transpose();
        }
        else {
          loglik=loglik+log(1-lambda);
        }
      
    }
  }
  
  
  List result;
  result["loglik"]=loglik;
  result["score_t"]=score_t;
  result["score_v"]=score_v;
  result["info_t"]=info_t;
  result["info_tv"]=info_tv;
  result["info_v"]=info_v;
  
  
  return result;
}

// [[Rcpp::export]]
List UpdateKL_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd delta, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v, int max_t, int c, int r, Eigen::MatrixXd beta_t_tilde, Eigen::MatrixXd beta_v_tilde, double eta){
  double loglik=0;
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  Eigen::MatrixXd info_t(max_t,1);
  info_t.setZero(max_t,1);
  Eigen::MatrixXd info_v(c,c);
  info_v.setZero(c,c);
  Eigen::MatrixXd info_tv(max_t,c);
  info_tv.setZero(max_t,c);
  Eigen::MatrixXd LP_tilde(r,1);
  LP_tilde.setZero(r,1); 
  
  LP_tilde=X*beta_v_tilde;
  for (int i = 0 ; i < r ; i++){
    for (int s = 1 ; s <= t(i,0) ; s++){
        double delta_tilde=1/(1+exp(-LP_tilde(i,0)-beta_t_tilde(s-1,0)));
        double lambda=1/(1+exp(-beta_t(s-1,0)-(X.row(i)*beta_v)(0,0)));
        loglik=loglik+log(1-lambda);
        score_t(s-1,0)=score_t(s-1,0)-lambda;
        score_v=score_v-lambda*X.row(i).transpose();
        info_t(s-1,0)=info_t(s-1,0)+lambda*(1-lambda);
        info_v=info_v+(lambda*(1-lambda))*(X.row(i).transpose()*X.row(i));
        info_tv.row(s-1)=info_tv.row(s-1)+(lambda*(1-lambda))*X.row(i);
        
        if (t(i,0) != s){
          double delta_prime=(eta*delta_tilde)/(1+eta);
          loglik=loglik+delta_prime*log(lambda)-delta_prime*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime;
          score_v=score_v+delta_prime*X.row(i).transpose();
        }
        if (t(i,0) == s){
          double delta_prime=(delta(i,0)+(eta*delta_tilde))/(1+eta);
          loglik=loglik+delta_prime*log(lambda)-delta_prime*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime;
          score_v=score_v+delta_prime*X.row(i).transpose();
        }
        //if (t(i,0) == s and ind(i,0) == 1){
        //  loglik=loglik+log(lambda);
        //  score_t(s-1,0)=score_t(s-1,0)+1;
        //  score_v=score_v+X.row(i).transpose();
        //}
        //else {
        //  loglik=loglik+log(1-lambda);
        //}   
    }
  }
  
  
  List result;
  result["loglik"]=loglik;
  result["score_t"]=score_t;
  result["score_v"]=score_v;
  result["info_t"]=info_t;
  result["info_tv"]=info_tv;
  result["info_v"]=info_v;
  
  
  return result;
}



// [[Rcpp::export]]
List NR_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v,double tol, int max_iter){
  int r = X.rows();
  int c = X.cols();
  int max_t=t.maxCoeff();
  Eigen::MatrixXd beta2_t=beta_t;
  Eigen::MatrixXd beta2_v=beta_v;
  Eigen::MatrixXd A_inv(max_t,max_t);
  A_inv.setZero(max_t,max_t);
  Eigen::MatrixXd A(max_t,1);
  A.setZero(max_t,1);
  Eigen::MatrixXd B(max_t,c);
  B.setZero(max_t,c);
  Eigen::MatrixXd C(c,c);
  C.setZero(c,c);
  Eigen::MatrixXd schur(c,c);
  schur.setZero(c,c);
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  Eigen::MatrixXd loglik_vec(1, max_iter+1); 
  loglik_vec.setZero(1, max_iter+1);
  List result;
  double ll,ll2;
  List update=Update_logit(t,X,ind,beta_t,beta_v,max_t,c,r);
  ll=update["loglik"];
  ll2=ll;
  for (int i = 0 ; i<=max_iter ; i++){
    A=update["info_t"];
    B=update["info_tv"];
    C=update["info_v"];
    score_t=update["score_t"];
    score_v=update["score_v"];
    A=A.array().inverse();
    A_inv=A.asDiagonal();
    schur=(C-(B.transpose())*(A_inv)*(B)).inverse();
    beta2_t=beta_t+(A_inv+A_inv*B*schur*(B.transpose())*A_inv)*score_t-A_inv*B*schur*score_v;
    beta2_v=beta_v+schur*score_v-schur*(B.transpose())*A_inv*score_t;
    
    update=Update_logit(t,X,ind,beta2_t,beta2_v,max_t,c,r);
    ll2=update["loglik"];
    loglik_vec(0,i) = ll2;
    
    result["beta_t"]=beta2_t;
    result["beta_v"]=beta2_v;
    result["loglik"]=ll2;
    result["iter"]=i;
    result["ll_path"]=loglik_vec;

    if((ll2-ll)*(ll2-ll)<tol){
      return result;
    }
    ll=ll2;
    beta_t=beta2_t;
    beta_v=beta2_v;
  }
  return result;
}


// [[Rcpp::export]]
List NRKL_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v,double tol, int max_iter, Eigen::MatrixXd beta_t_tilde, Eigen::MatrixXd beta_v_tilde, double eta){
  int r = X.rows();
  int c = X.cols();
  int max_t=t.maxCoeff();
  Eigen::MatrixXd beta2_t=beta_t;
  Eigen::MatrixXd beta2_v=beta_v;
  Eigen::MatrixXd A_inv(max_t,max_t);
  A_inv.setZero(max_t,max_t);
  Eigen::MatrixXd A(max_t,1);
  A.setZero(max_t,1);
  Eigen::MatrixXd B(max_t,c);
  B.setZero(max_t,c);
  Eigen::MatrixXd C(c,c);
  C.setZero(c,c);
  Eigen::MatrixXd schur(c,c);
  schur.setZero(c,c);
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  List result;
  double ll,ll2;
  List update=UpdateKL_logit(t,X,ind,beta_t,beta_v,max_t,c,r,beta_t_tilde,beta_v_tilde,eta);
  ll=update["loglik"];
  ll2=ll;
  for (int i = 0 ; i<=max_iter ; i++){
    A=update["info_t"];
    B=update["info_tv"];
    C=update["info_v"];
    score_t=update["score_t"];
    score_v=update["score_v"];
    A=A.array().inverse();
    A_inv=A.asDiagonal();
    schur=(C-(B.transpose())*(A_inv)*(B)).inverse();
    beta2_t=beta_t+(A_inv+A_inv*B*schur*(B.transpose())*A_inv)*score_t-A_inv*B*schur*score_v;
    beta2_v=beta_v+schur*score_v-schur*(B.transpose())*A_inv*score_t;
    
    update=UpdateKL_logit(t,X,ind,beta2_t,beta2_v,max_t,c,r,beta_t_tilde,beta_v_tilde,eta);
    ll2=update["loglik"];
      
    result["beta_t"]=beta2_t;
    result["beta_v"]=beta2_v;
    result["loglik"]=ll2;

    if((ll2-ll)*(ll2-ll)<tol){
      return result;
    }
    ll=ll2;
    beta_t=beta2_t;
    beta_v=beta2_v;
  }
  return result;
}

// [[Rcpp::export]]
List UpdateKL2_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd delta, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v, int max_t, int c, int r, Eigen::MatrixXd beta_t_tilde1, Eigen::MatrixXd beta_v_tilde1, double eta1, Eigen::MatrixXd beta_t_tilde2, Eigen::MatrixXd beta_v_tilde2, double eta2){
  double loglik=0;
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  Eigen::MatrixXd info_t(max_t,1);
  info_t.setZero(max_t,1);
  Eigen::MatrixXd info_v(c,c);
  info_v.setZero(c,c);
  Eigen::MatrixXd info_tv(max_t,c);
  info_tv.setZero(max_t,c);
  Eigen::MatrixXd LP_tilde1(r,1);
  LP_tilde1.setZero(r,1); 
  Eigen::MatrixXd LP_tilde2(r,1);
  LP_tilde2.setZero(r,1); 
  
  LP_tilde1=X*beta_v_tilde1;
  LP_tilde2=X*beta_v_tilde2;

  for (int i = 0 ; i < r ; i++){
    for (int s = 1 ; s <= t(i,0) ; s++){
        double delta_tilde1=1/(1+exp(-LP_tilde1(i,0)-beta_t_tilde1(s-1,0)));
        double delta_tilde2=1/(1+exp(-LP_tilde2(i,0)-beta_t_tilde2(s-1,0)));

        double lambda=1/(1+exp(-beta_t(s-1,0)-(X.row(i)*beta_v)(0,0)));
        loglik=loglik+log(1-lambda);
        score_t(s-1,0)=score_t(s-1,0)-lambda;
        score_v=score_v-lambda*X.row(i).transpose();
        info_t(s-1,0)=info_t(s-1,0)+lambda*(1-lambda);
        info_v=info_v+(lambda*(1-lambda))*(X.row(i).transpose()*X.row(i));
        info_tv.row(s-1)=info_tv.row(s-1)+(lambda*(1-lambda))*X.row(i);
        
        if (t(i,0) != s){
          double delta_prime=(eta1*delta_tilde1+eta2*delta_tilde2)/(1+eta1+eta2);
          loglik=loglik+delta_prime*log(lambda)-delta_prime*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime;
          score_v=score_v+delta_prime*X.row(i).transpose();
        }
        if (t(i,0) == s){
          double delta_prime=(delta(i,0)+(eta1*delta_tilde1+eta2*delta_tilde2))/(1+eta1+eta2);
          loglik=loglik+delta_prime*log(lambda)-delta_prime*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime;
          score_v=score_v+delta_prime*X.row(i).transpose();
        }  
    }
  }
  
  
  List result;
  result["loglik"]=loglik;
  result["score_t"]=score_t;
  result["score_v"]=score_v;
  result["info_t"]=info_t;
  result["info_tv"]=info_tv;
  result["info_v"]=info_v;
  
  
  return result;
}

// [[Rcpp::export]]
List NRKL2_logit(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v,double tol, int max_iter, Eigen::MatrixXd beta_t_tilde1, Eigen::MatrixXd beta_v_tilde1, double eta1, Eigen::MatrixXd beta_t_tilde2, Eigen::MatrixXd beta_v_tilde2, double eta2){
  int r = X.rows();
  int c = X.cols();
  int max_t=t.maxCoeff();
  Eigen::MatrixXd beta2_t=beta_t;
  Eigen::MatrixXd beta2_v=beta_v;
  Eigen::MatrixXd A_inv(max_t,max_t);
  A_inv.setZero(max_t,max_t);
  Eigen::MatrixXd A(max_t,1);
  A.setZero(max_t,1);
  Eigen::MatrixXd B(max_t,c);
  B.setZero(max_t,c);
  Eigen::MatrixXd C(c,c);
  C.setZero(c,c);
  Eigen::MatrixXd schur(c,c);
  schur.setZero(c,c);
  Eigen::MatrixXd score_t(max_t,1);
  score_t.setZero(max_t,1);
  Eigen::MatrixXd score_v(c,1);
  score_v.setZero(c,1);
  List result;
  double ll,ll2;
  List update=UpdateKL2_logit(t,X,ind,beta_t,beta_v,max_t,c,r,beta_t_tilde1,beta_v_tilde1,eta1,beta_t_tilde2,beta_v_tilde2,eta2);
  ll=update["loglik"];
  ll2=ll;
  for (int i = 0 ; i<=max_iter ; i++){
    A=update["info_t"];
    B=update["info_tv"];
    C=update["info_v"];
    score_t=update["score_t"];
    score_v=update["score_v"];
    A=A.array().inverse();
    A_inv=A.asDiagonal();
    schur=(C-(B.transpose())*(A_inv)*(B)).inverse();
    beta2_t=beta_t+(A_inv+A_inv*B*schur*(B.transpose())*A_inv)*score_t-A_inv*B*schur*score_v;
    beta2_v=beta_v+schur*score_v-schur*(B.transpose())*A_inv*score_t;
    
    update=UpdateKL2_logit(t,X,ind,beta2_t,beta2_v,max_t,c,r,beta_t_tilde1,beta_v_tilde1,eta1,beta_t_tilde2,beta_v_tilde2,eta2);
    ll2=update["loglik"];
    
    result["beta_t"]=beta2_t;
    result["beta_v"]=beta2_v;
    result["loglik"]=ll2;

    if((ll2-ll)*(ll2-ll)<tol){
      return result;
    }
    ll=ll2;
    beta_t=beta2_t;
    beta_v=beta2_v;
  }
  return result;
}

