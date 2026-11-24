from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.accounts.student_links import get_linked_student_nos

from config.cache_utils import (
    build_cache_key,
    safe_cache_delete,
    safe_cache_get,
    safe_cache_set,
)

from .models import Notice, NoticeRead, Notification


UserModel = get_user_model()


# 역할 → 그 역할이 받는 공지의 대상 체크 칸
ROLE_FLAG = {
    User.Role.ADMIN: "for_admin",
    User.Role.TEACHER: "for_teacher",
    User.Role.STUDENT: "for_student",
    User.Role.PARENT: "for_parent",
}


@dataclass(frozen=True)
class _RecipientTarget:
    resource: str
    recipient_id: int


_RECIPIENT_PATH_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "assignment",
        re.compile(r"(?:^|/)assignments/my/(?P<recipient_id>\d+)/?$")
    ),
    (
        "discussion",
        re.compile(r"(?:^|/)learning/my/discussions/(?P<recipient_id>\d+)/?$")
    ),
    (
        "quiz",
        re.compile(r"(?:^|/)learning/my/quizzes/(?P<recipient_id>\d+)/?$")
    ),
)
_ASSIGNMENT_EVENT_PATTERN = re.compile(
    r"^assignment:\d+:recipient:(?P<recipient_id>\d+)$"
)
_FEEDBACK_EVENT_PATTERN = re.compile(
    r"^feedback:(?P<submission_id>\d+):\d+$"
)
_DISCUSSION_EVENT_PATTERN = re.compile(
    r"^discussion:\d+:recipient:(?P<recipient_id>\d+)$"
)
_QUIZ_EVENT_PATTERN = re.compile(
    r"^quiz:\d+:recipient:(?P<recipient_id>\d+)$"
)


def _notification_header_cache_key(user_id: int) -> str:
    return build_cache_key(
        "communications",
        "notification-header",
        "v1",
        int(user_id),
    )


def invalidate_notification_header_cache(user_id: int | None) -> None:
    if user_id is None:
        return
    safe_cache_delete(_notification_header_cache_key(int(user_id)))


def _audience_scope(user) -> Q:
    """공지 대상에 이 사용자의 역할이 체크돼 있어야 보입니다(최고 관리자는 모든 대상)."""
    if user.is_superuser:
        return Q()
    flag = ROLE_FLAG.get(user.role)
    return Q(**{flag: True}) if flag else Q(pk__in=[])


def _class_notice_scope(user) -> Q:
    """반 공지는 그 반 학생·학부모와 그 반 강사에게만 보입니다(관리자는 모두)."""
    from apps.lms.access import visible_groups  # lms 앱이 이 모듈을 쓰므로 여기서 가져옵니다

    if user.is_superuser or user.role == User.Role.ADMIN:
        return Q()
    return ~Q(category=Notice.Category.CLASS) | Q(group__in=visible_groups(user))


def visible_notices_for_user(user) -> QuerySet[Notice]:
    if not user.is_authenticated:
        return Notice.objects.none()

    return Notice.objects.filter(
        _class_notice_scope(user),
        is_published=True,
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    ).filter(_audience_scope(user)).select_related("created_by", "group")


def can_view_notice(user, notice: Notice) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.role == User.Role.ADMIN:
        return True
    return (
        notice.is_published
        and notice.published_at is not None
        and notice.published_at <= timezone.now()
        and Notice.objects.filter(_class_notice_scope(user), _audience_scope(user), pk=notice.pk).exists()
    )


def users_for_notice(notice: Notice) -> QuerySet:
    users = _users_for_audience(notice)
    if notice.category != Notice.Category.CLASS:
        return users
    # 반 공지: 관리자, 그 반 강사(개설자·담당), 그 반 학생·학부모만 알림을 받습니다.
    from apps.lms.models import GroupMember

    members = GroupMember.objects.filter(group_id=notice.group_id, active=True).values("student_no")
    return users.filter(
        Q(is_superuser=True)
        | Q(role=User.Role.ADMIN)
        | Q(role=User.Role.TEACHER, created_learning_groups__pk=notice.group_id)
        | Q(role=User.Role.TEACHER, lms_teaching_groups__group_id=notice.group_id, lms_teaching_groups__active=True)
        | Q(student_links__is_active=True, student_links__student_no__in=members)
    ).distinct()


