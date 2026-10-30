# UTF-8 Encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   🚀 منصة إيجاري طلاب مصر v3.1 - سكربت الرفع السريع إلى GitHub" -ForegroundColor Green
Write-Host "   Ejari Students Egypt v3.1 - Fast GitHub Deployment Script" -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

# Update PATH for gh if needed
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Check Git
try {
    $null = git status
} catch {
    Write-Host "[خطأ] لم يتم العثور على git أو المجلد ليس مستودعاً صالحاً." -ForegroundColor Red
    Read-Host "اضغط Enter للخروج..."
    exit 1
}

# Check gh CLI
$ghCmd = Get-Command gh -ErrorAction SilentlyContinue
if ($ghCmd) {
    Write-Host "[✓] أداة GitHub CLI (gh) متوفرة: $($ghCmd.Source)" -ForegroundColor Green
    $authCheck = & gh auth status 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[✓] تم توثيق تسجيل الدخول إلى حساب GitHub بنجاح!" -ForegroundColor Green
    } else {
        Write-Host "[i] يمكنك تسجيل الدخول إلى GitHub بسهولة عبر أمر: gh auth login" -ForegroundColor Gray
    }
} else {
    Write-Host "[i] سيتم الرفع باستخدام أوامر Git القياسية." -ForegroundColor Gray
}

Write-Host "`nأدخل اسم المستخدم في GitHub (أو رابط المستودع بالكامل):" -ForegroundColor White
$inputVal = Read-Host ">> GitHub Username / URL"

if ([string]::IsNullOrWhiteSpace($inputVal)) {
    Write-Host "[خطأ] لم تقم بإدخال اسم المستخدم." -ForegroundColor Red
    Read-Host "اضغط Enter للخروج..."
    exit 1
}

$repoUrl = ""
if ($inputVal -match "^https?://" -or $inputVal -match "^git@") {
    $repoUrl = $inputVal.Trim()
} else {
    $cleanUser = $inputVal.Trim()
    $repoUrl = "https://github.com/$cleanUser/ejari-students-egypt-v31.git"
}

Write-Host "`n[1/3] تهيئة الرابط البعيد origin: $repoUrl" -ForegroundColor Cyan
git remote remove origin 2>$null
git remote add origin $repoUrl
git branch -M main

Write-Host "[2/3] جاري رفع الكود إلى فرع main..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=====================================================================" -ForegroundColor Green
    Write-Host " ✅ تم رفع المشروع بنجاح إلى GitHub!" -ForegroundColor Green
    Write-Host " 🌐 الرابط: $repoUrl" -ForegroundColor Yellow
    Write-Host "=====================================================================" -ForegroundColor Green
    Write-Host "`n[3/3] جاري فتح لوحة Render Blueprints في المتصفح لنشر التطبيق مجاناً..." -ForegroundColor Cyan
    Start-Process "https://dashboard.render.com/blueprints"
} else {
    Write-Host "`n=====================================================================" -ForegroundColor Red
    Write-Host " ⚠️ تعذر إتمام الرفع. يرجى التأكد من:" -ForegroundColor Yellow
    Write-Host "  1. إنشاء مستودع باسم 'ejari-students-egypt-v31' على حسابك في GitHub." -ForegroundColor White
    Write-Host "  2. تسجيل الدخول باستخدام Personal Access Token أو تشغيل 'gh auth login'." -ForegroundColor White
    Write-Host "=====================================================================" -ForegroundColor Red
}

Write-Host ""
Read-Host "اضغط Enter للمتابعة..."
