@echo off
REM ===================================================================
REM  One-shot Windows build for the EigenVib flasher GUI.
REM  Output: dist\EigenVib-Flasher.exe  (one self-contained file)
REM
REM  Prerequisites on this Windows PC (once):
REM    * Python 3.11 (or 3.12) from python.org  -- during install TICK
REM      "Add python.exe to PATH".
REM    * This folder must contain: eigenvib_flasher_gui.py,
REM      eigenvib_flasher.py, and firmware\ with the 3 .bin files.
REM
REM  Then just double-click this file.
REM ===================================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo ERROR: Python launcher "py" not found.
  echo        Install Python 3.11 from https://www.python.org/downloads/windows/
  echo        and TICK "Add python.exe to PATH" during setup, then re-run this.
  echo.
  pause
  exit /b 1
)

if not exist firmware\sensor_node.bin (
  echo.
  echo ERROR: firmware\sensor_node.bin is missing.
  echo        Copy the whole firmware\ folder ^(bootloader.bin, partition-table.bin,
  echo        sensor_node.bin^) next to this script and re-run.
  echo.
  pause
  exit /b 1
)

echo == [1/4] creating build venv (prefer Python 3.11) ==
REM Pick an interpreter: try the 3.11 launcher, then any py 3, then plain python.
set "PYL=py -3.11"
%PYL% -c "import sys" 1>nul 2>nul || set "PYL=py -3"
%PYL% -c "import sys" 1>nul 2>nul || set "PYL=python"
echo    using: %PYL%
%PYL% -m venv build_venv || goto :err
REM IMPORTANT: run everything through the venv's OWN python.exe — never a bare
REM "pyinstaller"/"python" on PATH, or PyInstaller may run against a different
REM interpreter that lacks our deps and bundle almost nothing into the .exe.
set "VPY=build_venv\Scripts\python.exe"

echo == [2/4] installing dependencies (pinned) ==
"%VPY%" -m pip install --upgrade pip || goto :err
"%VPY%" -m pip install esptool==4.12.0 pyserial==3.5 segno==1.6.6 "pillow>=10.2" pyinstaller || goto :err

echo == [3/4] building EigenVib-Flasher.exe ==
REM Windows uses ';' as the --add-data separator (macOS/Linux use ':').
"%VPY%" -m PyInstaller --onefile --windowed --clean --noconfirm ^
  --name EigenVib-Flasher ^
  --collect-data esptool ^
  --add-data "firmware;firmware" ^
  eigenvib_flasher_gui.py || goto :err

echo == [4/4] done ==
for %%A in ("dist\EigenVib-Flasher.exe") do echo    built: %%~zA bytes  (expect ~8-10 MB; if only KB the bundle failed)
echo.
echo ============================================================
echo   BUILD OK  ->  dist\EigenVib-Flasher.exe
echo   Send THAT single .exe to whoever flashes nodes.
echo   (First run: Windows SmartScreen -^> "More info" -^> "Run anyway".)
echo ============================================================
echo.
pause
exit /b 0

:err
echo.
echo *** BUILD FAILED - see the error above. ***
echo.
pause
exit /b 1
