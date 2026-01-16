@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo       DANH SACH CAC TIEN TRINH THU LIVE DANG CHAY
echo ========================================================
echo.

REM Liệt kê các tiến trình python đang chạy và lọc lấy tham số dòng lệnh
wmic process where "name='python.exe' and commandline like '%%src/main.py%%'" get ProcessId,CommandLine /format:csv > temp_processes.csv

REM Đọc file CSV và hiển thị danh sách thân thiện hơn
set /a count=0
for /f "skip=2 tokens=2,3 delims=," %%A in (temp_processes.csv) do (
    set "cmd=%%B"
    set "pid=%%A"
    
    REM Trích xuất tên user từ command line (tìm chuỗi sau -user)
    REM Cách làm đơn giản: in cả dòng command rút gọn
    echo [!pid!] %%B
    set /a count+=1
)

if %count%==0 (
    echo Khong tim thay tien trinh thu live nao dang chay.
    del temp_processes.csv
    pause
    exit /b
)

echo.
echo ========================================================
echo Nhap PID (cot dau tien, vi du 1234) cua user ban muon STOP.
echo De dung tat ca, nhap: ALL
echo ========================================================
set /p target_pid="Nhap PID hoac ALL: "

if /i "%target_pid%"=="ALL" (
    taskkill /F /IM python.exe
    echo Da dung tat ca cac tien trinh python!
) else (
    taskkill /F /PID %target_pid%
    echo Da dung tien trinh co PID %target_pid%.
)

del temp_processes.csv
echo.
pause
