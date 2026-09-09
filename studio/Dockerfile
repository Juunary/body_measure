# syntax=docker/dockerfile:1
#
# Build from the body_measure repository root, not from studio/. The image
# retains the directory arrangement expected by studio/studio/paths.py.
#
#   docker build -f studio/Dockerfile -t mass-dpp-studio .
#   docker run --rm -p 8010:8080 -e STUDIO_PASSWORD=... mass-dpp-studio
#
# No dataset is in git, so none is in the image. Scans a deployment may
# show are placed on the mounted volume (STUDIO_EXTRA_DATA), behind the
# password — see studio/README.md.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

COPY studio/requirements.txt studio/requirements.txt
RUN pip install --no-cache-dir -r studio/requirements.txt

# the three siblings, package code only
COPY polo-line-sim/polo_line polo-line-sim/polo_line
COPY polo-line-sim/run.py polo-line-sim/run.py
COPY body_measure body-measure/body_measure
COPY measurement-spec.v1.yaml body-measure/measurement-spec.v1.yaml
COPY qr-configurator/backend/app qr-configurator/backend/app
COPY qr-configurator/backend/static/dppview qr-configurator/backend/static/dppview

COPY studio/studio studio/studio
COPY studio/static studio/static
COPY studio/examples studio/examples

# three.js is reused from the DPP viewer bundle, as setup.ps1 does
RUN cp qr-configurator/backend/static/dppview/assets/three.module-*.js studio/static/vendor/three.module.js

# uploads and per-job results live on the volume; the catalogue reads
# deployed scans from it too
ENV STUDIO_STATE_DIR=/data \
    STUDIO_EXTRA_DATA=/data/scans \
    STUDIO_LANG=en
RUN mkdir -p /data/scans

WORKDIR /app/studio
EXPOSE 8080

# STUDIO_PASSWORD is a deployment secret, never baked into the image.
CMD ["sh", "-c", "uvicorn studio.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
