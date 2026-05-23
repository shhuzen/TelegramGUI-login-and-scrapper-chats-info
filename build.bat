@echo off
echo === TelegramManager Build ===

echo [0/4] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 ( echo venv not found — run: python -m venv venv & pause & exit /b 1 )

echo [1/4] Generating icon...
python create_icon.py
if errorlevel 1 ( echo Failed to create icon & pause & exit /b 1 )

echo [2/4] Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 ( echo Failed to install deps & pause & exit /b 1 )

echo [3/4] Building exe...
pyinstaller telegram_manager.spec --clean --noconfirm --distpath .
if errorlevel 1 ( echo Build failed & pause & exit /b 1 )

echo [4/4] Cleaning up build artifacts...
rmdir /s /q build 2>nul
del /q *.spec.bak 2>nul

echo.
echo === Done! ===
echo Exe is at:  TelegramManager.exe
echo.
pause
