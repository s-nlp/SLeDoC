FROM python:3.11-slim

LABEL maintainer="Vir_Ven"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /opt/models/intfloat/multilingual-e5-base
RUN python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="intfloat/multilingual-e5-base",
    local_dir="/opt/models/intfloat/multilingual-e5-base",
    local_dir_use_symlinks=False
)
PY

ENV E5_MODEL_PATH=/opt/models/intfloat/multilingual-e5-base \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1 \
    HF_HOME=/opt/hf-cache

COPY app ./app

EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]