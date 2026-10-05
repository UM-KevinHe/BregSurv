#include <Rcpp.h>
#include <RcppEigen.h>
#include <math.h>
//[[Rcpp::depends(RcppEigen)]]

using namespace Rcpp;
using namespace std;
using Eigen::MatrixXd;
using std::numeric_limits;

// all the input must be sorted according to t, large->small.  
  
// [[Rcpp::export]]
List Update_cloglog(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v, int max_t, int c, int r, double epsilon){
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
        //double lambda=1/(1+exp(-beta_t(s-1,0)-(X.row(i)*beta_v)(0,0)));
        double u=beta_t(s-1,0)+(X.row(i)*beta_v)(0,0);
        // logit link
        //double lambda=1/(1+exp(-u));
        //double lambda_prime = lambda*(1-lambda);
        //double lambda_prime2 = lambda*(1-lambda)*(1-2*lambda); 
        // cloglog link 
        //double lambda=1-exp(-exp(u));
        //double lambda_prime = exp(u)*(1-lambda);
        //double lambda_prime2 = lambda_prime*(1-exp(u));
        Eigen::MatrixXd lambdamin(2,1);
        lambdamin.setZero(2,1);  
        Eigen::MatrixXd lambdamax(2,1);
        lambdamax.setZero(2,1); 
        lambdamin(1,0)=1-epsilon;
        lambdamax(1,0)=epsilon;
        lambdamin(0,0)=1-exp(-exp(u));
        lambdamax(0,0)=lambdamin.minCoeff();
        double lambda=lambdamax.maxCoeff();;
        double lambda_prime = exp(u)*(1-lambda);
        double lambda_prime2 = lambda_prime*(1-exp(u));
        double ratio1 = lambda_prime/lambda;
        double ratio2 = lambda_prime/(1-lambda);
        double ratio3 = (lambda_prime2/lambda)-(ratio1*ratio1);
        double ratio4 = (lambda_prime2/(1-lambda))+(ratio2*ratio2);
        if (t(i,0) == s and ind(i,0) == 1){
          loglik=loglik+log(lambda);
          score_t(s-1,0)=score_t(s-1,0)+ratio1;
          score_v=score_v+ratio1*X.row(i).transpose();
          info_t(s-1,0)=info_t(s-1,0)-ratio3;
          info_v=info_v-ratio3*(X.row(i).transpose()*X.row(i));
          info_tv.row(s-1)=info_tv.row(s-1)+(-ratio3)*X.row(i);
        }
        else {
          loglik=loglik+log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)-ratio2;
          score_v=score_v-ratio2*X.row(i).transpose();
          info_t(s-1,0)=info_t(s-1,0)+ratio4;
          info_v=info_v+ratio4*(X.row(i).transpose()*X.row(i));
          info_tv.row(s-1)=info_tv.row(s-1)+(ratio4)*X.row(i);
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
List UpdateKL_cloglog(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd delta, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v, int max_t, int c, int r, Eigen::MatrixXd beta_t_tilde, Eigen::MatrixXd beta_v_tilde, double eta, double epsilon){
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
        double u=beta_t(s-1,0)+(X.row(i)*beta_v)(0,0);      
        // logit link
        //double delta_tilde=1/(1+exp(-LP_tilde(i,0)-beta_t_tilde(s-1,0)));    
        //double lambda=1/(1+exp(-u));
        //double lambda_prime = lambda*(1-lambda);
        //double lambda_prime2 = lambda*(1-lambda)*(1-2*lambda); 
        // cloglog link 
        double u_tilde=LP_tilde(i,0)+beta_t_tilde(s-1,0);
        double delta_tilde=1-exp(-exp(u_tilde));
        //double lambda=1-exp(-exp(u));
        //double lambda_prime = exp(u)*(1-lambda);
        //double lambda_prime2 = lambda_prime*(1-exp(u));
        Eigen::MatrixXd lambdamin(2,1);
        lambdamin.setZero(2,1);  
        Eigen::MatrixXd lambdamax(2,1);
        lambdamax.setZero(2,1); 
        lambdamin(1,0)=1-epsilon;
        lambdamax(1,0)=epsilon;
        lambdamin(0,0)=1-exp(-exp(u));
        lambdamax(0,0)=lambdamin.minCoeff();
        double lambda=lambdamax.maxCoeff();
        double lambda_prime = exp(u)*(1-lambda);
        double lambda_prime2 = lambda_prime*(1-exp(u));
        double ratio1 = lambda_prime/lambda;
        double ratio2 = lambda_prime/(1-lambda);
        double ratio3 = (lambda_prime2/lambda)-(ratio1*ratio1);
        double ratio4 = (lambda_prime2/(1-lambda))+(ratio2*ratio2);

        if (t(i,0) != s){
          double delta_prime=(eta*delta_tilde)/(1+eta);
          loglik=loglik+delta_prime*log(lambda)+(1-delta_prime)*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime*ratio1+(1-delta_prime)*(-ratio2);
          score_v=score_v+delta_prime*ratio1*X.row(i).transpose()+(1-delta_prime)*(-ratio2)*X.row(i).transpose();
          info_t(s-1,0)=info_t(s-1,0)+delta_prime*(-ratio3)+(1-delta_prime)*ratio4;
          info_v=info_v+delta_prime*(-ratio3)*(X.row(i).transpose()*X.row(i))+(1-delta_prime)*ratio4*(X.row(i).transpose()*X.row(i));
          info_tv.row(s-1)=info_tv.row(s-1)+delta_prime*(-ratio3)*X.row(i)+(1-delta_prime)*ratio4*X.row(i);
        }
        if (t(i,0) == s){
          double delta_prime=(delta(i,0)+(eta*delta_tilde))/(1+eta);
          loglik=loglik+delta_prime*log(lambda)+(1-delta_prime)*log(1-lambda);
          score_t(s-1,0)=score_t(s-1,0)+delta_prime*ratio1+(1-delta_prime)*(-ratio2);
          score_v=score_v+delta_prime*ratio1*X.row(i).transpose()+(1-delta_prime)*(-ratio2)*X.row(i).transpose();
          info_t(s-1,0)=info_t(s-1,0)+delta_prime*(-ratio3)+(1-delta_prime)*ratio4;
          info_v=info_v+delta_prime*(-ratio3)*(X.row(i).transpose()*X.row(i))+(1-delta_prime)*ratio4*(X.row(i).transpose()*X.row(i));
          info_tv.row(s-1)=info_tv.row(s-1)+delta_prime*(-ratio3)*X.row(i)+(1-delta_prime)*ratio4*X.row(i);
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
List NR_cloglog(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v,double tol, int max_iter, double epsilon){
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
  List update=Update_cloglog(t,X,ind,beta_t,beta_v,max_t,c,r, epsilon);
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
    
    update=Update_cloglog(t,X,ind,beta2_t,beta2_v,max_t,c,r, epsilon);
    ll2=update["loglik"];
    
    result["beta_t"]=beta2_t;
    result["beta_v"]=beta2_v;
    result["loglik"]=ll2;
    result["iter"]=i;

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
List NRKL_cloglog(Eigen::MatrixXd t, Eigen::MatrixXd X, Eigen::MatrixXd ind, Eigen::MatrixXd beta_t, Eigen::MatrixXd beta_v,double tol, int max_iter, Eigen::MatrixXd beta_t_tilde, Eigen::MatrixXd beta_v_tilde, double eta, double epsilon){
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
  List update=UpdateKL_cloglog(t,X,ind,beta_t,beta_v,max_t,c,r,beta_t_tilde,beta_v_tilde,eta,epsilon);
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
    
    update=UpdateKL_cloglog(t,X,ind,beta2_t,beta2_v,max_t,c,r,beta_t_tilde,beta_v_tilde,eta,epsilon);
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

