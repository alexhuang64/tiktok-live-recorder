@echo off
REM Configuration
SET USER=datvilla94
SET OUTPUT_DIR=F:\Live Tiktok Record

REM Create output directory if it doesn't exist
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Run the recorder
echo Starting TikTok Live Recorder for user: %USER%
echo Output Directory: %OUTPUT_DIR%
echo Mode: Automatic
echo Telegram Notification: Enabled

python src/main.py -user %USER% -mode automatic -output "%OUTPUT_DIR%" -telegram -automatic_interval 2

pause
