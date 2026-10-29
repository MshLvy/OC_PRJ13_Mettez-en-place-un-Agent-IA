# syntax=docker/dockerfile:1
FROM python:3.12.14-slim-bookworm@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a
WORKDIR /opt/project
ENV PYTHONPATH=/opt/project PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1     HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HOME=/tmp HF_HOME=/tmp/hf     OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY retrieval ./retrieval
COPY backend/app/data/advisor_v3/chunks.json ./backend/app/data/advisor_v3/chunks.json
RUN --network=none --mount=type=bind,from=wheelhouse,target=/packages,readonly     python -m retrieval.acquire --verify-dependencies /packages     && pip install --no-index --no-deps --find-links=/packages setuptools==84.0.0 wheel==0.48.0 packaging==26.3     && pip install --no-index --no-deps --no-build-isolation --no-cache-dir --require-hashes --find-links=/packages -r retrieval/requirements.lock     && pip check
USER 10001:10001
CMD ["python", "-m", "retrieval.server"]
