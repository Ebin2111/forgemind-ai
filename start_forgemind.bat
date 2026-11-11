@echo off
setlocal
cd /d "%~dp0"
title ForgeMind AI - launcher
echo ==================================================
echo    ForgeMind AI - starting
echo ==================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [X] The Python environment ".venv" was not found in this folder.
  echo     Folder checked: %CD%
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing the website packages - first time only, a few minutes...
  pushd frontend
  call npm install
  popd
)

if not exist "frontend\.next\BUILD_ID" (
  echo Preparing the website - first time only, about 1 to 2 minutes...
  pushd frontend
  call npm run build
  popd
)
if not exist "frontend\.next\BUILD_ID" (
  echo [X] The website could not be prepared. Run  npm run build  inside the frontend folder to see why.
  pause
  exit /b 1
)

echo Closing any old ForgeMind servers still running...
for %%P in (3000 8000) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do taskkill /PID %%I /T /F >nul 2>&1
)

echo Starting the backend...
start "ForgeMind backend" /min cmd /k .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

echo Starting the website...
start "ForgeMind website" /min /d "%~dp0frontend" cmd /k npm start -- -H 0.0.0.0 -p 3000

echo Waiting until the website is ready...
powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){ try{ Invoke-WebRequest http://localhost:3000/login -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 }catch{ Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo [X] The website did not start. Open the two minimized windows named ForgeMind to read the error.
  pause
  exit /b 1
)

start "" http://localhost:3000

echo.
echo ==================================================
echo    ForgeMind AI is running
echo ==================================================
echo.
echo  On this computer :  http://localhost:3000
echo.
echo  On your phone (same Wi-Fi) - open one of these:
ipconfig | findstr /i "IPv4"
echo      then add :3000 at the end, for example  http://192.168.1.20:3000
echo.
echo  Keep this window open while you use ForgeMind.
echo  To STOP everything, press any key here.
echo.
pause >nul

echo Stopping...
taskkill /FI "WINDOWTITLE eq ForgeMind backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq ForgeMind website*" /T /F >nul 2>&1
for %%P in (3000 8000) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do taskkill /PID %%I /T /F >nul 2>&1
)
echo Stopped. You can close this window.
timeout /t 3 >nul