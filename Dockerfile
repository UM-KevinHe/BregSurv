# Single Dockerfile serving BOTH HuggingFace Space (Docker SDK)
# AND Stage 4d self-host (`docker run -p 7860:7860 ...`).
#
# Layer ordering optimised for incremental rebuilds: R/system deps
# (~10-15 min on cold build) come first and rarely change; Python deps
# and app code change often and live near the end.
#
# Build:    docker build -t bregsurv-agent .
# Run:      docker run -p 7860:7860 \
#               -e DEPLOYMENT_MODE=local \
#               -e OPENAI_API_KEY=sk-... \
#               bregsurv-agent

FROM python:3.11-slim AS base

# Non-interactive apt; pin tzdata to avoid prompts.
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# --------------------------------------------------------------------
# System packages
#   * R + dev headers (for compiling RcppArmadillo etc.)
#   * Pango / Cairo / harfbuzz: weasyprint runtime deps
#   * libxml2 / libssl / libcurl: required by R's curl/openssl/xml2
#   * build tools + gfortran: needed by some CRAN compiles
# --------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      r-base r-base-dev \
      build-essential gfortran \
      libxml2-dev libssl-dev libcurl4-openssl-dev \
      libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
      libcairo2 libcairo2-dev \
      libharfbuzz0b libfribidi0 \
      libffi-dev \
      libfontconfig1 libfreetype6 \
      ca-certificates curl \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------
# R packages — must include EVERY entry in DESCRIPTION's Imports +
# LinkingTo, plus our MCP helpers (jsonlite, remotes). dependencies=TRUE
# pulls all transitive deps recursively (e.g. riskRegression brings
# prodlim/pec/timereg/foreach etc.).
#
# Past Stage 4c lesson: the original list was missing `dplyr`,
# `reshape2`, `rlang`, `mvtnorm`, `scales` — install.packages succeeds
# silently for the listed ones but R CMD INSTALL of BregSurv then fails
# at "dependencies not available". The DESCRIPTION Imports list is the
# canonical source of truth; keep this `c(...)` block in sync with it.
# --------------------------------------------------------------------
RUN R -e " \
    options(repos = c(CRAN='https://cloud.r-project.org'), Ncpus = 4); \
    install.packages(c( \
      'Rcpp', 'RcppArmadillo', \
      'ggplot2', 'cowplot', 'Matrix', 'rlang', \
      'riskRegression', 'dplyr', 'reshape2', \
      'survival', 'MASS', 'mvtnorm', 'scales', \
      'rBayesianOptimization', \
      'jsonlite', 'remotes' \
    ), dependencies = TRUE); \
    missing <- c('Rcpp','RcppArmadillo','ggplot2','cowplot','Matrix','rlang','riskRegression','dplyr','reshape2','survival','MASS','mvtnorm','scales','rBayesianOptimization','jsonlite','remotes'); \
    missing <- missing[!missing %in% rownames(installed.packages())]; \
    if (length(missing)) stop('Failed to install: ', paste(missing, collapse=', ')); \
    cat('R deps installed; library:', .libPaths()[1], '\n')"

# --------------------------------------------------------------------
# Python deps
# --------------------------------------------------------------------
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# --------------------------------------------------------------------
# BregSurv R package source. Installed from local source so we don't
# depend on the (yet-to-be-renamed) GitHub repo or any network call.
# Skip vignettes/ — saves ~minutes; the Space doesn't need built docs.
# --------------------------------------------------------------------
COPY DESCRIPTION NAMESPACE /app/_bregsurv_pkg/
COPY R/    /app/_bregsurv_pkg/R/
COPY src/  /app/_bregsurv_pkg/src/
COPY man/  /app/_bregsurv_pkg/man/
COPY data/ /app/_bregsurv_pkg/data/

RUN R CMD INSTALL --no-docs --no-multiarch /app/_bregsurv_pkg \
    && R -e "library(BregSurv); cat('BregSurv installed:', as.character(packageVersion('BregSurv')), '\n')"

# Application files. These change most often; keep last for cache reuse.
COPY mcp/r_scripts/ /app/mcp/r_scripts/
COPY mcp/server.py /app/mcp/server.py
COPY data/ /app/data/
COPY bregsurv_agent/ /app/bregsurv_agent/
COPY app.py generate_transcripts.py /app/

# --------------------------------------------------------------------
# Runtime configuration
# --------------------------------------------------------------------
ENV GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860 \
    DEPLOYMENT_MODE=demo \
    SURVBREGDIV_RSCRIPT=/usr/bin/Rscript \
    SURVBREGDIV_R_SCRIPTS=/app/mcp/r_scripts

EXPOSE 7860

# Health probe: confirm Rscript + BregSurv + python imports work.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import gradio, openai; \
                   from bregsurv_agent import BregSurvAgent" || exit 1

CMD ["python", "app.py"]
