@echo off
setlocal
cd /d %~dp0

echo [1/3] Python paketleri kuruluyor...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
if errorlevel 1 goto :error

echo [2/3] EXE olusturuluyor...
python -m PyInstaller --clean --noconfirm --onefile --name ShopifyToolsPanel desktop_launcher.py
if errorlevel 1 goto :error

echo [3/3] Tamamlandi.
echo EXE: %cd%\dist\ShopifyToolsPanel.exe
pause
exit /b 0

:error
echo.
echo HATA: EXE olusturulamadi.
pause
exit /b 1
