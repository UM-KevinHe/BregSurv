#' Example high-dimensional survival data
#'
#' A simulated high-dimensional survival dataset under a linear Cox model
#' with 50 covariates (6 signals + 44 noise variables), a Weibull baseline
#' hazard, and controlled censoring. The dataset includes internal
#' train/test samples and multiple externally estimated coefficient vectors
#' representing different forms of coefficient perturbation.
#'
#' @name ExampleData_highdim
#' @docType data
#' @usage data(ExampleData_highdim)
#'
#' @format A list with the following components:
#' \describe{
#'   \item{train}{A list containing:
#'     \describe{
#'       \item{z}{A data frame of dimension \eqn{n_{\mathrm{train}} \times 50}
#'         containing covariates \code{Z1}–\code{Z50}.}
#'       \item{status}{A numeric vector of event indicators
#'         (\code{1}=event, \code{0}=censored).}
#'       \item{time}{A numeric vector of observed survival times
#'         \eqn{\min(T, C)}.}
#'       \item{stratum}{A vector of stratum labels (here all equal to \code{1}).}
#'     }
#'   }
#'   \item{test}{A list with the same structure as \code{train}, with
#'     covariates of dimension \eqn{n_{\mathrm{test}} \times 50}.}
#'   \item{beta_external}{A numeric vector of length 50 (named
#'     \code{Z1}–\code{Z50}) containing Cox regression coefficients estimated
#'     from an external dataset using only \code{Z1}–\code{Z6}, with zeros
#'     for \code{Z7}–\code{Z50}.}
#'   \item{beta_external.multi1}{External coefficient vector with additive
#'     Gaussian noise applied to the nonzero entries of \code{beta_external},
#'     preserving the original sparsity pattern.}
#'   \item{beta_external.multi2}{External coefficient vector with weak
#'     Gaussian noise applied to all 50 coefficients, yielding a dense but
#'     low-magnitude perturbation.}
#'   \item{beta_external.multi3}{A scaled version of \code{beta_external}
#'     with uniformly attenuated signal strength.}
#'   \item{beta_external.multi4}{External coefficient vector in which a
#'     subset of the nonzero coefficients in \code{beta_external} have their
#'     signs randomly flipped.}
#'   \item{beta_external.multi5}{External coefficient vector with weakened
#'     original signals and a small number of newly introduced weak signals
#'     among previously zero coefficients.}
#' }
#'
#' @details
#' Data-generating mechanism:
#' \itemize{
#'   \item \strong{Covariates:} 50 covariates with true signals in
#'     \code{Z1}–\code{Z6} and noise variables in \code{Z7}–\code{Z50}.
#'     \itemize{
#'       \item \code{Z1}, \code{Z2}: bivariate normal with AR(1) correlation
#'         \eqn{\rho = 0.5}.
#'       \item \code{Z3}, \code{Z4}: independent Bernoulli(0.5).
#'       \item \code{Z5} \eqn{\sim N(2, 1)}, \code{Z6} \eqn{\sim N(-2, 1)}.
#'       \item \code{Z7}–\code{Z50}: multivariate normal with AR(1)
#'         correlation \eqn{\rho = 0.5}.
#'     }
#'   \item \strong{True coefficients:}
#'     \eqn{\beta = (0.3, -0.3, 0.3, -0.3, 0.3, -0.3, 0, \ldots, 0)}.
#'   \item \strong{Event times:} Weibull baseline hazard
#'     \eqn{h_0(t) = \lambda \nu t^{\nu - 1}} with \eqn{\lambda = 1} and
#'     \eqn{\nu = 2}. Given linear predictor \eqn{\eta = Z^\top \beta},
#'     event times are generated as
#'     \deqn{T = \left(\frac{-\log U}{\lambda e^{\eta}}\right)^{1/\nu},
#'     \quad U \sim \mathrm{Unif}(0,1).}
#'   \item \strong{Censoring:} \eqn{C \sim \mathrm{Unif}(0, \mathrm{ub})},
#'     where \code{ub} is tuned to achieve the target censoring rate
#'     (internal: 0.70; external: 0.50). The observed time is
#'     \eqn{\min(T, C)} with event indicator
#'     \eqn{\mathbf{1}\{T \le C\}}.
#'   \item \strong{External coefficients:} Cox regression models with
#'     Breslow ties are fitted on the external dataset using
#'     \code{Z1}–\code{Z6}. The resulting estimates are embedded into
#'     length-50 coefficient vectors, with additional variants constructed
#'     to represent different forms of coefficient perturbation and
#'     distributional shift.
#' }
#'
#' @examples
#' data(ExampleData_highdim)
"ExampleData_highdim"



