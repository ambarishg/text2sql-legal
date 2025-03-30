@echo off
REM Script to find and kill the process running on port 3000

echo Finding the process using port 3000...
FOR /F "tokens=5" %%P IN ('netstat -ano ^| findstr :3000') DO (
    echo Process ID found: %%P
    echo Killing process with PID %%P...
    taskkill /F /PID %%P
)

echo Process terminated successfully.
