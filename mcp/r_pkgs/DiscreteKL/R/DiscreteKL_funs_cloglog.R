kl_cloglog <- function(day_prior, beta_prior, eta_min, eta_max, eta_interval, df_input)
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
      est_KL=discSurvKL_cloglog(df_train$time, X_train, df_train$status, tol = 1e-20, max_iter = 25, day_prior, beta_prior, eta)
      likelihood_cv[cv] <- DiscLoglik_cloglog(df_test$time, X_test, df_test$status,est_KL$beta_t,est_KL$beta_v)
    }
    likelihood[k] <- mean(likelihood_cv)
  }
  max_loc <- which(likelihood==max(likelihood))
  eta_where_max <- eta_vec[max_loc][1]
  
  est_KL_final=discSurvKL_cloglog(df_input$time, X_input, df_input$status, tol = 1e-20, max_iter = 25, day_prior, beta_prior, eta_where_max)
  return_list <- list("model"=est_KL_final, "eta"= eta_where_max, "likelihood"=likelihood)
  return(return_list)
}

AR1 <- function(tau, m) {
  if(m==1) {R <- 1}
  if(m > 1) {
    R <- diag(1, m)
    for(i in 1:(m-1)) {
      for(j in (i+1):m) {
        R[i,j] <- R[j,i] <- tau^(abs(i-j))
      }
    }
  }
  return(R)
}

simu_z <- function(n, size.groups)
{
  Sigma_z1=diag(size.groups) # =p
  Corr1<-AR1(0.5,size.groups) #correlation structure 0.5 0.6
  diag(Corr1) <- 1
  Sigma_z1<- Corr1
  pre_z= rmvnorm(n, mean=rep(0,size.groups), sigma=Sigma_z1)
  return(pre_z)
}

sim.disc.cloglog <- function(beta, eta, prov.size, Z.char, censor) {
  N <- prov.size 
  p_1 <- 0.5*length(beta)
  Z1 <- as.matrix(simu_z(N, p_1))
  Z2 <- matrix(rbinom(N*p_1,1,0.5),N,p_1)
  Z <- cbind(Z1, Z2)
  day <- 1 #1
  idx.atrisk <- 1:N
  days.to.event <- rep(length(eta), N)
  status <- rep(0, N)
  probs <- VGAM::cloglog((eta[1]+(as.matrix(Z)%*%beta)), bvalue=.Machine$double.eps, inverse=TRUE)
  idx.event <- idx.atrisk[rbinom(length(probs), 1, probs)==1]
  status[idx.event] <- 1
  days.to.event[idx.event] <- day
  idx.out <- idx.event
  censoring=runif(N,1,censor)
  conTime = data.frame(time=censoring)
  censoring_time <- as.numeric(contToDisc(dataShort = conTime, timeColumn = "time", intervalLimits = 1:(censor))$timeDisc)#3
  for (x in tail(eta,-1)) {
    day <- day+1
    idx.atrisk <- c(1:N)[-idx.out]  
    probs <- VGAM::cloglog((x+(as.matrix(Z[idx.atrisk,])%*%beta)), bvalue=.Machine$double.eps, inverse=TRUE)
    idx.event <- idx.atrisk[rbinom(length(probs), 1, probs)==1]
    status[idx.event] <- 1
    days.to.event[idx.event] <- day
    idx.out <- unique(c(idx.out, idx.event))
  }
  
  tcens <- as.numeric(censoring<days.to.event) # censoring indicator
  delta <- 1-tcens
  time <- days.to.event*(delta==1)+censoring_time*(delta==0)
  delta[-idx.out] <- 0
  data <- as.data.frame(cbind(delta, Z, time))
  colnames(data) <- c("status", Z.char, "time")
  
  return(data)
}

discSurv_cloglog=function(t, X, ind, tol = 1e-20, max_iter = 25){
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
  
  return (NR_cloglog(t, X, ind, beta_t, beta_v, tol, max_iter, epsilon=.Machine$double.eps))
}

discSurvKL_cloglog=function(t, X, ind, tol = 1e-20, max_iter = 25, beta_t_tilde, beta_v_tilde, eta){
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
  
  return (NRKL_cloglog(t, X, ind, beta_t, beta_v, tol, max_iter, beta_t_tilde, beta_v_tilde, eta, epsilon=.Machine$double.eps))
}

DiscLoglik_cloglog = function(t, X, ind, beta_t, beta_v){
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
  
  return (Update_cloglog(t, X, ind, beta_t, beta_v, maxt, c, r, epsilon=.Machine$double.eps)$loglik)
}


