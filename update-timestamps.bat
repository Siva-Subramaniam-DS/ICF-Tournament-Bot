@echo off
REM ICF Tournament Bot - Update File Timestamps (Windows)
REM Last Updated: September 7, 2025

echo Updating file timestamps for ICF Tournament Bot v3.0.0...

REM Update all configuration files by copying them to themselves
copy /b .dockerignore +,, > nul
copy /b .gitignore +,, > nul
copy /b .railwayignore +,, > nul
copy /b nixpacks.toml +,, > nul
copy /b pip.conf +,, > nul
copy /b requirements-lock.txt +,, > nul
copy /b railway.json +,, > nul
copy /b Procfile +,, > nul
copy /b runtime.txt +,, > nul

echo ✅ All file timestamps updated to current date
echo 🚀 Ready for Git push and Railway deployment
pause