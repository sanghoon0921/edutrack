from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser

from .models import StudentAccountLink


def get_primary_student_no(
    user: AbstractBaseUser,
) -> str | None:
    """로그인 계정에 연결된 대표 학생번호를 반환합니다."""

    if not user.is_authenticated:
        return None

    link = (
        StudentAccountLink.objects
        .filter(
            user=user,
            is_active=True,
        )
        .order_by(
            "-is_primary",
            "id",
        )
        .first()
    )

    if link is None:
        return None

    return link.student_no


def get_primary_student_no_by_username(
    username: str,
) -> str | None:
    """사용자명으로 대표 학생번호를 찾습니다."""

    cleaned_username = str(username).strip()

    if not cleaned_username:
        return None

    link = (
        StudentAccountLink.objects
        .filter(
            user__username=cleaned_username,
            user__is_active=True,
            is_active=True,
        )
        .order_by(
            "-is_primary",
            "id",
        )
        .first()
    )

    if link is None:
        return None

    return link.student_no


def get_linked_student_nos(
    user: AbstractBaseUser,
) -> list[str]:
    """계정에 연결된 모든 활성 학생번호를 반환합니다."""

    if not user.is_authenticated:
        return []

    return list(
        StudentAccountLink.objects
        .filter(
            user=user,
            is_active=True,
        )
        .order_by(
            "-is_primary",
            "id",
        )
        .values_list(
            "student_no",
            flat=True,
        )
    )
