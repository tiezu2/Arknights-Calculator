@echo off
chcp 65001 >nul
rem GitHub 在本机被 hosts 屏蔽，需要先起本地 CONNECT 代理再 push
cd /d "%~dp0.."
set GIT_TERMINAL_PROMPT=0
start "" /min python "%~dp0mini_proxy.py"
timeout /t 2 >nul
git -c http.proxy=http://127.0.0.1:7899 push %*
echo.
echo 推送完成。若失败，检查 tools\mini_proxy.py 顶部的 GitHub IP 是否可用。
pause