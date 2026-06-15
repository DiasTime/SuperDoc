# NOTE: M2 swaps this for a CUDA base image to run PaddleOCR + serve/consume
# the self-hosted Qwen2.5-VL 7B. For M0/M1 (CPU pipeline) slim is fine.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# OpenCV/weasyprint runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY worker ./worker

CMD ["python", "-m", "worker.main"]
