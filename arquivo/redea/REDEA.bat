@echo off
title REDEA
cd /d "%~dp0agent"
:loop
python redea_agent.py
echo.
echo [agente caiu, subindo de novo em 3s - feche esta janela para parar]
timeout /t 3 >nul
goto loop
