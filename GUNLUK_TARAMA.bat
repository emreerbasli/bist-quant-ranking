@echo off
chcp 65001 > nul
title BIST V3 Quant - Paper Trading Kontrolu

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python main.py tarama
pause
