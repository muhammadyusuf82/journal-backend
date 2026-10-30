from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Group, Payment, SalaryAdvance, Student


class JournalTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("t", password="p")
        self.other = get_user_model().objects.create_user("o", password="p")
        self.group = Group.objects.create(teacher=self.user, name="G", monthly_fee=100, teacher_percent=40)
        self.student = Student.objects.create(group=self.group, first_name="A")
        self.client.force_authenticate(self.user)

    def test_payment_status_colors(self):
        self.assertEqual(self.student.payment_status(date(2026, 3, 1)), "pending")
        self.assertEqual(self.student.payment_status(date(2026, 3, 4)), "pending")
        self.assertEqual(self.student.payment_status(date(2026, 3, 5)), "overdue")
        Payment.objects.create(student=self.student, year=2026, month=3, amount=100)
        self.assertEqual(self.student.payment_status(date(2026, 3, 20)), "paid")

    def test_discounts(self):
        s = self.student
        s.discount_type, s.discount_percent = "permanent", Decimal(20)
        self.assertEqual(s.monthly_due(), Decimal("80.00"))
        s.discount_type, s.discount_until = "temporary", date(2020, 1, 1)
        self.assertEqual(s.monthly_due(), Decimal("100.00"))  # expired

    def test_salary_calculation(self):
        today = date.today()
        Payment.objects.create(student=self.student, year=today.year, month=today.month, amount=250)
        SalaryAdvance.objects.create(teacher=self.user, year=today.year, month=today.month, amount=30)
        r = self.client.get("/api/salary/").json()
        self.assertEqual(Decimal(r["total_share"]), Decimal("100"))
        self.assertEqual(Decimal(r["remaining"]), Decimal("70"))

    def test_teacher_isolation(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/students/").json(), [])
        r = self.client.post("/api/payments/", {"student": self.student.id, "year": 2026, "month": 1, "amount": 1})
        self.assertEqual(r.status_code, 400)

    def test_token_post_ignores_csrf_with_session_cookie(self):
        # Regression: a Django admin session cookie made DRF demand CSRF on API calls
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient

        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)  # session cookie, like being logged into admin
        token = Token.objects.create(user=self.user)
        r = client.post("/api/channels/", {"name": "TG"}, format="json",
                        HTTP_AUTHORIZATION=f"Token {token.key}", HTTP_ORIGIN="http://localhost:5174")
        self.assertEqual(r.status_code, 201)

    def test_admin_adds_teacher_who_can_log_in(self):
        from django.test import Client

        admin_user = get_user_model().objects.create_superuser("boss", password="p")
        c = Client()
        c.force_login(admin_user)
        self.assertEqual(c.get("/admin/journal/teacher/").status_code, 200)
        self.assertEqual(c.get("/admin/journal/teacher/add/").status_code, 200)
        r = c.post("/admin/journal/teacher/add/", {
            "username": "newteacher", "first_name": "Nodira", "last_name": "K", "email": "",
            "password1": "S3cure-pass-123", "password2": "S3cure-pass-123",
        })
        self.assertEqual(r.status_code, 302, r.content[:2000])
        t = get_user_model().objects.get(username="newteacher")
        self.assertFalse(t.is_staff)
        self.assertEqual(c.get(f"/admin/journal/teacher/{t.id}/change/").status_code, 200)
        login = self.client.post("/api/auth/login/", {"username": "newteacher", "password": "S3cure-pass-123"})
        self.assertIn("token", login.json())

    def test_mark_attendance(self):
        r = self.client.post("/api/attendance/mark/", {"student": self.student.id, "date": "2026-10-26", "status": "present"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.student.attendance.get().status, "present")
        self.client.post("/api/attendance/mark/", {"student": self.student.id, "date": "2026-10-26", "status": None}, format="json")
        self.assertFalse(self.student.attendance.exists())
