@echo off
chcp 65001 > nul
echo Starting Telegram Bot...
echo.

REM Активируем виртуальное окружение
call venv\Scripts\activate.bat

REM Запускаем бота
python main.py

REM Пауза перед закрытием окна
pause