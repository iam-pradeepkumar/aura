# AURA Cloud Agent base image — Python deps baked in at build time (PyPI not required at runtime).
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/aura-deps

COPY simulation/requirements.txt simulation/requirements.txt
COPY dashboard/requirements.txt dashboard/requirements.txt
COPY tools/requirements.txt tools/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir \
        -r simulation/requirements.txt \
        -r dashboard/requirements.txt \
        -r tools/requirements.txt \
        pytest

RUN useradd -m -s /bin/bash ubuntu 2>/dev/null || true
USER ubuntu
