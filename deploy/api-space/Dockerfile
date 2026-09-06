# Bhao API — Hugging Face Space (Docker).
# Free tier: CPU, no card, sleeps after 48h idle and wakes on request;
# artefacts are fetched from the GitHub Release at every cold start, so the
# panel is always the latest weekly run.
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY contracts ./contracts
COPY ingest ./ingest
COPY orchestration ./orchestration
COPY features ./features
COPY models ./models
COPY evaluation ./evaluation
COPY drift ./drift
COPY registry ./registry
COPY api ./api
COPY ops ./ops
COPY deploy/api-space/fetch_data.py ./fetch_data.py

RUN pip install --no-cache-dir .

ENV BHAO_DATA_DIR=/app/data
EXPOSE 7860

# HF Spaces routes public traffic to 7860
CMD ["sh", "-c", "python fetch_data.py && uvicorn api.main:app --host 0.0.0.0 --port 7860"]
