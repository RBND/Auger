@echo off
setlocal

REM Clear any invalid system-wide PYTHONHOME variable
set "PYTHONHOME="

REM Change to the directory where this batch file is located.
cd /d "%~dp0"

echo ========================================================
echo   Running Repomix on Auger Codebase
echo ========================================================
echo.

REM Check if repomix is installed globally
where repomix >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=repomix"
    goto :run_tool
)

REM Check if npx is available
where npx >nul 2>nul
if %errorlevel%==0 (
    set "RUNNER=npx.cmd --yes repomix"
    goto :run_tool
)

echo [ERROR] Neither 'repomix' nor 'npx' was found on your PATH.
echo.
echo To run Repomix, please install Node.js:
echo   1. Download and install Node.js from https://nodejs.org/
echo   2. Or install Repomix globally via: npm install -g repomix
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b 1

:run_tool
echo Executing: %RUNNER% %*
echo.

call %RUNNER% %*
set "EXIT_CODE=%errorlevel%"

echo.
if %EXIT_CODE%==0 (
    echo ========================================================
    echo   Repomix completed successfully!
    echo ========================================================
) else (
    echo ========================================================
    echo   [ERROR] Repomix failed with exit code %EXIT_CODE%.
    echo ========================================================
)

if not "%NO_PAUSE%"=="1" (
    echo.
    pause
)

exit /b %EXIT_CODE%
