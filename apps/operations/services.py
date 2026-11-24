from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import StudentAccountLink, User

from .models import AccountAuditLog, TeacherStudentAccess


UserModel = get_user_model()


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def record_account_audit(*, request, target_user: User | None, action: str, summary: str, metadata: dict | None = None) -> AccountAuditLog:
    return AccountAuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        target_user=target_user,
        action=action,
        summary=summary,
        metadata=metadata or {},
        ip_address=client_ip(request),
    )


def ensure_target_manageable(actor: User, target_user: User) -> None:
    if not actor.is_superuser and (
        target_user.is_superuser or target_user.role == User.Role.ADMIN
    ):
        raise PermissionDenied("관리자 계정은 최고관리자만 변경할 수 있습니다.")


def active_admin_count() -> int:
    return UserModel.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(role=User.Role.ADMIN)
    ).count()


def ensure_admin_continuity(target_user: User, *, new_role: str) -> None:
    currently_admin = target_user.is_superuser or target_user.role == User.Role.ADMIN
    remains_admin = target_user.is_superuser or new_role == User.Role.ADMIN
    if currently_admin and not remains_admin and active_admin_count() <= 1:
        raise ValidationError("마지막 관리자 계정의 역할은 변경할 수 없습니다.")


@transaction.atomic
def create_managed_user(*, request, cleaned_data: dict) -> User:
    role = cleaned_data["role"]
    if role == User.Role.ADMIN and not request.user.is_superuser:
        raise PermissionDenied("관리자 역할 계정은 최고관리자만 생성할 수 있습니다.")
    user = UserModel.objects.create_user(
        username=cleaned_data["username"],
        password=cleaned_data["password1"],
        display_name=cleaned_data["display_name"],
        email=cleaned_data.get("email", ""),
        role=role,
        is_active=True,
        needs_first_setup=role == User.Role.STUDENT,
    )
    student_no = str(cleaned_data.get("student_no") or "").strip()
    if student_no:
        relationship = (
            StudentAccountLink.Relationship.SELF
            if user.role == User.Role.STUDENT
            else StudentAccountLink.Relationship.PARENT
        )
        StudentAccountLink.objects.create(
            user=user,
            student_no=student_no,
            relationship=relationship,
            is_primary=True,
            is_active=True,
        )
    record_account_audit(
        request=request,
        target_user=user,
        action=AccountAuditLog.Action.USER_CREATED,
        summary=f"{user.username} 계정을 생성했습니다.",
        metadata={"role": user.role, "student_no": student_no},
    )
    return user


@transaction.atomic
def update_managed_user(*, request, target_user: User, cleaned_data: dict) -> User:
    ensure_target_manageable(request.user, target_user)
    requested_role = cleaned_data.get("role", target_user.role)
    new_role = requested_role if request.user.is_superuser else target_user.role
    if new_role != target_user.role:
        ensure_admin_continuity(target_user, new_role=new_role)

    before = {
        "username": target_user.username,
        "display_name": target_user.display_name,
        "email": target_user.email,
        "role": target_user.role,
    }
    target_user.username = cleaned_data["username"]
    target_user.display_name = cleaned_data["display_name"]
    target_user.email = cleaned_data.get("email", "")
    target_user.role = new_role
    password_changed = bool(cleaned_data.get("password1"))
    if password_changed:
        target_user.set_password(cleaned_data["password1"])
    target_user.save()

    links = target_user.student_links.filter(is_active=True)
    if new_role in {User.Role.ADMIN, User.Role.TEACHER}:
        links.update(is_active=False, is_primary=False)
    else:
        relationship = (
            StudentAccountLink.Relationship.SELF
            if new_role == User.Role.STUDENT
            else StudentAccountLink.Relationship.PARENT
        )
        links.update(relationship=relationship)

    after = {
        "username": target_user.username,
        "display_name": target_user.display_name,
        "email": target_user.email,
        "role": target_user.role,
    }
    changed = {
        key: {"before": before[key], "after": after[key]}
        for key in before
        if before[key] != after[key]
    }
    record_account_audit(
        request=request,
        target_user=target_user,
        action=AccountAuditLog.Action.USER_UPDATED,
        summary=f"{target_user.username} 계정 정보를 수정했습니다.",
        metadata={"changes": changed, "password_changed": password_changed},
    )
    return target_user