#' Example low-dimensional survival data
#'
#' A simulated survival dataset in a low-dimensional linear setting
#' with 6 covariates (2 correlated continuous, 2 binary, 2 mean-shifted normals),
#' Weibull baseline hazard, and controlled censoring. Includes internal train/test sets,
#' and three external-quality coefficient vectors.
#'
#' @name ExampleData_lowdim
#' @docType data
#' @usage data(ExampleData_lowdim)
#'
#' @format A list containing the following elements:
#' \describe{
#'   \item{train}{A list with components:
#'     \describe{
#'       \item{z}{Data frame of size \eqn{n_\mathrm{train}\times 6} with covariates \code{Z1}–\code{Z6}.}
#'       \item{status}{Vector of event indicators (\code{1}=event, \code{0}=censored).}
#'       \item{time}{Numeric vector of observed times \eqn{\min(T, C)}.}
#'       \item{stratum}{Vector of stratum labels (here all \code{1}).}
#'     }
#'   }
#'   \item{test}{A list with the same structure as \code{train}, with size \eqn{n_\mathrm{test}\times 6} for \code{z}.}
#'   \item{beta_external_good}{Numeric vector (length 6; named \code{Z1}–\code{Z6}) of Cox coefficients estimated on a
#'     "Good" external dataset using all \code{Z1}–\code{Z6}.}
#'   \item{beta_external_fair}{Numeric vector (length 6; names \code{Z1}–\code{Z6}) of Cox coefficients estimated on a
#'     "Fair" external dataset using a reduced subset \code{Z1}, \code{Z3}, \code{Z5}, \code{Z6};
#'     coefficients for variables not used are \code{0}.}
#'   \item{beta_external_poor}{Numeric vector (length 6; names \code{Z1}–\code{Z6}) of Cox coefficients estimated on a
#'     "Poor" external dataset using \code{Z1} and \code{Z5} only; remaining entries are \code{0}.}
#' }
#'
#' @details Data-generating mechanism:
#' \itemize{
#'   \item Covariates: 6 variables \code{Z1}–\code{Z6}.
#'     \itemize{
#'       \item \code{Z1}, \code{Z2} ~ bivariate normal with AR(1) correlation \eqn{\rho=0.5}.
#'       \item \code{Z3}, \code{Z4} ~ independent Bernoulli(0.5).
#'       \item \code{Z5} ~ \eqn{N(2,1)}, \code{Z6} ~ \eqn{N(-2,1)} (group indicator fixed at 1 for internal train/test).
#'     }
#'   \item True coefficients: \eqn{\beta = (0.3,-0.3,0.3,-0.3,0.3,-0.3)} (length 6).
#'   \item Event times: Weibull baseline hazard
#'     \eqn{h_0(t)=\lambda\nu \, t^{\nu-1}} with \eqn{\lambda=1}, \eqn{\nu=2}.
#'     Given linear predictor \eqn{\eta = Z^\top \beta}, draw \eqn{U\sim\mathrm{Unif}(0,1)} and set
#'     \deqn{T = \left(\frac{-\log U}{\lambda \, e^{\eta}}\right)^{1/\nu}.}
#'   \item Censoring: \eqn{C\sim \mathrm{Unif}(0,\text{ub})} with \code{ub} tuned iteratively to
#'     achieve the target censoring rate (internal: \code{0.70}; external: \code{0.50}).
#'     Observed time is \eqn{\min(T,C)}, status is \eqn{\mathbf{1}\{T \le C\}}.
#'   \item External coefficients: For each quality level ("Good", "Fair", "Poor"), fit a Cox model
#'     \code{Surv(time, status) ~ Z1 + ...} on the corresponding external data (Breslow ties)
#'     using the specified covariate subset; place estimates into a length-6 vector named \code{Z1}–\code{Z6}
#'     with zeros for variables not included.
#' }
#'
#' @examples
#' data(ExampleData_lowdim)
"ExampleData_lowdim"


