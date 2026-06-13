@echo off
REM Open-Canoe One-Click Deploy and Run
REM Run from project root: tools\deploy.bat
REM External tool paths use environment variables (see REQUIREMENTS.md §11)

cd /d "%~dp0\.."

echo ============================================================
echo   Open-Canoe One-Click Deploy
echo   Target: STM32F103C8T6
echo ============================================================

echo.
echo [1/3] Building and flashing firmware...
cd tools
python build.py flash f103
if %ERRORLEVEL% NEQ 0 (
    echo BUILD/FLASH FAILED!
    pause
    exit /b 1
)
cd ..

echo.
echo [2/3] Running hardware tests...
cd open-canoe
uv run python ..\test\test_hardware.py COM7
if %ERRORLEVEL% NEQ 0 (
    echo TESTS FAILED!
)
cd ..

echo.
echo [3/3] Launching App...
cd open-canoe
start "" uv run python main.py
cd ..

echo.
echo ============================================================
echo   DEPLOY COMPLETE - App is starting...
echo ============================================================
pause
