@echo off
echo === TelegramManager Build ===

echo [1/3] Generating icon...
python create_icon.py
if errorlevel 1 ( echo Failed to create icon & pause & exit /b 1 )

echo [2/3] Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 ( echo Failed to install deps & pause & exit /b 1 )

echo [3/3] Building exe...
pyinstaller telegram_manager.spec --clean --noconfirm
if errorlevel 1 ( echo Build failed & pause & exit /b 1 )

echo.
echo === Done! ===
echo Exe is at:  dist\TelegramManager.exe
echo.
pause
