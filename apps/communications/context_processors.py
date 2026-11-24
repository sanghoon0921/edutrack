from __future__ import annotations

from typing import Any

from .services import (
    visible_notices_for_user,
    visible_unread_notification_count,
)


CHAT_PAGE_VIEWS = {'lms:inbox', 'lms:conversation', 'lms:new-conversation', 'lms:conversation-members'}


def communication_summary(request) -> dict[str, Any]:
    user = request.user
    if not user.is_authenticated:
        return {
            "unread_notification_count": 0,
            "header_notifications": [],
            "latest_notice_preview": [],
        }

    resolver_match = getattr(request, "resolver_match", None)
    view_name = getattr(resolver_match, "view_name", "")

    # 대시보드에서만 공지 미리보기를 조회합니다. 다른 모든 화면은 상단
    # 숫자만 가볍게 계산해 공통 컨텍스트 프로세서의 반복 쿼리를 줄입니다.
    latest_notice_preview = []
    if view_name == "dashboard":
        latest_notice_preview = list(visible_notices_for_user(user)[:3])

    enabled = user.is_active and user.role != 'PARENT'
    chat_unread = 0
    if enabled:
        from apps.lms.message_queries import summary_queryset
        chat_unread = summary_queryset(user).filter(has_unread=True).count()
    notice_unread = visible_unread_notification_count(user)
    return {
        'messenger_enabled': enabled, 'chat_unread_count': chat_unread,
        # 메시지 페이지 안에서는 같은 기능이 겹치므로 오른쪽 아래 작은 메신저 버튼을 숨깁니다(11/16).
        'chat_fab_hidden': view_name in CHAT_PAGE_VIEWS,
        'portal_unread_total': notice_unread + chat_unread,
        "unread_notification_count": notice_unread,
        "header_notifications": [],
        "latest_notice_preview": latest_notice_preview,
    }
