# دليل النشر السحابي الكامل: منصة إيجاري طلاب مصر v2.0
### (Cloud Deployment Guide for Ejari Students Egypt)

يشرح هذا الدليل كيفية رفع ونشر منصة **إيجاري طلاب مصر v2.0** على خوادم سحابية للحصول على رابط إنترنت عام (`https://...`) يعمل مباشرة على هواتف الطلاب وأولياء الأمور في أي مكان بمصر.

---

## 🚀 الخيار الأول: النشر السريع والمجاني عبر Render.com (مُوصى به)

يقدم موقع **Render** استضافة مجانية جاهزة تدعم ملف `render.yaml` المرفق مع المشروع.

### الخطوات:
1. أنشئ حساباً مجانياً على [Render.com](https://render.com).
2. قم برفع مجلد المشروع إلى مستودع على **GitHub** (مثلاً: `ejari-students-egypt`).
3. في لوحة تحكم Render:
   - اضغط على **New +** ثم اختر **Blueprint**.
   - اختر مستودع GitHub الخاص بك.
   - سيقرأ Render ملف `render.yaml` تلقائياً ويقوم بتهيئة الخدمة.
4. اضغط على **Apply**:
   - سيبدأ الخادم في العمل وسيعطيك Render رابطاً عاماً مثل:
     `https://ejari-students-egypt.onrender.com`
5. افتح الرابط من متصفح هاتفك أو أرسله للطلاب — ستعمل الواجهة بالكامل مع بوابات الدفع وقاعدة البيانات!

---

## 🐳 الخيار الثاني: النشر باستخدام Docker (أي خادم سحابي / VPS)

المشروع مزود بـ `Dockerfile` خفيف وسريع مبني على `python:3.11-slim`.

### خطوات التشغيل المحلي أو على خادم Ubuntu / Debian VPS:
```bash
# 1. بناء صورة الدوكر
docker build -t ejari-students-v2 .

# 2. تشغيل الحاوية وربط المنفذ 5000
docker run -d -p 5000:5000 --name ejari-app ejari-students-v2

# 3. التحقق من عمل الحاوية
docker ps
```
يمكنك فتح المتصفح على `http://<IP_الخادم>:5000`.

---

## 🚆 الخيار الثالث: النشر عبر Railway.app

1. سجل الدخول إلى [Railway.app](https://railway.app).
2. اضغط **New Project** واختر **Deploy from GitHub repo**.
3. سيتعرف Railway تلقائياً على `Dockerfile` أو كود Python ويبدأ البناء.
4. اذهب إلى **Settings** ثم **Generate Domain** للحصول على رابط عام مجاني `https://...up.railway.app`.

---

## 💳 تهيئة بوابات الدفع الحقيقية (Paymob Live Production)

في البيئة التجريبية (Sandbox)، يعمل النظام بمحاكي دفع متكامل بدون الحاجة لأي مفاتيح خارجية.
عند الانتقال للتشغيل التجاري الحقيقي مع شركة **Paymob**:
1. سجل حساب تاجر على [Paymob Accept](https://accept.paymob.com).
2. أنشئ Integrations لـ:
   - بطاقات ميزة وفيزا وماستركارد (Cards).
   - المحافظ الإلكترونية فودافون كاش ومحفظتي (Mobile Wallets).
   - منافذ فوري (Fawry Pay).
3. أضف المتغيرات التالية في إعدادات البيئة (Environment Variables):
   - `PAYMOB_API_KEY`: مفتاح الـ API السري الخاص بك.
   - `PAYMOB_INTEGRATION_ID_CARD`: معرّف بطاقات الدفع.
   - `PAYMOB_INTEGRATION_ID_WALLET`: معرّف المحافظ.
   - `PAYMOB_IFRAME_ID`: رقم الـ Iframe الخاص بالبطاقات.
4. أضف رابط الـ Webhook في لوحة Paymob:
   `https://<YOUR_DOMAIN>/api/payments/webhook`

---

## 🔒 حسابات الدخول التجريبية الجاهزة للاختبار:
- **حساب طالب مغترب:** `01012345678` / كلمة المرور: `student123`
- **حساب مؤجر ومالك سكن:** `01123456789` / كلمة المرور: `landlord123`
- **حساب مدير المنصة (Admin):** `01234567890` / كلمة المرور: `admin123`
