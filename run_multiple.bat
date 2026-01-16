@echo off
REM Configuration
SET OUTPUT_DIR=F:\Live Tiktok Record

REM List of users to monitor (separated by space)
SET USERS=ngoctrinh89 luhao0205 
REM Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo Starting monitoring for users: %USERS%

(for %%a in (%USERS%) do (
   echo Launching monitor for %%a...
   start "Monitor %%a" python src/main.py -user %%a -mode automatic -output "%OUTPUT_DIR%" -telegram -automatic_interval 2
))

echo.
echo All monitors started! Do not close the popup windows.
pause