def _users_for_audience(notice: Notice) -> QuerySet:
    """체크된 대상 그룹의 활성 사용자(관리자 그룹이면 최고 관리자 포함)."""
    roles = [role for role, flag in ROLE_FLAG.items() if getattr(notice, flag)]
    if not roles:
        return UserModel.objects.none()
    match = Q(role__in=roles)
    if notice.for_admin:
        match |= Q(is_superuser=True)
    return UserModel.objects.filter(match, is_active=True)


def create_notification(
    *,
    user,
    kind: str,
    title: str,
    message: str = "",
    target_url: str = "",
    event_key: str = "",
) -> Notification | None:
    if not user or not user.is_active:
        return None

    defaults = {
        "kind": kind,
        "title": title,
        "message": message,
        "target_url": target_url,
    }

    if event_key:
        notification, _ = Notification.objects.update_or_create(
            user=user,
            event_key=event_key,
            defaults=defaults,
        )
        return notification

    return Notification.objects.create(user=user, **defaults)


def create_notifications(
    users: Iterable,
    *,
    kind: str,
    title: str,
    message: str = "",
    target_url: str = "",
    event_key: str = "",
) -> None:
    for user in users:
        create_notification(
            user=user,
            kind=kind,
            title=title,
            message=message,
            target_url=target_url,
            event_key=event_key,
        )


def notify_notice_published(notice: Notice) -> None:
    if not notice.is_published:
        return

    create_notifications(
        users_for_notice(notice).iterator(),
        kind=Notification.Kind.NOTICE,
        title=f"새 공지: {notice.title}",
        message=notice.content[:180],
        target_url=reverse(
            "communications:notice-detail",
            kwargs={"notice_id": notice.pk},
        ),
        event_key=f"notice:{notice.pk}:published",
    )


def learner_users_for_student(student_id: str) -> QuerySet:
    cleaned_id = str(student_id).strip()
    if not cleaned_id:
        return UserModel.objects.none()

    linked_user_ids = StudentAccountLink.objects.filter(
        student_no=cleaned_id,
        is_active=True,
        user__is_active=True,
        user__role__in=(User.Role.STUDENT, User.Role.PARENT),
    ).values_list("user_id", flat=True)

    fallback = Q(username=cleaned_id, role=User.Role.STUDENT)

    demo_student_username = str(
        getattr(settings, "DEMO_STUDENT_USERNAME", "student_test")
    ).strip()
    demo_fallback_student_no = str(
        getattr(settings, "STUDENT_TEST_STUDENT_ID", "")
    ).strip()

    # 테스트 계정에 활성 DB 연결이 없을 때만 과거 환경변수 연결을 보완합니다.
    # 관리자가 다른 학생을 선택한 뒤 이전 학생 알림을 계속 받는 일을 막습니다.
    demo_has_active_link = StudentAccountLink.objects.filter(
        user__username=demo_student_username,
        user__role=User.Role.STUDENT,
        user__is_active=True,
        is_active=True,
    ).exists()
    if (
        not demo_has_active_link
        and cleaned_id == demo_fallback_student_no
        and demo_student_username
    ):
        fallback |= Q(
            username=demo_student_username,
            role=User.Role.STUDENT,
        )

    return UserModel.objects.filter(
        Q(pk__in=linked_user_ids) | fallback,
        is_active=True,
    ).distinct()


def _linked_student_nos_for_notification_user(user) -> set[str]:
    """현재 계정이 실제로 열 수 있는 학생번호만 반환합니다."""

    linked = {
        str(student_no).strip()
        for student_no in get_linked_student_nos(user)
        if str(student_no).strip()
    }
    if linked:
        # 활성 DB 연결이 있으면 설정값이나 과거 테스트 연결을 섞지 않습니다.
        return linked

    username = str(getattr(user, "username", "")).strip()
    account_map = getattr(settings, "STUDENT_ACCOUNT_MAP", {})
    if isinstance(account_map, dict):
        mapped = str(account_map.get(username, "")).strip()
        if mapped:
            linked.add(mapped)

    demo_usernames = {
        str(getattr(settings, "DEMO_STUDENT_USERNAME", "student_test")).strip(),
        str(getattr(settings, "DEMO_PARENT_USERNAME", "parent_test")).strip(),
    }
    if username in demo_usernames:
        fallback = str(
            getattr(settings, "STUDENT_TEST_STUDENT_ID", "")
        ).strip()
        if fallback:
            linked.add(fallback)

    if getattr(user, "role", "") == User.Role.STUDENT and username:
        linked.add(username)

    return linked


