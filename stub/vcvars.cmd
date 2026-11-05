@echo off
rem The MSVC x64 tools, in whichever Visual Studio 2017+ (or its Build Tools) holds them, found with vswhere.
rem Called by the build.cmd scripts; no setlocal here, so the tools stay set in the caller.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto missing
set "PATH=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer;%PATH%"
set "VCVARS="
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find VC\Auxiliary\Build\vcvars64.bat`) do set "VCVARS=%%i"
if not defined VCVARS goto missing
call "%VCVARS%" >nul || exit /b 1
exit /b 0
:missing
echo The MSVC x64 compiler was not found. Install "Build Tools for Visual Studio" (or Visual Studio) with the
echo "Desktop development with C++" workload, or use the prebuilt DLLs from the project's Releases page.
exit /b 1
