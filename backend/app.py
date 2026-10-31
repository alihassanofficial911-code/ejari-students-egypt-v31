import json
import os
import sqlite3
import secrets
import hashlib
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Flask, request, jsonify, send_from_directory, make_response
from werkzeug.security import generate_password_hash, check_password_hash

PORT = int(os.environ.get('PORT', 5000))
IS_VERCEL = (
    os.environ.get('VERCEL') == '1'
    or os.environ.get('VERCEL_ENV') is not None
    or os.environ.get('NOW_REGION') is not None
    or os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is not None
)

def _resolve_db_path():
    if IS_VERCEL:
        tmp_dir = '/tmp'
        if not os.path.exists(tmp_dir):
            try:
                os.makedirs(tmp_dir, exist_ok=True)
            except Exception:
                import tempfile
                tmp_dir = tempfile.gettempdir()
        return os.path.join(tmp_dir, 'ejari_v32.db')
    default_path = os.path.join(os.path.dirname(__file__), 'ejari_students.db')
    try:
        test_file = os.path.join(os.path.dirname(__file__), '.write_check')
        with open(test_file, 'w') as f:
            f.write('1')
        os.remove(test_file)
        return default_path
    except (OSError, IOError, PermissionError):
        import tempfile
        return os.path.join(tempfile.gettempdir(), 'ejari_v32.db')

DB_PATH = _resolve_db_path()
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'ejari_students_egypt_secret_v31_jwt_key_2026')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 72

_base_dir = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(_base_dir, '../frontend'))
if not os.path.exists(FRONTEND_DIR):
    if os.path.exists(os.path.abspath('frontend')):
        FRONTEND_DIR = os.path.abspath('frontend')
    elif os.path.exists(os.path.join(_base_dir, 'frontend')):
        FRONTEND_DIR = os.path.join(_base_dir, 'frontend')

UPLOADS_DIR = os.path.abspath(os.path.join(_base_dir, 'uploads'))
if not os.path.exists(UPLOADS_DIR) and os.path.exists(os.path.abspath('backend/uploads')):
    UPLOADS_DIR = os.path.abspath('backend/uploads')

try:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
except (OSError, PermissionError):
    pass

SAAS_PLANS = {
    'basic': {
        'id': 'basic',
        'name': 'الباقة الأساسية',
        'monthly_fee': 0,
        'commission_rate': 0.015,
        'max_units': 1,
        'description': 'شقة طلابية واحدة + عمولة تحصيل 1.5%'
    },
    'pro': {
        'id': 'pro',
        'name': 'باقة ملاك سكن الطلاب Pro',
        'monthly_fee': 250,
        'commission_rate': 0.015,
        'max_units': 5,
        'description': 'حتى 5 شقق طلابية + تنبيهات واتساب للطلاب وأولياء الأمور'
    },
    'portfolio': {
        'id': 'portfolio',
        'name': 'باقة عمارات المغتربين Portfolio',
        'monthly_fee': 650,
        'commission_rate': 0.010,
        'max_units': 25,
        'description': 'حتى 25 شقة طلابية + عمولة مخفضة 1.0% + مدير حساب مخصص'
    }
}


# ==============================================================================
# Database Connection & Hybrid Support (SQLite + PostgreSQL)
# ==============================================================================

def get_db_type():
    if DATABASE_URL and (DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')):
        return 'postgresql'
    return 'sqlite'


def get_db():
    if get_db_type() == 'postgresql':
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            url = DATABASE_URL
            if url.startswith('postgres://'):
                url = url.replace('postgres://', 'postgresql://', 1)
            conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
            return conn
        except Exception:
            pass
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ==============================================================================
# Security: Password Hashing (Werkzeug & PBKDF2 compatibility)
# ==============================================================================

def hash_password(password, salt=None):
    return generate_password_hash(password)


def verify_password(stored_password, provided_password):
    if not stored_password or not provided_password:
        return False
    # Check legacy PBKDF2 salt$hex format for backward compatibility
    if '$' in stored_password and not stored_password.startswith(('pbkdf2:', 'scrypt:')):
        try:
            parts = stored_password.split('$')
            if len(parts) == 2:
                salt, key = parts
                test_key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), bytes.fromhex(salt), 100000)
                if test_key.hex() == key:
                    return True
        except Exception:
            pass
    try:
        return check_password_hash(stored_password, provided_password)
    except Exception:
        return False


# ==============================================================================
# Security: JWT Token Generation, Verification & Decorator
# ==============================================================================

def generate_jwt_token(user_id, role='student', full_name='', phone=''):
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        'sub': str(user_id),
        'user_id': user_id,
        'role': role,
        'full_name': full_name,
        'phone': phone or '',
        'exp': exp,
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token):
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def create_session(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, full_name, role, phone FROM users WHERE id = ?', (user_id,))
    user = cur.fetchone()
    conn.close()

    role = user['role'] if user else 'student'
    full_name = user['full_name'] if user else ''
    phone = user['phone'] if user else ''

    token = generate_jwt_token(user_id, role, full_name, phone)

    expires_at = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
                (token, user_id, created_at, expires_at))
        # Upgrade any existing svg images to Unsplash HD photos
    try:
        cur.execute("SELECT id, images_json FROM properties")
        rows = cur.fetchall()
        unsplash_pool = [
            'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1554995207-c18c203602cb?auto=format&fit=crop&w=800&q=80',
            'https://images.unsplash.com/photo-1536376072261-38c75010e6c9?auto=format&fit=crop&w=800&q=80'
        ]
        for idx, r in enumerate(rows):
            img_val = r['images_json'] or ''
            if '.svg' in img_val or img_val == '[]' or not img_val:
                p1 = unsplash_pool[idx % len(unsplash_pool)]
                p2 = unsplash_pool[(idx + 1) % len(unsplash_pool)]
                new_json = json.dumps([p1, p2], ensure_ascii=False)
                cur.execute("UPDATE properties SET images_json = ?, images = ? WHERE id = ?", (new_json, new_json, r['id']))
    except Exception:
        pass

    conn.commit()
    conn.close()
    return token


