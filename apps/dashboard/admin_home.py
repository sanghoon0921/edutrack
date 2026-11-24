"""관리자 홈: 오늘 처리할 일(실제 숫자)과 최근 공지·메시지. 자체 DB만 읽어 인트라넷이 느려도 홈이 먼저 뜹니다."""
from datetime import timedelta

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.communications.models import Notice
from apps.learning.models import Quiz
from apps.lms.access import visible_groups
from apps.lms.message_queries import message_summary

from .student_home import home_clock, home_notices


def home_context(user):
    now = timezone.now()
    week = now + timedelta(days=7)
    messages = message_summary(user, 5)
    queue = [
        {"key": "feedback", "label": "채점할 제출", "icon": "clipboard", "area": "learning",
         "count": AssignmentRecipient.objects.filter(submission__submitted_at__isnull=False,
                                                     submission__feedback_at__isnull=True).count(),
         "url": reverse("lms:gradebook") + "?kind=assignment"},
        {"key": "due_week", "label": "이번 주 마감 과제", "icon": "clock", "area": "learning",
         "count": Assignment.objects.filter(is_published=True, due_at__gte=now, due_at__lt=week).count(),
         "url": reverse("assignments:list")},
        {"key": "quiz_week", "label": "이번 주 마감 퀴즈", "icon": "list-check", "area": "learning",
         "count": Quiz.objects.filter(is_published=True, due_at__gte=now, due_at__lt=week).count(),
         "url": reverse("learning:quiz-list")},
        {"key": "messages", "label": "안 읽은 메시지", "icon": "message", "area": "messages",
         "count": messages["unread_count"], "url": reverse("lms:inbox")},
        {"key": "notices_week", "label": "최근 7일 공지", "icon": "megaphone", "area": "notices",
         "count": Notice.objects.filter(is_published=True, published_at__gte=now - timedelta(days=7)).count(),
         "url": reverse("communications:notice-manage")},
    ]
    accounts = dict(User.objects.filter(is_active=True).values_list("role").annotate(n=Count("pk")).values_list("role", "n"))
    return {"admin_home": {
        "today": home_clock()[0],
        "queue": queue,
        "notices": home_notices(user, visible_groups(user), 5),
        "messages": messages,
        "accounts": [(label, accounts.get(role, 0)) for role, label in User.Role.choices],
    }}
