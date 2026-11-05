@echo off
rem Build the x64 local platform adapter with the existing MSVC toolchain.
setlocal
call "%~dp0..\vcvars.cmd" || exit /b 1
cd /d "%~dp0"
if not exist build mkdir build
cl /nologo /O2 /W4 /WX /MT /LD local_platform.c /Fobuild\ /Fe:build\gameforge_api64.dll /link /NOLOGO shell32.lib || exit /b 1
