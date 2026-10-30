from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Attendance, Channel, Group, Payment, SalaryAdvance, Student


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email"]


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ["id", "name", "link"]


class GroupSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    student_count = serializers.SerializerMethodField()
    paid_count = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()
    overdue_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            "id", "name", "level", "level_display", "lesson_days", "lesson_time",
            "monthly_fee", "teacher_percent", "student_count", "paid_count",
            "pending_count", "overdue_count",
        ]

    def _statuses(self, obj):
        cache = getattr(obj, "_status_cache", None)
        if cache is None:
            today = date.today()
            cache = [s.payment_status(today) for s in obj.students.filter(is_active=True)]
            obj._status_cache = cache
        return cache

    def get_student_count(self, obj):
        return len(self._statuses(obj))

    def get_paid_count(self, obj):
        return self._statuses(obj).count("paid")

    def get_pending_count(self, obj):
        return self._statuses(obj).count("pending")

    def get_overdue_count(self, obj):
        return self._statuses(obj).count("overdue")


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "student", "year", "month", "amount", "paid_at", "note"]

    def validate_student(self, student):
        if student.group.teacher_id != self.context["request"].user.id:
            raise serializers.ValidationError("Not your student.")
        return student

    def validate_month(self, month):
        if not 1 <= month <= 12:
            raise serializers.ValidationError("Month must be 1-12.")
        return month


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="__str__", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    payment_status = serializers.SerializerMethodField()
    current_payment = serializers.SerializerMethodField()
    monthly_due = serializers.SerializerMethodField()
    discount_active = serializers.SerializerMethodField()
    channels = serializers.PrimaryKeyRelatedField(many=True, queryset=Channel.objects.all(), required=False)

    class Meta:
        model = Student
        fields = [
            "id", "group", "group_name", "first_name", "last_name", "full_name",
            "phone", "parent_phone", "parent_name", "birth_date", "joined_at",
            "channels", "discount_type", "discount_percent", "discount_until",
            "discount_reason", "notes", "is_active", "payment_status",
            "current_payment", "monthly_due", "discount_active",
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            fields["group"].queryset = Group.objects.filter(teacher=request.user)
            fields["channels"].child_relation.queryset = Channel.objects.filter(teacher=request.user)
        return fields

    def get_payment_status(self, obj):
        return obj.payment_status()

    def get_current_payment(self, obj):
        today = date.today()
        p = obj.payments.filter(year=today.year, month=today.month).first()
        return PaymentSerializer(p).data if p else None

    def get_monthly_due(self, obj):
        return str(obj.monthly_due())

    def get_discount_active(self, obj):
        return obj.discount_active()

    def validate(self, attrs):
        dtype = attrs.get("discount_type", getattr(self.instance, "discount_type", "none"))
        pct = attrs.get("discount_percent", getattr(self.instance, "discount_percent", 0))
        if dtype != "none" and not (0 < pct <= 100):
            raise serializers.ValidationError({"discount_percent": "Discount must be between 0 and 100."})
        if dtype == "none":
            attrs["discount_percent"] = 0
            attrs["discount_until"] = None
        return attrs


class AttendanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attendance
        fields = ["id", "student", "date", "status"]


class SalaryAdvanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryAdvance
        fields = ["id", "year", "month", "amount", "received_at", "note"]
