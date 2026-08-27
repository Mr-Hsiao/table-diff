@echo off
rem 打包为单机 exe(后端 + 前端静态)。首次运行前: pip install pyinstaller
rem 产物: backend\dist\table-diff.exe
rem 部署: 把 exe 放到用户电脑上双击运行,浏览器打开提示的地址;
rem        同目录会自动生成 data 文件夹(存映射方案和对账记录),拷走即备份
cd /d %~dp0backend
.venv\Scripts\pip install pyinstaller 2>nul || pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --name table-diff ^
  --add-data "app\static;app\static" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  entry.py
echo.
echo 完成: backend\dist\table-diff.exe
echo 提示: 注册为开机自启可用 NSSM(服务方式)或放入启动文件夹。

