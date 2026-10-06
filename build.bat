@echo off
REM Windows에서 더블클릭하면 dist\PhotoSplitter.exe 를 만듭니다. (Python 3 설치 필요)
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller || goto :error
python -m PyInstaller --onefile --windowed --name PhotoSplitter --paths src src\app.py || goto :error
echo.
echo 완료: dist\PhotoSplitter.exe
pause
exit /b 0

:error
echo.
echo 빌드 실패. Python이 설치되어 있는지 확인하세요.
pause
exit /b 1