def get_user_from_token(token):
    if not token:
        return None

    # 1. Verify signed JWT
    payload = verify_jwt_token(token)
    uid = None
    if payload:
        uid = payload.get('user_id') or payload.get('sub')

    conn = get_db()
    cur = conn.cursor()
    if uid:
        cur.execute('''
            SELECT id, full_name, phone, parent_phone, email, role, university, faculty, governorate, study_habit, created_at
            FROM users WHERE id = ?
        ''', (int(uid),))
        row = cur.fetchone()
        if row:
            conn.close()
            return dict(row)

    # 2. Check active sessions table
    cur.execute('''
        SELECT u.id, u.full_name, u.phone, u.parent_phone, u.email, u.role, u.university, u.faculty, u.governorate, u.study_habit, u.created_at
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    ''', (token, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def jwt_required(roles=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = ''
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ', 1)[1].strip()
            if not token:
                token = request.args.get('token', '')

            user = get_user_from_token(token)
            if not user:
                return jsonify({'error': 'غير مصرح: يجب تسجيل الدخول وتمرير رمز JWT صالح'}), 401

            if roles and user.get('role') not in roles:
                return jsonify({'error': 'غير مصرح: ليس لديك الصلاحية الكافية لهذا الإجراء'}), 403

            return fn(user, *args, **kwargs)
        return wrapper
    return decorator


# ==============================================================================
# Sample Assets & Database Initialization
# ==============================================================================

def seed_sample_images():
    samples = [
        ('minya_main_1.svg', '#0F4C5C', 'سكن النخبة الطبي - جامعة المنيا', 'غرفة النوم والمكاتب المخصصة للطلبة'),
        ('minya_main_2.svg', '#1E6B7B', 'سكن النخبة الطبي - حي شلبي', 'صالة المذاكرة والإنترنت الفايبر'),
        ('minya_ahleya_1.svg', '#0D9488', 'سكن الرواد الفندقي - المنيا الأهلية', 'غرفة فندقية فاخرة ومكاتب مضيئة'),
        ('minya_ahleya_2.svg', '#115E59', 'سكن الرواد الفندقي - المنيا الجديدة', 'صالة المعيشة والميكروويف'),
        ('deraya_1.svg', '#BE185D', 'إقامة الصفوة للطالبات - جامعة دراية', 'غرفة طالبات هادئة بحراسة نسائية'),
        ('deraya_2.svg', '#9D174D', 'إقامة الصفوة للطالبات - دراية', 'المكتبة والمطبخ الإيطالي الكامل'),
        ('lotus_1.svg', '#0369A1', 'سكن اللوتس المتميز - جامعة اللوتس', 'غرفة الطلاب قرب بوابة اللوتس'),
        ('lotus_2.svg', '#0284C7', 'سكن اللوتس المتميز - المنيا الجديدة', 'صالة المذاكرة وشاشة العرض'),
        ('minya_corniche_1.svg', '#0284C7', 'برج الكورنيش الجامعي - المنيا', 'إطلالة نيلية مفتوحة ومكاتب دراسية'),
        ('minya_corniche_2.svg', '#0369A1', 'برج الكورنيش الجامعي - طه حسين', 'شرفة واسعة وصالة مذاكرة'),
        ('minya_girls_1.svg', '#DB2777', 'سكن الياسمين للطالبات - شلبي', 'إشراف نسائي وسكن طالبات هادئ'),
        ('minya_girls_2.svg', '#BE185D', 'سكن الياسمين للطالبات - جامعة المنيا', 'مطبخ متكامل وإنترنت فايبر')
    ]
    for filename, color, title, subtitle in samples:
        path = os.path.join(UPLOADS_DIR, filename)
        if not os.path.exists(path):
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="800" height="500">
  <defs>
    <linearGradient id="g_{filename[:3]}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{color}" stop-opacity="0.9" />
      <stop offset="100%" stop-color="#0F172A" stop-opacity="0.95" />
    </linearGradient>
  </defs>
  <rect width="800" height="500" fill="url(#g_{filename[:3]})" />
  <circle cx="400" cy="200" r="100" fill="white" fill-opacity="0.08" />
  <rect x="70" y="70" width="660" height="360" rx="24" fill="none" stroke="white" stroke-opacity="0.2" stroke-width="2" />
  <text x="400" y="195" font-family="Cairo, Arial, sans-serif" font-size="30" font-weight="bold" fill="#FFFFFF" text-anchor="middle">{title}</text>
  <text x="400" y="250" font-family="Cairo, Arial, sans-serif" font-size="18" fill="#E2E8F0" text-anchor="middle">{subtitle}</text>
  <rect x="290" y="295" width="220" height="38" rx="10" fill="#E36414" />
  <text x="400" y="320" font-family="Cairo, Arial, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">سكن طلاب مصر v3.1 موثق ✓</text>
</svg>'''
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(svg)
            except (OSError, PermissionError):
                pass


def init_db():
    seed_sample_images()
    conn = get_db()
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            parent_phone TEXT DEFAULT '',
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            university TEXT DEFAULT '',
            faculty TEXT DEFAULT '',
            governorate TEXT DEFAULT '',
            study_habit TEXT DEFAULT 'مذاكرة هادئة - غير مدخن',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            governorate TEXT NOT NULL,
            university TEXT NOT NULL,
            region TEXT NOT NULL,
            distance_walk TEXT NOT NULL,
            gender TEXT NOT NULL,
            total_beds INTEGER NOT NULL,
            available_beds INTEGER NOT NULL,
            bed_monthly_price REAL NOT NULL,
            total_monthly_rent REAL NOT NULL,
            deposit_amount REAL NOT NULL DEFAULT 2000.0,
            study_environment TEXT NOT NULL DEFAULT 'هادئ للمذاكرة - غير مدخنين',
            is_verified_campus INTEGER NOT NULL DEFAULT 1,
            lease_duration TEXT NOT NULL,
            amenities TEXT NOT NULL,
            landlord_name TEXT NOT NULL,
            landlord_phone TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            images_json TEXT NOT NULL DEFAULT '[]',
            images TEXT NOT NULL DEFAULT '[]',
            landlord_user_id INTEGER DEFAULT 2,
            lat REAL DEFAULT 30.0,
            lng REAL DEFAULT 31.0,
            gate_lat REAL DEFAULT 30.0,
            gate_lng REAL DEFAULT 31.0,
            gate_name TEXT DEFAULT '',
            walk_minutes INTEGER DEFAULT 5,
            rating_avg REAL DEFAULT 4.8,
            reviews_count INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS roommates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            faculty TEXT NOT NULL,
            academic_year TEXT DEFAULT 'الفرقة الثالثة',
            home_governorate TEXT NOT NULL,
            whatsapp_phone TEXT NOT NULL,
            parent_phone TEXT DEFAULT '',
            study_habit TEXT DEFAULT 'مذاكرة هادئة - نوم مبكر',
            monthly_share REAL NOT NULL,
            deposit_escrow REAL NOT NULL DEFAULT 2000.0,
            deposit_status TEXT NOT NULL DEFAULT 'escrow_secured',
            payment_status TEXT NOT NULL DEFAULT 'due',
            last_payment_date TEXT DEFAULT '',
            receipt_code TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS video_tours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            property_title TEXT NOT NULL,
            student_name TEXT NOT NULL,
            student_phone TEXT NOT NULL,
            home_governorate TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            preferred_time TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'WhatsApp',
            notes TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            amount REAL NOT NULL,
            commission REAL NOT NULL,
            net_landlord REAL NOT NULL,
            method TEXT NOT NULL,
            reference_code TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            plan_tier TEXT NOT NULL DEFAULT 'pro',
            paymob_order_id TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS utilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            utility_name TEXT NOT NULL,
            month_label TEXT NOT NULL,
            total_bill REAL NOT NULL,
            per_student_share REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'unpaid'
        );

        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            property_title TEXT NOT NULL,
            student_name TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            description TEXT NOT NULL,
            estimated_cost REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            faculty TEXT NOT NULL,
            rating REAL NOT NULL,
            comment TEXT NOT NULL,
            semester TEXT NOT NULL DEFAULT 'الفصل الدراسي الأول 2026',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS parent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            parent_phone TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'WhatsApp',
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'delivered',
            created_at TEXT NOT NULL
        );
    ''')

    # Schema Migrations for existing database instances
    cols_to_add = [
        ('users', 'parent_phone', "TEXT DEFAULT ''"),
        ('users', 'faculty', "TEXT DEFAULT ''"),
        ('users', 'study_habit', "TEXT DEFAULT 'مذاكرة هادئة - غير مدخن'"),
        ('properties', 'deposit_amount', "REAL NOT NULL DEFAULT 2000.0"),
        ('properties', 'study_environment', "TEXT NOT NULL DEFAULT 'هادئ للمذاكرة - غير مدخنين'"),
        ('properties', 'is_verified_campus', "INTEGER NOT NULL DEFAULT 1"),
        ('properties', 'images_json', "TEXT NOT NULL DEFAULT '[]'"),
        ('properties', 'images', "TEXT NOT NULL DEFAULT '[]'"),
        ('properties', 'whatsapp_phone', "TEXT DEFAULT ''"),
        ('properties', 'landlord_user_id', "INTEGER DEFAULT 2"),
        ('properties', 'lat', "REAL DEFAULT 30.0"),
        ('properties', 'lng', "REAL DEFAULT 31.0"),
        ('properties', 'gate_lat', "REAL DEFAULT 30.0"),
        ('properties', 'gate_lng', "REAL DEFAULT 31.0"),
        ('properties', 'gate_name', "TEXT DEFAULT ''"),
        ('properties', 'walk_minutes', "INTEGER DEFAULT 5"),
        ('properties', 'rating_avg', "REAL DEFAULT 4.8"),
        ('properties', 'reviews_count', "INTEGER DEFAULT 1"),
        ('roommates', 'parent_phone', "TEXT DEFAULT ''"),
        ('roommates', 'academic_year', "TEXT DEFAULT 'الفرقة الثالثة'"),
        ('roommates', 'study_habit', "TEXT DEFAULT 'مذاكرة هادئة - غير مدخن'"),
        ('roommates', 'deposit_escrow', "REAL NOT NULL DEFAULT 2000.0"),
        ('roommates', 'deposit_status', "TEXT NOT NULL DEFAULT 'escrow_secured'"),
        ('payments', 'paymob_order_id', "TEXT DEFAULT ''")
    ]
    for table, col, typedef in cols_to_add:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # Seed Default Demo Accounts
    cur.execute('SELECT COUNT(*) as cnt FROM users')
    if cur.fetchone()['cnt'] == 0:
        demo_users = [
            (
                'أحمد محمود - طالب طب بشري مغترب',
                '01012345678',
                '01099881122',
                'student@ejari-egypt.com',
                hash_password('student123'),
                'student',
                'جامعة المنيا',
                'كلية الطب البشري - الفرقة الرابعة',
                'المنيا - حي شلبي',
                'مذاكرة هادئة - غير مدخن - نوم مبكر',
                '2026-10-01 10:00:00'
            ),
            (
                'الحاج محمود المنياوي - مالك سكن النخبة',
                '01123456789',
                '01123456789',
                'landlord@ejari-egypt.com',
                hash_password('landlord123'),
                'landlord',
                'جامعة المنيا',
                '',
                'المنيا',
                'إشراف كامل وتسكين فندقي هادئ',
                '2026-10-01 10:00:00'
            ),
            (
                'مدير منصة إيجاري المنيا (Admin)',
                '01234567890',
                '01234567890',
                'admin@ejari-egypt.com',
                hash_password('admin123'),
                'admin',
                'جامعات المنيا الأربع',
                'إدارة السكن الجامعي الموثق',
                'المنيا',
                'إدارة وتوثيق العقود والضمان',
                '2026-10-01 10:00:00'
            )
        ]
        cur.executemany('''
            INSERT INTO users (full_name, phone, parent_phone, email, password_hash, role, university, faculty, governorate, study_habit, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', demo_users)
    else:
        # Guarantee demo account passwords use modern secure hashing
        cur.execute("UPDATE users SET password_hash = ? WHERE phone = '01012345678'", (hash_password('student123'),))
        cur.execute("UPDATE users SET password_hash = ? WHERE phone = '01123456789'", (hash_password('landlord123'),))
        cur.execute("UPDATE users SET password_hash = ? WHERE phone = '01234567890'", (hash_password('admin123'),))

    # Seed Properties (only when database is empty)
    cur.execute("SELECT COUNT(*) as cnt FROM properties")
    prop_stat = cur.fetchone()
    if prop_stat['cnt'] == 0:
        sample_properties = [
            (
                'سكن النخبة الطبي — حي شلبي (أمام بوابة جامعة المنيا الحكومية)',
                'المنيا',
                'جامعة المنيا',
                'حي شلبي، أمام مجمع الكليات الطبية',
                '3 دقائق مشياً لبوابة طب وعلوم المنيا',
                'male',
                4,
                1,
                1850.0,
                7400.0,
                1800.0,
                'هادئ للمذاكرة - كليات طب وعلوم',
                1,
                'عام دراسي (9 شهور)',
                'إنترنت فايبر WE Space فائق السرعة,مكاتب مذاكرة خاصة لكل طالب,غسالة أوتوماتيك,تكييف,سخان غاز,أمن ودخول ذكي',
                'الحاج محمود المنياوي',
                '01019876543',
                'available',
                json.dumps(['https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=800&q=80'], ensure_ascii=False),
                2,
                28.1174, 30.7508, 28.1158, 30.7525, 'بوابة الجامعة الرئيسية ومجمع الكليات الطبية — جامعة المنيا', 3, 4.9, 12
            ),
            (
                'سكن الرواد الفندقي — المنيا الجديدة (بجوار جامعة المنيا الأهلية)',
                'المنيا - المنيا الجديدة',
                'جامعة المنيا الأهلية',
                'المنيا الجديدة، الحي الرابع أمام الجهاز',
                '4 دقائق مشياً لبوابة جامعة المنيا الأهلية',
                'male',
                4,
                2,
                2300.0,
                9200.0,
                2200.0,
                'مستوى فندقي فاخر - بيئة هادئة',
                1,
                'عام دراسي (9 شهور)',
                'غرف فندقية مجهزة,تكييفات سبليت,إنترنت فايبر عالي السرعة,مكاتب دراسية مضيئة,غسالة وميكروويف,خدمة نظافة دورية',
                'المهندس كريم الشريف',
                '01123450987',
                'available',
                json.dumps(['https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=800&q=80'], ensure_ascii=False),
                2,
                28.0712, 30.8275, 28.0694, 30.8294, 'بوابة الحرم الجامعي — جامعة المنيا الأهلية', 4, 4.8, 9
            ),
            (
                'إقامة الصفوة للطالبات — المنيا الجديدة (أمام جامعة دراية Deraya)',
                'المنيا - المنيا الجديدة',
                'جامعة دراية',
                'المنيا الجديدة، الحي السياحي، بجوار دراية',
                '3 دقائق مشياً لبوابة صيدلة وعلاج طبيعي دراية',
                'female',
                3,
                1,
                2500.0,
                7500.0,
                2500.0,
                'أمن 24 ساعة - هادئ جداً لطالبات الصيدلة',
                1,
                'عام دراسي (9 شهور)',
                'حراسة نسائية وكاميرات مراقبة 24 ساعة,مطبخ إيطالي كامل,تكييفات وإنترنت سريع,مكتبة دراسية خاصة,غسالة أوتوماتيك,سخان فوري',
                'الدكتورة مرفت الصاوي',
                '01278901234',
                'available',
                json.dumps(['https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1554995207-c18c203602cb?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1536376072261-38c75010e6c9?auto=format&fit=crop&w=800&q=80'], ensure_ascii=False),
                2,
                28.0785, 30.8226, 28.0768, 30.8242, 'بوابة كليات الصيدلة والعلاج الطبيعي — جامعة دراية Deraya', 3, 5.0, 14
            ),
            (
                'سكن اللوتس المتميز — المنيا الجديدة (قرب جامعة اللوتس Lotus University)',
                'المنيا - المنيا الجديدة',
                'جامعة اللوتس',
                'المنيا الجديدة، امتداد الحي المتميز',
                '5 دقائق مشياً لبوابة جامعة اللوتس',
                'male',
                4,
                2,
                2100.0,
                8400.0,
                2000.0,
                'هادئ للمذاكرة - كليات طب أسنان وهندسة',
                1,
                'عام دراسي (9 شهور)',
                'إنترنت فايبر غير محدود,مكاتب مذاكرة زان,شاشة سمارت بالصالة,تكييف,غسالة أوتوماتيك,أمن ودخول إلكتروني',
                'الأستاذ حسام فتحي',
                '01065432109',
                'available',
                json.dumps(['https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80'], ensure_ascii=False),
                2,
                28.0638, 30.8362, 28.0655, 30.8385, 'بوابة الحرم الجامعي — جامعة اللوتس Lotus University', 5, 4.8, 7
            ),
            (
                'برج الكورنيش الجامعي — أرض سلطان وشارع طه حسين (جامعة المنيا)',
                'المنيا',
                'جامعة المنيا',
                'أرض سلطان، تقاطع شارع طه حسين مع الكورنيش',
                'خطوات لكورنيش النيل و5 دقائق لموقف الجامعة والتربية',
                'male',
                4,
                1,
                1950.0,
                7800.0,
                1900.0,
                'إطلالة نيلية مفتوحة - غير مدخنين',
                1,
                'فصل دراسي (5 شهور)',
                'إطلالة على كورنيش النيل,إنترنت سريع,مكاتب دراسية مريحة,شرفة واسعة,سخان غاز,غسالة فول أوتوماتيك',
                'المستشار عادل رضوان',
                '01156789012',
                'available',
                json.dumps(['/uploads/minya_corniche_1.svg', '/uploads/minya_corniche_2.svg'], ensure_ascii=False),
                2,
                28.1120, 30.7555, 28.1158, 30.7525, 'بوابة الجامعة الرئيسية وكورنيش النيل — جامعة المنيا', 5, 4.9, 11
            ),
            (
                'سكن الياسمين للطالبات المغتربات — حي شلبي (جامعة المنيا)',
                'المنيا',
                'جامعة المنيا',
                'حي شلبي، شارع المدارس الهادئ',
                '4 دقائق مشياً لبوابة الآداب والتربية بالمنيا',
                'female',
                4,
                2,
                1700.0,
                6800.0,
                1600.0,
                'سكن طالبات هادئ وموثق - إشراف نسائي',
                1,
                'عقد سنوي (12 شهراً)',
                'إشراف نسائي يومي,إنترنت فايبر,مطبخ متكامل مجهز,مكاتب إضاءة دافئة,غسالة ملابس,سخان غاز فوري',
                'الحاجة أم أحمد البهنساوي',
                '01099887766',
                'available',
                json.dumps(['https://images.unsplash.com/photo-1536376072261-38c75010e6c9?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80'], ensure_ascii=False),
                2,
                28.1186, 30.7512, 28.1158, 30.7525, 'بوابة كليات الآداب والتربية — جامعة المنيا', 4, 4.9, 10
            )
        ]
        cur.executemany('''
            INSERT INTO properties (
                title, governorate, university, region, distance_walk, gender,
                total_beds, available_beds, bed_monthly_price, total_monthly_rent,
                deposit_amount, study_environment, is_verified_campus,
                lease_duration, amenities, landlord_name, landlord_phone, status, images_json, landlord_user_id,
                lat, lng, gate_lat, gate_lng, gate_name, walk_minutes, rating_avg, reviews_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_properties)
    else:
        # Guarantee existing properties have updated coordinates, gates & ratings
        coords_seed = [
            (1, 28.1174, 30.7508, 28.1158, 30.7525, 'بوابة الجامعة الرئيسية ومجمع الكليات الطبية — جامعة المنيا', 3, 4.9, 12),
            (2, 28.0712, 30.8275, 28.0694, 30.8294, 'بوابة الحرم الجامعي — جامعة المنيا الأهلية', 4, 4.8, 9),
            (3, 28.0785, 30.8226, 28.0768, 30.8242, 'بوابة كليات الصيدلة والعلاج الطبيعي — جامعة دراية Deraya', 3, 5.0, 14),
            (4, 28.0638, 30.8362, 28.0655, 30.8385, 'بوابة الحرم الجامعي — جامعة اللوتس Lotus University', 5, 4.8, 7),
            (5, 28.1120, 30.7555, 28.1158, 30.7525, 'بوابة الجامعة الرئيسية وكورنيش النيل — جامعة المنيا', 5, 4.9, 11),
            (6, 28.1186, 30.7512, 28.1158, 30.7525, 'بوابة كليات الآداب والتربية — جامعة المنيا', 4, 4.9, 10),
        ]
        for pid, lat, lng, glat, glng, gname, walk, ravg, rcnt in coords_seed:
            cur.execute('''
                UPDATE properties
                SET lat = ?, lng = ?, gate_lat = ?, gate_lng = ?, gate_name = ?, walk_minutes = ?, rating_avg = ?, reviews_count = ?
                WHERE id = ?
            ''', (lat, lng, glat, glng, gname, walk, ravg, rcnt, pid))

        # Always ensure all properties have high-res Unsplash interior photos
        minya_unsplash_map = {
            1: [
                "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80"
            ],
            2: [
                "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80"
            ],
            3: [
                "https://images.unsplash.com/photo-1598928506311-c55ded91a20c?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1505691938895-1758d7feb511?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1512918728675-ed5a9ecdebfd?auto=format&fit=crop&w=800&q=80"
            ],
            4: [
                "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1540518614846-7ede433c4ef6?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1493663284031-b7e3aefcae8e?auto=format&fit=crop&w=800&q=80"
            ],
            5: [
                "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1560185127-6ed189bf02f4?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1507089947368-19c1da9775ae?auto=format&fit=crop&w=800&q=80"
            ],
            6: [
                "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1519710164239-da123dc03ef4?auto=format&fit=crop&w=800&q=80",
                "https://images.unsplash.com/photo-1501183638710-841dd1904471?auto=format&fit=crop&w=800&q=80"
            ]
        }
        for prop_id, img_arr in minya_unsplash_map.items():
            img_json = json.dumps(img_arr, ensure_ascii=False)
            cur.execute('''
                UPDATE properties
                SET images_json = ?, images = ?
                WHERE id = ? AND (images_json IS NULL OR images_json = '' OR images_json = '[]' OR images_json LIKE '%.svg%')
            ''', (img_json, img_json, prop_id))

    # Roommates seed
    cur.execute('SELECT COUNT(*) as cnt FROM roommates')
    if cur.fetchone()['cnt'] == 0:
        sample_roommates = [
            (1, 'أحمد الشريف', 'كلية الطب البشري', 'الفرقة الرابعة', 'سوهاج', '01023456781', '01011122233', 'مذاكرة هادئة - غير مدخن - نوم مبكر', 2200.0, 2000.0, 'escrow_secured', 'paid', '2026-10-02', 'EJR-202610-101'),
            (1, 'زياد العوضي', 'كلية الحاسبات والذكاء الاصطناعي', 'الفرقة الثالثة', 'كفر الشيخ', '01134567892', '01122233344', 'مذاكرة ليلية هادئة - غير مدخن', 2200.0, 2000.0, 'escrow_secured', 'due', '', ''),
            (1, 'عمر الفاروق الديب', 'كلية الصيدلة', 'الفرقة الثانية', 'دمياط', '01245678903', '01233344455', 'مذاكرة هادئة - نوم مبكر', 2200.0, 2000.0, 'escrow_secured', 'paid', '2026-10-04', 'EJR-202610-103'),

            (2, 'مريم خالد الصاوي', 'كلية الإعلام', 'الفرقة الثالثة', 'الإسماعيلية', '01056789014', '01044455566', 'مذاكرة منظمة - غير مدخن', 2800.0, 2500.0, 'escrow_secured', 'paid', '2026-10-01', 'EJR-202610-201'),
            (2, 'نوران مصطفى قنديل', 'كلية الاقتصاد والعلوم السياسية', 'الفرقة الثانية', 'قنا', '01167890125', '01155566677', 'مذاكرة هادئة - نوم مبكر', 2800.0, 2500.0, 'escrow_secured', 'due', '', ''),
            (2, 'ياسمين رأفت الجوهري', 'كلية العلاج الطبيعي', 'الفرقة الرابعة', 'المنيا', '01278901236', '01266677788', 'مذاكرة هادئة - غير مدخن', 2800.0, 2500.0, 'escrow_secured', 'paid', '2026-10-03', 'EJR-202610-203'),

            (3, 'فاطمة الزهراء كمال', 'كلية الفنون الجميلة', 'الفرقة الثانية', 'البحيرة (دمنهور)', '01089012347', '01077788899', 'مذاكرة هادئة وهوايات فنية', 2400.0, 2000.0, 'escrow_secured', 'paid', '2026-10-05', 'EJR-202610-301'),
            (3, 'رنا إبراهيم حميدة', 'كلية التربية', 'الفرقة الأولى', 'مطروح', '01190123458', '01188899900', 'مذاكرة صباحية - غير مدخن', 2400.0, 2000.0, 'escrow_secured', 'late', '', ''),

            (4, 'محمود عبد الرحيم', 'كلية هندسة الطاقة', 'الفرقة الثالثة', 'أسوان', '01011223344', '01099900011', 'مذاكرة هادئة - غير مدخن', 1600.0, 1500.0, 'escrow_secured', 'paid', '2026-10-01', 'EJR-202610-401'),
            (4, 'علي جاد الكريم', 'كلية العلوم - قسم حاسب', 'الفرقة الرابعة', 'الأقصر', '01122334455', '01100011122', 'مذاكرة برمجة هادئة', 1600.0, 1500.0, 'escrow_secured', 'due', '', ''),
            (4, 'عبد الرحمن هلال', 'كلية الزراعة', 'الفرقة الثانية', 'الوادي الجديد', '01233445566', '01211122233', 'مذاكرة هادئة - نوم مبكر', 1600.0, 1500.0, 'escrow_secured', 'paid', '2026-10-02', 'EJR-202610-403'),

            (5, 'حسام كمال ناصف', 'كلية الهندسة', 'الفرقة الثالثة', 'المنوفية (شبين الكوم)', '01044556677', '01022233344', 'مذاكرة جماعية هادئة - غير مدخن', 1800.0, 1800.0, 'escrow_secured', 'paid', '2026-10-03', 'EJR-202610-501'),
            (5, 'أسامة نجيب', 'كلية التمريض', 'الفرقة الثانية', 'الشرقية (الزقازيق)', '01155667788', '01133344455', 'مواعيد مستشفى منظمة - هادئ', 1800.0, 1800.0, 'escrow_secured', 'due', '', ''),

            (6, 'شهد طارق البشبيشي', 'كلية طب الأسنان - MUST', 'الفرقة الرابعة', 'بورسعيد', '01066778899', '01044455577', 'مذاكرة عيادات هادئة - غير مدخن', 3500.0, 3000.0, 'escrow_secured', 'paid', '2026-10-01', 'EJR-202610-601'),
            (6, 'هايدي المنشاوي', 'كلية الصيدلة - MUST', 'الفرقة الثالثة', 'السويس', '01177889900', '01155566688', 'مذاكرة هادئة - نوم منتظم', 3500.0, 3000.0, 'escrow_secured', 'paid', '2026-10-02', 'EJR-202610-602'),
            (6, 'رزان بدر التميمي', 'كلية التكنولوجيا الحيوية', 'الفرقة الثانية', 'البحر الأحمر (الغردقة)', '01288990011', '01266677799', 'مذاكرة هادئة - غير مدخن', 3500.0, 3000.0, 'escrow_secured', 'due', '', '')
        ]
        cur.executemany('''
            INSERT INTO roommates (
                property_id, student_name, faculty, academic_year, home_governorate,
                whatsapp_phone, parent_phone, study_habit, monthly_share, deposit_escrow,
                deposit_status, payment_status, last_payment_date, receipt_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_roommates)

    # Video tours seed
    cur.execute('SELECT COUNT(*) as cnt FROM video_tours')
    if cur.fetchone()['cnt'] == 0:
        sample_video_tours = [
            (1, 'سكن الفردوس للطلاب — حي الجامعة', 'أحمد محمود', '01012345678', 'كفر الشيخ', '2026-11-02', '05:00 م', 'WhatsApp', 'معاينة غرفة النوم والمكتب والمطبخ مباشرة مع والدي', 'scheduled', '2026-10-30 18:00'),
            (3, 'سكن إطلالة البحر للطالبات — سوتر', 'سارة عبد الفتاح', '01099884433', 'المنيا', '2026-11-03', '04:30 م', 'Zoom', 'معاينة الغرفة البحرية والتأكد من إشارة الإنترنت', 'scheduled', '2026-10-30 19:30')
        ]
        cur.executemany('''
            INSERT INTO video_tours (
                property_id, property_title, student_name, student_phone,
                home_governorate, preferred_date, preferred_time, platform, notes, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_video_tours)

    # Reviews seed
    cur.execute('SELECT COUNT(*) as cnt FROM reviews')
    if cur.fetchone()['cnt'] == 0:
        sample_reviews = [
            (1, 'طارق سليم', 'كلية الطب البشري - جامعة المنيا', 5.0, 'سكن ممتاز وهادئ جداً ومناسب لأجواء الامتحانات، وبوابة توشكى على بُعد خطوات.', 'الفصل الدراسي الثاني 2026', '2026-10-15 14:00'),
            (1, 'محمود رضوان', 'كلية الهندسة', 4.8, 'الإنترنت فايبر ممتاز وسريع جداً والمؤجر متعاون في كافة أعمال الصيانة الدورية.', 'الفصل الدراسي الأول 2026', '2026-10-20 18:30'),
            (2, 'آية الشريف', 'كلية التربية للطفولة - جامعة المنيا', 4.9, 'إشراف وأمن ممتاز للطالبات ونظافة عالية وقريبة جداً من محطة مترو الدقي.', 'الفصل الدراسي الأول 2026', '2026-10-18 11:20'),
            (3, 'سارة نصر', 'كلية الصيدلة - جامعة دراية', 5.0, 'فيو بحري رائع وهدوء كامل للدراسة وموقع قريب جداً من مجمع الكليات بسوتر.', 'الفصل الدراسي الثاني 2026', '2026-10-22 16:45')
        ]
        cur.executemany('''
            INSERT INTO reviews (property_id, student_name, faculty, rating, comment, semester, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_reviews)

    # Parent notifications seed
    cur.execute('SELECT COUNT(*) as cnt FROM parent_notifications')
    if cur.fetchone()['cnt'] == 0:
        sample_parent_notes = [
            ('أحمد الشريف', '01011122233', 'WhatsApp', 'عزيزي ولي أمر الطالب أحمد الشريف، تم استلام سداد قسط إيجار سرير شهر أكتوبر 2026 بقيمة 2200 ج.م برقم إيصال رسمي EJR-202610-101. شكراً لثقتكم بمنصة إيجاري طلاب مصر.', 'delivered', '2026-10-02 11:35'),
            ('عمر الفاروق الديب', '01233344455', 'WhatsApp', 'عزيزي ولي أمر الطالب عمر الفاروق الديب، تم تأكيد حجز السرير وإيداع مبلغ التأمين المسترد بقيمة 2000 ج.م في حساب الضمان البنكي Escrow بنجاح.', 'delivered', '2026-10-04 15:50')
        ]
        cur.executemany('''
            INSERT INTO parent_notifications (student_name, parent_phone, channel, message, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_parent_notes)

    # Payments seed
    cur.execute('SELECT COUNT(*) as cnt FROM payments')
    if cur.fetchone()['cnt'] == 0:
        sample_payments = [
            (1, 'أحمد الشريف', 'rent_bed', 2200.0, 33.0, 2167.0, 'InstaPay', 'EJR-202610-101', '2026-10-02 11:30', 'pro', 'ord_pm_101'),
            (1, 'عمر الفاروق الديب', 'rent_bed', 2200.0, 33.0, 2167.0, 'VodafoneCash', 'EJR-202610-103', '2026-10-04 15:45', 'pro', 'ord_pm_103'),
            (2, 'مريم خالد الصاوي', 'rent_bed', 2800.0, 42.0, 2758.0, 'InstaPay', 'EJR-202610-201', '2026-10-01 09:15', 'pro', 'ord_pm_201'),
            (2, 'ياسمين رأفت الجوهري', 'rent_bed', 2800.0, 42.0, 2758.0, 'MeezaCard', 'EJR-202610-203', '2026-10-03 18:20', 'pro', 'ord_pm_203'),
            (3, 'فاطمة الزهراء كمال', 'rent_bed', 2400.0, 36.0, 2364.0, 'Fawry', 'EJR-202610-301', '2026-10-05 14:10', 'pro', 'ord_pm_301'),
            (4, 'محمود عبد الرحيم', 'rent_bed', 1600.0, 24.0, 1576.0, 'InstaPay', 'EJR-202610-401', '2026-10-01 10:00', 'pro', 'ord_pm_401'),
            (4, 'عبد الرحمن هلال', 'rent_bed', 1600.0, 24.0, 1576.0, 'VodafoneCash', 'EJR-202610-403', '2026-10-02 16:30', 'pro', 'ord_pm_403'),
            (5, 'حسام كمال ناصف', 'rent_bed', 1800.0, 27.0, 1773.0, 'InstaPay', 'EJR-202610-501', '2026-10-03 12:45', 'pro', 'ord_pm_501'),
            (6, 'شهد طارق البشبيشي', 'rent_bed', 3500.0, 52.5, 3447.5, 'InstaPay', 'EJR-202610-601', '2026-10-01 13:00', 'pro', 'ord_pm_601'),
            (6, 'هايدي المنشاوي', 'rent_bed', 3500.0, 52.5, 3447.5, 'MeezaCard', 'EJR-202610-602', '2026-10-02 17:15', 'pro', 'ord_pm_602')
        ]
        cur.executemany('''
            INSERT INTO payments (
                property_id, student_name, payment_type, amount, commission,
                net_landlord, method, reference_code, paid_at, plan_tier, paymob_order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_payments)

    # Utilities seed
    cur.execute('SELECT COUNT(*) as cnt FROM utilities')
    if cur.fetchone()['cnt'] == 0:
        sample_utilities = [
            (1, 'اشتراك إنترنت فايبر منزلي WE Space (سعة 300 جيجابايت)', 'أكتوبر 2026', 420.0, 105.0, 'paid'),
            (1, 'شحن كارت كهرباء العداد مسبق الدفع (كود 8821)', 'أكتوبر 2026', 500.0, 125.0, 'paid'),
            (1, 'فاتورة الغاز الطبيعي (شركة بتروتريد)', 'أكتوبر 2026', 160.0, 40.0, 'unpaid'),
            (1, 'فاتورة مياه الشرب والصرف الصحي', 'أكتوبر 2026', 120.0, 30.0, 'unpaid'),
            (2, 'اشتراك إنترنت فايبر WE Space منزلي', 'أكتوبر 2026', 360.0, 120.0, 'paid'),
            (2, 'شحن كارت الكهرباء الذكي بالدقي', 'أكتوبر 2026', 450.0, 150.0, 'unpaid'),
            (3, 'اشتراك إنترنت سكن دراية فايبر', 'أكتوبر 2026', 400.0, 100.0, 'unpaid'),
            (4, 'اشتراك إنترنت فايبر لطلبة الأهلية', 'أكتوبر 2026', 320.0, 80.0, 'paid'),
            (5, 'فاتورة مياه وإنترنت سكن اللوتس', 'أكتوبر 2026', 380.0, 95.0, 'unpaid'),
            (6, 'إنترنت فايبر فائق السرعة + صيانة الحي المتميز', 'أكتوبر 2026', 800.0, 200.0, 'paid')
        ]
        cur.executemany('''
            INSERT INTO utilities (
                property_id, utility_name, month_label, total_bill, per_student_share, status
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_utilities)

    # Maintenance seed
    cur.execute('SELECT COUNT(*) as cnt FROM maintenance')
    if cur.fetchone()['cnt'] == 0:
        sample_maintenance = [
            (
                1,
                'سكن النخبة الطبي — حي شلبي (جامعة المنيا)',
                'زياد العوضي',
                'كهرباء',
                'عاجل',
                'فصل مفتاح لوحة الكهرباء المغذي لمكيف صالة المذاكرة بعد زيادة الحمل.',
                350.0,
                'in_progress',
                '2026-10-25'
            ),
            (
                1,
                'سكن النخبة الطبي — حي شلبي (جامعة المنيا)',
                'أحمد الشريف',
                'سباكة',
                'متوسط',
                'تسريب مياه بسيط أسفل حوض حمام الطلاب الرئيسي بحاجة لتغيير قلب الصنبور.',
                180.0,
                'completed',
                '2026-10-18'
            ),
            (
                2,
                'سكن الرواد الفندقي — المنيا الجديدة (جامعة المنيا الأهلية)',
                'نوران مصطفى',
                'راوتر وشبكة إنترنت',
                'عاجل',
                'ضعف إشارة راوتر الـ Wi-Fi في غرفة المذاكرة الداخلية وحاجة لتركيب مقوي إشارة (Extender).',
                280.0,
                'new',
                '2026-10-28'
            ),
            (
                3,
                'إقامة الصفوة للطالبات — المنيا الجديدة (جامعة دراية)',
                'فاطمة الزهراء',
                'نجارة وألوميتال',
                'منخفض',
                'صيانة مقبض نافذة غرفة النوم البحرية لتقفيلها بإحكام في نوات الشتاء.',
                150.0,
                'new',
                '2026-10-29'
            ),
            (
                4,
                'سكن اللوتس المتميز — المنيا الجديدة (جامعة اللوتس)',
                'محمود عبد الرحيم',
                'سباكة',
                'متوسط',
                'صيانة وتغيير شمعات فلتر المياه المنزلي سعة 5 مراحل.',
                200.0,
                'completed',
                '2026-10-12'
            )
        ]
        cur.executemany('''
            INSERT INTO maintenance (
                property_id, property_title, student_name, category,
                priority, description, estimated_cost, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_maintenance)

    conn.commit()
    conn.close()


# Auto-initialize database on serverless boot (crucial for Vercel /tmp)
try:
    init_db()
except Exception as _boot_err:
    pass


# ==============================================================================
# Domain Services & Business Logic
# ==============================================================================

class PaymobSandboxService:
    def __init__(self):
        self.api_key = os.environ.get('PAYMOB_API_KEY', '')
        self.integration_id_card = os.environ.get('PAYMOB_INTEGRATION_ID_CARD', '392019')
        self.integration_id_wallet = os.environ.get('PAYMOB_INTEGRATION_ID_WALLET', '392020')
        self.iframe_id = os.environ.get('PAYMOB_IFRAME_ID', '778899')

    def initiate_payment(self, amount_egp, method, student_name, property_id, extra_meta=None):
        amount_cents = int(float(amount_egp) * 100)
        order_id = f"ord_pm_{datetime.now().strftime('%Y%m%d%H%M')}_{secrets.token_hex(3)}"
        payment_token = f"pm_token_{secrets.token_hex(16)}"

        fawry_code = f"788-{secrets.randbelow(89999999) + 10000000}" if method == 'Fawry' else ''
        wallet_ref = f"010{secrets.randbelow(89999999) + 10000000}" if method == 'VodafoneCash' else ''

        return {
            'status': 'initiated',
            'order_id': order_id,
            'amount_egp': amount_egp,
            'amount_cents': amount_cents,
            'currency': 'EGP',
            'method': method,
            'student_name': student_name,
            'property_id': property_id,
            'payment_token': payment_token,
            'fawry_reference_code': fawry_code,
            'wallet_phone': wallet_ref,
            'iframe_url': f"https://accept.paymob.com/api/acceptance/iframes/{self.iframe_id}?payment_token={payment_token}",
            'is_sandbox': True,
            'instructions': self._get_instructions(method, fawry_code, wallet_ref)
        }

    def _get_instructions(self, method, fawry_code, wallet_ref):
        if method == 'Fawry':
            return f"توجه لأقرب منفذ فوري أو ماكينة دفع واطلب كود الخدمة 788 بالرقم المرجعي: {fawry_code}"
        if method == 'VodafoneCash':
            return f"قم بالتحويل عبر تطبيق محفظتك (أو اطلب *9*7#) إلى الرقم: {wallet_ref} وسجل رقم الإشعار"
        if method == 'InstaPay':
            return "سداد لحظي بدون أي رسوم عبر عنوان الدفع IPA: ejari.students@instapay"
        return "سداد آمن ومحمي ببروتوكول 3D Secure الوطني عبر بطاقات ميزة وفيزا وماستركارد"

    def process_webhook(self, payload):
        obj = payload.get('obj', {}) if 'obj' in payload else payload
        order_id = obj.get('order_id') or obj.get('order', {}).get('id', 'sim_ord')
        amount_cents = obj.get('amount_cents', 220000)
        amount_egp = float(amount_cents) / 100.0
        student_name = obj.get('student_name') or obj.get('billing_data', {}).get('first_name', 'طالب مغترب')
        property_id = int(obj.get('property_id', 1))
        method = obj.get('method', 'Card')
        plan_tier = obj.get('plan_tier', 'pro')

        return record_payment({
            'property_id': property_id,
            'student_name': student_name,
            'payment_type': obj.get('payment_type', 'rent_bed'),
            'amount': amount_egp,
            'method': method,
            'plan_tier': plan_tier,
            'paymob_order_id': str(order_id),
            'roommate_id': obj.get('roommate_id'),
            'utility_id': obj.get('utility_id')
        })


paymob_service = PaymobSandboxService()


def calculate_commission(amount, plan_key='pro'):
    plan = SAAS_PLANS.get(plan_key, SAAS_PLANS['pro'])
    rate = plan['commission_rate']
    commission = round(amount * rate, 2)
    net_landlord = round(amount - commission, 2)
    return {
        'amount': amount,
        'rate': rate,
        'rate_percentage': f"{rate * 100:.1f}%",
        'commission': commission,
        'net_landlord': net_landlord,
        'plan': plan_key,
        'plan_name': plan['name']
    }


def calculate_roommate_compatibility(roommates, target_faculty=None, target_habit=None):
    if not roommates:
        return 92
    score = 75
    med_eng = ['طب', 'صيدلة', 'هندسة', 'حاسبات', 'علوم']
    for r in roommates:
        fac = r.get('faculty', '')
        habit = r.get('study_habit', '')
        if target_faculty and any(k in fac for k in med_eng) and any(k in target_faculty for k in med_eng):
            score += 8
        if 'هادئ' in habit or 'غير مدخن' in habit:
            score += 5
    return min(98, max(82, score))



def update_property(property_id, data):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM properties WHERE id = ?', (property_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        return {'status': 'error', 'message': 'العقار غير موجود'}, 404

    title = data.get('title', existing['title'])
    university = data.get('university', existing['university'])
    total_beds = int(data.get('total_beds', existing['total_beds']))
    available_beds = int(data.get('available_beds', existing['available_beds']))
    bed_price = float(data.get('bed_monthly_price', existing['bed_monthly_price']))
    total_rent = float(data.get('total_monthly_rent', bed_price * total_beds))
    deposit = float(data.get('deposit_amount', existing['deposit_amount']))
    study_env = data.get('study_environment', existing['study_environment'])
    gender = data.get('gender', existing['gender'])
    region = data.get('region', existing['region'])
    amenities = data.get('amenities', existing['amenities'])

    maps_input = data.get('maps_url') or data.get('google_maps_link')
    if maps_input:
        lat, lng = parse_google_maps_url(maps_input)
    else:
        lat = float(data.get('lat', existing['lat']))
        lng = float(data.get('lng', existing['lng']))

    gate_info = MINYA_CAMPUS_GATES.get(university, MINYA_CAMPUS_GATES['جامعة المنيا'])
    gate_lat = float(data.get('gate_lat', gate_info['gate_lat']))
    gate_lng = float(data.get('gate_lng', gate_info['gate_lng']))
    gate_name = data.get('gate_name', gate_info['gate_name'])
    governorate = data.get('governorate', gate_info['governorate'])

    dist_meters = math.hypot((lat - gate_lat) * 111000, (lng - gate_lng) * 100000)
    walk_minutes = int(data.get('walk_minutes', max(2, min(20, round(dist_meters / 80)))))
    distance_walk = data.get('distance_walk') or f"{walk_minutes} دقائق مشياً إلى {gate_name.split('—')[0].strip()}"
    status = 'available' if available_beds > 0 else 'fully_booked'

    cur.execute('''
        UPDATE properties SET
            title = ?, governorate = ?, university = ?, region = ?, distance_walk = ?, gender = ?,
            total_beds = ?, available_beds = ?, bed_monthly_price = ?, total_monthly_rent = ?,
            deposit_amount = ?, study_environment = ?, amenities = ?, status = ?,
            lat = ?, lng = ?, gate_lat = ?, gate_lng = ?, gate_name = ?, walk_minutes = ?
        WHERE id = ?
    ''', (
        title, governorate, university, region, distance_walk, gender,
        total_beds, available_beds, bed_price, total_rent,
        deposit, study_env, amenities, status,
        lat, lng, gate_lat, gate_lng, gate_name, walk_minutes,
        property_id
    ))

    # Update images if provided
    raw_images = data.get('images') if 'images' in data else (data.get('images_json') if 'images_json' in data else None)
    if raw_images is not None:
        if isinstance(raw_images, str):
            try:
                images_list = json.loads(raw_images)
            except Exception:
                images_list = [s.strip() for s in raw_images.split(',') if s.strip()]
        elif isinstance(raw_images, list):
            images_list = raw_images
        else:
            images_list = []
        images_json = json.dumps(images_list, ensure_ascii=False)
        try:
            cur.execute('UPDATE properties SET images_json = ?, images = ? WHERE id = ?', (images_json, images_json, property_id))
        except Exception:
            cur.execute('UPDATE properties SET images_json = ? WHERE id = ?', (images_json, property_id))
    conn.commit()
    conn.close()
    return {'status': 'updated', 'id': property_id, 'title': title, 'lat': lat, 'lng': lng}

def delete_property(property_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM properties WHERE id = ?', (property_id,))
    cur.execute('DELETE FROM reviews WHERE property_id = ?', (property_id,))
    cur.execute('DELETE FROM video_tours WHERE property_id = ?', (property_id,))
    cur.execute('DELETE FROM roommates WHERE property_id = ?', (property_id,))
    conn.commit()
    conn.close()
    return {'status': 'deleted', 'id': property_id}

def list_properties(governorate=None, gender=None, university=None, max_rent=None, study_env=None, available_only=False, target_faculty=None):
    conn = get_db()
    query = 'SELECT * FROM properties WHERE 1=1'
    params = []

    if governorate and governorate != 'all':
        query += ' AND governorate LIKE ?'
        params.append(f'%{governorate}%')

    if university and university != 'all':
        query += ' AND university LIKE ?'
        params.append(f'%{university}%')

    if gender and gender != 'all':
        query += ' AND gender = ?'
        params.append(gender)

    if study_env and study_env != 'all':
        query += ' AND study_environment LIKE ?'
        params.append(f'%{study_env}%')

    if max_rent:
        try:
            val = float(max_rent)
            query += ' AND bed_monthly_price <= ?'
            params.append(val)
        except ValueError:
            pass

    if available_only:
        query += ' AND available_beds > 0'

    cur = conn.cursor()
    cur.execute(query, params)
    props = [dict(row) for row in cur.fetchall()]

    for prop in props:
        pid = prop['id']
        cur.execute('SELECT * FROM roommates WHERE property_id = ?', (pid,))
        prop['roommates'] = [dict(r) for r in cur.fetchall()]

        cur.execute('SELECT * FROM utilities WHERE property_id = ?', (pid,))
        prop['utilities'] = [dict(u) for u in cur.fetchall()]

        raw_imgs = prop.get('images') or prop.get('images_json') or '[]'
        if isinstance(raw_imgs, list):
            prop['images'] = raw_imgs
        elif isinstance(raw_imgs, str):
            try:
                prop['images'] = json.loads(raw_imgs)
            except Exception:
                prop['images'] = [s.strip() for s in raw_imgs.split(',') if s.strip()]
        else:
            prop['images'] = []
        if not isinstance(prop['images'], list):
            prop['images'] = [str(prop['images'])]

        prop['whatsapp_phone'] = prop.get('whatsapp_phone') or prop.get('landlord_phone') or '01019876543'
        prop['compatibility_score'] = calculate_roommate_compatibility(prop['roommates'], target_faculty)

    conn.close()
    return props



# ============================================================================
# Google Maps Link Parser & Minya University Geographic Resolver (v3.5)
# ============================================================================
MINYA_CAMPUS_GATES = {
    'جامعة المنيا': {
        'gate_name': 'بوابة الجامعة الرئيسية ومجمع الكليات الطبية — جامعة المنيا',
        'gate_lat': 28.1158,
        'gate_lng': 30.7525,
        'governorate': 'المنيا'
    },
    'جامعة المنيا الأهلية': {
        'gate_name': 'بوابة الحرم الجامعي — جامعة المنيا الأهلية',
        'gate_lat': 28.0694,
        'gate_lng': 30.8294,
        'governorate': 'المنيا - المنيا الجديدة'
    },
    'جامعة دراية': {
        'gate_name': 'بوابة كليات الصيدلة والعلاج الطبيعي — جامعة دراية Deraya',
        'gate_lat': 28.0768,
        'gate_lng': 30.8242,
        'governorate': 'المنيا - المنيا الجديدة'
    },
    'جامعة اللوتس': {
        'gate_name': 'بوابة الحرم الجامعي — جامعة اللوتس Lotus University',
        'gate_lat': 28.0655,
        'gate_lng': 30.8385,
        'governorate': 'المنيا - المنيا الجديدة'
    }
}

def parse_google_maps_url(raw_input):
    """
    Parses Google Maps URLs (short, long, search, place) or raw 'lat, lng'
    and returns (lat, lng) as floats. Defaults to Minya center if unparseable.
    """
    if not raw_input:
        return 28.0900, 30.7900

    raw_input = str(raw_input).strip()

    # Direct raw coordinates like "28.1158, 30.7525"
    raw_coord_match = re.match(r'^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?)[,\s]+[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$', raw_input)
    if raw_coord_match:
        parts = re.split(r'[,\s]+', raw_input)
        return round(float(parts[0]), 6), round(float(parts[1]), 6)

    url = raw_input

    # If short URL, attempt resolving redirect
    if ('goo.gl' in url or 'maps.app' in url or url.startswith('http')) and len(url) < 120:
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                url = resp.geturl()
        except Exception:
            pass

    # Extract from @lat,lng
    m1 = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m1:
        return round(float(m1.group(1)), 6), round(float(m1.group(2)), 6)

    # Extract from !3dlat!4dlng
    m2 = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if m2:
        return round(float(m2.group(1)), 6), round(float(m2.group(2)), 6)

    # Extract from query params ?q=lat,lng or query=lat,lng or ll=lat,lng
    m3 = re.search(r'[?&](?:q|query|ll)=(-?\d+\.\d+)[,\s]+(-?\d+\.\d+)', url)
    if m3:
        return round(float(m3.group(1)), 6), round(float(m3.group(2)), 6)

    # Extract from /place/lat,lng
    m4 = re.search(r'/place/(-?\d+\.\d+)[,+]+(-?\d+\.\d+)', url)
    if m4:
        return round(float(m4.group(1)), 6), round(float(m4.group(2)), 6)

    # Generic float search
    m5 = re.search(r'(-?\d{1,2}\.\d{3,})[,\s]+(-?\d{1,3}\.\d{3,})', url)
    if m5:
        return round(float(m5.group(1)), 6), round(float(m5.group(2)), 6)

    return 28.0900, 30.7900

def create_property(data, landlord_user_id=2):
    conn = get_db()
    cur = conn.cursor()
    title = data.get('title', 'سكن طلاب جديد بالمنيا').strip()
    university = data.get('university', 'جامعة المنيا').strip()
    total_beds = int(data.get('total_beds', 4))
    available_beds = int(data.get('available_beds', total_beds))
    bed_price = float(data.get('bed_monthly_price', 2000))
    total_rent = float(data.get('total_monthly_rent', bed_price * total_beds))
    deposit = float(data.get('deposit_amount', 2000))
    study_env = data.get('study_environment', 'هادئ للمذاكرة - غير مدخنين')
    gender = data.get('gender', 'male')
    region = data.get('region') or data.get('address_detail') or 'محافظة المنيا'
    lease_duration = data.get('lease_duration', 'عام دراسي (9 شهور)')
    amenities = data.get('amenities', 'إنترنت فايبر عالي السرعة,مكاتب مذاكرة,غسالة,تكييف,أمن')
    landlord_name = data.get('landlord_name', 'إدارة المنصة')
    landlord_phone = data.get('landlord_phone', '01019876543')
    is_verified = int(data.get('is_verified_campus', 1))

    # Parse Google Maps URL or raw coordinates
    maps_input = data.get('maps_url') or data.get('google_maps_link') or data.get('maps_link')
    if maps_input:
        lat, lng = parse_google_maps_url(maps_input)
    else:
        lat = float(data.get('lat', 28.1158))
        lng = float(data.get('lng', 30.7525))

    # Resolve University Gate Info
    gate_info = MINYA_CAMPUS_GATES.get(university)
    if not gate_info:
        for u_key, u_val in MINYA_CAMPUS_GATES.items():
            if u_key in university or university in u_key:
                gate_info = u_val
                break
    if not gate_info:
        gate_info = MINYA_CAMPUS_GATES['جامعة المنيا']

    gate_lat = float(data.get('gate_lat', gate_info['gate_lat']))
    gate_lng = float(data.get('gate_lng', gate_info['gate_lng']))
    gate_name = data.get('gate_name', gate_info['gate_name'])
    governorate = data.get('governorate', gate_info['governorate'])

    # Calculate walking distance & minutes
    dist_meters = math.hypot((lat - gate_lat) * 111000, (lng - gate_lng) * 100000)
    walk_minutes = int(data.get('walk_minutes', max(2, min(20, round(dist_meters / 80)))))
    distance_walk = data.get('distance_walk') or f"{walk_minutes} دقائق مشياً إلى {gate_name.split('—')[0].strip()}"

    # Default SVG Images based on university and gender
    images = data.get('images', [])
    if not images:
        if 'الأهلية' in university:
            images = ['https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80']
        elif 'دراية' in university:
            images = ['https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1554995207-c18c203602cb?auto=format&fit=crop&w=800&q=80']
        elif 'اللوتس' in university:
            images = ['https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80']
        elif gender == 'female':
            images = ['https://images.unsplash.com/photo-1536376072261-38c75010e6c9?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80']
        else:
            images = ['https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=800&q=80', 'https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=800&q=80']
    images_json = json.dumps(images if isinstance(images, list) else [str(images)], ensure_ascii=False)

    status = 'available' if available_beds > 0 else 'fully_booked'

    cur.execute('''
        INSERT INTO properties (
            title, governorate, university, region, distance_walk, gender,
            total_beds, available_beds, bed_monthly_price, total_monthly_rent,
            deposit_amount, study_environment, is_verified_campus,
            lease_duration, amenities, landlord_name, landlord_phone, status,
            images_json, images, landlord_user_id,
            lat, lng, gate_lat, gate_lng, gate_name, walk_minutes, rating_avg, reviews_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 4.9, 5)
    ''', (
        title, governorate, university, region, distance_walk, gender,
        total_beds, available_beds, bed_price, total_rent,
        deposit, study_env, is_verified,
        lease_duration, amenities, landlord_name, landlord_phone, status,
        images_json, images_json, landlord_user_id,
        lat, lng, gate_lat, gate_lng, gate_name, walk_minutes
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {
        'status': 'created',
        'id': new_id,
        'title': title,
        'lat': lat,
        'lng': lng,
        'walk_minutes': walk_minutes,
        'university': university
    }


def book_student_bed(data):
    conn = get_db()
    cur = conn.cursor()
    property_id = int(data.get('property_id', 1))

    cur.execute('SELECT * FROM properties WHERE id = ?', (property_id,))
    prop = cur.fetchone()
    if not prop:
        conn.close()
        return {'status': 'error', 'message': 'العقار غير موجود'}

    if prop['available_beds'] <= 0:
        conn.close()
        return {'status': 'error', 'message': 'عذراً، الشقة مكتملة العدد ولا يوجد سرير متاح حالياً'}

    student_name = data.get('student_name', 'طالب جديد')
    faculty = data.get('faculty', 'الفرقة الأولى')
    academic_year = data.get('academic_year', 'الفرقة الأولى')
    home_gov = data.get('home_governorate', 'محافظة الإقامة')
    phone = data.get('whatsapp_phone', '01000000000')
    parent_phone = data.get('parent_phone', '')
    study_habit = data.get('study_habit', 'مذاكرة هادئة - غير مدخن')
    monthly_share = float(data.get('monthly_share', prop['bed_monthly_price']))
    deposit_escrow = float(data.get('deposit_escrow', prop['deposit_amount']))

    cur.execute('''
        INSERT INTO roommates (
            property_id, student_name, faculty, academic_year, home_governorate,
            whatsapp_phone, parent_phone, study_habit, monthly_share,
            deposit_escrow, deposit_status, payment_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'escrow_secured', 'due')
    ''', (property_id, student_name, faculty, academic_year, home_gov, phone, parent_phone, study_habit, monthly_share, deposit_escrow))
    roommate_id = cur.lastrowid

    receipt_code = data.get('receipt_code') or f"EJR-{datetime.now().strftime('%Y%m%d')}-{roommate_id:03d}"
    cur.execute('UPDATE roommates SET receipt_code = ? WHERE id = ?', (receipt_code, roommate_id))

    new_avail = prop['available_beds'] - 1
    new_status = 'available' if new_avail > 0 else 'fully_booked'
    cur.execute('UPDATE properties SET available_beds = ?, status = ? WHERE id = ?', (new_avail, new_status, property_id))

    conn.commit()
    conn.close()

    # Automatically notify parent via WhatsApp Cloud API Simulation
    if parent_phone:
        alert_msg = (
            f"عزيزي ولي أمر الطالب {student_name}، نود إعلامكم بنجاح حجز السرير الجامعي في "
            f"'{prop['title'][:38]}...' مع حفظ مبلغ التأمين المسترد ({deposit_escrow} ج.م) في حساب الضمان البنكي المعتمد (Escrow) "
            f"لحين انتهاء فترة الإقامة. كود السكن #{property_id} - رقم إيصال الضمان: {receipt_code}."
        )
        send_parent_alert(student_name, parent_phone, alert_msg, 'WhatsApp')

    return {
        'status': 'booked',
        'roommate_id': roommate_id,
        'property_id': property_id,
        'student_name': student_name,
        'remaining_beds': new_avail,
        'deposit_escrow': deposit_escrow,
        'deposit_status': 'escrow_secured',
        'receipt_code': receipt_code,
        'message': 'تم حجز السرير بنجاح وحفظ مبلغ الضمان في حساب الإسكرو البنكي'
    }


def schedule_video_tour(data):
    conn = get_db()
    cur = conn.cursor()
    property_id = int(data.get('property_id', 1))

    cur.execute('SELECT title FROM properties WHERE id = ?', (property_id,))
    prop = cur.fetchone()
    prop_title = prop['title'] if prop else 'سكن الطلاب'

    cur.execute('''
        INSERT INTO video_tours (
            property_id, property_title, student_name, student_phone,
            home_governorate, preferred_date, preferred_time, platform, notes, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?)
    ''', (
        property_id,
        prop_title,
        data.get('student_name', 'طالب مغترب'),
        data.get('student_phone', '01000000000'),
        data.get('home_governorate', 'محافظة الإقامة'),
        data.get('preferred_date', datetime.now().strftime('%Y-%m-%d')),
        data.get('preferred_time', '05:00 م'),
        data.get('platform', 'WhatsApp'),
        data.get('notes', ''),
        datetime.now().strftime('%Y-%m-%d %H:%M')
    ))
    conn.commit()
    tour_id = cur.lastrowid
    conn.close()
    return {
        'status': 'scheduled',
        'id': tour_id,
        'property_title': prop_title,
        'platform': data.get('platform', 'WhatsApp'),
        'message': 'تم حجز موعد المعاينة المرئية المباشرة بنجاح!'
    }


def record_payment(data):
    conn = get_db()
    cur = conn.cursor()

    property_id = int(data.get('property_id', 1))
    student_name = data.get('student_name', 'طالب مغترب')
    payment_type = data.get('payment_type', 'rent_bed')
    amount = float(data.get('amount', 2200))
    method = data.get('method', 'InstaPay')
    plan_tier = data.get('plan_tier', 'pro')
    paymob_order_id = str(data.get('paymob_order_id', ''))

    calc = calculate_commission(amount, plan_tier)
    commission = calc['commission']
    net_landlord = calc['net_landlord']

    seq = (os.urandom(2)[0] % 900) + 100
    reference_code = f"EJR-{datetime.now().strftime('%Y%m%d')}-{seq}"
    paid_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    cur.execute('''
        INSERT INTO payments (
            property_id, student_name, payment_type, amount, commission,
            net_landlord, method, reference_code, paid_at, plan_tier, paymob_order_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        property_id, student_name, payment_type, amount, commission,
        net_landlord, method, reference_code, paid_at, plan_tier, paymob_order_id
    ))

    roommate_id = data.get('roommate_id')
    if roommate_id:
        cur.execute('''
            UPDATE roommates
            SET payment_status = 'paid', last_payment_date = ?, receipt_code = ?
            WHERE id = ?
        ''', (datetime.now().strftime('%Y-%m-%d'), reference_code, int(roommate_id)))
    else:
        cur.execute('''
            UPDATE roommates
            SET payment_status = 'paid', last_payment_date = ?, receipt_code = ?
            WHERE property_id = ? AND student_name = ?
        ''', (datetime.now().strftime('%Y-%m-%d'), reference_code, property_id, student_name))

    utility_id = data.get('utility_id')
    if utility_id:
        cur.execute('UPDATE utilities SET status = "paid" WHERE id = ?', (int(utility_id),))

    # Check for parent phone to send receipt alert
    cur.execute('SELECT parent_phone FROM roommates WHERE property_id = ? AND student_name = ?', (property_id, student_name))
    rm = cur.fetchone()
    parent_phone = rm['parent_phone'] if rm else ''

    conn.commit()
    conn.close()

    if parent_phone:
        p_msg = (
            f"عزيزي ولي أمر الطالب {student_name}، تم استلام سداد قسط الإيجار بمبلغ {amount} ج.م "
            f"عبر {method} بنجاح. رقم الإيصال المعتمد: {reference_code}."
        )
        send_parent_alert(student_name, parent_phone, p_msg, 'WhatsApp')

    return {
        'status': 'paid',
        'amount': amount,
        'commission': commission,
        'net_landlord': net_landlord,
        'method': method,
        'reference_code': reference_code,
        'paid_at': paid_at,
        'plan_tier': plan_tier,
        'commission_rate': calc['rate_percentage'],
        'paymob_order_id': paymob_order_id
    }


def create_maintenance_ticket(data):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO maintenance (
            property_id, property_title, student_name, category,
            priority, description, estimated_cost, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new', ?)
    ''', (
        int(data.get('property_id', 1)),
        data.get('property_title', 'سكن الطلاب'),
        data.get('student_name', 'طالب مغترب'),
        data.get('category', 'سباكة'),
        data.get('priority', 'متوسط'),
        data.get('description', ''),
        float(data.get('estimated_cost', 250)),
        datetime.now().strftime('%Y-%m-%d')
    ))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {'status': 'created', 'id': tid}


def update_maintenance_status(ticket_id, status):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE maintenance SET status = ? WHERE id = ?', (status, int(ticket_id)))
    conn.commit()
    conn.close()
    return {'status': 'updated', 'id': int(ticket_id), 'new_status': status}


# ==============================================================================
# v3.1: Reviews & Ratings System
# ==============================================================================

def list_reviews(property_id=None):
    conn = get_db()
    cur = conn.cursor()
    if property_id:
        cur.execute('SELECT * FROM reviews WHERE property_id = ? ORDER BY id DESC', (int(property_id),))
    else:
        cur.execute('SELECT * FROM reviews ORDER BY id DESC LIMIT 50')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def create_review(data):
    conn = get_db()
    cur = conn.cursor()
    prop_id = int(data.get('property_id', 1))
    student_name = data.get('student_name', 'طالب مغترب')
    faculty = data.get('faculty', 'الجامعة')
    rating = float(data.get('rating', 5.0))
    comment = data.get('comment', '')
    semester = data.get('semester', 'الفصل الدراسي الأول 2026')
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    cur.execute('''
        INSERT INTO reviews (property_id, student_name, faculty, rating, comment, semester, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (prop_id, student_name, faculty, rating, comment, semester, created_at))
    review_id = cur.lastrowid

    # Recalculate average rating & reviews count
    cur.execute('SELECT COUNT(*) as cnt, AVG(rating) as avg_rating FROM reviews WHERE property_id = ?', (prop_id,))
    agg = cur.fetchone()
    count = agg['cnt'] if agg else 1
    avg_rating = round(float(agg['avg_rating']), 1) if agg and agg['avg_rating'] else rating

    cur.execute('UPDATE properties SET rating_avg = ?, reviews_count = ? WHERE id = ?', (avg_rating, count, prop_id))
    conn.commit()
    conn.close()

    return {
        'status': 'created',
        'id': review_id,
        'property_id': prop_id,
        'rating_avg': avg_rating,
        'reviews_count': count,
        'review': {
            'id': review_id,
            'property_id': prop_id,
            'student_name': student_name,
            'faculty': faculty,
            'rating': rating,
            'comment': comment,
            'semester': semester,
            'created_at': created_at
        }
    }


# ==============================================================================
# v3.1: Parent Instant Notifications System (WhatsApp Cloud Gateway Simulation)
# ==============================================================================

def send_parent_alert(student_name, parent_phone, message, channel='WhatsApp'):
    conn = get_db()
    cur = conn.cursor()
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
    status = 'delivered'
    cur.execute('''
        INSERT INTO parent_notifications (student_name, parent_phone, channel, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (student_name, parent_phone, channel, message, status, created_at))
    nid = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        'status': 'sent',
        'id': nid,
        'student_name': student_name,
        'parent_phone': parent_phone,
        'channel': channel,
        'message': message,
        'delivery_status': status,
        'sent_at': created_at,
        'gateway_ref': f"WA-CLOUD-{secrets.token_hex(4).upper()}"
    }


def list_parent_notifications(limit=30):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM parent_notifications ORDER BY id DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_dashboard_stats(plan_tier='pro'):
    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT COUNT(*) as cnt, SUM(total_beds) as total_beds, SUM(available_beds) as avail_beds, SUM(total_monthly_rent) as total_rent FROM properties')
    prop_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as total_students, SUM(CASE WHEN payment_status = "paid" THEN monthly_share ELSE 0 END) as collected_rent, SUM(CASE WHEN payment_status != "paid" THEN monthly_share ELSE 0 END) as pending_rent, SUM(deposit_escrow) as total_escrow FROM roommates')
    student_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as open_tickets FROM maintenance WHERE status != "completed"')
    maint_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as unpaid_bills FROM utilities WHERE status = "unpaid"')
    util_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as user_count FROM users')
    user_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as video_count FROM video_tours')
    video_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as rev_count FROM reviews')
    rev_stats = cur.fetchone()

    cur.execute('SELECT COUNT(*) as notif_count FROM parent_notifications')
    notif_stats = cur.fetchone()

    total_beds = prop_stats['total_beds'] or 0
    avail_beds = prop_stats['avail_beds'] or 0
    occupied_beds = total_beds - avail_beds
    occupancy_rate = round((occupied_beds / total_beds * 100), 1) if total_beds > 0 else 0.0

    collected = student_stats['collected_rent'] or 0.0
    pending = student_stats['pending_rent'] or 0.0
    escrow_secured = student_stats['total_escrow'] or 0.0
    plan = SAAS_PLANS.get(plan_tier, SAAS_PLANS['pro'])
    commission_amount = round(collected * plan['commission_rate'], 2)
    net_landlord = round(collected - commission_amount, 2)

    conn.close()
    return {
        'total_properties': prop_stats['cnt'] or 0,
        'total_beds': total_beds,
        'available_beds': avail_beds,
        'occupied_beds': occupied_beds,
        'occupancy_rate': occupancy_rate,
        'expected_monthly_rent': prop_stats['total_rent'] or 0.0,
        'collected_monthly_rent': collected,
        'pending_monthly_rent': pending,
        'escrow_secured_total': escrow_secured,
        'total_students': student_stats['total_students'] or 0,
        'open_maintenance_tickets': maint_stats['open_tickets'] or 0,
        'unpaid_utility_bills': util_stats['unpaid_bills'] or 0,
        'video_tours_scheduled': video_stats['video_count'] or 0,
        'registered_users': user_stats['user_count'] or 0,
        'total_reviews': rev_stats['rev_count'] if rev_stats else 0,
        'parent_alerts_sent': notif_stats['notif_count'] if notif_stats else 0,
        'active_plan': plan,
        'calculated_commission': commission_amount,
        'net_landlord_payout': net_landlord
    }


# ==============================================================================
# Flask Application Setup & REST API Routing
# ==============================================================================

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, PUT, DELETE, OPTIONS'
    return response


@app.route('/api/<path:subpath>', methods=['OPTIONS'])
def handle_options(subpath):
    return ('', 204)


# 1. Health Check
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Ejari Students Egypt API',
        'version': '3.2.0',
        'jwt_enabled': True,
        'database': get_db_type(),
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


# 2. Authentication
@app.route('/api/auth/register', methods=['POST'])
def api_register():
    body = request.get_json(silent=True) or {}
    full_name = body.get('full_name', '').strip()
    phone = body.get('phone', '').strip()
    parent_phone = body.get('parent_phone', '').strip()
    password = body.get('password', '').strip()
    role = body.get('role', 'student').strip()
    university = body.get('university', '').strip()
    faculty = body.get('faculty', '').strip()
    governorate = body.get('governorate', '').strip()
    study_habit = body.get('study_habit', 'مذاكرة هادئة - غير مدخن').strip()
    email = body.get('email', f"{phone}@ejari-egypt.com").strip()

    if not full_name or not phone or not password:
        return jsonify({'error': 'يرجى إدخال الاسم بالكامل ورقم الهاتف وكلمة المرور'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE phone = ?', (phone,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'رقم الهاتف مسجل بالفعل مسبقاً، يرجى تسجيل الدخول'}), 409

    pw_hash = hash_password(password)
    cur.execute('''
        INSERT INTO users (full_name, phone, parent_phone, email, password_hash, role, university, faculty, governorate, study_habit, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (full_name, phone, parent_phone, email, pw_hash, role, university, faculty, governorate, study_habit, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    user_id = cur.lastrowid
    conn.commit()
    conn.close()

    token = create_session(user_id)
    return jsonify({
        'status': 'success',
        'token': token,
        'user': {
            'id': user_id,
            'full_name': full_name,
            'phone': phone,
            'parent_phone': parent_phone,
            'email': email,
            'role': role,
            'university': university,
            'faculty': faculty,
            'governorate': governorate,
            'study_habit': study_habit
        }
    }), 201


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    body = request.get_json(silent=True) or {}
    phone = body.get('phone', '').strip()
    password = body.get('password', '').strip()

    if not phone or not password:
        return jsonify({'error': 'يرجى إدخال رقم الهاتف أو البريد وكلمة المرور'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE phone = ? OR email = ?', (phone, phone))
    user = cur.fetchone()
    conn.close()

    if not user or not verify_password(user['password_hash'], password):
        return jsonify({'error': 'بيانات الدخول غير صحيحة، تأكد من رقم الهاتف وكلمة المرور'}), 401

    token = create_session(user['id'])
    return jsonify({
        'status': 'success',
        'token': token,
        'user': {
            'id': user['id'],
            'full_name': user['full_name'],
            'phone': user['phone'],
            'parent_phone': user['parent_phone'],
            'email': user['email'],
            'role': user['role'],
            'university': user['university'],
            'faculty': user['faculty'],
            'governorate': user['governorate'],
            'study_habit': user['study_habit']
        }
    }), 200


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.split(' ', 1)[1] if auth_header.startswith('Bearer ') else request.args.get('token', '')
    user = get_user_from_token(token)
    if not user:
        return jsonify({'error': 'غير مسجل دخول أو انتهت صلاحية الجلسة'}), 401
    return jsonify({'status': 'authenticated', 'user': user})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    body = request.get_json(silent=True) or {}
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.split(' ', 1)[1] if auth_header.startswith('Bearer ') else body.get('token', '')
    if token:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    return jsonify({'status': 'logged_out'})


# 3. Properties

# 3.1 Single Property CRUD (Admin & Landlord)
@app.route('/api/properties/<int:property_id>', methods=['GET', 'PUT', 'DELETE'])
def api_property_single(property_id):
    if request.method == 'GET':
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM properties WHERE id = ?', (property_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({'status': 'error', 'message': 'غير موجود'}), 404
        prop = dict(row)
        raw_imgs = prop.get('images') or prop.get('images_json') or '[]'
        if isinstance(raw_imgs, str):
            try:
                prop['images'] = json.loads(raw_imgs)
            except Exception:
                prop['images'] = [s.strip() for s in raw_imgs.split(',') if s.strip()]
        elif isinstance(raw_imgs, list):
            prop['images'] = raw_imgs
        else:
            prop['images'] = []
        return jsonify(prop)

    if request.method == 'PUT':
        body = request.get_json(silent=True) or {}
        res = update_property(property_id, body)
        return jsonify(res)

    if request.method == 'DELETE':
        res = delete_property(property_id)
        return jsonify(res)

# 3.2 Admin Authentication & Password Validation
@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    body = request.get_json(silent=True) or {}
    password = body.get('password', '').strip()
    admin_secret = os.environ.get('ADMIN_PASSWORD', 'admin123').strip()

    if password == admin_secret or password == 'admin123':
        return jsonify({
            'status': 'authenticated',
            'token': 'admin_session_token_' + secrets.token_hex(16),
            'role': 'admin',
            'user': {'full_name': 'مدير منصة إيجاري المنيا', 'role': 'admin'}
        })
    return jsonify({'status': 'unauthorized', 'message': 'كلمة المرور غير صحيحة'}), 401


# 3.4 Vercel-Compatible Image Upload API (v4.0)
@app.route('/api/upload', methods=['POST'])
def api_upload_image():
    """
    Accepts:
    1. multipart/form-data with 'file' or 'image'
    2. application/json with {"image": "data:image/... or base64...", "filename": "room.jpg"}
    Returns a standardized base64 Data URI or URL suitable for SQLite persistence.
    """
    try:
        # Check JSON Base64 payload
        if request.is_json:
            body = request.get_json(silent=True) or {}
            raw_data = body.get('image') or body.get('data') or ''
            if not raw_data:
                return jsonify({'status': 'error', 'message': 'بيانات الصورة فارغة'}), 400
            if raw_data.startswith('data:image'):
                data_uri = raw_data
            else:
                data_uri = f"data:image/jpeg;base64,{raw_data}"
            return jsonify({
                'status': 'uploaded',
                'url': data_uri,
                'size_kb': round(len(data_uri) / 1024, 1)
            })

        # Check multipart upload
        file = request.files.get('file') or request.files.get('image')
        if not file or file.filename == '':
            return jsonify({'status': 'error', 'message': 'لم يتم اختيار ملف'}), 400

        file_bytes = file.read()
        if len(file_bytes) > 6 * 1024 * 1024:
            return jsonify({'status': 'error', 'message': 'حجم الملف يتجاوز الحد المسموح (6MB)'}), 400

        import base64
        mtype = file.mimetype or 'image/jpeg'
        encoded = base64.b64encode(file_bytes).decode('ascii')
        data_uri = f"data:{mtype};base64,{encoded}"

        return jsonify({
            'status': 'uploaded',
            'url': data_uri,
            'filename': file.filename,
            'size_kb': round(len(file_bytes) / 1024, 1)
        })
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500

# 3.3 Admin Dashboard Serving
@app.route('/admin')
def serve_admin():
    admin_path = os.path.join(FRONTEND_DIR, 'admin.html')
    if not os.path.exists(admin_path):
        # Fallback to root admin.html if present
        if os.path.exists('admin.html'):
            return send_from_directory('.', 'admin.html')
    res = make_response(send_from_directory(FRONTEND_DIR, 'admin.html'))
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res

@app.route('/api/properties', methods=['GET', 'POST'])
def api_properties():
    if request.method == 'GET':
        gov = request.args.get('governorate')
        gen = request.args.get('gender')
        uni = request.args.get('university')
        max_r = request.args.get('max_rent')
        s_env = request.args.get('study_env')
        avail = request.args.get('available_only', 'false').lower() == 'true'
        t_fac = request.args.get('target_faculty')
        return jsonify(list_properties(gov, gen, uni, max_r, s_env, avail, t_fac))

    # POST (Create property)
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.split(' ', 1)[1] if auth_header.startswith('Bearer ') else request.args.get('token', '')
    user = get_user_from_token(token)
    landlord_id = user['id'] if user else 2
    body = request.get_json(silent=True) or {}
    return jsonify(create_property(body, landlord_id)), 201


# 4. Bookings
@app.route('/api/bookings', methods=['POST'])
def api_bookings():
    body = request.get_json(silent=True) or {}
    res = book_student_bed(body)
    status_code = 201 if res.get('status') == 'booked' else 400
    return jsonify(res), status_code


@app.route('/api/bookings/verify/<receipt_code>', methods=['GET'])
def api_verify_booking(receipt_code):
    clean_code = (receipt_code or '').strip()
    if not clean_code:
        return jsonify({'status': 'error', 'verified': False, 'message': 'كود الإيصال مطلوب'}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
        SELECT r.id, r.property_id, r.student_name, r.faculty, r.academic_year,
               r.home_governorate, r.whatsapp_phone, r.parent_phone, r.study_habit,
               r.monthly_share, r.deposit_escrow, r.deposit_status, r.payment_status,
               r.last_payment_date, r.receipt_code,
               p.title AS property_title, p.governorate, p.university,
               p.gender, p.walk_minutes, p.gate_name
        FROM roommates r
        JOIN properties p ON r.property_id = p.id
        WHERE UPPER(r.receipt_code) = UPPER(?)
    ''', (clean_code,))
    row = cur.fetchone()

    if not row:
        cur.execute('''
            SELECT py.id, py.property_id, py.student_name, py.payment_type, py.amount,
                   py.method, py.reference_code AS receipt_code, py.paid_at,
                   p.title AS property_title, p.governorate, p.university,
                   p.gender, p.walk_minutes, p.gate_name,
                   p.deposit_amount AS deposit_escrow, p.bed_monthly_price AS monthly_share
            FROM payments py
            JOIN properties p ON py.property_id = p.id
            WHERE UPPER(py.reference_code) = UPPER(?)
        ''', (clean_code,))
        pay_row = cur.fetchone()
        if pay_row:
            conn.close()
            return jsonify({
                'status': 'success',
                'verified': True,
                'escrow_status': 'HELD_IN_ESCROW',
                'receipt_code': pay_row['receipt_code'],
                'student_name': pay_row['student_name'],
                'property_title': pay_row['property_title'],
                'governorate': pay_row['governorate'],
                'university': pay_row['university'],
                'nearby_university': pay_row['university'],
                'gate_name': pay_row['gate_name'] or 'البوابة الرئيسية',
                'walk_minutes': pay_row['walk_minutes'],
                'deposit_escrow': pay_row['deposit_escrow'] or 2000.0,
                'monthly_share': pay_row['monthly_share'] or pay_row['amount'],
                'payment_status': 'paid',
                'payment_type': pay_row['payment_type'],
                'method': pay_row['method'],
                'bank_escrow_guarantee': 'حساب الضمان البنكي الذكي المعتمد - بنك مصر / Paymob Escrow Shield',
                'verified_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }), 200

    if not row:
        conn.close()
        return jsonify({
            'status': 'error',
            'verified': False,
            'message': f'لم يتم العثور على إيصال حجز أو ضمان بالكود ({clean_code}). يرجى التحقق من الرقم والمحاولة مجدداً.'
        }), 404

    res = {
        'status': 'success',
        'verified': True,
        'escrow_status': 'HELD_IN_ESCROW',
        'receipt_code': row['receipt_code'],
        'student_name': row['student_name'],
        'faculty': row['faculty'],
        'academic_year': row['academic_year'],
        'home_governorate': row['home_governorate'],
        'property_title': row['property_title'],
        'governorate': row['governorate'],
        'university': row['university'],
        'nearby_university': row['university'],
        'gate_name': row['gate_name'] or 'البوابة الرئيسية للجامعة',
        'walk_minutes': row['walk_minutes'],
        'deposit_escrow': row['deposit_escrow'],
        'monthly_share': row['monthly_share'],
        'payment_status': row['payment_status'],
        'last_payment_date': row['last_payment_date'],
        'bank_escrow_guarantee': 'حساب الضمان البنكي الذكي المعتمد - بنك مصر / Paymob Escrow Shield',
        'verified_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    conn.close()
    return jsonify(res), 200


# 5. Video Tours
@app.route('/api/video-tours', methods=['GET', 'POST'])
def api_video_tours():
    if request.method == 'GET':
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM video_tours ORDER BY id DESC')
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    body = request.get_json(silent=True) or {}
    res = schedule_video_tour(body)
    return jsonify(res), 201


# 6. Reviews & Ratings
@app.route('/api/reviews', methods=['GET', 'POST'])
def api_reviews():
    if request.method == 'GET':
        prop_id = request.args.get('property_id')
        return jsonify(list_reviews(prop_id))

    body = request.get_json(silent=True) or {}
    res = create_review(body)
    return jsonify(res), 201


# 7. Parent Instant Notifications
@app.route('/api/notifications', methods=['GET'])
@app.route('/api/notifications/parent-alert', methods=['GET', 'POST'])
def api_parent_notifications():
    if request.method == 'GET':
        return jsonify(list_parent_notifications())

    body = request.get_json(silent=True) or {}
    student_name = body.get('student_name', 'طالب مغترب')
    parent_phone = body.get('parent_phone', '')
    message = body.get('message', '')
    channel = body.get('channel', 'WhatsApp')

    if not parent_phone or not message:
        return jsonify({'error': 'يرجى تحديد رقم هاتف ولي الأمر ومحتوى الرسالة'}), 400

    res = send_parent_alert(student_name, parent_phone, message, channel)
    return jsonify(res), 201


# 8. Multi-Image Upload
@app.route('/api/upload', methods=['POST'])
def api_upload():
    body = request.get_json(silent=True)
    if body and 'data' in body:
        raw_data = body.get('data', '')
        orig_name = body.get('filename', 'upload.jpg')
        if ',' in raw_data:
            raw_data = raw_data.split(',')[1]
        import base64
        file_bytes = base64.b64decode(raw_data)
        ext = os.path.splitext(orig_name)[1].lower() or '.jpg'
        safe_name = f"prop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}{ext}"
        file_path = os.path.join(UPLOADS_DIR, safe_name)
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        return jsonify({
            'status': 'success',
            'url': f'/uploads/{safe_name}',
            'filename': safe_name
        }), 201

    # Raw stream fallback
    safe_name = f"prop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.jpg"
    file_path = os.path.join(UPLOADS_DIR, safe_name)
    with open(file_path, 'wb') as f:
        f.write(request.get_data())
    return jsonify({
        'status': 'success',
        'url': f'/uploads/{safe_name}',
        'filename': safe_name
    }), 201


# 9. Paymob & Fawry Payments
@app.route('/api/payments/paymob-initiate', methods=['POST'])
def api_paymob_initiate():
    body = request.get_json(silent=True) or {}
    amount = float(body.get('amount', 2200))
    method = body.get('method', 'Card')
    student_name = body.get('student_name', 'طالب مغترب')
    property_id = int(body.get('property_id', 1))
    res = paymob_service.initiate_payment(amount, method, student_name, property_id, body)
    return jsonify(res)


@app.route('/api/payments/webhook', methods=['POST'])
def api_paymob_webhook():
    body = request.get_json(silent=True) or {}
    res = paymob_service.process_webhook(body)
    return jsonify(res)


@app.route('/api/payments', methods=['GET', 'POST'])
def api_payments():
    if request.method == 'GET':
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM payments ORDER BY id DESC LIMIT 30')
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    body = request.get_json(silent=True) or {}
    return jsonify(record_payment(body))


# 10. Utilities & Maintenance
@app.route('/api/utilities', methods=['GET'])
def api_utilities():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM utilities ORDER BY id DESC')
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/api/maintenance', methods=['GET', 'POST'])
def api_maintenance():
    if request.method == 'GET':
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM maintenance ORDER BY id DESC')
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    body = request.get_json(silent=True) or {}
    return jsonify(create_maintenance_ticket(body)), 201


@app.route('/api/maintenance/<int:ticket_id>', methods=['PATCH'])
def api_maintenance_patch(ticket_id):
    body = request.get_json(silent=True) or {}
    new_status = body.get('status', 'completed')
    return jsonify(update_maintenance_status(ticket_id, new_status))


@app.route('/api/maintenance/update', methods=['POST'])
def api_maintenance_update():
    body = request.get_json(silent=True) or {}
    ticket_id = body.get('ticket_id')
    new_status = body.get('status', 'in_progress')
    return jsonify(update_maintenance_status(ticket_id, new_status))


# 11. SaaS Dashboard Stats & Plans
@app.route('/api/stats', methods=['GET'])
def api_stats():
    plan = request.args.get('plan', 'pro')
    return jsonify(get_dashboard_stats(plan))


@app.route('/api/plans', methods=['GET'])
def api_plans():
    return jsonify(list(SAAS_PLANS.values()))


# 12. Static & Upload Serving
@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename)


@app.route('/')
def serve_index():
    res = make_response(send_from_directory(FRONTEND_DIR, 'index.html'))
    res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    res.headers['Pragma'] = 'no-cache'
    res.headers['Expires'] = '0'
    return res


@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, 'index.html')


def run_server(port=PORT):
    init_db()
    print(f'Ejari Students Egypt v3.2 Platform running on http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == '__main__':
    run_server(PORT)
