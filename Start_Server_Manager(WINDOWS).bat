@echo off
setlocal

REM Clear any invalid system-wide PYTHONHOME variable that causes Python startup warnings.
set "PYTHONHOME="

REM Change to the directory where this batch file is located.
cd /d "%~dp0"

REM Check whether Python is installed and available on PATH.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo.
        echo Python 3 is not installed or is not available on PATH.
        echo Please install Python 3 from https://www.python.org/downloads/
        echo (Make sure to check "Add python.exe to PATH" and "tcl/tk and IDLE")
        echo.
        pause
        exit /b 1
    )
)

REM Run main.py if it exists.
if exist "main.py" (
    echo Starting Auger Dedicated Server Manager...
    %PYTHON% main.py
) else if exist "Main.py" (
    echo Starting Auger Dedicated Server Manager...
    %PYTHON% Main.py
) else (
    echo Error: main.py not found in this directory!
)

echo.
echo Process finished.
pause
