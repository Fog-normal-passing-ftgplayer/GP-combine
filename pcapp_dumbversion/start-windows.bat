@echo off
rem 懒人包启动器（Windows）：优先用包内的 python，其次用系统的
setlocal
set "HERE=%~dp0"
if exist "%HERE%python\python.exe" (
  "%HERE%python\python.exe" "%HERE%main.py" %*
) else (
  python "%HERE%main.py" %*
)
endlocal
