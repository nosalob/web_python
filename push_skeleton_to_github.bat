@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Push guestbook-skeleton to GitHub
echo ==========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo ERROR: Git was not found. Install Git first: https://git-scm.com/
    pause
    exit /b 1
)

set /p REPO_URL=Paste the empty GitHub repository URL: 
if "%REPO_URL%"=="" (
    echo ERROR: Repository URL cannot be empty.
    pause
    exit /b 1
)

if not exist ".git" (
    git init
    if errorlevel 1 goto :error
)

git branch -M main
if errorlevel 1 goto :error

git add .
if errorlevel 1 goto :error

git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Add guestbook project skeleton"
    if errorlevel 1 goto :error
) else (
    echo No new changes to commit.
)

git remote get-url origin >nul 2>nul
if errorlevel 1 (
    git remote add origin "%REPO_URL%"
    if errorlevel 1 goto :error
) else (
    git remote set-url origin "%REPO_URL%"
    if errorlevel 1 goto :error
)

git push -u origin main
if errorlevel 1 goto :error

echo.
echo SUCCESS: Skeleton pushed to GitHub.
pause
exit /b 0

:error
echo.
echo ERROR: A Git command failed. Check the messages above.
pause
exit /b 1
