@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/4] scorer: Python 3.11 가상환경 생성...
py -3.11 -m venv scorer\.venv || goto :err

echo [2/4] scorer: 패키지 설치... (torch, COMET 포함이라 수 분 걸립니다)
call scorer\.venv\Scripts\activate.bat
python -m pip install --upgrade pip || goto :err
pip install -r scorer\requirements.txt || goto :err
call deactivate

echo [3/4] server: Node 패키지 설치...
pushd server
call npm install || (popd & goto :err)
popd

echo [4/4] .env 준비...
if not exist .env (
  copy .env.example .env >nul
  echo .env 파일을 만들었습니다. 메모장으로 열어 DEEPL_API_KEY, HF_TOKEN 값을 채워주세요.
)

echo.
echo 완료. start.bat 으로 실행하세요.
pause
exit /b 0

:err
echo.
echo 설치 중 오류가 발생했습니다. Python 3.11 과 Node.js 가 설치돼 있는지 확인하세요.
echo   py -3.11 --version
echo   node --version
pause
exit /b 1
