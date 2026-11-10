// The grouped-time (discrete-time) solver.
//
// Every member of the framework on a discrete-time target is a weighted Bernoulli likelihood on the
// person-intervals (see R/discrete_engine.R), so one solver fits all of them. The data arrive stacked:
// one row per subject (internal subjects, then, for the composite likelihood, the external records),
// with n x K matrices of targets Tm (0/1, or the soft Kullback-Leibler target) and weights Wt (zero
// where the subject is not at risk). The interval parameters G (one row per baseline cell, one column
// per interval) are profiled out by their diagonal Schur complement; the coefficient step is a Newton
// step (unpenalized, ridge) or a proximal-Newton step solved by coordinate descent (lasso, elastic
// net), followed by backtracking on the full objective.

#include <RcppArmadillo.h>
// [[Rcpp::depends(RcppArmadillo)]]

namespace {

struct DtProblem {
  const arma::mat &Z;      // N x p, stacked rows
  arma::mat Zt;            // p x N
  arma::uvec cell;         // N, 0-based baseline cell of each row
  const arma::mat &Tm;     // N x K targets
  const arma::mat &Wt;     // N x K weights
  int link;                // 0 = complementary log-log, 1 = logit
  double n;                // the objective is divided by n
  int n_cell, K;
  double l1, l2;           // lambda * alpha and lambda * (1 - alpha)
  bool maha;
  const arma::mat &Qm;
  const arma::vec &bext;
  double eta_m;

