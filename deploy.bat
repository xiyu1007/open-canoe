@echo off
REM Open-Canoe One-Click Deploy and Run
REM Run from project root directory.

cd /d "%~dp0"

echo ============================================================
echo   Open-Canoe One-Click Deploy
echo   Target: STM32F103C8T6
echo ============================================================

echo.
echo [1/4] Building firmware...
set "PATH=d:/Software/msys64/usr/bin;d:/STM32/Environment/gcc-arm-none-eabi-10.3-2021.10/bin;%PATH%"
cd firmware
make -f Makefile_f103 -j8
if %ERRORLEVEL% NEQ 0 (
    echo BUILD FAILED!
    pause
    exit /b 1
)
echo Build OK.

echo.
echo [2/4] Flashing firmware...
cd /d "%~dp0"
"assert\stlink-1.7.0-x86_64-w64-mingw32\stlink-1.7.0-x86_64-w64-mingw32\bin\st-flash.exe" --reset write "firmware\build_f103\open_canoe_f103.bin" 0x08000000
if %ERRORLEVEL% NEQ 0 (
    echo FLASH FAILED!
    pause
    exit /b 1
)
echo Flash OK.

echo.
echo [3/4] Running hardware tests...
cd /d "%~dp0"
cd open-canoe
uv run python ..\test\test_hardware.py COM7
echo.

echo [4/4] Launching App...
start "" uv run python main.py

echo.
echo ============================================================
echo   DEPLOY COMPLETE - App is starting...
echo ============================================================
pause
