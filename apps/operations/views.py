from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required
from apps.accounts.models import StudentAccountLink, User

from .forms import (
    ManagedUserCreateForm,
    ManagedUserUpdateForm,
    StudentLinkForm,
    TeacherStudentAccessForm,
    UserFilterForm,
)
from .models import AccountAuditLog, TeacherStudentAccess
from .services import (
    add_student_link,
    add_teacher_student_access,
    create_managed_user,
    deactivate_student_link,
    remove_teacher_student_access,
    set_primary_student_link,
    update_managed_user,
)


UserModel = get_user_model()


def _managed_user_or_404(user_id: int) -> User:
    return get_object_or_404(UserModel, pk=user_id)


def _handle_validation_error(request: HttpRequest, error: ValidationError) -> None:
    messages.error(request, "; ".join(error.messages))


@admin_required
def operations_dashboard(request: HttpRequest) -> HttpResponse:
    users = UserModel.objects.all()
    active_users = users.filter(is_active=True)
    recent_logs = AccountAuditLog.objects.select_related("actor", "target_user")[:10]

    return render(
        request,
        "operations/dashboard.html",
        {
            "page_title": "계정관리",
            "active_user_count": active_users.count(),
            "admin_count": active_users.filter(
                Q(is_superuser=True) | Q(role=User.Role.ADMIN)
            ).count(),
            "teacher_count": active_users.filter(role=User.Role.TEACHER).count(),
            "student_count": active_users.filter(role=User.Role.STUDENT).count(),
            "parent_count": active_users.filter(role=User.Role.PARENT).count(),
            "teacher_scope_count": TeacherStudentAccess.objects.filter(
                is_active=True
            ).count(),
            "recent_logs": recent_logs,
            "intranet_pending": UserModel.objects.filter(role=User.Role.STUDENT, first_setup_at__isnull=False, intranet_synced_at__isnull=True).count(),
        },
    )


@admin_required
def user_list(request: HttpRequest) -> HttpResponse:
    form = UserFilterForm(request.GET or None)
    queryset = UserModel.objects.annotate(
        active_link_count=Count(
            "student_links",
            filter=Q(student_links__is_active=True),
            distinct=True,
        )
    ).order_by(Lower("username"), "id")

    if form.is_valid():
        q = (form.cleaned_data.get("q") or "").strip()
        role = form.cleaned_data.get("role", "")
        link = form.cleaned_data.get("link", "")
        if q:
            queryset = queryset.filter(
                Q(username__icontains=q)
                | Q(display_name__icontains=q)
                | Q(email__icontains=q)
            )
        if role:
            queryset = queryset.filter(role=role)
        if link == "linked":
            queryset = queryset.filter(active_link_count__gt=0)
        elif link == "unlinked":
            queryset = queryset.filter(active_link_count=0)

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "operations/user_list.html",
        {
            "page_title": "사용자 관리",
            "filter_form": form,
            "page_obj": page_obj,
            "result_count": paginator.count,
        },
    )