  DtProblem(const arma::mat &Z_, const Rcpp::IntegerVector &cell_, const arma::mat &Tm_,
            const arma::mat &Wt_, int link_, double n_, int n_cell_, double lambda, double alpha,
            const arma::mat &Qm_, const arma::vec &bext_, double eta_m_)
    : Z(Z_), Zt(Z_.t()), cell(cell_.size()), Tm(Tm_), Wt(Wt_), link(link_), n(n_), n_cell(n_cell_),
      K(Tm_.n_cols), l1(lambda * alpha), l2(lambda * (1.0 - alpha)), maha(Qm_.n_elem > 0),
      Qm(Qm_), bext(bext_), eta_m(eta_m_) {
    for (int i = 0; i < cell_.size(); ++i) cell(i) = static_cast<arma::uword>(cell_[i]);
  }
};

// log h and log(1 - h) at the linear predictor u, stably
inline void dt_logs(double u, int link, double &lh, double &l1h) {
  if (link == 0) {
    const double e = std::exp(u);
    lh = (u > 3.6) ? std::log1p(-std::exp(-e)) : std::log(-std::expm1(-e));
    l1h = -e;
  } else {
    lh = (u > 0) ? -std::log1p(std::exp(-u)) : u - std::log1p(std::exp(u));
    l1h = (u > 0) ? -u - std::log1p(std::exp(-u)) : -std::log1p(std::exp(u));
  }
}

// derivative in u of t log h + (1 - t) log(1 - h), and its Fisher information
inline void dt_score_info(double u, double t, int link, double &d, double &w) {
  if (link == 0) {
    const double e = std::exp(u);
    const double mu = -std::expm1(-e);
    const double r = (mu > 0) ? e / mu : 1.0;
    d = t * r - e;
    w = e * r * (1.0 - mu);
  } else {
    const double mu = 1.0 / (1.0 + std::exp(-u));
    d = t - mu;
    w = mu * (1.0 - mu);
  }
}

// the objective to minimize: the weighted negative log-likelihood over n, the Mahalanobis term and
// the elastic-net penalty
double dt_objective(const DtProblem &P, const arma::mat &G, const arma::vec &beta) {
  const arma::vec lp = P.Z * beta;
  const arma::uword N = P.Z.n_rows;
  long double val = 0.0L;
  for (int k = 0; k < P.K; ++k) {
    for (arma::uword i = 0; i < N; ++i) {
      const double w = P.Wt(i, k);
      if (w == 0.0) continue;
      const double t = P.Tm(i, k);
      double lh, l1h;
      dt_logs(G(P.cell(i), k) + lp(i), P.link, lh, l1h);
      double term = 0.0;
      if (t > 0.0) term += t * lh;
      if (t < 1.0) term += (1.0 - t) * l1h;
      val -= static_cast<long double>(w * term);
    }
  }
  double out = static_cast<double>(val) / P.n;
  if (P.maha) {
    const arma::vec dv = beta - P.bext;
    out += 0.5 * P.eta_m * arma::dot(dv, P.Qm * dv);
  }
  return out + P.l1 * arma::accu(arma::abs(beta)) + 0.5 * P.l2 * arma::dot(beta, beta);
}

struct DtDerivs {
  arma::vec gb;   // gradient in beta
  arma::mat Hbb;  // information in beta
  arma::mat gG;   // gradient in G (n_cell x K)
  arma::mat HGG;  // diagonal information in G (n_cell x K)
  arma::mat HGb;  // cross information, (n_cell * K) x p, row index cell + n_cell * k
};

// gradient and Fisher information of the smooth part, divided by n
void dt_derivs(const DtProblem &P, const arma::mat &G, const arma::vec &beta, DtDerivs &D) {
  const arma::uword N = P.Z.n_rows, p = beta.n_elem;
  const arma::vec lp = P.Z * beta;
  arma::vec rD(N, arma::fill::zeros), rW(N, arma::fill::zeros);
  D.gG.zeros(P.n_cell, P.K);
  D.HGG.zeros(P.n_cell, P.K);
  arma::mat HGbT(p, static_cast<arma::uword>(P.n_cell) * P.K, arma::fill::zeros);
  for (int k = 0; k < P.K; ++k) {
    for (arma::uword i = 0; i < N; ++i) {
      const double w = P.Wt(i, k);
      if (w == 0.0) continue;
      const arma::uword c = P.cell(i);
      double d, wi;
      dt_score_info(G(c, k) + lp(i), P.Tm(i, k), P.link, d, wi);
      double Dv = -w * d, Wv = w * wi;
      if (!std::isfinite(Dv)) Dv = 0.0;
      if (!std::isfinite(Wv)) Wv = 0.0;
      rD(i) += Dv;
      rW(i) += Wv;
      D.gG(c, k) += Dv;
      D.HGG(c, k) += Wv;
      if (Wv != 0.0) HGbT.col(c + static_cast<arma::uword>(P.n_cell) * k) += Wv * P.Zt.col(i);
    }
  }
  D.gb = P.Zt * rD;
  arma::mat ZW = P.Z;
  ZW.each_col() %= rW;
  D.Hbb = P.Zt * ZW;
  D.gb /= P.n; D.Hbb /= P.n; D.gG /= P.n; D.HGG /= P.n;
  D.HGb = HGbT.t() / P.n;
  if (P.maha) {
    D.gb += P.eta_m * (P.Qm * (beta - P.bext));
    D.Hbb += P.eta_m * P.Qm;
  }
}

// cells (baseline row x interval) where anyone is at risk
arma::umat dt_live(const DtProblem &P) {
  arma::umat live(P.n_cell, P.K, arma::fill::zeros);
  const arma::uword N = P.Z.n_rows;
  for (int k = 0; k < P.K; ++k)
    for (arma::uword i = 0; i < N; ++i)
      if (P.Wt(i, k) != 0.0) live(P.cell(i), k) = 1;
  return live;
}

// the interval parameters with every coefficient held at zero (Newton steps on the diagonal)
arma::mat dt_gamma_only(const DtProblem &P, arma::mat G, double gmin) {
  const arma::vec beta0(P.Z.n_cols, arma::fill::zeros);
  DtDerivs D;
  for (int it = 0; it < 100; ++it) {
    dt_derivs(P, G, beta0, D);
    arma::mat step(P.n_cell, P.K, arma::fill::zeros);
    for (arma::uword j = 0; j < step.n_elem; ++j)
      if (D.HGG(j) > 1e-14) step(j) = -D.gG(j) / D.HGG(j);
    arma::mat Gn = arma::clamp(G + step, gmin, arma::datum::inf);
    const double ch = arma::abs(Gn - G).max();
    G = Gn;
    if (ch < 1e-10) break;
  }
  return G;
}

} // namespace

