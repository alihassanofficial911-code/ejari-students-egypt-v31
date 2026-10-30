@echo off
chcp 65001 >nul
title رفع مشروع منصة إيجاري طلاب مصر إلى GitHub
echo =====================================================================
echo    🚀 منصة إيجاري طلاب مصر v3.1 - سكربت الرفع السريع إلى GitHub
echo    Ejari Students Egypt v3.1 - Fast GitHub Deployment Script
echo =====================================================================
echo.

cd /d "%~dp0"

:: Refresh Path to ensure gh is found if installed in Program Files
set "PATH=%PATH%;C:\Program Files\GitHub CLI;%LOCALAPPDATA%\Programs\GitHub CLI"

echo [1/4] فحص حالة مستودع Git المحلي وأداة GitHub CLI...
git status >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [خطأ] المجلد الحالي ليس مستودع Git صالح!
    pause
    exit /b 1
)

where gh >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [✓] أداة GitHub CLI (gh) مثبتة ومتوفرة.
    gh auth status >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [✓] أنت مسجل الدخول بالفعل في GitHub CLI.
    ) else (
        echo [i] يمكنك تسجيل الدخول إلى GitHub عبر سطر الأوامر بأمر: gh auth login
    )
) else (
    echo [i] سيتم الاعتماد على أوامر Git المباشرة.
)

echo.
set /p USER_INPUT=">> برجاء إدخال اسم مستخدم GitHub (أو رابط المستودع بالكامل): "

if "%USER_INPUT%"=="" (
    echo [خطأ] لم تقم بإدخال أي قيمة! يرجى إعادة التشغيل وإدخال اسم الحساب.
    pause
    exit /b 1
)

:: Check if user input is full URL or just username
echo %USER_INPUT% | findstr /i "^http ^git@" >nul
if %ERRORLEVEL% equ 0 (
    set "REPO_URL=%USER_INPUT%"
) else (
    set "REPO_URL=https://github.com/%USER_INPUT%/ejari-students-egypt-v31.git"
)

echo.
echo [2/4] ربط المستودع البعيد: %REPO_URL%
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
    echo.
    echo [4/4] جاري فتح لوحة تحكم Render Blueprints في المتصفح...
    start https://dashboard.render.com/blueprints
    echo تم فتح المتصفح. يمكنك اختيار مستودعك والضغط على "Apply" للنشر المجاني.
) else (
    echo.
    echo =====================================================================
    echo  ⚠️ تنبيه: فشل الرفع عبر Git. الأسباب المحتملة:
    echo   1. المستودع غير موجود على حسابك (قم بإنشائه أولاً على GitHub باسم ejari-students-egypt-v31).
    echo   2. لم يتم توثيق الدخول (يتطلب GitHub استخدام Personal Access Token ككلمة مرور).
    echo   3. لتسجيل الدخول السريع التلقائي، شغّل الأمر: gh auth login
    echo =====================================================================
)

echo.
pause
