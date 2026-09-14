@echo off
chcp 65001 > nul
title BIST V4 Quant - Paper Trading Servisi (9-Feature Ranker)

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python run_paper_trader_v4.py %*
pause
