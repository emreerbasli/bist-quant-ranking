@echo off
chcp 65001 > nul
title BIST V3 Quant - Gunluk Veri Guncelleme Servisi

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python tasks\data_sync_service.py %*
pause
