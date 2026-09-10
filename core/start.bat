@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /i "%~1"=="stop" goto do_stop
if /i "%~1"=="fg" goto do_fg

call :ensure_venv
if errorlevel 1 exit /b 1
call :load_env
if not exist "data" mkdir "data"

powershell -NoProfile -Command "Start-Process -FilePath '%CD%\.venv\Scripts\python.exe' -ArgumentList '-m','jamescore' -WorkingDirectory '%CD%' -WindowStyle Hidden"
echo jamesCore em segundo plano  http://%JAMESCORE_HTTP_HOST%:%JAMESCORE_HTTP_PORT%
echo Parar:  start.bat stop    ^|  Console: start.bat fg
exit /b 0

:do_fg
call :ensure_venv
if errorlevel 1 exit /b 1
call :load_env
if not exist "data" mkdir "data"
echo jamesCore (console)  http://%JAMESCORE_HTTP_HOST%:%JAMESCORE_HTTP_PORT%
echo Encerrar: Ctrl+C  ou  start.bat stop
echo.
".venv\Scripts\python.exe" -m jamescore
exit /b %ERRORLEVEL%

:do_stop
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="JAMESCORE_HTTP_PORT" set "JAMESCORE_HTTP_PORT=%%B"
    )
)
if not defined JAMESCORE_HTTP_PORT set "JAMESCORE_HTTP_PORT=8010"
set "KILLED=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%JAMESCORE_HTTP_PORT% " ^| findstr "LISTENING"') do (
    echo Encerrando PID %%P na porta %JAMESCORE_HTTP_PORT%
    taskkill /PID %%P /F >nul
    set "KILLED=1"
)
if "%KILLED%"=="0" echo Nada escutando na porta %JAMESCORE_HTTP_PORT%.
exit /b 0

:load_env
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
)
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)
if not defined JAMESCORE_HTTP_HOST set "JAMESCORE_HTTP_HOST=127.0.0.1"
if not defined JAMESCORE_HTTP_PORT set "JAMESCORE_HTTP_PORT=8010"
if not defined PYTHONPATH set "PYTHONPATH=%CD%\src"
exit /b 0

:ensure_venv
if exist ".venv\Scripts\python.exe" goto venv_ok
echo Criando .venv...
where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -m venv ".venv" 2>nul || py -3 -m venv ".venv"
) else (
    python -m venv ".venv"
)
if errorlevel 1 (
    echo ERRO: nao foi possivel criar .venv
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo ERRO: pip install falhou.
    exit /b 1
)
:venv_ok
exit /b 0
