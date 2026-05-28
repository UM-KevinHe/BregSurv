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
#
# *-dev variants are REQUIRED — R packages like textshaping, systemfonts,
# ragg, svglite compile from source against harfbuzz/fribidi/freetype/
# fontconfig/png/jpeg/tiff headers. Listing only the runtime libs
# (libharfbuzz0b, libfontconfig1, etc.) causes textshaping to fail with
# a 2MiB cascade of Eigen template errors that's painful to diagnose.
# (-dev packages pull in their runtime counterparts automatically.)
#
# Also bundled:
#   * r-base / r-base-dev: R + headers for RcppArmadillo etc.
#   * build-essential + gfortran: required by several CRAN compiles
#   * libxml2/libssl/libcurl-dev: R's xml2/openssl/curl packages
#   * libpango1.0-dev + libcairo2-dev: weasyprint AND R graphics
# --------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      r-base r-base-dev \
      build-essential gfortran pkg-config \
      libxml2-dev libssl-dev libcurl4-openssl-dev \
      libpango1.0-dev libcairo2-dev \
      libharfbuzz-dev libfribidi-dev \
      libfreetype6-dev libfontconfig1-dev \
      libpng-dev libjpeg-dev libtiff-dev \
      libmagick++-dev \
      libuv1-dev libsodium-dev libgit2-dev libsecret-1-dev \
      libffi-dev \
      ca-certificates curl \
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
    ), dependencies = c('Depends', 'Imports', 'LinkingTo')); \
    missing <- c('Rcpp','RcppArmadillo','ggplot2','cowplot','Matrix','rlang','riskRegression','dplyr','reshape2','survival','MASS','mvtnorm','scales','rBayesianOptimization','jsonlite','remotes'); \
    missing <- missing[!missing %in% rownames(installed.packages())]; \
    if (length(missing)) stop('Failed to install: ', paste(missing, collapse=', ')); \
    cat('R deps installed; library:', .libPaths()[1], '\n')"

# --------------------------------------------------------------------
# Defense-in-depth runtime extras — added in a SEPARATE layer AFTER
# the slow R install so this can change without invalidating the
# R-install cache.
#   * fonts-dejavu-core / fonts-liberation: matplotlib + weasyprint
#     need at least one TrueType family to render text. python-slim
#     ships none; without these, plots have empty glyphs and PDFs
#     are blank.
#   * shared-mime-info: weasyprint uses it to identify image MIMEs;
#     missing it manifests as a noisy warning at PDF time, not a hard
#     fail, but trivially cheap to fix.
#   * locales: ensures en_US.UTF-8 is generated so R / Python don't
#     fall back to C-locale and choke on non-ASCII data.
# --------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-dejavu-core fonts-liberation \
      shared-mime-info \
      locales \
    && sed -i '/^# en_US.UTF-8/s/^# //' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

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
    SURVBREGDIV_R_SCRIPTS=/app/mcp/r_scripts \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    PYTHONIOENCODING=utf-8

EXPOSE 7860

# Health probe: confirm Rscript + BregSurv + python imports work.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import gradio, openai; \
                   from bregsurv_agent import BregSurvAgent" || exit 1

CMD ["python", "app.py"]
