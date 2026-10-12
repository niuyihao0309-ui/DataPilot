@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ==========================================================================
REM   data-agent 项目开关（增强版）
REM   ----------------------------------------------------------------------
REM   双击运行              -> Docker 没开就【自动启动 Docker Desktop】并等待就绪，
REM                            然后起全栈（基础设施 + 后端 + 前端），
REM                            最后【自动打开前端页面】—— 双击一下全搞定
REM   app_switch.bat start  -> 同双击
REM   app_switch.bat stop   -> 停止全部容器
REM   app_switch.bat status -> 查看容器状态
REM   app_switch.bat logs   -> 跟踪后端日志
REM   app_switch.bat build  -> 强制重建前后端镜像后再启动（改了代码用这个）
REM ==========================================================================

set "ACTION=%~1"
if /i "%ACTION%"=="stop"   goto :STOP
if /i "%ACTION%"=="status" goto :STATUS
if /i "%ACTION%"=="logs"   goto :LOGS
if /i "%ACTION%"=="build"  goto :BUILD
goto :START


REM ==========================================================================
REM  子过程：确保 Docker 引擎可用（没开就拉起 Docker Desktop 并轮询等待）
REM  返回： errorlevel 0 = 已就绪；1 = 找不到 / 启动超时
REM ==========================================================================
:ENSURE_DOCKER
docker info >nul 2>&1
if not errorlevel 1 exit /b 0

echo       Docker 未运行，正在自动启动 Docker Desktop ...

set "DD="
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set "DD=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not defined DD if exist "%LocalAppData%\Docker\Docker Desktop.exe" set "DD=%LocalAppData%\Docker\Docker Desktop.exe"

if not defined DD (
    echo       [X] 找不到 Docker Desktop.exe，请手动启动 Docker Desktop 后重试。
    exit /b 1
)

start "" "%DD%"
echo       已发出启动命令，等待引擎就绪（首次可能要 1~2 分钟，请耐心等待）...

set /a _WAIT=0
:WAIT_DOCKER
ping -n 4 127.0.0.1 >nul
docker info >nul 2>&1
if not errorlevel 1 (
    echo.
    echo       Docker 已就绪。
    exit /b 0
)
set /a _WAIT+=3
if %_WAIT% GEQ 180 (
    echo.
    echo       [X] 等待 180 秒仍未就绪，请手动确认 Docker Desktop 状态后重试。
    exit /b 1
)
<nul set /p "=."
goto :WAIT_DOCKER


:START
echo.
echo ===== data-agent 项目开关 · 启动 =====
echo.
echo [1/3] 检查 Docker ...
call :ENSURE_DOCKER
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo [2/3] 启动容器（首次会构建前后端镜像，耗时较长）...
cd docker
docker compose up -d
if errorlevel 1 (
    echo       启动失败，请看上面的报错。
    cd ..
    pause
    exit /b 1
)
cd ..

echo [3/3] 完成，服务如下：
echo.
echo       前端:      http://localhost:5173
echo       后端:      http://localhost:8005
echo       接口文档:  http://localhost:8005/docs
echo       Kibana:    http://localhost:5601
echo.
echo       5 秒后自动打开前端页面（给 nginx 一点启动时间）...
ping -n 6 127.0.0.1 >nul
start "" "http://localhost:5173"
pause
exit /b 0


:BUILD
echo.
echo ===== data-agent 项目开关 · 重建并启动 =====
echo.
echo [1/2] 检查 Docker ...
call :ENSURE_DOCKER
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo [2/2] 重建前后端镜像并启动 ...
cd docker
docker compose up -d --build
if errorlevel 1 (
    echo       构建/启动失败，请看上面的报错。
    cd ..
    pause
    exit /b 1
)
cd ..
echo.
echo 已重建并启动，5 秒后自动打开前端页面 ...
ping -n 6 127.0.0.1 >nul
start "" "http://localhost:5173"
pause
exit /b 0


:STOP
echo.
echo ===== data-agent 项目开关 · 停止 =====
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker 未运行，无需停止。
    pause
    exit /b 0
)
cd docker
docker compose down
cd ..
echo.
echo 已停止。
pause
exit /b 0


:STATUS
echo.
echo ===== data-agent 项目开关 · 状态 =====
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker 未运行。
    pause
    exit /b 0
)
cd docker
docker compose ps
cd ..
pause
exit /b 0


:LOGS
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker 未运行。
    pause
    exit /b 0
)
cd docker
docker compose logs -f backend
cd ..
exit /b 0
