@echo off
call "%~dp0python.cmd" "%~dp0example.py" %*
exit /b %errorlevel%
