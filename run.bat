@echo off
setlocal EnableDelayedExpansion
title KING SLAYER

where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

set "PF86=%ProgramFiles(x86)%"
set "BRAVE_FOUND=0"
if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" set "BRAVE_FOUND=1"
if defined PF86 if exist "%PF86%\BraveSoftware\Brave-Browser\Application\brave.exe" set "BRAVE_FOUND=1"
if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" set "BRAVE_FOUND=1"
if "!BRAVE_FOUND!"=="0" (
    where brave >nul 2>&1
    if not errorlevel 1 set "BRAVE_FOUND=1"
)
if "!BRAVE_FOUND!"=="0" (
    echo.
    echo   BRAVE BROWSER NOT FOUND
    echo   KING SLAYER currently ONLY supports Brave Browser.
    echo.
    echo   Download Brave from:  https://brave.com/download/
    echo   After installing, run this launcher again.
    echo.
    pause
    exit /b 1
)
echo [OK] Brave browser found.

set MISSING=0
for %%p in (requests websocket chess colorama) do (
    python -c "import %%p" >nul 2>&1
    if errorlevel 1 (
        pip install %%p --quiet
        if errorlevel 1 set MISSING=1
    )
)
if "!MISSING!"=="1" (
    echo Failed to install dependencies. Run: pip install requests websocket-client chess colorama
    pause
    exit /b 1
)

if not exist "%~dp0king_slayer.py" (
    echo king_slayer.py not found. Make sure all files are in the same folder.
    pause
    exit /b 1
)

set PATRICIA_PATH=
if exist "PATRICIA.exe" set PATRICIA_PATH=PATRICIA.exe
if exist "PATRICIA" set PATRICIA_PATH=PATRICIA
if "!PATRICIA_PATH!"=="" where PATRICIA >nul 2>&1 && set PATRICIA_PATH=PATRICIA
if "!PATRICIA_PATH!"=="" (
    for %%f in ("%~dp0engines\PATRICIA.exe" "%~dp0engines\PATRICIA" "%LOCALAPPDATA%\PATRICIA\PATRICIA.exe") do (
        if "!PATRICIA_PATH!"=="" if exist %%f set PATRICIA_PATH=%%f
    )
)
if "!PATRICIA_PATH!"=="" (
    set /p PATRICIA_PATH="Patricia not found. Enter path to PATRICIA.exe (or press Enter to skip): "
)

cd /d "%~dp0"
if not "!PATRICIA_PATH!"=="" (
    python king_slayer.py --patricia "!PATRICIA_PATH!"
) else (
    python king_slayer.py
)

if errorlevel 1 pause
endlocal