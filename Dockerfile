FROM python:3.11-slim

WORKDIR /app

# libgomp1 required by LightGBM and CatBoost on Debian/slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies as a separate layer so docker build cache
# is reused when only source code changes (not requirements).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY configs/   configs/
COPY features/  features/
COPY training/  training/
COPY prediction/ prediction/

# models/ and logs/ will be mounted from host via docker-compose volumes.
# Create the dirs so the container starts cleanly even without mounts.
RUN mkdir -p models logs

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_DIR=/app/models

CMD ["python", "-m", "prediction.predict"]