@transaction.atomic
def add_student_link(*, request, target_user: User, student_no: str, is_primary: bool) -> StudentAccountLink:
    ensure_target_manageable(request.user, target_user)
    relationship = (
        StudentAccountLink.Relationship.SELF
        if target_user.role == User.Role.STUDENT
        else StudentAccountLink.Relationship.PARENT
    )
    active_links = target_user.student_links.filter(is_active=True)
    should_be_primary = is_primary or not active_links.exists()
    if should_be_primary:
        active_links.update(is_primary=False)
    link, created = StudentAccountLink.objects.get_or_create(
        user=target_user,
        student_no=student_no,
        defaults={
            "relationship": relationship,
            "is_primary": should_be_primary,
            "is_active": True,
        },
    )
    if not created:
        link.relationship = relationship
        link.is_active = True
        link.is_primary = should_be_primary
        link.save(update_fields=("relationship", "is_active", "is_primary", "updated_at"))
    record_account_audit(
        request=request,
        target_user=target_user,
        action=AccountAuditLog.Action.LINK_ADDED,
        summary=f"{target_user.username} 계정에 학생 {student_no}을 연결했습니다.",
        metadata={"student_no": student_no, "is_primary": should_be_primary},
    )
    return link


@transaction.atomic
def set_primary_student_link(*, request, target_user: User, link: StudentAccountLink) -> None:
    ensure_target_manageable(request.user, target_user)
    if not link.is_active:
        raise ValidationError("해제된 학생 연결은 대표로 지정할 수 없습니다.")
    target_user.student_links.filter(is_active=True).update(is_primary=False)
    link.is_primary = True
    link.save(update_fields=("is_primary", "updated_at"))
    record_account_audit(
        request=request,
        target_user=target_user,
        action=AccountAuditLog.Action.LINK_PRIMARY,
        summary=f"{target_user.username} 계정의 대표 학생을 {link.student_no}으로 변경했습니다.",
        metadata={"student_no": link.student_no},
    )


@transaction.atomic
def deactivate_student_link(*, request, target_user: User, link: StudentAccountLink) -> None:
    ensure_target_manageable(request.user, target_user)
    was_primary = link.is_primary
    link.is_active = False
    link.is_primary = False
    link.save(update_fields=("is_active", "is_primary", "updated_at"))
    if was_primary:
        next_link = target_user.student_links.filter(is_active=True).order_by("id").first()
        if next_link:
            next_link.is_primary = True
            next_link.save(update_fields=("is_primary", "updated_at"))
    record_account_audit(
        request=request,
        target_user=target_user,
        action=AccountAuditLog.Action.LINK_DEACTIVATED,
        summary=f"{target_user.username} 계정에서 학생 {link.student_no} 연결을 해제했습니다.",
        metadata={"student_no": link.student_no},
    )


@transaction.atomic
def add_teacher_student_access(*, request, teacher: User, student_no: str, student_name: str) -> TeacherStudentAccess:
    ensure_target_manageable(request.user, teacher)
    if teacher.role != User.Role.TEACHER:
        raise ValidationError("강사 계정에만 담당 학생을 배정할 수 있습니다.")
    access, _ = TeacherStudentAccess.objects.get_or_create(
        teacher=teacher,
        student_no=student_no,
        defaults={
            "student_name": student_name,
            "assigned_by": request.user,
            "is_active": True,
        },
    )
    access.student_name = student_name
    access.assigned_by = request.user
    access.is_active = True
    access.save(update_fields=("student_name", "assigned_by", "is_active", "updated_at"))
    record_account_audit(
        request=request,
        target_user=teacher,
        action=AccountAuditLog.Action.TEACHER_STUDENT_ADDED,
        summary=f"{teacher.username} 강사에게 학생 {student_no}을 배정했습니다.",
        metadata={"student_no": student_no, "student_name": student_name},
    )
    return access


@transaction.atomic
def remove_teacher_student_access(*, request, teacher: User, access: TeacherStudentAccess) -> None:
    ensure_target_manageable(request.user, teacher)
    access.is_active = False
    access.save(update_fields=("is_active", "updated_at"))
    record_account_audit(
        request=request,
        target_user=teacher,
        action=AccountAuditLog.Action.TEACHER_STUDENT_REMOVED,
        summary=f"{teacher.username} 강사의 학생 {access.student_no} 배정을 해제했습니다.",
        metadata={"student_no": access.student_no},
    )
