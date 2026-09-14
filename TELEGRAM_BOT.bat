@echo off
chcp 65001 > nul
title BIST V4 Quant - Telegram Canli Botu

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python main.py bot
pause
