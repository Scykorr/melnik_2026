@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск ИАМ «Регион»...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1"
echo.
echo Сервер остановлен.
pause
