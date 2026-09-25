@echo off
setlocal
title Yomiba Kurulumu
echo ============================================
echo   YOMIBA - yerel kurulum (Windows)
echo ============================================
echo.
echo [0/4] Sistem kontrolu...

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3")
if defined PY goto :py_ok
where python >nul 2>nul
if %errorlevel%==0 (set "PY=python")
if defined PY goto :py_ok
echo HATA: Python bulunamadi.
echo   https://python.org'dan Python 3.11+ kuralim; kurulumda "Add Python to PATH" kutusunu isaretle.
goto :end

:py_ok
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>nul
if %errorlevel%==0 goto :node_check
echo HATA: Python 3.11+ gerekiyor, daha eski bir surum bulundu.
goto :end

:node_check
where node >nul 2>nul
if %errorlevel%==0 goto :venv
echo HATA: Node.js bulunamadi.
echo   https://nodejs.org'dan Node 18+ (LTS) kuralim.
goto :end

:venv
echo [1/4] Backend sanal ortami (ilk kerede ~1 dk)...
cd /d "%~dp0backend"
if errorlevel 1 (
  echo HATA: "%~dp0backend" klasoru bulunamadi. Zip'i once bir klasore CIKAR, sonra calistir.
  goto :end
)
if exist .venv goto :npm
%PY% -m venv .venv
if errorlevel 1 (
  echo HATA: sanal ortam kurulamadi.
  goto :end
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo HATA: pip install basarisiz oldu (Python surumu mu?).
  goto :end
)
goto :npm

:npm
echo [2/4] Frontend bagimlilari (ilk kerede ~1 dk)...
cd /d "%~dp0frontend"
if errorlevel 1 (
  echo HATA: "%~dp0frontend" klasoru bulunamadi. Zip'i once bir klasore CIKAR, sonra calistir.
  goto :end
)
if exist node_modules goto :backup
call npm install --no-audit --no-fund
if errorlevel 1 (
  echo HATA: npm install basarisiz oldu.
  goto :end
)
goto :backup

:backup
cd /d "%~dp0"
if not exist backend\yomiba.db.bak-first (
  copy /y backend\yomiba.db backend\yomiba.db.bak-first >nul
  echo   DB yedeklendi: backend\yomiba.db.bak-first
)

echo [4/4] Hizmetler baslatiliyor (iki yeni pencere acilacak)...
start "Yomiba API (:8000)" cmd /k "cd /d %~dp0backend && set CATALOG_SYNC_INTERVAL_HOURS=12&& set PRICE_REFRESH_INTERVAL_HOURS=24&& set IMPORT_MAX_CONCURRENT_JOBS=8&& .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info"
start "Yomiba Web (:3000)" cmd /k "cd /d %~dp0frontend && npm run dev"
timeout /t 6 /nobreak >nul
echo.
echo ============================================
echo   HAZIR!
echo   Web    : http://localhost:3000
echo   Admin  : http://localhost:3000/admin
echo ============================================
echo.
echo   Telefon  : ayni WiFi'da  http://^<bilgisayar-LAN-IP^>:3000
echo   Ilk is   : admin sayfasinda "Tum katalogu isit" (1 kere, ~45 dk)
echo   Kapatmak : "Yomiba API" ve "Yomiba Web" pencerelerini kapat
echo.
goto :end

:end
echo.
pause
