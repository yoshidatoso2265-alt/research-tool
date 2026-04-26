@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ====================================
echo  中古10サイト横断リサーチ Web UI
echo ====================================
echo.
echo ブラウザが自動で開きます...
echo 終了する時はこのウィンドウで Ctrl+C を押してください
echo.
python -m streamlit run app.py
pause