// Fit at one (eta, lambda). Z is on the scale the caller chose (standardized for a penalized fit).
// [[Rcpp::export]]
Rcpp::List dt_solve_cpp(const arma::mat &Z, const Rcpp::IntegerVector &cell, const arma::mat &Tm,
                        const arma::mat &Wt, int link, double n, int n_cell, double lambda,
                        double alpha, const arma::mat &Qm, const arma::vec &bext, double eta_m,
                        arma::vec beta, arma::mat G, double gmin, double tol, int max_iter) {
  DtProblem P(Z, cell, Tm, Wt, link, n, n_cell, lambda, alpha, Qm, bext, eta_m);
  const arma::uword p = beta.n_elem;
  const arma::umat live = dt_live(P);
  const arma::uvec live_idx = arma::find(live);
  double F_old = dt_objective(P, G, beta);
  bool converged = false;
  int it = 0;
  DtDerivs D;
  for (it = 1; it <= max_iter; ++it) {
    dt_derivs(P, G, beta, D);
    // the reduced (Schur) quadratic in the coefficient step
    const arma::vec hg = arma::vectorise(D.HGG);
    arma::vec Dinv(hg.n_elem, arma::fill::zeros);
    for (arma::uword j = 0; j < hg.n_elem; ++j)
      if (live(j) && hg(j) > 1e-14) Dinv(j) = 1.0 / hg(j);
    const arma::vec gGv = arma::vectorise(D.gG);
    arma::mat HD = D.HGb;
    HD.each_col() %= Dinv;
    const arma::mat Hs = D.Hbb - D.HGb.t() * HD;
    const arma::vec gs = D.gb - D.HGb.t() * (Dinv % gGv);
    arma::vec step_b(p);
    if (P.l1 == 0.0) {
      const arma::mat A = Hs + P.l2 * arma::eye(p, p);
      const arma::vec rhs = gs + P.l2 * beta;
      arma::vec sol;
      bool ok = arma::solve(sol, A, rhs, arma::solve_opts::no_approx);
      if (!ok) sol = arma::pinv(A) * rhs;
      step_b = -sol;
    } else {
      // proximal Newton: coordinate descent on the reduced quadratic plus the penalty
      arma::vec x = beta, v(p, arma::fill::zeros);
      const arma::vec hd = Hs.diag();
      for (int sweep = 0; sweep < 1000; ++sweep) {
        double maxd = 0.0;
        for (arma::uword j = 0; j < p; ++j) {
          const double a = hd(j) + P.l2;
          if (a <= 0.0) continue;
          const double zj = hd(j) * x(j) - (gs(j) + v(j));
          const double sgn = (zj > 0.0) ? 1.0 : ((zj < 0.0) ? -1.0 : 0.0);
          const double xn = sgn * std::max(std::abs(zj) - P.l1, 0.0) / a;
          const double d = xn - x(j);
          if (d != 0.0) {
            v += d * Hs.col(j);
            x(j) = xn;
            maxd = std::max(maxd, std::abs(d) * std::sqrt(a));
          }
        }
        if (maxd < tol) break;
      }
      step_b = x - beta;
    }
    arma::vec step_G = -Dinv % (gGv + D.HGb * step_b);
    arma::mat step_Gm(step_G.memptr(), P.n_cell, P.K, false, true);
    // backtracking on the full objective
    double s = 1.0, Fn = F_old;
    arma::vec bn;
    arma::mat Gn;
    bool accepted = false;
    for (int h = 0; h < 30; ++h) {
      bn = beta + s * step_b;
      Gn = arma::clamp(G + s * step_Gm, gmin, arma::datum::inf);
      Fn = dt_objective(P, Gn, bn);
      if (std::isfinite(Fn) && Fn <= F_old + 1e-12 * std::abs(F_old)) { accepted = true; break; }
      s /= 2.0;
    }
    if (!accepted) break;
    double change = p ? arma::abs(bn - beta).max() : 0.0;
    if (live_idx.n_elem) change = std::max(change, arma::abs(Gn.elem(live_idx) - G.elem(live_idx)).max());
    beta = bn;
    G = Gn;
    const double dF = F_old - Fn;
    F_old = Fn;
    if (change < tol || dF < tol * 1e-3 * std::max(1.0, std::abs(Fn))) { converged = true; break; }
  }
  if (it > max_iter) it = max_iter;
  // a cell no subject reaches carries the last reached interval of its row forward
  for (int c = 0; c < P.n_cell; ++c) {
    bool any = false;
    for (int k = 0; k < P.K; ++k) if (live(c, k)) { any = true; break; }
    if (!any) continue;
    bool have = false;
    double last = 0.0;
    for (int k = 0; k < P.K; ++k) {
      if (live(c, k)) { last = G(c, k); have = true; }
      else if (have) G(c, k) = last;
    }
  }
  return Rcpp::List::create(Rcpp::Named("beta") = Rcpp::NumericVector(beta.begin(), beta.end()),
                            Rcpp::Named("G") = G,
                            Rcpp::Named("objective") = F_old,
                            Rcpp::Named("converged") = converged,
                            Rcpp::Named("iterations") = it);
}

// The interval parameters with every coefficient at zero, and the largest absolute gradient in the
// coefficients there: the start of the penalty path.
// [[Rcpp::export]]
Rcpp::List dt_null_fit_cpp(const arma::mat &Z, const Rcpp::IntegerVector &cell, const arma::mat &Tm,
                           const arma::mat &Wt, int link, double n, int n_cell, const arma::mat &Qm,
                           const arma::vec &bext, double eta_m, arma::mat G, double gmin) {
  DtProblem P(Z, cell, Tm, Wt, link, n, n_cell, 0.0, 0.0, Qm, bext, eta_m);
  G = dt_gamma_only(P, G, gmin);
  DtDerivs D;
  dt_derivs(P, G, arma::vec(Z.n_cols, arma::fill::zeros), D);
  return Rcpp::List::create(Rcpp::Named("G") = G,
                            Rcpp::Named("max_gradient") = Z.n_cols ? arma::abs(D.gb).max() : 0.0);
}
