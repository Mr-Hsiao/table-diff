@echo off
rem 打包为单机 exe(后端 + 前端静态)。首次运行前: pip install pyinstaller
rem 产物: backend\dist\hotel-recon.exe
rem 部署: 把 exe 放到酒店电脑上双击运行,浏览器打开 http://127.0.0.1:8000
cd /d %~dp0backend
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --name hotel-recon ^
  --add-data "app\static;app\static" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  app.main
echo.
echo 完成: backend\dist\hotel-recon.exe
echo 提示: 注册为开机自启可用 NSSM(服务方式)或放入启动文件夹。
