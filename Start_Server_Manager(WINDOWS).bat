@echo off
setlocal

REM Clear any invalid system-wide PYTHONHOME variable that causes Python startup warnings.
set "PYTHONHOME="

REM Change to the directory where this batch file is located.
cd /d "%~dp0"

REM Find Python 3. "if errorlevel 1" is evaluated at run time, unlike %errorlevel%
REM inside a parenthesized block (which is expanded once, when the block is parsed).
set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)

if not defined PYTHON (
    echo.
    echo Python 3 is not installed or is not available on PATH.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo ^(Make sure to check "Add python.exe to PATH" and "tcl/tk and IDLE"^)
    echo.
    pause
    exit /b 1
)

REM Make sure Tkinter (the GUI library) is available.
%PYTHON% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was found, but its Tkinter GUI module is missing.
    echo Re-run the Python installer, choose "Modify", and tick "tcl/tk and IDLE".
    echo.
    pause
    exit /b 1
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
