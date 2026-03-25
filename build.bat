@echo off
echo Cleaning old build...
if exist "dist\LAN-FT"  rmdir /s /q "dist\LAN-FT"
if exist "build\LAN-FT" rmdir /s /q "build\LAN-FT"

echo Building LAN-FT...
pyinstaller LAN-FT.spec ^
  --noconfirm ^
  --clean

if exist "dist\LAN-FT\LAN-FT.exe" (
    echo.
    echo SUCCESS: dist\LAN-FT\LAN-FT.exe
) else (
    echo FAILED: exe not found
)
pause
