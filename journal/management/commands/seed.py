import random
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from journal.models import Attendance, Channel, Group, Payment, SalaryAdvance, Student

FIRST = ["Ali", "Madina", "Jasur", "Dilnoza", "Bekzod", "Malika", "Sardor", "Nilufar", "Aziz", "Shahzoda", "Otabek", "Zarina"]
LAST = ["Karimov", "Rahimova", "Tursunov", "Yusupova", "Aliyev", "Saidova", "Nazarov", "Ergasheva"]


class Command(BaseCommand):
    help = "Create a demo teacher (teacher / teacher123) with groups, students and payments."

    def handle(self, *args, **options):
        User = get_user_model()
        teacher, created = User.objects.get_or_create(username="teacher", defaults={"first_name": "Demo", "last_name": "Teacher"})
        if created:
            teacher.set_password("teacher123")
            teacher.save()
        if teacher.groups_taught.exists():
            self.stdout.write("Demo data already exists.")
            return

        tg = Channel.objects.create(teacher=teacher, name="Telegram channel", link="https://t.me/example")
        ig = Channel.objects.create(teacher=teacher, name="Instagram", link="https://instagram.com/example")

        today = date.today()
        specs = [
            ("Morning A1", "beginner", "0,2,4", "09:00", 400000),
            ("Evening B1", "intermediate", "1,3,5", "18:00", 500000),
            ("IELTS C1", "advanced", "0,2,4", "16:00", 700000),
        ]
        random.seed(1)
        for name, level, days, time, fee in specs:
            g = Group.objects.create(teacher=teacher, name=name, level=level, lesson_days=days, lesson_time=time, monthly_fee=fee)
            for i in range(6):
                s = Student.objects.create(
                    group=g,
                    first_name=random.choice(FIRST),
                    last_name=random.choice(LAST),
                    phone=f"+99890{random.randint(1000000, 9999999)}",
                    parent_phone=f"+99891{random.randint(1000000, 9999999)}",
                    parent_name=random.choice(FIRST),
                )
                if i % 2 == 0:
                    s.channels.add(tg)
                if i % 3 == 0:
                    s.channels.add(ig)
                if i == 1:
                    s.discount_type, s.discount_percent = "permanent", 20
                    s.discount_reason = "Sibling discount"
                    s.save()
                if i == 2:
                    s.discount_type, s.discount_percent = "temporary", 10
                    s.discount_until = date(today.year, 12, 31)
                    s.save()
                if i < 3:  # half the group has paid this month
                    Payment.objects.create(student=s, year=today.year, month=today.month, amount=s.monthly_due())
                for d in g.lesson_dates(today.year, today.month):
                    if d < today:
                        Attendance.objects.create(student=s, date=d, status=random.choice(["present"] * 6 + ["absent", "late"]))

        SalaryAdvance.objects.create(teacher=teacher, year=today.year, month=today.month, amount=300000, note="Advance")
        self.stdout.write(self.style.SUCCESS("Demo data created. Login: teacher / teacher123"))
