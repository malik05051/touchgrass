@echo off
REM Builds dist\TouchGrass.exe (a single, self-contained Windows executable).
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --onefile --windowed --name TouchGrass touchgrass.py || exit /b 1
echo.
echo Done! Your game is at dist\TouchGrass.exe
