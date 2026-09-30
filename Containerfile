# Chit API image (CPU). Build:  podman build -t chit -f Containerfile .
FROM docker.io/library/python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# CPU-only PyTorch first: the default wheel bundles ~2 GB of CUDA libraries.
# Then the rest of requirements.txt (its torch pin is already satisfied).
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install -r requirements.txt

COPY pranav/ pranav/
COPY configs/ configs/
COPY data/ data/
COPY pyproject.toml README.md ./

# Paths in the configs (data/train.txt, checkpoints/...) are relative to /app.
# compose.yaml mounts data/ and checkpoints/ from the host so they persist.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

# Single worker on purpose: model state and the training-job registry live in this process.
CMD ["uvicorn", "pranav.chit.api:app", "--host", "0.0.0.0", "--port", "8000"]
