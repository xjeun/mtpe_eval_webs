@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo .venv 가 없습니다. 먼저 setup.bat 을 실행하세요.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
streamlit run app.py
pause
