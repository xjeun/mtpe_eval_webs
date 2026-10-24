@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/3] Python 3.11 가상환경 생성...
py -3.11 -m venv .venv || goto :err

echo [2/3] pip 업그레이드...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :err

echo [3/3] 패키지 설치... (torch, COMET 포함이라 수 분 걸립니다)
pip install -r requirements.txt || goto :err

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo .env 파일을 만들었습니다. 메모장으로 열어 OPENAI_API_KEY, HF_TOKEN 값을 채워주세요.
)

echo.
echo 완료. run.bat 으로 실행하세요.
pause
exit /b 0

:err
echo.
echo 설치 중 오류가 발생했습니다. Python 3.11 이 설치돼 있는지 확인하세요 (py -3.11 --version).
pause
exit /b 1
