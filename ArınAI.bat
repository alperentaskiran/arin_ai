@echo off
title Arin AI Sunum Modu
echo Arin AI Baslatiliyor, lutfen bekleyin...

:: Projenin bilgisayarındaki tam klasör yoluna gidiyoruz
cd /d "C:\Users\alper\safe_mine_agent"

:: Streamlit sunucusunu projenin tam yoluyla baslatıyoruz
start /b venv\Scripts\python.exe -m streamlit run "C:\Users\alper\safe_mine_agent\main.py" --global.developmentMode=false --server.headless=true --server.port=8501

:: Sunucunun açılması için 4 saniye bekliyoruz
timeout /t 4 /nobreak >nul

:: Chrome'u özel uygulama penceresi modunda açıyoruz
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:8501
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:8501
) else (
    start http://localhost:8501
)

exit