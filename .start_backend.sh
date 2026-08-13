#!/usr/bin/env bash
# Start the customer backend (memory-system code) on :8000. conda env python direct.
# App loads .env (FPT key etc.) via database.connection. PYTHONUTF8 for the CrewAI
# Windows cp1252 crash (see memory: crewai-windows-utf8-crash).
PY="/c/Users/Laptop/miniconda3/envs/ai_restaurant/python.exe"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH=backend
cd "$(dirname "$0")"
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
