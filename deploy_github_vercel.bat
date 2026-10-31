@echo off
chcp 65001 >nul
title رفع ونشر منصة إيجاري طلاب مصر إلى GitHub و Vercel
echo =====================================================================
echo   ▲ منصة إيجاري طلاب مصر v3.2 - سكربت النشر على GitHub و Vercel
echo   Ejari Students Egypt v3.2 - GitHub & Vercel Automated Deployer
echo   المستخدم المعتمد: Ali Hassan (alihassanofficial911@gmail.com)
echo =====================================================================
echo.

cd /d "%~dp0"

:: Refresh Path to ensure gh and node/npx are found
set "PATH=%PATH%;C:\Program Files\GitHub CLI;C:\Program Files\nodejs;%LOCALAPPDATA%\Programs\GitHub CLI"

echo [1/4] فحص حالة Git وتحديث هوية المطور المعتمد...
git config user.email "alihassanofficial911@gmail.com"
git config user.name "Ali Hassan"
echo [✓] تم ضبط الحساب: Ali Hassan (alihassanofficial911@gmail.com)

echo.
set /p USER_INPUT=">> برجاء إدخال اسم مستخدم GitHub (أو رابط المستودع بالكامل): "

if "%USER_INPUT%"=="" (
    echo [خطأ] لم تقم بإدخال أي قيمة! يرجى إعادة التشغيل وإدخال اسم الحساب.
    pause
    exit /b 1
)

:: Check if user input is full URL or username
echo %USER_INPUT% | findstr /i "^http ^git@" >nul
if %ERRORLEVEL% equ 0 (
    set "REPO_URL=%USER_INPUT%"
) else (
    set "REPO_URL=https://github.com/%USER_INPUT%/ejari-students-egypt-v31.git"
)

echo.
echo [2/4] ربط مستودع GitHub البعيد: %REPO_URL%
git remote remove origin >nul 2>&1
git remote add origin %REPO_URL%
git branch -M main

echo [3/4] جاري رفع الكود إلى GitHub (git push -u origin main)...
echo.
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo =====================================================================
    echo  ✅ تم رفع المشروع بنجاح إلى GitHub!
    echo  🌐 المستودع: %REPO_URL%
    echo =====================================================================
) else (
    echo.
    echo  ⚠️ تنبيه: فشل الرفع عبر Git المباشر. إذا لم تكن مسجلاً الدخول:
    echo  شغّل: gh auth login
)

echo.
echo [4/4] جاري محاولة النشر السحابي المباشر عبر Vercel CLI...
where npx >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo جاري تشغيل Vercel CLI (npx vercel --prod)...
    call npx vercel --prod
) else (
    echo لم يتم العثور على npx محلياً، سيتم فتح صفحة الاستيراد في المتصفح...
)

echo.
echo فتح صفحة استيراد المستودع المباشرة على Vercel:
start https://vercel.com/new
echo يمكنك اختيار مستودعك ejari-students-egypt-v31 والنقر على Deploy.

echo.
pause
