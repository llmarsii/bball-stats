@echo off
setlocal

cd /d "%~dp0"
set PORT=8765

python -c "import socket, sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) == 0 else 1)" %PORT%
if %ERRORLEVEL%==0 (
    echo Port %PORT% is already in use. Close the other app or edit start.bat and pick another port.
    pause
    exit /b 1
)

python -c "import streamlit" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Streamlit is not installed. Installing requirements now...
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% NEQ 0 (
        echo Dependency install failed.
        pause
        exit /b 1
    )
)

echo Starting Pickup Stat Tracker on http://localhost:%PORT%
echo Close this window to stop the local app.
python -m streamlit run app.py --server.port %PORT% --server.address localhost

pause
