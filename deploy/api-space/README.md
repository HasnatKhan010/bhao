---
title: Bhao API
emoji: 📈
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: true
---

# Bhao API — Hugging Face Space

FastAPI over DuckDB serving the weekly price panel, forecasts, scorecard and
drift log. On every cold start the container fetches the latest artefacts from
the project's GitHub Release, so the space always serves the newest weekly run
without anyone logging in.

The web app (deployed separately) points its API URL at this space. Public,
read-only, no auth — see the repository for the full contract.
