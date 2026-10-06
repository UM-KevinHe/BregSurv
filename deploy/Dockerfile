# BregSurv agent (V4) -- one image for the Hugging Face Space and for local use.
# Everything runs inside: Qwen3-8B-AWQ served by vLLM, the harness, R and BregSurv.
# No external API is called. The model weights are baked in at build time.
#
#   local:  docker build -t bregsurv-agent . && docker run --gpus all -p 7860:7860 bregsurv-agent
#           then open http://localhost:7860
FROM vllm/vllm-openai:v0.27.1-cu129

ENV DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# R 4.5 from CRAN's Ubuntu repository, plus what the R packages compile against
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg software-properties-common \
    && curl -fsSL https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc \
       | gpg --dearmor -o /usr/share/keyrings/cran.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/cran.gpg] https://cloud.r-project.org/bin/linux/ubuntu ${UBUNTU_CODENAME}-cran40/" \
       > /etc/apt/sources.list.d/cran.list \
    && apt-get update && apt-get install -y --no-install-recommends \
      r-base r-base-dev build-essential gfortran \
      libxml2-dev libssl-dev libcurl4-openssl-dev libfontconfig1-dev \
      libfreetype6-dev libpng-dev libjpeg-dev libtiff-dev libharfbuzz-dev libfribidi-dev \
      libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# R dependencies: Posit binaries for this Ubuntu release, CRAN source as fallback
RUN . /etc/os-release && R -q -e " \
    options(repos = c(PPM = 'https://packagemanager.posit.co/cran/__linux__/${UBUNTU_CODENAME}/latest', \
                      CRAN = 'https://cloud.r-project.org'), \
            HTTPUserAgent = sprintf('R/%s R (%s)', getRversion(), paste(getRversion(), R.version[['platform']], R.version[['arch']], R.version[['os']])), \
            Ncpus = 4); \
    pk <- c('Rcpp','RcppArmadillo','RcppEigen','ggplot2','cowplot','Matrix','rlang','riskRegression', \
            'dplyr','reshape2','survival','MASS','mvtnorm','scales','rBayesianOptimization', \
            'jsonlite','readxl','arrow','future','future.apply'); \
    install.packages(pk); \
    miss <- pk[!vapply(pk, requireNamespace, logical(1), quietly = TRUE)]; \
    if (length(miss)) stop('R packages failed: ', paste(miss, collapse = ', '))"

# The estimator library and the discrete-time package, from source
COPY r_pkgs/ /opt/r_pkgs/
RUN R CMD INSTALL /opt/r_pkgs/BregSurv && R CMD INSTALL /opt/r_pkgs/DiscreteKL \
    && R -q -e "library(BregSurv); library(DiscreteKL); cat('BregSurv', as.character(packageVersion('BregSurv')), '\n')"

# The harness and the UI
# The app gets its own environment on top of the image's Python, so Gradio's web stack cannot
# disturb vLLM's; torch (for the discrete-time network members) is shared from the image.
COPY requirements.txt /app/requirements.txt
RUN python3 -m venv --system-site-packages /opt/appenv \
    && /opt/appenv/bin/pip install -r /app/requirements.txt
COPY app/ /app/

# Qwen3-8B-AWQ (Apache-2.0), downloaded once at build time
RUN python3 -c "from huggingface_hub import snapshot_download; \
snapshot_download('Qwen/Qwen3-8B-AWQ', local_dir='/models/qwen3-8b-awq')"

# The retrieval models for the example banks (Apache-2.0): embedding and reranker, run on the CPU
RUN python3 -c "from huggingface_hub import snapshot_download; \
snapshot_download('Qwen/Qwen3-Embedding-0.6B', local_dir='/models/retrieval/Qwen3-Embedding-0.6B'); \
snapshot_download('Qwen/Qwen3-Reranker-0.6B', local_dir='/models/retrieval/Qwen3-Reranker-0.6B')"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /tmp/bregsurv && chmod 777 /tmp/bregsurv

ENV VLLM_MODEL_PATH=/models/qwen3-8b-awq \
    SURVBREGDIV_MODEL_NAME=qwen3-8b-awq \
    SURVBREGDIV_MODEL_ENDPOINT=http://127.0.0.1:8000/v1 \
    OPENAI_API_KEY=EMPTY \
    BREGSURV_RETRIEVAL_MODELS=/models/retrieval BREGSURV_RETRIEVAL_DEVICE=cuda \
    BREGSURV_THINKING=auto BREGSURV_PLANNER=on BREGSURV_MEMORY=off \
    VLLM_USE_FLASHINFER_SAMPLER=0 BREGSURV_PYTHON=/opt/appenv/bin/python \
    GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT=7860 \
    DEPLOYMENT_MODE=local
EXPOSE 7860
ENTRYPOINT ["/entrypoint.sh"]
