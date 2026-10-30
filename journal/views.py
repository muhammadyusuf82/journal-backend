from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Attendance, Channel, Group, Payment, SalaryAdvance, Student
from .serializers import (
    ChannelSerializer, GroupSerializer, PaymentSerializer, SalaryAdvanceSerializer,
    StudentSerializer, UserSerializer,
)


def year_month(request):
    today = date.today()
    try:
        year = int(request.query_params.get("year", today.year))
        month = int(request.query_params.get("month", today.month))
    except ValueError:
        raise ValidationError("year and month must be numbers")
    if not 1 <= month <= 12:
        raise ValidationError("month must be 1-12")
    return year, month


@api_view(["GET"])
def me(request):
    return Response(UserSerializer(request.user).data)


class GroupViewSet(viewsets.ModelViewSet):
    serializer_class = GroupSerializer

    def get_queryset(self):
        return Group.objects.filter(teacher=self.request.user).prefetch_related("students__payments")

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)

    @action(detail=True, methods=["get"])
    def attendance(self, request, pk=None):
        """Monthly attendance grid: lesson dates x students."""
        group = self.get_object()
        year, month = year_month(request)
        dates = group.lesson_dates(year, month)
        students = group.students.filter(is_active=True)
        records = {}
        for a in Attendance.objects.filter(student__in=students, date__year=year, date__month=month):
            records.setdefault(a.student_id, {})[a.date.isoformat()] = a.status
        return Response({
            "year": year,
            "month": month,
            "dates": [d.isoformat() for d in dates],
            "students": [{"id": s.id, "full_name": str(s)} for s in students],
            "records": records,
        })


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer

    def get_queryset(self):
        qs = Student.objects.filter(group__teacher=self.request.user).select_related("group").prefetch_related("channels")
        group = self.request.query_params.get("group")
        if group:
            qs = qs.filter(group_id=group)
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(first_name__icontains=search) | Q(last_name__icontains=search))
        return qs

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        """Payment history for a year and attendance totals for the student card."""
        student = self.get_object()
        year = int(request.query_params.get("year", date.today().year))
        payments = {p.month: PaymentSerializer(p).data for p in student.payments.filter(year=year)}
        att = student.attendance.all()
        return Response({
            "year": year,
            "payments": payments,
            "attendance": {
                "present": att.filter(status=Attendance.PRESENT).count(),
                "late": att.filter(status=Attendance.LATE).count(),
                "absent": att.filter(status=Attendance.ABSENT).count(),
            },
            "recent_attendance": [
                {"date": a.date.isoformat(), "status": a.status} for a in att.order_by("-date")[:20]
            ],
        })


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer

    def get_queryset(self):
        qs = Payment.objects.filter(student__group__teacher=self.request.user)
        student = self.request.query_params.get("student")
        if student:
            qs = qs.filter(student_id=student)
        return qs


class ChannelViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelSerializer

    def get_queryset(self):
        return Channel.objects.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class SalaryAdvanceViewSet(viewsets.ModelViewSet):
    serializer_class = SalaryAdvanceSerializer

    def get_queryset(self):
        qs = SalaryAdvance.objects.filter(teacher=self.request.user)
        if "year" in self.request.query_params:
            year, month = year_month(self.request)
            qs = qs.filter(year=year, month=month)
        return qs

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


@api_view(["POST"])
def mark_attendance(request):
    """Body: {student, date, status}. status=null removes the mark."""
    try:
        student = Student.objects.get(pk=request.data.get("student"), group__teacher=request.user)
    except (Student.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)
    day = request.data.get("date")
    st = request.data.get("status")
    try:
        day = date.fromisoformat(day)
    except (TypeError, ValueError):
        return Response({"detail": "Invalid date."}, status=status.HTTP_400_BAD_REQUEST)
    if st in (None, ""):
        Attendance.objects.filter(student=student, date=day).delete()
        return Response({"student": student.id, "date": day.isoformat(), "status": None})
    if st not in dict(Attendance.STATUSES):
        return Response({"detail": "Invalid status."}, status=status.HTTP_400_BAD_REQUEST)
    Attendance.objects.update_or_create(student=student, date=day, defaults={"status": st})
    return Response({"student": student.id, "date": day.isoformat(), "status": st})


@api_view(["GET"])
def salary(request):
    """Collected money per group for a month, the teacher's share and advances."""
    year, month = year_month(request)
    groups = []
    total_share = Decimal(0)
    for g in Group.objects.filter(teacher=request.user):
        collected = Payment.objects.filter(student__group=g, year=year, month=month).aggregate(s=Sum("amount"))["s"] or Decimal(0)
        active = g.students.filter(is_active=True)
        expected = sum((s.monthly_due(date(year, month, 1)) for s in active), Decimal(0))
        share = (collected * g.teacher_percent / Decimal(100)).quantize(Decimal("0.01"))
        total_share += share
        groups.append({
            "id": g.id,
            "name": g.name,
            "level_display": g.get_level_display(),
            "teacher_percent": str(g.teacher_percent),
            "collected": str(collected),
            "expected": str(expected),
            "paid_count": Payment.objects.filter(student__group=g, year=year, month=month).count(),
            "student_count": active.count(),
            "share": str(share),
        })
    advances = SalaryAdvance.objects.filter(teacher=request.user, year=year, month=month)
    advance_total = advances.aggregate(s=Sum("amount"))["s"] or Decimal(0)
    return Response({
        "year": year,
        "month": month,
        "groups": groups,
        "advances": SalaryAdvanceSerializer(advances, many=True).data,
        "total_share": str(total_share),
        "advance_total": str(advance_total),
        "remaining": str(total_share - advance_total),
    })
