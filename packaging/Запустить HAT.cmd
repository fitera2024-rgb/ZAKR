@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".hat-runtime\Scripts\python.exe" call "Установить HAT.cmd"
if not exist ".hat-runtime\Scripts\python.exe" exit /b 1

start "" http://127.0.0.1:8765/
".hat-runtime\Scripts\python.exe" -m uvicorn hierarchy_account_transfer.api:app --host 127.0.0.1 --port 8765
