@echo off
setlocal enabledelayedexpansion

:: -----------------------------------------------
:: Yonetici izni kontrolu
:: -----------------------------------------------
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Yonetici izinleri isteniyor...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0""", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B
)

CD /D "%~dp0"

echo =========================================
echo    SysMonitor - Kurulum Baslatiliyor
echo =========================================
echo.

:: -----------------------------------------------
:: ADIM 1: Python bul veya kur
:: -----------------------------------------------
echo [1/4] Python kontrol ediliyor...

set PYTHON_CMD=
set PYTHON_FOUND=0

:: Oncelik sirasi: py -> python -> python3 -> tam yol
py --version >nul 2>&1
if %errorlevel% EQU 0 ( set PYTHON_CMD=py & set PYTHON_FOUND=1 & goto :PythonReady )

python --version >nul 2>&1
if %errorlevel% EQU 0 ( set PYTHON_CMD=python & set PYTHON_FOUND=1 & goto :PythonReady )

python3 --version >nul 2>&1
if %errorlevel% EQU 0 ( set PYTHON_CMD=python3 & set PYTHON_FOUND=1 & goto :PythonReady )

:: Standart kurulum konumlarini kontrol et
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
) do (
    if exist %%P (
        set PYTHON_CMD=%%P
        set PYTHON_FOUND=1
        goto :PythonReady
    )
)

:: Python bulunamadi - kur
echo [!] Python bulunamadi. Indiriliyor ve kuruluyor...
echo     Bu islem birka dakika surebilir, lutfen bekleyin...
echo.

:: Yontem 1: winget
winget --version >nul 2>&1
if %errorlevel% EQU 0 (
    echo     [winget] Python 3.12 kuruluyor...
    winget install --id Python.Python.3.12 --source winget --silent --accept-package-agreements --accept-source-agreements
    goto :CheckAfterInstall
)

:: Yontem 2: PowerShell ile indir
echo     [PowerShell] Python indiriliyor (python.org)...
powershell -ExecutionPolicy Bypass -Command "& { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $url = 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe'; $out = '%TEMP%\python_setup.exe'; Write-Host '    Indiriliyor...'; Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Write-Host '    Kuruluyor...'; Start-Process $out -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 SimpleInstall=1' -Wait; Remove-Item $out -Force -ErrorAction SilentlyContinue; Write-Host '    [OK] Python kuruldu.' }"

:CheckAfterInstall
:: PATH'i yenile
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
set "PATH=C:\Python312;C:\Python312\Scripts;%PATH%"

:: Tekrar kontrol et
py --version >nul 2>&1
if %errorlevel% EQU 0 ( set PYTHON_CMD=py & set PYTHON_FOUND=1 & goto :PythonReady )

python --version >nul 2>&1
if %errorlevel% EQU 0 ( set PYTHON_CMD=python & set PYTHON_FOUND=1 & goto :PythonReady )

for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Python312\python.exe"
) do (
    if exist %%P (
        set PYTHON_CMD=%%P
        set PYTHON_FOUND=1
        goto :PythonReady
    )
)

:: Hala bulunamadi
echo.
echo [HATA] Python kurulamadi!
echo.
echo  Cozum: https://python.org adresine gidin
echo  "Download Python 3.12" butonuna basin
echo  Kurulumda asagidaki secenekleri isaretleyin:
echo   [x] Add Python to PATH
echo   [x] Install for all users (opsiyonel)
echo.
echo  Kurulumdan sonra bu dosyayi tekrar calistirin.
echo.
pause
exit /B 1

:PythonReady
echo [OK] Python hazir: %PYTHON_CMD%

:: -----------------------------------------------
:: ADIM 2: Pip paketlerini kur
:: -----------------------------------------------
echo.
echo [2/4] Gerekli paketler kontrol ediliyor...
%PYTHON_CMD% -m pip install --upgrade pip --quiet --no-warn-script-location
%PYTHON_CMD% -m pip install -r "%~dp0requirements.txt" --quiet --no-warn-script-location
if %errorlevel% NEQ 0 (
    echo [HATA] Paketler kurulamadi!
    echo        requirements.txt dosyasini kontrol edin.
    pause
    exit /B 1
)
echo [OK] Tum paketler hazir.

:: -----------------------------------------------
:: ADIM 3: Veritabani
:: -----------------------------------------------
echo.
echo [3/4] Veritabani hazirlaniyor...
%PYTHON_CMD% "%~dp0database.py"
%PYTHON_CMD% "%~dp0check_db.py"
echo [OK] Veritabani hazir.

:: -----------------------------------------------
:: ADIM 4: Servisleri baslat
:: -----------------------------------------------
echo.
echo [4/4] SysMonitor baslatiliyor...

:: Eski prosesleri temizle
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

:: Windows baslangicinа ekle
REG ADD "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "SysMonitor" /t REG_SZ /d "\"%~dp0run.bat\"" /f >nul 2>&1

:: Logger ve Web sunucusunu baslat
start /b %PYTHON_CMD% "%~dp0logger.py" >> "%~dp0logger.log" 2>&1
start /b %PYTHON_CMD% "%~dp0app.py" >> "%~dp0app.log" 2>&1

:: Sunucunun hazir olmasini bekle
echo [!] Sunucu baslatiliyor...
timeout /t 5 >nul

:: Tarayiciyi ac
start http://127.0.0.1:5000

echo.
echo =========================================
echo  SysMonitor arka planda calisiyor.
echo  Adres: http://127.0.0.1:5000
echo =========================================
echo  Bu pencereyi kapatabilirsiniz.
echo =========================================
timeout /t 5 >nul
