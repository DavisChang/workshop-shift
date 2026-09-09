@echo off
setlocal
chcp 65001 >nul
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
pushd "%~dp0"
if errorlevel 1 exit /b 1

py -3 -c "import sys, sqlite3; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_py
python3 -c "import sys, sqlite3; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_python3
python -c "import sys, sqlite3; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 goto run_python

echo Python 3.9 or newer with SQLite support is required.
echo Install Python 3 with the Python launcher or add Python to PATH.
echo Then run start.bat again.
popd
pause
exit /b 1

:run_py
py -3 -X utf8 -B app.py %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
goto finished

:run_python3
python3 -X utf8 -B app.py %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
goto finished

:run_python
python -X utf8 -B app.py %*
set "APP_EXIT_CODE=%ERRORLEVEL%"

:finished
popd
if not "%APP_EXIT_CODE%"=="0" pause
exit /b %APP_EXIT_CODE%
