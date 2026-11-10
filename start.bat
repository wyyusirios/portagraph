@echo off
rem Запуск PortaGraph на Windows: двойной щелчок по start.bat
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Создаю виртуальное окружение...
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python run.py
pause
