@echo off
:: BatchGotAdmin
:-------------------------------------
REM  --> Check for permissions
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

REM --> If error flag set, we do not have admin.
if '%errorlevel%' NEQ '0' (
    echo Yonetici izinleri isteniyor...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params= %*
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"

    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    pushd "%CD%"
    CD /D "%~dp0"
:--------------------------------------
cd /d "%~dp0"
echo ==========================================================
echo SysMonitor - Uzaktan Erisim Sistemi (Cloudflare Tunnel)
echo ==========================================================
echo.
echo Not: Bu ekran size telefonunuzdan veya baska bir cihazdan
echo     sisteme erisebilmeniz icin ozel bir link uretecektir.
echo ==========================================================
echo.

if not exist cloudflared.exe (
    echo [BILGI] Tunel araci bilgisayarinizda yok. Indiriliyor, lutfen bekleyin - Yaklasik 30 MB...
    curl.exe -k -L -o cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
    if errorlevel 1 (
        echo [HATA] Indirme basarisiz oldu. Lutfen internet baglantinizi kontrol edin.
        pause
        exit /b
    )
)

echo.
echo [1/2] SysMonitor Arka Plan Hizmetleri Baslatiliyor...
:: run.bat'i yeni bir gizli veya ayri komut penceresinde calistir
start "SysMonitor Local" cmd /c "run.bat"

echo.
echo [1/2] Sistemlerin tam olarak hazir olmasi icin 5 saniye bekleniyor...
timeout /t 5 /nobreak >nul

echo.
echo [2/2] Guvenli Tunel Baglantisi Baslatiliyor!
echo.
echo ======================== ONEMLI UYARI ========================
echo Lutfen asagidaki yazilarin icinde su formata benzer bir URL bulun:
echo https://[rastgele-kelimeler].trycloudflare.com
echo.
echo Bu baglantiyi telefonunuzun tarayicisina yazarak veya gondererek 
echo sisteme (admin / admin sifresiyle) ulasabilirsiniz.
echo ==============================================================
echo.
cmd /k "cloudflared.exe tunnel --url http://127.0.0.1:5000"
