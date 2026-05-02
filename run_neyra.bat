@echo off
REM Thin wrapper: all logic in UTF-8 PowerShell (avoids cmd.exe + Cyrillic + parenthesis bugs).
cd /d "%~dp0"
chcp 65001 >nul
title Neyra · control deck
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\neyra_win_launcher.ps1"
exit /b %ERRORLEVEL%
