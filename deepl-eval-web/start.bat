@echo off
chcp 65001 >nul
setlocal

REM ==== Project root (이 파일이 있는 폴더) ====
cd /d "%~dp0"

if not exist scorer\.venv (
  echo scorer\.venv 가 없습니다. 먼저 setup.bat 을 실행하세요.
  pause
  exit /b 1
)
if not exist .env (
  echo .env 가 없습니다. .env.example 을 .env 로 복사하고 키를 채우세요.
  pause
  exit /b 1
)

REM ==== Start scorer (Python FastAPI) ====
start "scorer-8001" cmd /k "cd scorer && call .venv\Scripts\activate.bat && uvicorn app:app --host 127.0.0.1 --port 8001"

REM ==== Start server (Node/Express) ====
start "server-3000" cmd /k "cd server && npm run dev"

echo Started scorer(8001) and server(3000).
echo - 처음 실행 때는 COMET 모델(약 5GB)을 내려받느라 scorer 창이 몇 분 걸립니다.
echo - scorer 창에 "COMETkiwi loaded." 가 뜬 뒤에 웹을 쓰세요.
echo - Scorer docs: http://127.0.0.1:8001/docs
echo - Web UI:      http://127.0.0.1:3000
echo - Health:      http://127.0.0.1:3000/api/health
pause
endlocal
