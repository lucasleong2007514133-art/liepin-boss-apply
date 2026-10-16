@echo off
chcp 65001 >nul
setlocal
title 启动可控制浏览器（独立 profile · 安全）

set "PORT=9222"
set "BROWSER=D:\chrome谷歌浏览器\ChromeCore\ChromeCore.exe"
set "SAFEPROFILE=%~dp0profile"

echo ============================================================
echo   启动「可被 AI 控制」的浏览器（独立 profile）
echo ============================================================
echo   浏览器     : %BROWSER%
echo   独立资料夹 : %SAFEPROFILE%
echo   调试端口   : %PORT%
echo ------------------------------------------------------------
echo   说明：这里用的是**独立的**浏览器资料夹，不会碰你日常
echo         那个 ChromeCore（书签/登录态/标签页完全不受影响），
echo         所以**不需要**退出你正在用的浏览器。
echo.
echo   第一次用需要在弹出的窗口里登录一次猎聘/BOSS直聘，
echo   登录状态会保存在这个独立资料夹里，以后不用重复登录。
echo ============================================================
echo.

if not exist "%BROWSER%" (
  echo [x] 找不到浏览器: %BROWSER%
  pause
  exit /b 1
)

if not exist "%SAFEPROFILE%" mkdir "%SAFEPROFILE%"

echo [*] 正在启动...
start "" "%BROWSER%" --remote-debugging-port=%PORT% --user-data-dir="%SAFEPROFILE%" --no-first-run --no-default-browser-check

echo [*] 等待调试端口就绪...
set /a N=0
:waitloop
set /a N+=1
timeout /t 2 /nobreak >nul
curl -s -o nul http://127.0.0.1:%PORT%/json/version 2>nul
if not errorlevel 1 goto ready
if %N% LSS 15 goto waitloop

echo [x] 端口 %PORT% 未就绪。可能原因：
echo     - 该浏览器内核不支持此参数
echo     - 端口被其他程序占用
echo.
pause
exit /b 1

:ready
echo.
echo [√] 已就绪！这个浏览器现在可以被 AI 控制。
echo.
echo     下一步：
echo       1) 在这个窗口里打开并登录 猎聘 / BOSS直聘（只需一次）
echo       2) 回来告诉 AI 你要做什么
echo.
echo     收尾：直接关掉这个浏览器窗口即可，不影响你日常用的 ChromeCore。
echo.
timeout /t 5 /nobreak >nul
exit /b 0
