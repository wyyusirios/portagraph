@echo off
rem Запуск PortaGraph на Windows: двойной щелчок по start.bat
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Создаю виртуальное окружение...
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo Не удалось установить зависимости. Проверьте интернет и запустите start.bat ещё раз.
  pause
  exit /b 1
)
python run.py
pause
