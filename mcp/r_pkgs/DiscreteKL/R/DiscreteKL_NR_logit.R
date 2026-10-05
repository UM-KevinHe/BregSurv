kl_logit <- function(day_prior, beta_prior, eta_min, eta_max, eta_interval, df_input)
{
  eta_vec <- seq(from = eta_min, to = eta_max, by = eta_interval)
  df_input <- as.data.frame(df_input)
  likelihood <- eta_vec - eta_vec
  X_input <- dplyr::select(df_input, -c("time", "status"))
  
  folds <- cut(seq(1,nrow(df_input)),breaks=5,labels=FALSE)
  
  k=0
  for (eta in eta_vec)
  {
    k=k+1
    likelihood_cv = rep(0, 5)
    for (cv in 1:5)
    {
      testIndexes <- which(folds==cv,arr.ind=TRUE)
      df_test <- df_input[testIndexes, ]
      df_train <- df_input[-testIndexes, ]
      X_train <- dplyr::select(df_train, -c("time", "status"))
      X_test <- dplyr::select(df_test, -c("time", "status"))
      est_KL=discSurvKL_logit(df_train$time, X_train, df_train$status, tol = 1e-20, max_iter = 25, day_prior, beta_prior, eta)
      likelihood_cv[cv] <- DiscLoglik_logit(df_test$time, X_test, df_test$status,est_KL$beta_t,est_KL$beta_v)
    }
    likelihood[k] <- mean(likelihood_cv)
  }
  max_loc <- which(likelihood==max(likelihood))
  eta_where_max <- eta_vec[max_loc][1]
  
  est_KL_final=discSurvKL_logit(df_input$time, X_input, df_input$status, tol = 1e-20, max_iter = 25, day_prior, beta_prior, eta_where_max)
  return_list <- list("model"=est_KL_final, "eta"= eta_where_max, "likelihood"=likelihood)
  return(return_list)
}

discSurv_logit<-function(t, X, ind, tol = 1e-20, max_iter = 25){
  maxt=max(t)
  c=ncol(X)
  r=nrow(X)
  # order t
  od=order(t,decreasing = T)
  t=t[od]
  ind=ind[od]
  X=X[od,]
  
  # formatting
  ind=as.matrix(ind)
  beta_t=as.matrix(rep(0,maxt))
  beta_v=as.matrix(rep(0,c))
  t=as.matrix(t)
  X=as.matrix(X)
  
  return (NR_logit(t, X, ind, beta_t, beta_v, tol, max_iter))
}

discSurvKL_logit<-function(t, X, ind, tol = 1e-20, max_iter = 25, beta_t_tilde, beta_v_tilde, eta){
  maxt=max(t)
  c=ncol(X)
  r=nrow(X)
  # order t
  od=order(t,decreasing = T)
  t=t[od]
  ind=ind[od]
  X=X[od,]
  
  # formatting
  ind=as.matrix(ind)
  beta_t=as.matrix(rep(0,maxt))
  beta_v=as.matrix(rep(0,c))
  t=as.matrix(t)
  beta_t_tilde=as.matrix(beta_t_tilde)
  beta_v_tilde=as.matrix(beta_v_tilde)
  X=as.matrix(X)
  
  return (NRKL_logit(t, X, ind, beta_t, beta_v, tol, max_iter, beta_t_tilde, beta_v_tilde, eta))
}

DiscLoglik_logit<-function(t, X, ind, beta_t, beta_v){
  maxt=max(t)
  c=ncol(X)
  r=nrow(X)
  # order t
  od=order(t,decreasing = T)
  t=t[od]
  ind=ind[od]
  X=X[od,]
  
  # formatting
  ind=as.matrix(ind)
  beta_t=as.matrix(beta_t)
  beta_v=as.matrix(beta_v)
  t=as.matrix(t)
  X=as.matrix(X)
  
  return (Update_logit(t, X, ind, beta_t, beta_v, maxt, c, r)$loglik)
}


