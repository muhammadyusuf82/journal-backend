import calendar
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User, UserManager
from django.db import models

# Payment is "overdue" (red) from this day of the month if still unpaid.
OVERDUE_DAY = 5


class TeacherManager(UserManager):
    def get_queryset(self):
        # Teachers are regular (non-admin) accounts that log into the journal app
        return super().get_queryset().filter(is_staff=False, is_superuser=False)


class Teacher(User):
    """Proxy over Django's User so teachers get their own section in admin."""

    objects = TeacherManager()

    class Meta:
        proxy = True
        verbose_name = "teacher"
        verbose_name_plural = "teachers"


class Group(models.Model):
    LEVELS = [
        ("beginner", "Beginner"),
        ("elementary", "Elementary"),
        ("pre_intermediate", "Pre-Intermediate"),
        ("intermediate", "Intermediate"),
        ("upper_intermediate", "Upper-Intermediate"),
        ("advanced", "Advanced"),
    ]

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="groups_taught")
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=30, choices=LEVELS, default="beginner")
    # Weekdays of lessons, Monday=0 ... Sunday=6, comma separated, e.g. "0,2,4"
    lesson_days = models.CharField(max_length=20, default="0,2,4")
    lesson_time = models.CharField(max_length=20, blank=True)
    monthly_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Teacher's share of the group's collected payments, in percent
    teacher_percent = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def lesson_weekdays(self):
        return [int(d) for d in self.lesson_days.split(",") if d.strip().isdigit()]

    def lesson_dates(self, year, month):
        days = self.lesson_weekdays()
        _, last = calendar.monthrange(year, month)
        return [date(year, month, d) for d in range(1, last + 1) if date(year, month, d).weekday() in days]


class Channel(models.Model):
    """A channel students should be subscribed to (Telegram, Instagram...)."""

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="channels")
    name = models.CharField(max_length=100)
    link = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    DISCOUNT_NONE = "none"
    DISCOUNT_TEMPORARY = "temporary"
    DISCOUNT_PERMANENT = "permanent"
    DISCOUNT_TYPES = [
        (DISCOUNT_NONE, "No discount"),
        (DISCOUNT_TEMPORARY, "Temporary"),
        (DISCOUNT_PERMANENT, "Permanent"),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="students")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    parent_phone = models.CharField(max_length=30, blank=True)
    parent_name = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    joined_at = models.DateField(default=date.today)
    channels = models.ManyToManyField(Channel, blank=True, related_name="subscribers")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default=DISCOUNT_NONE)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_until = models.DateField(null=True, blank=True, help_text="End date for temporary discounts")
    discount_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    def discount_active(self, on=None):
        on = on or date.today()
        if self.discount_type == self.DISCOUNT_PERMANENT:
            return self.discount_percent > 0
        if self.discount_type == self.DISCOUNT_TEMPORARY:
            return self.discount_percent > 0 and (self.discount_until is None or on <= self.discount_until)
        return False

    def monthly_due(self, on=None):
        fee = Decimal(self.group.monthly_fee)
        if self.discount_active(on):
            pct = Decimal(self.discount_percent)
            fee = fee * (Decimal(100) - pct) / Decimal(100)
        return fee.quantize(Decimal("0.01"))

    def payment_status(self, today=None):
        """paid / pending (month started, unpaid) / overdue (5th day or later, unpaid)."""
        today = today or date.today()
        paid = self.payments.filter(year=today.year, month=today.month).exists()
        if paid:
            return "paid"
        return "overdue" if today.day >= OVERDUE_DAY else "pending"


class Payment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="payments")
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateField(default=date.today)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-year", "-month"]
        unique_together = [("student", "year", "month")]

    def __str__(self):
        return f"{self.student} {self.month:02d}/{self.year}: {self.amount}"


class Attendance(models.Model):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    STATUSES = [(PRESENT, "Present"), (ABSENT, "Absent"), (LATE, "Late")]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUSES, default=PRESENT)

    class Meta:
        ordering = ["date"]
        unique_together = [("student", "date")]


class SalaryAdvance(models.Model):
    """Part of the teacher's salary received earlier, in advance."""

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="advances")
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_at = models.DateField(default=date.today)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-received_at"]
