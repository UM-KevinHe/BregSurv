### Simulate continuous-time survival data
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

### most-basic simulation for continuous data
sim.con <- function(beta, N, Z.char, upper_C){
  p_h <- 0.5*length(beta)
  Z1 <- as.matrix(simu_z(N, p_h))
  Z2 <- matrix(rbinom(N*p_h,1,0.5),N,p_h)
  Z <- cbind(Z1, Z2)
  U=runif(N, 0,1)
  #Exponential 
  #lambda = 0.5
  #time=-log(U)/(lambda*exp(Z%*%beta)) 
  #Weibull
  lambda=1
  nu=2
  time=(-log(U)/(lambda*exp(Z%*%beta)))^(1/nu) 
  #censoring=runif(N,1,2) #0.9
  censoring=runif(N,0,upper_C) #0 or 0.5
  tcens=(censoring<time) # censoring indicator
  delta=1-tcens
  time=time*(delta!=0)+censoring*(delta==0)
  
  ###order data; 
  delta = delta[order(time)]
  Z = Z[order(time),]
  time = time[order(time)]
  data <- as.data.frame(cbind(Z, delta, time))
  colnames(data) <- c(Z.char, "status", "time")
  
  return(data)
}

