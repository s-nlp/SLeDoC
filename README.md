# Semantic-Mismatch 🖥️

Gradio-based dashboards for Semantic-Mismatch

working on nlp1: link[http://10.16.88.11:7860]


## Repository
```
app/ Python package
│
├─ main.py FastAPI entry – mounts all three UIs
├─ semantic_mismatch.py Mismatch viewer (path: /mismatch)
├─ nli.py NLI viewer (path: /nli)
└─ pipeline.py Two-step pipeline (path: /pipeline)
│
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
└─ Makefile
```

## Quick start (Docker)

```bash
# 1. build the image
docker build -t viewers .

# 2. run it (ports 7860 → 7860)
docker run --rm -p 7860:7860 viewers
```

## local development
```bash
# install deps into the active venv
make vendor          # pip install -r requirements.txt

# run with auto-reload
make run             # uvicorn app.main:app --reload

# format code
make fmt

# static analysis
make lint

# run tests (pytest will look in tests/)
make test

# run a service
make run
```


> **Creator** – [@Viroslav](https://github.com/Viroslav)