@echo off
rem 一键启动:优先用虚拟环境 .venv,没有则直接用系统 Python(依赖需已安装)
cd /d %~dp0backend
if exist ".venv\Scripts\python.exe" (
  echo [使用虚拟环境 backend\.venv]
  set "PY=.venv\Scripts\python.exe"
) else (
  echo [未找到 .venv,使用系统 Python(需已安装 fastapi/uvicorn/openpyxl)]
  set "PY=python"
)
echo [启动服务: http://127.0.0.1:8000 ]
%PY% -m app.main
