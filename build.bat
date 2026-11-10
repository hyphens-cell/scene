@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto ready
py -3.12 -m venv .venv
if errorlevel 1 (
    echo Install Python 3.12 or newer, then run: python -m venv .venv
    exit /b 1
)
:ready
if not exist "artifacts" mkdir "artifacts"
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest -q --basetemp=artifacts/build-tests
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm PDFPresenter.spec
if errorlevel 1 exit /b 1
copy /y README.md "dist\PDFPresenter\README.md" >nul
copy /y README.ru.md "dist\PDFPresenter\README.ru.md" >nul
copy /y CHANGELOG.md "dist\PDFPresenter\CHANGELOG.md" >nul
echo.
echo Ready: %CD%\dist\PDFPresenter\PDFPresenter.exe
echo Keep the entire PDFPresenter directory, including _internal.
endlocal
