from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group as AuthGroup

from .models import Attendance, Channel, Group, Payment, SalaryAdvance, Student, Teacher

# Django's permission "Groups" are not used and get confused with study groups.
admin.site.unregister(AuthGroup)


class TeacherCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Teacher
        fields = ("username", "first_name", "last_name", "email")


class GroupInline(admin.TabularInline):
    model = Group
    fk_name = "teacher"
    fields = ["name", "level", "lesson_days", "lesson_time", "monthly_fee", "teacher_percent"]
    extra = 0
    show_change_link = True


@admin.register(Teacher)
class TeacherAdmin(UserAdmin):
    add_form = TeacherCreationForm
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "first_name", "last_name", "email", "password1", "password2"),
        }),
    )
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Status", {"fields": ("is_active", "last_login", "date_joined")}),
    )
    readonly_fields = ["last_login", "date_joined"]
    list_display = ["username", "first_name", "last_name", "email", "group_count", "is_active"]
    list_filter = ["is_active"]
    filter_horizontal = []
    inlines = [GroupInline]

    @admin.display(description="Groups")
    def group_count(self, obj):
        return obj.groups_taught.count()

    def get_inlines(self, request, obj):
        return self.inlines if obj else []  # groups can be added after the teacher exists

    def save_model(self, request, obj, form, change):
        obj.is_staff = False  # teachers use the journal app, not the admin panel
        obj.is_superuser = False
        super().save_model(request, obj, form, change)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "teacher", "monthly_fee", "teacher_percent"]
    list_filter = ["level", "teacher"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "teacher":
            kwargs["queryset"] = Teacher.objects.order_by("username")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["first_name", "last_name", "group", "phone", "parent_phone", "discount_type", "is_active"]
    list_filter = ["group", "discount_type", "is_active"]
    search_fields = ["first_name", "last_name", "phone", "parent_phone"]


admin.site.register(Channel)
admin.site.register(Payment)
admin.site.register(Attendance)
admin.site.register(SalaryAdvance)
