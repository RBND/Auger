@echo off
setlocal

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
        echo Please install Python 3, then run this script again.
        echo.
        pause
        exit /b 1
    )
)

REM Create the virtual environment if it does not already exist.
if not exist "venv\" (
    echo Creating a virtual environment...
    %PYTHON% -m venv venv
    if errorlevel 1 (
        echo.
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

REM Activate the virtual environment.
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo.
    echo Failed to activate the virtual environment.
    pause
    exit /b 1
)

REM Install requirements if requirements.txt exists.
if exist "requirements.txt" (
    echo Installing requirements...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Failed to install requirements.
        pause
        exit /b 1
    )
) else (
    echo Error: requirements.txt not found in this directory!
)

REM Run main.py if it exists.
if exist "main.py" (
    echo Starting main.py...
    python main.py
) else if exist "Main.py" (
    echo Starting Main.py...
    python Main.py
) else (
    echo Error: main.py not found in this directory!
)

echo.
echo Process finished.
pause
