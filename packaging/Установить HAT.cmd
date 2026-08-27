@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON="
where py >nul 2>nul && set "PYTHON=py -3.12"
if not defined PYTHON where python >nul 2>nul && set "PYTHON=python"
if not defined PYTHON goto :install_python

%PYTHON% -c "import sys;raise SystemExit(sys.version_info < (3,12))" >nul 2>nul
if errorlevel 1 goto :install_python

goto :create_environment

:install_python
echo Python 3.12 не найден. Загружаю официальный установщик Python...
set "PYTHON_INSTALLER=%TEMP%\python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%PYTHON_INSTALLER%'" || goto :no_python
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1 || goto :no_python
del "%PYTHON_INSTALLER%" >nul 2>nul
set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PYTHON%" set "PYTHON=py -3.12"

:create_environment

echo Создание изолированного окружения HAT...
%PYTHON% -m venv .hat-runtime || goto :failed
".hat-runtime\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip || goto :failed
".hat-runtime\Scripts\python.exe" -m pip install --disable-pip-version-check ".\app" || goto :failed
if not exist runs mkdir runs
if not exist local_inputs mkdir local_inputs
echo.
echo HAT установлен. Запустите «Запустить HAT.cmd».
pause
exit /b 0

:no_python
echo.
echo Ошибка: нужен Python 3.12 или новее.
echo Не удалось автоматически установить Python. Проверьте подключение к интернету.
pause
exit /b 1

:failed
echo.
echo Установка не завершена. Проверьте подключение к интернету и повторите запуск.
pause
exit /b 1
