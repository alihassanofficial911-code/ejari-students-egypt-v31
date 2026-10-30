# خطة التنفيذ المحدثة: منصة إيجاري طلاب مصر v2.0 (Ejari Students Egypt)

منصة وسيطة متكاملة وسحابية (SaaS) لإدارة وحجز سكن الطلاب المغتربين والوافدين قرب الجامعات المصرية بالمحافظات.

---

## 1. أهداف ترقية الإصدار v2.0

### أ. نظام تسجيل الدخول والصلاحيات المتقدم (Role-Based Authentication)
- جدول `users` في SQLite يحتوي على `id, full_name, phone, email, password_hash, role, university, governorate, created_at`.
- تشفير كلمات المرور باستخدام `hashlib.pbkdf2_hmac('sha256', ...)` مع 100,000 جولة وSalt عشوائي فريد.
- جدول `sessions` للتحقق من هوية المستخدمين وصلاحية الجلسة عبر `Bearer Token`.
- نقاط نهاية الـ Auth:
  - `POST /api/auth/register`: تسجيل طالب مغترب جديد أو مؤجر/مالك سكن.
  - `POST /api/auth/login`: تسجيل الدخول عبر الهاتف/البريد وكلمة المرور.
  - `GET /api/auth/me`: جلب بيانات المستخدم المسجل والتحقق من الجلسة.
  - `POST /api/auth/logout`: إبطال الجلسة وحذف التوكن.
- حسابات تجريبية مهيأة مسبقاً بنقرة واحدة (1-Click Demo Login):
  - **طالب مغترب:** `01012345678` / `student123`
  - **مؤجر ومالك سكن:** `01123456789` / `landlord123`
  - **مدير المنصة Admin:** `01234567890` / `admin123`
- إخفاء وإظهار التبويبات بحسب الصلاحيات (Role-Based View Filter).

### ب. رفع وتخزين الصور الحقيقية للشقق (Real Multi-Image Upload)
- مجلد التخزين السحابي المحلي `backend/uploads/`.
- حقل `images_json` في جدول `properties` لتخزين مصفوفة صور الغرف والمرافق.
- نقطة نهاية `POST /api/upload`: تدعم رفع الملفات من كاميرا الموبايل والكمبيوتر (Base64 و Binary) مع توليد أسماء عشوائية آمنة.
- تقديم الملفات الساكنة `/uploads/<filename>` مباشرة من خادم Python بنوع محتوى ملائم (`image/jpeg`, `image/png`, `image/webp`, `image/svg+xml`).
- معرض صور تفاعلي (Photo Switcher + Lightbox) في كل بطاقة شقة بالسوق.

### ج. تكامل بوابات الدفع المصرية (Paymob & Fawry Sandbox Integration)
- فئة `PaymobSandboxService` في `backend/app.py`:
  - قراءة المتغيرات `PAYMOB_API_KEY`, `PAYMOB_INTEGRATION_ID_CARD`, `PAYMOB_INTEGRATION_ID_WALLET`, `PAYMOB_IFRAME_ID`.
  - محاكي محلي ذكي (Local Sandbox Simulator) يعمل تلقائياً في حال عدم توفر مفاتيح حية.
  - إصدار كود دفع فوري برقم مرجعي معتمد `788-XXXXXXXX`.
  - محاكاة دفع محافظ المحمول فودافون كاش ومحفظتي.
  - استقبال ومعالجة إشعارات الـ Webhook عبر `POST /api/payments/webhook`.
  - توليد الإيصال الرقمي الفوري `EJR-YYYYMMDD-XXX`.

### د. النشر السحابي (Cloud Deployment Ready)
- دعم `PORT = int(os.environ.get('PORT', 5000))` والربط بـ `0.0.0.0`.
- إعداد `Dockerfile` و `.dockerignore`.
- إعداد `render.yaml` لمنصة Render.com.
- إعداد `DEPLOY_GUIDE_AR.md` باللغة العربية.

---

## 2. قائمة التحقق والاختبارات الآلية (Verification Checklist)
- [x] بناء وتجهيز جداول المستخدمين `users` والجلسات `sessions` والتشفير بـ PBKDF2.
- [x] إضافة ودعم رفع ومعاينة الصور للشقق السكنية `/api/upload` وتخزينها في `backend/uploads/`.
- [x] بناء وتفعيل خدمة `PaymobSandboxService` وتوليد أكواد فوري وأوامر الدفع ومعالجة الـ Webhooks.
- [x] كتابة الاختبارات في `backend/test_app.py` وتشغيلها بنجاح 100% (6/6).
- [x] إعداد حزم النشر السحابي (`Dockerfile`, `render.yaml`, `.env.example`, `DEPLOY_GUIDE_AR.md`).
- [x] إطلاق الخادم عبر المنفذ 5000 والتأكد من استجابة كافة المسارات.
