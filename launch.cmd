@echo off
chcp 65001 >nul
cd /d "%~dp0"
title voice-pilot

rem Izolace: aplikace musi videt jen sve balicky, ne uzivatelovy globalni.
set PYTHONNOUSERSITE=1

rem Instalator pribaluje vlastni Python ve slozce python\.
rem Vyvojove prostredi ma .venv\.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) else if exist "python\python.exe" (
    "python\python.exe" run.py
) else (
    python run.py
)

if errorlevel 1 (
    echo.
    echo  Aplikace skoncila s chybou.
    pause
)
