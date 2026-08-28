@echo off
rem 打包为单机 exe(后端 + 前端静态,无控制台窗口)。首次运行前: pip install pyinstaller
rem 产物: backend\dist\table-diff.exe
rem 部署: 把 exe 放到用户电脑上,双击 -> 后台启动服务并自动打开网页;服务已运行则直接打开网页
rem 停止: 运行 table-diff.exe --stop(或任务管理器结束);data 文件夹存数据,拷走即备份
cd /d %~dp0backend
.venv\Scripts\pip install pyinstaller 2>nul || pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --noconsole --name table-diff ^
  --add-data "app\static;app\static" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  entry.py
echo.
echo 完成: backend\dist\table-diff.exe
echo 提示: 双击即用(自动开网页);停止用 table-diff.exe --stop。

