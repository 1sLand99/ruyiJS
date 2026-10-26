@echo off
"%~dp0vendor\necko-derived\python\python.exe" -I -B "%~dp0python\_run.py" %*
exit /b %errorlevel%
