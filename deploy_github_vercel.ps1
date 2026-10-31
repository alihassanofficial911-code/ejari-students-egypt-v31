# UTF-8 Encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  ▲ منصة إيجاري طلاب مصر v3.2 - سكربت النشر على GitHub و Vercel" -ForegroundColor Green
Write-Host "  Ejari Students Egypt v3.2 - GitHub & Vercel Automated Deployer" -ForegroundColor Yellow
Write-Host "  المستخدم المعتمد: Ali Hassan (alihassanofficial911@gmail.com)" -ForegroundColor Magenta
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $PSScriptRoot

# Update PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Set Git User Config
git config user.email "alihassanofficial911@gmail.com"
git config user.name "Ali Hassan"
Write-Host "[✓] تم ضبط هوية Git: Ali Hassan (alihassanofficial911@gmail.com)" -ForegroundColor Green

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
} else {
    Write-Host "`n⚠️ تنبيه: فشل الرفع عبر Git. يمكنك تشغيل 'gh auth login' للمصادقة." -ForegroundColor Yellow
}

Write-Host "`n[3/3] جاري تشغيل نشر Vercel السحابي..." -ForegroundColor Cyan
try {
    & npx vercel --prod
} catch {
    Write-Host "جاري فتح صفحة استيراد المستودع المباشرة في المتصفح..." -ForegroundColor Yellow
}

Start-Process "https://vercel.com/new"
Write-Host "تم فتح صفحة الاستيراد https://vercel.com/new في المتصفح بنجاح." -ForegroundColor Green

Write-Host ""
Read-Host "اضغط Enter للمتابعة..."