#' Example Data for Conditional Logistic Regression
#'
#' @description
#' A simulated dataset generated for 1:M matched case-control studies
#' (Conditional Logistic Regression, CLR). The data is organized into matched sets
#' (strata), with exactly one case (\code{y=1}) and \eqn{m=4} controls (\code{y=0}) per set.
#'
#' @name ExampleData_cc
#' @docType data
#' @usage data(ExampleData_cc)
#'
#' @format A list containing the following elements:
#' \describe{
#'   \item{train}{A list with components for training the CLR model:
#'     \describe{
#'       \item{z}{Numeric matrix of covariates (dimension \eqn{n_{\mathrm{train}}\times 6})
#'         with columns named \code{Z1}--\code{Z6}.}
#'       \item{y}{Binary outcome vector (\code{1}=case, \code{0}=control).}
#'       \item{stratum}{Integer vector identifying the matched set for each observation
#'         (200 unique strata in \code{train}).}
#'     }
#'   }
#'   \item{test}{A list with the same structure as \code{train}, used for external evaluation
#'     (500 unique strata in \code{test}).}
#'   \item{beta_external}{Numeric vector (length 6) of CLR coefficients estimated on a separate
#'     external dataset using all \code{Z1}--\code{Z6}.}
#' }
#'
#' @details
#' Data-generating mechanism:
#' \itemize{
#'   \item \strong{Study design:} 1:4 matched case-control study (\eqn{m=4} controls per case).
#'   \item \strong{Covariates:} 6 variables (\code{Z1}--\code{Z6}) drawn from a correlated multivariate
#'     normal distribution.
#'   \item \strong{True coefficients:} \eqn{\beta = (1, -1, 1, -1, 1, -1)}.
#'   \item \strong{Set-specific effect:} A random stratum-specific intercept
#'     \eqn{\theta_i \sim N(0, 0.5^2)} is added to the linear predictor; it is eliminated by CLR conditioning.
#'   \item \strong{Outcome generation:} Within each stratum \eqn{i}, the single case (\code{y=1}) is selected
#'     with probability proportional to \eqn{\exp(\theta_i + Z^\top \beta)}.
#'   \item \strong{External beta estimation:} \code{beta_external} is obtained by fitting \code{ncc} on a
#'     separate simulated dataset with a slightly different true coefficient vector
#'     \eqn{\beta_{\mathrm{ext}} = (0.8, -0.8, \dots)} and correlation \eqn{\rho = 0.3},
#'     using the \code{"breslow"} tie approximation.
#' }
#'
#' @examples
#' data(ExampleData_cc)
"ExampleData_cc"



#' Example high-dimensional matched case-control data
#'
#' A simulated 1:5 matched case-control dataset with 20 covariates,
#' where 10 covariates are truly non-zero. The data are split into
#' training and test sets and include both the true underlying coefficients
#' and an externally supplied coefficient vector for KL-based integration.
#'
#' @name ExampleData_cc_highdim
#' @docType data
#' @usage data(ExampleData_cc_highdim)
#'
#' @format A list containing:
#' \describe{
#'   \item{train}{List with elements \code{y}, \code{z}, and \code{stratum}.}
#'   \item{test}{Same structure as \code{train}.}
#'   \item{beta_true}{Numeric vector (length 50) of true coefficients.}
#'   \item{beta_external}{Numeric vector (length 50) representing external coefficients.}
#' }
#'
#' @examples
#' data(ExampleData_cc_highdim)
"ExampleData_cc_highdim"


#' Example internal/external Cox individual-level data
#'
#' A simulated survival dataset for illustrating \code{cox_indi()} and
#' \code{cv.cox_indi()}. The object contains one internal cohort and one external
#' cohort, each stratified into multiple strata, along with the true coefficient
#' vector used in simulation.
#'
#' @name ExampleData_indi
#' @docType data
#' @usage data(ExampleData_indi)
#'
#' @format A list containing:
#' \describe{
#'   \item{internal}{List with elements \code{z}, \code{time}, \code{status}, \code{stratum}.}
#'   \item{external}{List with elements \code{z}, \code{time}, \code{status}, \code{stratum}.}
#'   \item{beta_true}{Numeric vector (length p) of true coefficients.}
#'   \item{meta}{List of simulation settings for internal and external cohorts.}
#' }
#'
#' @examples
#' data(ExampleData_indi)
#' str(ExampleData_indi)
"ExampleData_indi"



