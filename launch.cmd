@echo off
chcp 65001 >nul
cd /d "%~dp0"
title voice-pilot
".venv\Scripts\python.exe" run.py
if errorlevel 1 (
    echo.
    echo  Aplikace skoncila s chybou.
    pause
)
