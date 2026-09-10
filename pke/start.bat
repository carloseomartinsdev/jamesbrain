@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /i "%~1"=="stop" goto do_stop
if /i "%~1"=="fg" goto do_fg

call :ensure_venv
if errorlevel 1 (
    echo.
    echo  Falha ao preparar o .venv.
    exit /b 1
)

call :load_env
if not exist "data" mkdir "data"

if /i "%~1"=="run" goto do_run

powershell -NoProfile -Command "Start-Process -FilePath '%CD%\.venv\Scripts\python.exe' -ArgumentList '-m','pke.product' -WorkingDirectory '%CD%' -WindowStyle Hidden"
echo PKE em segundo plano  http://%PKE_HTTP_HOST%:%PKE_HTTP_PORT%
echo Parar:  start.bat stop    ^|  Console: start.bat fg
exit /b 0

:do_fg
call :ensure_venv
if errorlevel 1 exit /b 1
call :load_env
if not exist "data" mkdir "data"
echo PKE (console)  http://%PKE_HTTP_HOST%:%PKE_HTTP_PORT%
echo Encerrar: Ctrl+C  ou  start.bat stop
echo.
".venv\Scripts\python.exe" -m pke.product
exit /b %ERRORLEVEL%

:do_run
".venv\Scripts\python.exe" -m pke.product
exit /b %ERRORLEVEL%

:do_stop
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="PKE_HTTP_PORT" set "PKE_HTTP_PORT=%%B"
    )
)
if not defined PKE_HTTP_PORT set "PKE_HTTP_PORT=8000"
set "KILLED=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PKE_HTTP_PORT% " ^| findstr "LISTENING"') do (
    echo Encerrando PID %%P na porta %PKE_HTTP_PORT%
    taskkill /PID %%P /F >nul
    set "KILLED=1"
)
if "%KILLED%"=="0" echo Nada escutando na porta %PKE_HTTP_PORT%.
exit /b 0

:load_env
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)
if not defined PKE_HTTP_HOST set "PKE_HTTP_HOST=127.0.0.1"
if not defined PKE_HTTP_PORT set "PKE_HTTP_PORT=8000"
if not defined PKE_AUTH_MODE set "PKE_AUTH_MODE=dev"
if not defined PYTHONPATH set "PYTHONPATH=%CD%\src"
exit /b 0

:ensure_venv
call :venv_home_ok
if not errorlevel 1 exit /b 0

echo.
echo  O .venv aponta para um Python que nao existe neste PC.
echo  Recriando o ambiente...
echo.

call :find_bootstrap_python
if not defined BOOTSTRAP (
    echo  ERRO: nenhum Python encontrado. Instale 3.11+ ^(ideal 3.12+^) e rode de novo.
    exit /b 1
)

echo  Usando: %BOOTSTRAP%
if exist ".venv" (
    echo  Removendo .venv antigo...
    rmdir /s /q ".venv"
    if exist ".venv" (
        echo  ERRO: nao foi possivel apagar .venv ^(arquivo em uso?^).
        exit /b 1
    )
)

%BOOTSTRAP% -m venv ".venv"
if errorlevel 1 (
    echo  ERRO: falha ao criar .venv
    exit /b 1
)

echo  Instalando o pacote PKE e dependencias...
".venv\Scripts\python.exe" -m pip install -U pip
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo  pip recusou a versao do Python; tentando com --ignore-requires-python...
    ".venv\Scripts\python.exe" -m pip install -e ".[dev]" --ignore-requires-python
    if errorlevel 1 (
        echo  ERRO: pip install falhou.
        exit /b 1
    )
)
echo  Ambiente pronto.
echo.
exit /b 0

:venv_home_ok
if not exist ".venv\Scripts\python.exe" exit /b 1
if not exist ".venv\pyvenv.cfg" exit /b 1
set "VENV_HOME="
for /f "usebackq tokens=1,* delims==" %%A in (".venv\pyvenv.cfg") do (
    if /i "%%A"=="home " set "VENV_HOME=%%B"
    if /i "%%A"=="home" set "VENV_HOME=%%B"
)
for /f "tokens=*" %%H in ("%VENV_HOME%") do set "VENV_HOME=%%H"
if not defined VENV_HOME exit /b 1
if not exist "%VENV_HOME%\python.exe" exit /b 1
exit /b 0

:find_bootstrap_python
set "BOOTSTRAP="
where py >nul 2>&1
if errorlevel 1 goto find_python_exe
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BOOTSTRAP=py -3.12"
    exit /b 0
)
py -3.13 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BOOTSTRAP=py -3.13"
    exit /b 0
)
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BOOTSTRAP=py -3"
    exit /b 0
)
:find_python_exe
where python >nul 2>&1
if not errorlevel 1 set "BOOTSTRAP=python"
exit /b 0
