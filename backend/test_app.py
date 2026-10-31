import os
import unittest
import sys
import gc

sys.path.insert(0, os.path.dirname(__file__))
import app as ejari_students_app


class EjariStudentsV31TestCase(unittest.TestCase):
    def setUp(self):
        self.test_db = os.path.join(os.path.dirname(__file__), 'test_ejari_students_v31.db')
        ejari_students_app.DB_PATH = self.test_db
        gc.collect()
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass
        ejari_students_app.init_db()

    def tearDown(self):
        gc.collect()
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # v3.0 Retained Test Cases
    # --------------------------------------------------------------------------

    def test_role_based_auth_with_parent_and_habits(self):
        """Test registration capturing parent phone, faculty, and study habits with password hashing."""
        conn = ejari_students_app.get_db()
        cur = conn.cursor()
        phone = "01055566677"
        parent_phone = "01099988811"
        password = "studentSecretPass123"
        pw_hash = ejari_students_app.hash_password(password)

        cur.execute('''
            INSERT INTO users (full_name, phone, parent_phone, email, password_hash, role, university, faculty, governorate, study_habit, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-10-30')
        ''', ('يوسف المنشاوي', phone, parent_phone, 'youssef@student.eg', pw_hash, 'student', 'جامعة الإسكندرية', 'كلية الطب البشري', 'سوهاج', 'مذاكرة هادئة - غير مدخن'))
        user_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Verify password validation
        self.assertTrue(ejari_students_app.verify_password(pw_hash, password))
        self.assertFalse(ejari_students_app.verify_password(pw_hash, 'wrong_pass'))

        # Create session & verify retrieval
        token = ejari_students_app.create_session(user_id)
        user = ejari_students_app.get_user_from_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user['full_name'], 'يوسف المنشاوي')
        self.assertEqual(user['parent_phone'], parent_phone)
        self.assertEqual(user['faculty'], 'كلية الطب البشري')
        self.assertEqual(user['study_habit'], 'مذاكرة هادئة - غير مدخن')

        # Check default demo accounts
        conn = ejari_students_app.get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE role = 'student' AND phone = '01012345678'")
        demo_student = cur.fetchone()
        self.assertIsNotNone(demo_student)
        self.assertTrue(ejari_students_app.verify_password(demo_student['password_hash'], 'student123'))
        conn.close()

    def test_multi_image_upload_and_verified_badge(self):
        """Test apartment creation with images, campus verified badge, and deposit amount."""
        created = ejari_students_app.create_property({
            'title': 'سكن طلاب موثق مع ضمان التأمين',
            'governorate': 'الدقهلية',
            'university': 'جامعة المنصورة',
            'region': 'شارع جيهان',
            'distance_walk': '4 دقائق',
            'gender': 'male',
            'total_beds': 4,
            'available_beds': 3,
            'bed_monthly_price': 2200.0,
            'total_monthly_rent': 8800.0,
            'deposit_amount': 2000.0,
            'study_environment': 'هادئ للمذاكرة - غير مدخنين',
            'is_verified_campus': 1,
            'lease_duration': 'عام دراسي (9 شهور)',
            'images': ['/uploads/mansoura_1.svg', '/uploads/mansoura_2.svg'],
            'lat': 31.0421,
            'lng': 31.3582,
            'gate_lat': 31.0442,
            'gate_lng': 31.3540,
            'gate_name': 'بوابة توشكى',
            'walk_minutes': 4
        })
        self.assertEqual(created['status'], 'created')
        pid = created['id']

        props = ejari_students_app.list_properties()
        found = next(p for p in props if p['id'] == pid)
        self.assertEqual(found['deposit_amount'], 2000.0)
        self.assertEqual(found['is_verified_campus'], 1)
        self.assertEqual(len(found['images']), 2)
        self.assertGreaterEqual(found['compatibility_score'], 80)

    def test_roommate_compatibility_and_escrow_booking(self):
        """Test roommate compatibility score calculation and refundable deposit escrow."""
        # Check compatibility calculation
        roommates_sample = [
            {'faculty': 'كلية الطب البشري', 'study_habit': 'مذاكرة هادئة - غير مدخن'},
            {'faculty': 'كلية الهندسة', 'study_habit': 'مذاكرة ليلية هادئة'}
        ]
        score = ejari_students_app.calculate_roommate_compatibility(roommates_sample, target_faculty='كلية الصيدلة')
        self.assertGreaterEqual(score, 85)

        # Book bed and verify escrow
        booking = ejari_students_app.book_student_bed({
            'property_id': 1,
            'student_name': 'طارق إبراهيم',
            'faculty': 'كلية الهندسة',
            'academic_year': 'الفرقة الثالثة',
            'home_governorate': 'أسوان',
            'whatsapp_phone': '01011223344',
            'parent_phone': '01055566677',
            'study_habit': 'مذاكرة هادئة - غير مدخن',
            'monthly_share': 2200.0,
            'deposit_escrow': 2000.0
        })
        self.assertEqual(booking['status'], 'booked')
        self.assertEqual(booking['deposit_escrow'], 2000.0)
        self.assertEqual(booking['deposit_status'], 'escrow_secured')

        # Verify property available beds decreased
        props = ejari_students_app.list_properties()
        p1 = next(p for p in props if p['id'] == 1)
        self.assertEqual(p1['available_beds'], 0)
        self.assertEqual(p1['status'], 'fully_booked')

    def test_remote_live_video_tour_scheduling(self):
        """Test scheduling a 10-minute live WhatsApp/Zoom video tour."""
        res = ejari_students_app.schedule_video_tour({
            'property_id': 1,
            'student_name': 'مريم الصاوي',
            'student_phone': '01012345678',
            'home_governorate': 'قنا',
            'preferred_date': '2026-11-05',
            'preferred_time': '06:00 م',
            'platform': 'WhatsApp',
            'notes': 'معاينة غرف النوم وشبكة الواي فاي'
        })
        self.assertEqual(res['status'], 'scheduled')
        self.assertIn('id', res)
        self.assertEqual(res['platform'], 'WhatsApp')

        # Check in database
        conn = ejari_students_app.get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM video_tours WHERE id = ?', (res['id'],))
        tour = cur.fetchone()
        self.assertIsNotNone(tour)
        self.assertEqual(tour['student_name'], 'مريم الصاوي')
        conn.close()

    def test_paymob_sandbox_and_commission_tiers(self):
        """Test Paymob sandbox order generation, Fawry reference code, and webhook."""
        service = ejari_students_app.PaymobSandboxService()
        init_res = service.initiate_payment(2500.0, 'Fawry', 'عمر الديب', 1)
        self.assertEqual(init_res['status'], 'initiated')
        self.assertTrue(init_res['fawry_reference_code'].startswith('788-'))

        # Webhook callback
        webhook_payload = {
            'obj': {
                'order_id': init_res['order_id'],
                'amount_cents': 250000,
                'student_name': 'زياد العوضي',
                'property_id': 1,
                'roommate_id': 2,
                'method': 'Fawry',
                'plan_tier': 'pro'
            }
        }
        res = service.process_webhook(webhook_payload)
        self.assertEqual(res['status'], 'paid')
        self.assertEqual(res['commission'], 37.5) # 1.5% of 2500
        self.assertEqual(res['net_landlord'], 2462.5)

        # Portfolio tier (1.0%)
        calc_port = ejari_students_app.calculate_commission(10000.0, 'portfolio')
        self.assertEqual(calc_port['commission'], 100.0)
        self.assertEqual(calc_port['net_landlord'], 9900.0)

    def test_maintenance_and_dashboard_occupancy_stats(self):
        """Test maintenance ticket status advancement and occupancy rate calculation."""
        ticket = ejari_students_app.create_maintenance_ticket({
            'property_id': 1,
            'property_title': 'سكن الفردوس',
            'student_name': 'أحمد الشريف',
            'category': 'تكييف وتبريد',
            'priority': 'عاجل',
            'description': 'صيانة دورية لتكييف صالة المذاكرة'
        })
        self.assertEqual(ticket['status'], 'created')
        updated = ejari_students_app.update_maintenance_status(ticket['id'], 'completed')
        self.assertEqual(updated['new_status'], 'completed')

        stats = ejari_students_app.get_dashboard_stats('pro')
        self.assertGreater(stats['occupancy_rate'], 50.0)
        self.assertGreater(stats['escrow_secured_total'], 0)
        self.assertIn('video_tours_scheduled', stats)
        self.assertIn('total_reviews', stats)
        self.assertIn('parent_alerts_sent', stats)

    # --------------------------------------------------------------------------
    # v3.1 New Test Cases
    # --------------------------------------------------------------------------

    def test_jwt_auth_and_password_hashing(self):
        """Test JWT token signing (HS256), verification, expiration, and password hashing security."""
        # 1. Test JWT creation and decoding
        token = ejari_students_app.generate_jwt_token(
            user_id=1,
            role='student',
            full_name='أحمد محمود',
            phone='01012345678'
        )
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 30)

        decoded = ejari_students_app.verify_jwt_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['user_id'], 1)
        self.assertEqual(decoded['role'], 'student')
        self.assertEqual(decoded['full_name'], 'أحمد محمود')

        # 2. Test user retrieval via JWT token
        user = ejari_students_app.get_user_from_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user['phone'], '01012345678')

        # 3. Test Demo Accounts Passwords
        conn = ejari_students_app.get_db()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE phone = '01012345678'")
        student_row = cur.fetchone()
        self.assertTrue(ejari_students_app.verify_password(student_row['password_hash'], 'student123'))

        cur.execute("SELECT password_hash FROM users WHERE phone = '01123456789'")
        landlord_row = cur.fetchone()
        self.assertTrue(ejari_students_app.verify_password(landlord_row['password_hash'], 'landlord123'))

        cur.execute("SELECT password_hash FROM users WHERE phone = '01234567890'")
        admin_row = cur.fetchone()
        self.assertTrue(ejari_students_app.verify_password(admin_row['password_hash'], 'admin123'))
        conn.close()

    def test_leaflet_map_coordinates_and_compatibility(self):
        """Test interactive Leaflet map fields (lat, lng, gate_lat, gate_lng, gate_name, walk_minutes)."""
        props = ejari_students_app.list_properties()
        self.assertGreaterEqual(len(props), 6)

        for p in props:
            # Lat & Lng must be in Egypt bounding box
            self.assertGreaterEqual(p['lat'], 22.0)
            self.assertLessEqual(p['lat'], 32.5)
            self.assertGreaterEqual(p['lng'], 25.0)
            self.assertLessEqual(p['lng'], 36.0)

            # University gate coordinates
            self.assertGreaterEqual(p['gate_lat'], 22.0)
            self.assertLessEqual(p['gate_lat'], 32.5)
            self.assertGreaterEqual(p['gate_lng'], 25.0)
            self.assertLessEqual(p['gate_lng'], 36.0)

            # Gate name and walk minutes
            self.assertTrue(len(p['gate_name']) > 0)
            self.assertGreater(p['walk_minutes'], 0)

    def test_reviews_and_rating_aggregation(self):
        """Test student reviews system and automatic recalculation of rating_avg and reviews_count."""
        initial_reviews = ejari_students_app.list_reviews(property_id=1)
        initial_count = len(initial_reviews)

        # Submit new review
        res = ejari_students_app.create_review({
            'property_id': 1,
            'student_name': 'إبراهيم الشامي',
            'faculty': 'كلية الهندسة',
            'rating': 5.0,
            'comment': 'سكن ممتاز جداً وقريب من الجامعة والإنترنت قوي وسريع.',
            'semester': 'الفصل الدراسي الأول 2026'
        })
        self.assertEqual(res['status'], 'created')
        self.assertEqual(res['reviews_count'], initial_count + 1)
        self.assertGreaterEqual(res['rating_avg'], 4.5)

        # Verify property table updated
        conn = ejari_students_app.get_db()
        cur = conn.cursor()
        cur.execute("SELECT rating_avg, reviews_count FROM properties WHERE id = 1")
        prop = cur.fetchone()
        conn.close()
        self.assertEqual(prop['reviews_count'], initial_count + 1)
        self.assertEqual(prop['rating_avg'], res['rating_avg'])

    def test_whatsapp_parent_notification_and_escrow_booking(self):
        """Test sending instant parent alerts (WhatsApp Cloud API simulation) and booking auto-alert."""
        # 1. Manual alert test
        alert = ejari_students_app.send_parent_alert(
            student_name='محمود كمال',
            parent_phone='01099881122',
            message='تذكير بسداد القسط الشهري لسكن الجامعة',
            channel='WhatsApp'
        )
        self.assertEqual(alert['status'], 'sent')
        self.assertEqual(alert['delivery_status'], 'delivered')
        self.assertTrue(alert['gateway_ref'].startswith('WA-CLOUD-'))

        # Check list_parent_notifications
        notes = ejari_students_app.list_parent_notifications()
        self.assertGreaterEqual(len(notes), 1)

        # 2. Automated alert upon bed booking with parent phone
        initial_notif_count = len(notes)
        booking = ejari_students_app.book_student_bed({
            'property_id': 3,
            'student_name': 'نورهان سعيد',
            'faculty': 'كلية الصيدلة',
            'academic_year': 'الفرقة الثانية',
            'home_governorate': 'المنيا',
            'whatsapp_phone': '01011225566',
            'parent_phone': '01099884433',
            'study_habit': 'مذاكرة هادئة',
            'monthly_share': 2400.0,
            'deposit_escrow': 2000.0
        })
        self.assertEqual(booking['status'], 'booked')

        # Verify parent notification dispatched
        updated_notes = ejari_students_app.list_parent_notifications()
        self.assertEqual(len(updated_notes), initial_notif_count + 1)
        latest = updated_notes[0]
        self.assertEqual(latest['parent_phone'], '01099884433')
        self.assertIn('Escrow', latest['message'])

    def test_escrow_receipt_verification_and_filters(self):
        """Test v3.2 Escrow receipt verification endpoint and governorate/budget filters."""
        client = ejari_students_app.app.test_client()

        # 1. Verify pre-seeded valid receipt (EJR-202610-101)
        res = client.get('/api/bookings/verify/EJR-202610-101')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['verified'])
        self.assertEqual(data['escrow_status'], 'HELD_IN_ESCROW')
        self.assertEqual(data['receipt_code'], 'EJR-202610-101')
        self.assertEqual(data['student_name'], 'أحمد الشريف')
        self.assertIn('المنيا', data['governorate'])
        self.assertIn('حساب الضمان البنكي', data['bank_escrow_guarantee'])

        # 2. Book a new student bed and verify its newly generated receipt code
        booking = ejari_students_app.book_student_bed({
            'property_id': 1,
            'student_name': 'عمر عبد العزيز',
            'faculty': 'كلية الهندسة',
            'academic_year': 'الفرقة الثالثة',
            'home_governorate': 'الشرقية',
            'whatsapp_phone': '01098765432',
            'parent_phone': '01011223344',
            'study_habit': 'مذاكرة هادئة',
            'monthly_share': 2200.0,
            'deposit_escrow': 2000.0
        })
        self.assertEqual(booking['status'], 'booked')
        new_receipt = booking['receipt_code']
        self.assertTrue(new_receipt.startswith('EJR-'))

        res_new = client.get(f'/api/bookings/verify/{new_receipt}')
        self.assertEqual(res_new.status_code, 200)
        data_new = res_new.get_json()
        self.assertTrue(data_new['verified'])
        self.assertEqual(data_new['student_name'], 'عمر عبد العزيز')
        self.assertEqual(data_new['deposit_escrow'], 2000.0)

        # 3. Verify non-existent receipt returns 404
        res_invalid = client.get('/api/bookings/verify/EJR-INVALID-999999')
        self.assertEqual(res_invalid.status_code, 404)
        data_inv = res_invalid.get_json()
        self.assertFalse(data_inv['verified'])

        # 4. Filter properties by governorate and max_rent
        gov_filtered = ejari_students_app.list_properties(governorate='المنيا')
        self.assertGreaterEqual(len(gov_filtered), 1)
        for p in gov_filtered:
            self.assertIn('المنيا', p['governorate'])

        budget_filtered = ejari_students_app.list_properties(max_rent='1800')
        self.assertGreaterEqual(len(budget_filtered), 1)
        for p in budget_filtered:
            self.assertLessEqual(p['bed_monthly_price'], 1800)


if __name__ == '__main__':
    unittest.main()
