from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("groups", views.GroupViewSet, basename="group")
router.register("students", views.StudentViewSet, basename="student")
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("channels", views.ChannelViewSet, basename="channel")
router.register("advances", views.SalaryAdvanceViewSet, basename="advance")

urlpatterns = [
    path("auth/login/", obtain_auth_token),
    path("auth/me/", views.me),
    path("attendance/mark/", views.mark_attendance),
    path("salary/", views.salary),
    path("", include(router.urls)),
]
