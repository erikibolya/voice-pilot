@echo off
chcp 65001 >nul
setlocal
title voice-pilot - instalace

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 goto :chyba

echo.
echo  Hotovo.
pause
exit /b 0

:chyba
echo.
echo  Instalace selhala. Podrobnosti jsou vypsane vyse.
pause
exit /b 1
