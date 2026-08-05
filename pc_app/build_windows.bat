@echo off
chcp 65001 >nul
rem 构建 Windows 版 GP-Fusion 配置向导
setlocal
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.10+，安装时勾选 "Add python.exe to PATH"
  pause
  exit /b 1
)

if not exist .venv (
  echo [1/4] 创建虚拟环境...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] 安装依赖（首次较慢，PySide6 约 200MB）...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo [错误] 依赖安装失败，请检查网络
  pause
  exit /b 1
)

echo [3/4] 打包可执行文件...
python -m PyInstaller --clean --noconfirm gpfusion.spec
if errorlevel 1 (
  echo [错误] 打包失败，请查看上方日志
  pause
  exit /b 1
)

echo [4/4] 生成压缩包...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\GP-Fusion配置向导' -DestinationPath 'dist\GP-Fusion配置向导-windows.zip'"

echo.
echo 完成！
echo 运行目录: dist\GP-Fusion配置向导\（整个文件夹一起拷贝）
echo 压缩包:   dist\GP-Fusion配置向导-windows.zip
pause