def _recipient_target_for_notification(
    notification: Notification,
) -> _RecipientTarget | None:
    path = urlsplit(notification.target_url or "").path
    for resource, pattern in _RECIPIENT_PATH_PATTERNS:
        match = pattern.search(path)
        if match:
            return _RecipientTarget(
                resource=resource,
                recipient_id=int(match.group("recipient_id")),
            )

    event_key = notification.event_key or ""
    match = _ASSIGNMENT_EVENT_PATTERN.match(event_key)
    if match:
        return _RecipientTarget(
            resource="assignment",
            recipient_id=int(match.group("recipient_id")),
        )

    match = _FEEDBACK_EVENT_PATTERN.match(event_key)
    if match:
        return _RecipientTarget(
            resource="feedback_submission",
            recipient_id=int(match.group("submission_id")),
        )

    match = _DISCUSSION_EVENT_PATTERN.match(event_key)
    if match:
        return _RecipientTarget(
            resource="discussion",
            recipient_id=int(match.group("recipient_id")),
        )

    match = _QUIZ_EVENT_PATTERN.match(event_key)
    if match:
        return _RecipientTarget(
            resource="quiz",
            recipient_id=int(match.group("recipient_id")),
        )

    return None


def _requires_recipient_scope(notification: Notification) -> bool:
    if notification.kind in {
        Notification.Kind.ASSIGNMENT,
        Notification.Kind.FEEDBACK,
    }:
        return True

    event_key = notification.event_key or ""
    return event_key.startswith(("discussion:", "quiz:"))


def _valid_recipient_targets(
    targets: set[_RecipientTarget],
    *,
    student_nos: set[str],
) -> set[_RecipientTarget]:
    if not targets or not student_nos:
        return set()

    from apps.assignments.models import AssignmentRecipient, Submission
    from apps.learning.models import DiscussionRecipient, QuizRecipient

    now = timezone.now()
    valid: set[_RecipientTarget] = set()

    assignment_ids = {
        target.recipient_id
        for target in targets
        if target.resource == "assignment"
    }
    if assignment_ids:
        rows = (
            AssignmentRecipient.objects.filter(
                pk__in=assignment_ids,
                student_id__in=student_nos,
                assignment__is_published=True,
            )
            .filter(
                Q(assignment__available_from__isnull=True)
                | Q(assignment__available_from__lte=now)
            )
            .values_list("pk", flat=True)
        )
        valid.update(
            _RecipientTarget("assignment", int(recipient_id))
            for recipient_id in rows
        )

    feedback_submission_ids = {
        target.recipient_id
        for target in targets
        if target.resource == "feedback_submission"
    }
    if feedback_submission_ids:
        rows = (
            Submission.objects.filter(
                pk__in=feedback_submission_ids,
                feedback_at__isnull=False,
                recipient__student_id__in=student_nos,
                recipient__assignment__is_published=True,
            )
            .filter(
                Q(recipient__assignment__available_from__isnull=True)
                | Q(recipient__assignment__available_from__lte=now)
            )
            .values_list("pk", flat=True)
        )
        valid.update(
            _RecipientTarget("feedback_submission", int(submission_id))
            for submission_id in rows
        )

    discussion_ids = {
        target.recipient_id
        for target in targets
        if target.resource == "discussion"
    }
    if discussion_ids:
        rows = (
            DiscussionRecipient.objects.filter(
                pk__in=discussion_ids,
                student_id__in=student_nos,
                discussion__is_published=True,
            )
            .filter(
                Q(discussion__available_from__isnull=True)
                | Q(discussion__available_from__lte=now)
            )
            .values_list("pk", flat=True)
        )
        valid.update(
            _RecipientTarget("discussion", int(recipient_id))
            for recipient_id in rows
        )

    quiz_ids = {
        target.recipient_id
        for target in targets
        if target.resource == "quiz"
    }
    if quiz_ids:
        rows = (
            QuizRecipient.objects.filter(
                pk__in=quiz_ids,
                student_id__in=student_nos,
                quiz__is_published=True,
            )
            .filter(
                Q(quiz__available_from__isnull=True)
                | Q(quiz__available_from__lte=now)
            )
            .values_list("pk", flat=True)
        )
        valid.update(
            _RecipientTarget("quiz", int(recipient_id))
            for recipient_id in rows
        )

    return valid


