@echo off
echo === TelegramManager Build ===

echo [0/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 ( echo venv not found. Run: python -m venv venv & pause & exit /b 1 )

where node >nul 2>&1
if errorlevel 1 ( echo Node.js not found. Install from nodejs.org & pause & exit /b 1 )

echo [1/5] Generating icon...
python create_icon.py
if errorlevel 1 ( pause & exit /b 1 )

echo [2/5] Installing Python dependencies...
pip install -r requirements.txt -q
if errorlevel 1 ( pause & exit /b 1 )

echo [3/5] Building frontend...
cd frontend
call npm install --silent
if errorlevel 1 ( cd .. & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( cd .. & pause & exit /b 1 )
cd ..

echo [4/5] Building exe...
pyinstaller telegram_manager.spec --clean --noconfirm --distpath .
if errorlevel 1 ( pause & exit /b 1 )

echo [5/5] Cleaning up...
rmdir /s /q build 2>nul

echo.
echo === Done! ===
echo Exe is at: TelegramManager.exe
echo.
pause
