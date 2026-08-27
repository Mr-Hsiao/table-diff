"""PyInstaller 打包入口(运行方式: python entry.py,或打包后的 hotel-recon.exe)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import run_server

if __name__ == "__main__":
    run_server()
