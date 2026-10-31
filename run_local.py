"""
Ejari Platform Local Development Runner (v4.1)
Single-command startup for local development.
Runs on http://127.0.0.1:5000 with live reload, proper static file serving, and full CORS headers.
"""
import os
import sys

# Ensure project root is in python path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from backend.app import app, init_db, FRONTEND_DIR, PORT

if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    print("=" * 65)
    print("🚀 منصة إيجاري لطلاب جامعات مصر (v4.1 - Minya Edition)")
    print("=" * 65)
    print(f"📁 مجلد الواجهة الأمامية: {FRONTEND_DIR}")
    print(f"🌐 الموقع الرئيسي للطلاب: http://127.0.0.1:{PORT}")
    print(f"⚙️  لوحة تحكم المشرف:      http://127.0.0.1:{PORT}/admin (الرمز: admin123)")
    print(f"🩺 فحص حالة السيرفر:      http://127.0.0.1:{PORT}/api/health")
    print("=" * 65)
    print("⚡ اضغط Ctrl+C لإيقاف السيرفر المحلي في أي وقت.")
    print("=" * 65)

    init_db()
    app.run(host='0.0.0.0', port=PORT, debug=True)
