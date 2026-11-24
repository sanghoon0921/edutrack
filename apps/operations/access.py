from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied

from apps.accounts.models import StudentAccountLink, User

from .models import TeacherStudentAccess


def is_admin(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN))


def is_ta(user) -> bool:
    return bool(user.is_authenticated and user.role == User.Role.TA)


def is_teacher(user) -> bool:
    return bool(user.is_authenticated and user.role == User.Role.TEACHER)


def teacher_student_ids(user) -> set[str]:
    if not is_teacher(user):
        return set()
    return set(
        TeacherStudentAccess.objects.filter(
            teacher=user,
            is_active=True,
        ).values_list("student_no", flat=True)
    )


def teacher_can_access_student(user, student_no: str) -> bool:
    if is_admin(user):
        return True
    if not is_teacher(user):
        return False
    return TeacherStudentAccess.objects.filter(
        teacher=user,
        student_no=str(student_no).strip(),
        is_active=True,
    ).exists()


def learner_student_ids(user) -> set[str]:
    if not user.is_authenticated or user.role not in {User.Role.STUDENT, User.Role.PARENT}:
        return set()

    values = {
        str(value).strip()
        for value in StudentAccountLink.objects.filter(
            user=user,
            is_active=True,
        ).values_list("student_no", flat=True)
        if str(value).strip()
    }

    # DB 연결이 있으면 환경변수의 과거 테스트 학생번호를 섞지 않습니다.
    if values:
        return values

    account_map = getattr(settings, "STUDENT_ACCOUNT_MAP", {})
    if isinstance(account_map, dict) and user.username in account_map:
        mapped = str(account_map[user.username]).strip()
        if mapped:
            values.add(mapped)

    if user.username == getattr(
        settings,
        "DEMO_STUDENT_USERNAME",
        "student_test",
    ):
        fallback = str(
            getattr(settings, "STUDENT_TEST_STUDENT_ID", "6333")
        ).strip()
        if fallback:
            values.add(fallback)

    return values


def class_student_ids(user) -> set[str]:
    """강사·TA가 담당하는 반(개설·지정)의 활성 학생번호(11/19). 관리자는 따로(전체 허용) 판단합니다."""
    if not (is_teacher(user) or is_ta(user)):
        return set()
    from apps.lms.access import staff_group_ids
    from apps.lms.models import GroupMember

    return {
        str(value).strip()
        for value in GroupMember.objects.filter(group_id__in=staff_group_ids(user), active=True).values_list("student_no", flat=True)
        if str(value).strip()
    }


def user_can_access_student(user, student_no: str) -> bool:
    cleaned = str(student_no).strip()
    if is_admin(user):
        return True
    if is_teacher(user):
        # 담당 학생 지정 + 자기 반 학생(11/19, 성적 분석 목록에서 누르면 열려야 함)
        return teacher_can_access_student(user, cleaned) or cleaned in class_student_ids(user)
    if is_ta(user):
        # TA(11/19): 담당 반 학생의 정보·DSG만
        return cleaned in class_student_ids(user)
    return cleaned in learner_student_ids(user)


def require_student_access(user, student_no: str, *, conceal: bool = False) -> None:
    if user_can_access_student(user, student_no):
        return
    if conceal:
        from django.http import Http404

        raise Http404("대상 정보를 찾을 수 없습니다.")
    raise PermissionDenied("담당하거나 연결된 학생 정보만 조회할 수 있습니다.")


def restrict_student_ids_for_user(user, student_ids: list[str] | set[str]) -> list[str]:
    cleaned = list(dict.fromkeys(str(item).strip() for item in student_ids if str(item).strip()))
    if is_admin(user):
        return cleaned
    if is_teacher(user):
        allowed = teacher_student_ids(user) | class_student_ids(user)
        return [student_id for student_id in cleaned if student_id in allowed]
    if is_ta(user):
        allowed = class_student_ids(user)
        return [student_id for student_id in cleaned if student_id in allowed]
    allowed = learner_student_ids(user)
    return [student_id for student_id in cleaned if student_id in allowed]