def _filter_visible_notifications(
    user,
    notifications: Sequence[Notification],
) -> list[Notification]:
    if not notifications:
        return []

    if user.is_superuser or user.role not in {
        User.Role.STUDENT,
        User.Role.PARENT,
    }:
        return list(notifications)

    targets_by_notification: dict[int, _RecipientTarget | None] = {
        notification.pk: _recipient_target_for_notification(notification)
        for notification in notifications
    }
    targets = {
        target
        for target in targets_by_notification.values()
        if target is not None
    }
    valid_targets = _valid_recipient_targets(
        targets,
        student_nos=_linked_student_nos_for_notification_user(user),
    )

    visible: list[Notification] = []
    for notification in notifications:
        target = targets_by_notification[notification.pk]
        if target is not None:
            if target in valid_targets:
                visible.append(notification)
            continue

        # 과제·피드백 알림인데 대상 정보를 해석할 수 없으면 안전하게 숨깁니다.
        if _requires_recipient_scope(notification):
            continue
        visible.append(notification)

    return visible


def visible_unread_notification_count(
    user,
    *,
    cap: int = 100,
) -> int:
    """
    상단 알림 배지용 읽지 않은 알림 수를 가볍게 계산합니다.

    관리자·강사는 인덱스가 적용된 읽지 않은 알림만 제한 조회합니다.
    학생·학부모는 현재 연결 학생의 실제 배정 대상까지 확인하되, 화면마다
    전체 알림 이력을 불러오지 않도록 최근 읽지 않은 후보만 검사합니다.
    """

    if not getattr(user, "is_authenticated", False):
        return 0

    try:
        normalized_cap = max(1, int(cap))
    except (TypeError, ValueError):
        normalized_cap = 100

    cache_key = _notification_header_cache_key(user.id)
    cached = safe_cache_get(cache_key, None)
    if cached is not None:
        try:
            return max(0, min(normalized_cap, int(cached)))
        except (TypeError, ValueError):
            pass

    unread = Notification.objects.filter(user=user, is_read=False)

    if user.is_superuser or user.role not in {
        User.Role.STUDENT,
        User.Role.PARENT,
    }:
        count = len(
            list(
                unread.order_by("-created_at", "-id")
                .values_list("pk", flat=True)[:normalized_cap]
            )
        )
    else:
        try:
            scan_limit = max(
                normalized_cap,
                int(
                    getattr(
                        settings,
                        "COMMUNICATION_HEADER_SCAN_LIMIT",
                        500,
                    )
                ),
            )
        except (TypeError, ValueError):
            scan_limit = max(normalized_cap, 500)

        candidates = list(
            unread.only(
                "id",
                "user_id",
                "kind",
                "target_url",
                "event_key",
                "is_read",
                "created_at",
            )[:scan_limit]
        )
        count = min(
            normalized_cap,
            len(_filter_visible_notifications(user, candidates)),
        )

    try:
        timeout = max(
            0,
            int(
                getattr(
                    settings,
                    "COMMUNICATION_HEADER_CACHE_SECONDS",
                    15,
                )
            ),
        )
    except (TypeError, ValueError):
        timeout = 15

    if timeout > 0:
        safe_cache_set(cache_key, count, timeout=timeout)
    return count


def visible_notifications_for_user(
    user,
    *,
    limit: int | None = None,
) -> list[Notification]:
    """
    현재 계정이 실제로 열 수 있는 알림만 반환합니다.

    학생·학부모 알림은 현재 활성 학생 연결과 과제·토론·퀴즈 대상 레코드를
    함께 확인합니다. 테스트 계정을 다른 학생으로 전환한 뒤 남은 과거 알림도
    목록과 배지에서 자동으로 제외됩니다.
    """

    if not user.is_authenticated:
        return []

    notifications = list(Notification.objects.filter(user=user))
    visible = _filter_visible_notifications(user, notifications)
    if limit is not None:
        return visible[: max(0, int(limit))]
    return visible


def notification_is_visible_to_user(
    user,
    notification: Notification,
) -> bool:
    if not user.is_authenticated or notification.user_id != user.id:
        return False
    return bool(_filter_visible_notifications(user, [notification]))


def mark_notice_read(user, notice: Notice) -> None:
    NoticeRead.objects.get_or_create(notice=notice, user=user)
    updated = Notification.objects.filter(
        user=user,
        event_key=f"notice:{notice.pk}:published",
        is_read=False,
    ).update(is_read=True, read_at=timezone.now())
    if updated:
        invalidate_notification_header_cache(user.id)
