@echo off
setlocal
cd /d %~dp0
python -m pip install -r requirements.txt
start "" http://127.0.0.1:8765
python -m uvicorn main:app --host 127.0.0.1 --port 8765