@admin_required
def user_create(request: HttpRequest) -> HttpResponse:
    form = ManagedUserCreateForm(request.POST or None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            user = create_managed_user(request=request, cleaned_data=form.cleaned_data)
        except (ValidationError, PermissionDenied) as error:
            if isinstance(error, PermissionDenied):
                raise
            _handle_validation_error(request, error)
        else:
            messages.success(request, f"{user.username} 계정을 생성했습니다.")
            return redirect("operations:user-detail", user_id=user.pk)
    return render(
        request,
        "operations/user_form.html",
        {
            "page_title": "새 사용자 등록",
            "form": form,
            "form_mode": "create",
            "target_user": None,
        },
    )


@admin_required
def user_detail(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = _managed_user_or_404(user_id)
    if not request.user.is_superuser and (
        target_user.is_superuser or target_user.role == User.Role.ADMIN
    ):
        raise PermissionDenied("관리자 계정은 최고관리자만 조회할 수 있습니다.")

    links = target_user.student_links.order_by("-is_active", "-is_primary", "id")
    link_form = StudentLinkForm(target_user=target_user)
    teacher_accesses = target_user.teacher_student_accesses.filter(is_active=True)
    teacher_access_form = TeacherStudentAccessForm(target_user=target_user)
    audit_logs = target_user.account_change_logs.select_related("actor")[:12]

    return render(
        request,
        "operations/user_detail.html",
        {
            "page_title": f"{target_user.effective_name} 계정",
            "target_user": target_user,
            "links": links,
            "link_form": link_form,
            "teacher_accesses": teacher_accesses,
            "teacher_access_form": teacher_access_form,
            "audit_logs": audit_logs,
        },
    )


@admin_required
def user_update(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = _managed_user_or_404(user_id)
    if not request.user.is_superuser and (
        target_user.is_superuser or target_user.role == User.Role.ADMIN
    ):
        raise PermissionDenied("관리자 계정은 최고관리자만 변경할 수 있습니다.")

    form = ManagedUserUpdateForm(
        request.POST or None,
        target_user=target_user,
        actor=request.user,
    )
    if request.method == "POST" and form.is_valid():
        try:
            password_changed = bool(form.cleaned_data.get("password1"))
            update_managed_user(
                request=request,
                target_user=target_user,
                cleaned_data=form.cleaned_data,
            )
        except (ValidationError, PermissionDenied) as error:
            if isinstance(error, PermissionDenied):
                raise
            _handle_validation_error(request, error)
        else:
            if target_user.pk == request.user.pk and password_changed:
                update_session_auth_hash(request, target_user)
            messages.success(request, "계정 정보를 저장했습니다.")
            return redirect("operations:user-detail", user_id=target_user.pk)

    return render(
        request,
        "operations/user_form.html",
        {
            "page_title": "사용자 정보 수정",
            "form": form,
            "form_mode": "update",
            "target_user": target_user,
        },
    )


@admin_required
@require_POST
def link_add(request: HttpRequest, user_id: int) -> HttpResponse:
    target_user = _managed_user_or_404(user_id)
    form = StudentLinkForm(request.POST, target_user=target_user)
    if form.is_valid():
        try:
            add_student_link(
                request=request,
                target_user=target_user,
                student_no=form.cleaned_data["student_no"],
                is_primary=bool(form.cleaned_data.get("is_primary")),
            )
        except (ValidationError, PermissionDenied) as error:
            if isinstance(error, PermissionDenied):
                raise
            _handle_validation_error(request, error)
        else:
            messages.success(request, "학생 연결을 저장했습니다.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect("operations:user-detail", user_id=target_user.pk)


@admin_required
@require_POST
def link_primary(request: HttpRequest, user_id: int, link_id: int) -> HttpResponse:
    target_user = _managed_user_or_404(user_id)
    link = get_object_or_404(StudentAccountLink, pk=link_id, user=target_user)
    try:
        set_primary_student_link(request=request, target_user=target_user, link=link)
    except ValidationError as error:
        _handle_validation_error(request, error)
    else:
        messages.success(request, "대표 학생을 변경했습니다.")
    return redirect("operations:user-detail", user_id=target_user.pk)


@admin_required
@require_POST
def link_deactivate(request: HttpRequest, user_id: int, link_id: int) -> HttpResponse:
    target_user = _managed_user_or_404(user_id)
    link = get_object_or_404(StudentAccountLink, pk=link_id, user=target_user)
    try:
        deactivate_student_link(request=request, target_user=target_user, link=link)
    except ValidationError as error:
        _handle_validation_error(request, error)
    else:
        messages.success(request, "학생 연결을 해제했습니다.")
    return redirect("operations:user-detail", user_id=target_user.pk)


@admin_required
@require_POST
def teacher_access_add(request: HttpRequest, user_id: int) -> HttpResponse:
    teacher = _managed_user_or_404(user_id)
    form = TeacherStudentAccessForm(request.POST, target_user=teacher)
    if form.is_valid():
        try:
            add_teacher_student_access(
                request=request,
                teacher=teacher,
                student_no=form.cleaned_data["student_no"],
                student_name=form.student_name,
            )
        except (ValidationError, PermissionDenied) as error:
            if isinstance(error, PermissionDenied):
                raise
            _handle_validation_error(request, error)
        else:
            messages.success(request, "담당 학생을 배정했습니다.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect("operations:user-detail", user_id=teacher.pk)


@admin_required
@require_POST
def teacher_access_remove(
    request: HttpRequest,
    user_id: int,
    access_id: int,
) -> HttpResponse:
    teacher = _managed_user_or_404(user_id)
    access = get_object_or_404(TeacherStudentAccess, pk=access_id, teacher=teacher)
    try:
        remove_teacher_student_access(request=request, teacher=teacher, access=access)
    except (ValidationError, PermissionDenied) as error:
        if isinstance(error, PermissionDenied):
            raise
        _handle_validation_error(request, error)
    else:
        messages.success(request, "담당 학생 배정을 해제했습니다.")
    return redirect("operations:user-detail", user_id=teacher.pk)


@admin_required
def audit_list(request: HttpRequest) -> HttpResponse:
    queryset = AccountAuditLog.objects.select_related("actor", "target_user")
    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "").strip()
    if q:
        queryset = queryset.filter(
            Q(summary__icontains=q)
            | Q(actor__username__icontains=q)
            | Q(actor__display_name__icontains=q)
            | Q(target_user__username__icontains=q)
            | Q(target_user__display_name__icontains=q)
        )
    if action in AccountAuditLog.Action.values:
        queryset = queryset.filter(action=action)
    paginator = Paginator(queryset, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "operations/audit_list.html",
        {
            "page_title": "계정 운영 기록",
            "page_obj": page_obj,
            "actions": AccountAuditLog.Action.choices,
            "selected_action": action,
            "q": q,
        },
    )


@admin_required
def intranet_sync_list(request: HttpRequest) -> HttpResponse:
    """학생이 첫 로그인 때 적은 이메일·DSG ID 중 인트라넷에 아직 옮기지 않은 것(11/17). 엑셀(CSV)로 받거나 '반영 완료'를 누릅니다."""
    import csv
    from django.utils import timezone
    pending = (UserModel.objects.filter(role=User.Role.STUDENT, first_setup_at__isnull=False, intranet_synced_at__isnull=True)
               .prefetch_related("student_links").order_by("first_setup_at"))
    if request.method == "POST":
        ids = [int(x) for x in request.POST.getlist("user") if x.isdigit()]
        done = pending.filter(pk__in=ids).update(intranet_synced_at=timezone.now())
        messages.success(request, f"{done}명을 인트라넷 반영 완료로 표시했습니다.")
        return redirect("operations:intranet-sync")
    rows = []
    for user in pending:
        links = [link.student_no for link in user.student_links.all() if link.is_active]
        rows.append({"user": user, "student_no": ", ".join(links)})
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="intranet-sync.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["학생번호", "이름", "아이디", "이메일", "DSG ID", "입력한 때"])
        for row in rows:
            u = row["user"]
            writer.writerow([row["student_no"], u.effective_name, u.username, u.email, u.dsg_login_id or "없음",
                             timezone.localtime(u.first_setup_at).strftime("%Y-%m-%d %H:%M")])
        return response
    return render(request, "operations/intranet_sync.html", {"page_title": "인트라넷 반영 목록", "rows": rows})
