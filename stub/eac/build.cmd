@echo off
rem Builds eac_stub.dll (x64) with the MSVC Build Tools.
setlocal
call "%~dp0..\vcvars.cmd" || exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
cl /nologo /O2 /W4 /LD eac_stub.c /Fobuild\ /Fe:build\eac_stub.dll /link /NOLOGO || exit /b 1
