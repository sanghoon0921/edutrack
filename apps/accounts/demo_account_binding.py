from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from .models import StudentAccountLink, User


@dataclass(frozen=True)
class DemoAccountBindingResult:
    student_username: str
    parent_username: str
    student_no: str
    updated_count: int


def demo_account_auto_binding_enabled() -> bool:
    """관리자가 선택한 학생으로 테스트 계정을 전환할지 반환합니다."""

    configured = getattr(
        settings,
        "ADMIN_AUTO_LINK_TEST_ACCOUNTS",
        settings.DEBUG,
    )
    if isinstance(configured, str):
        return configured.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(configured)


@transaction.atomic
def bind_demo_accounts_to_student(
    student_no: str,
) -> DemoAccountBindingResult:
    """
    ``student_test``와 ``parent_test``의 대표 학생을 한 번에 전환합니다.

    테스트 계정의 기존 활성 연결은 해제하지만 이력 행 자체는 남겨 둡니다.
    해당 계정이 아직 생성되지 않은 경우에는 존재하는 계정만 처리합니다.
    """

    cleaned_student_no = str(student_no).strip()
    if not cleaned_student_no:
        raise ValueError("학생번호가 필요합니다.")

    student_username = str(
        getattr(settings, "DEMO_STUDENT_USERNAME", "student_test")
    ).strip()
    parent_username = str(
        getattr(settings, "DEMO_PARENT_USERNAME", "parent_test")
    ).strip()

    targets = (
        (
            student_username,
            User.Role.STUDENT,
            StudentAccountLink.Relationship.SELF,
        ),
        (
            parent_username,
            User.Role.PARENT,
            StudentAccountLink.Relationship.PARENT,
        ),
    )

    updated_count = 0

    for username, expected_role, relationship in targets:
        if not username:
            continue

        user = (
            User.objects.select_for_update()
            .filter(
                username=username,
                role=expected_role,
            )
            .first()
        )
        if user is None:
            continue

        StudentAccountLink.objects.filter(
            user=user,
            is_active=True,
        ).exclude(
            student_no=cleaned_student_no,
        ).update(
            is_active=False,
            is_primary=False,
        )

        StudentAccountLink.objects.filter(
            user=user,
            is_active=True,
        ).update(is_primary=False)

        link, _ = StudentAccountLink.objects.get_or_create(
            user=user,
            student_no=cleaned_student_no,
            defaults={
                "relationship": relationship,
                "is_primary": True,
                "is_active": True,
            },
        )

        changed_fields: list[str] = []
        if link.relationship != relationship:
            link.relationship = relationship
            changed_fields.append("relationship")
        if not link.is_active:
            link.is_active = True
            changed_fields.append("is_active")
        if not link.is_primary:
            link.is_primary = True
            changed_fields.append("is_primary")
        if changed_fields:
            changed_fields.append("updated_at")
            link.save(update_fields=changed_fields)

        updated_count += 1

    return DemoAccountBindingResult(
        student_username=student_username,
        parent_username=parent_username,
        student_no=cleaned_student_no,
        updated_count=updated_count,
    )
