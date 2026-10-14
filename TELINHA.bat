@echo off
title TELINHA
cd /d "%~dp0agent"
:loop
python telinha_agent.py
rem Saiu de proposito (Ctrl+C, --list, --test) = codigo 0: nao reinicia.
if %errorlevel% equ 0 goto fim
echo.
echo [agente caiu com codigo %errorlevel%, subindo de novo em 3s - feche esta janela para parar]
timeout /t 3 >nul
goto loop
:fim
