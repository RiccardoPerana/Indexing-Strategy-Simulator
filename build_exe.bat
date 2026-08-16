@echo off
REM build_exe.bat
REM
REM Builds a standalone Windows .exe for the desktop GUI (gui_tk.py) --
REM double-click this file (or run it from a Command Prompt) on a Windows
REM machine with Python installed. The resulting .exe in dist\ runs on
REM any Windows machine with no Python install required at all.
REM
REM This MUST be run on Windows -- PyInstaller builds an executable for
REM whatever OS it's run on, it cannot cross-compile a Windows .exe from
REM Linux or Mac.
REM
REM Uses "python -m pip" / "python -m PyInstaller" throughout, NOT bare
REM "pip"/"pyinstaller" commands. Bare pip can fail with "The system
REM cannot execute the specified program" if the pip.exe on PATH is a
REM stale shim pointing at a Python install that's since moved or
REM changed -- a real, confirmed failure mode on at least one Windows
REM setup this was tested against. Routing everything through "python -m"
REM uses whatever Python is already known to work (since this script is
REM only reached at all if `python gui_tk.py` already runs), sidestepping
REM that whole class of PATH problems.

echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install requirements ^(see output above^).
    pause
    exit /b 1
)

python -m pip install pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install PyInstaller ^(see output above^).
    pause
    exit /b 1
)

echo.
echo Building IndexingStrategySimulator.exe ...
REM --onefile        : single .exe, no accompanying folder of files
REM --windowed       : no console window behind the GUI
REM --name           : output filename
REM --hidden-import  : matplotlib's Tk backend is loaded dynamically at
REM                    runtime, which PyInstaller's static import scan can
REM                    miss -- naming it explicitly avoids a "backend not
REM                    found" error in the built .exe that wouldn't show
REM                    up until someone actually tries to run it.
REM --collect-data   : PyInstaller's dependency scan only bundles PYTHON
REM                    CODE by default, not non-code data files a package
REM                    ships alongside it. ttkbootstrap ships an icon font
REM                    (bootstrap.ttf, used to render things like the
REM                    combobox dropdown arrow) as package data -- without
REM                    this flag, the .exe builds successfully (the code
REM                    itself is fine) but crashes at runtime the first
REM                    time ttkbootstrap tries to load that missing font.
REM                    This collects ALL of ttkbootstrap's data files, not
REM                    just that one, in case others are needed too.
python -m PyInstaller --onefile --windowed --name "IndexingStrategySimulator" ^
    --hidden-import matplotlib.backends.backend_tkagg ^
    --collect-data ttkbootstrap ^
    gui_tk.py
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed ^(see output above^). No .exe was produced.
    pause
    exit /b 1
)

echo.
echo SUCCESS. Find IndexingStrategySimulator.exe in the dist\ folder.
echo That single file is the whole app -- copy it anywhere and double-click to run.
pause
