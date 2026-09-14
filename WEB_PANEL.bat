@echo off
chcp 65001 > nul
title BIST V4 Quant - Web Yonetim Paneli

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python main.py panel
pause
