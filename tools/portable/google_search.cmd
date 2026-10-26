@echo off
"%~dp0vendor\necko-derived\python\python.exe" -I -B "%~dp0examples\google\google_search.py" %*
exit /b %errorlevel%
