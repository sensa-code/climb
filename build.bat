@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   CLIMB 打包腳本
echo   產出：dist\CLIMB.exe
echo ========================================
echo.

echo [1/5] 安裝 Python 依賴...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ❌ 依賴安裝失敗！
    exit /b 1
)

echo [2/5] 安裝 PyInstaller...
pip install pyinstaller -q
if errorlevel 1 (
    echo ❌ PyInstaller 安裝失敗！
    exit /b 1
)

echo [3/5] 確認 Playwright Chromium...
playwright install chromium
if errorlevel 1 (
    echo ❌ Playwright Chromium 安裝失敗！
    exit /b 1
)

echo [4/5] 執行測試...
python -m pytest test_scraper.py test_ai_processor.py test_task_runner.py -q
if errorlevel 1 (
    echo ❌ 測試失敗！請修復後再打包。
    exit /b 1
)

echo [5/5] 打包 .exe（含 Chromium，約需 3-5 分鐘）...
pyinstaller climb.spec --clean --noconfirm
if errorlevel 1 (
    echo ❌ PyInstaller 打包失敗！
    exit /b 1
)

echo.
echo ========================================
echo   ✅ 打包完成！
echo ========================================
echo.
if exist "dist\CLIMB.exe" (
    for %%F in (dist\CLIMB.exe) do echo   檔案：%%~fF
    for %%F in (dist\CLIMB.exe) do echo   大小：%%~zF bytes
) else (
    echo   ⚠️ 找不到 dist\CLIMB.exe
)
echo.
pause
