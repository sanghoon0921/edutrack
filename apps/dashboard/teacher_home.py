"""Teacher home (11/10): 할 일을 먼저 — 반별 피드백 대기, 작성 중인 리포트카드, 7일 안 마감, 그다음 공지·메시지·Zoom.
Local data only so a slow intranet does not block the page."""
from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.assignments.models import Assignment, AssignmentRecipient
from apps.learning.models import Quiz
from apps.lms.access import staff_scope, visible_groups
from apps.lms.message_queries import message_summary
from apps.lms.models import RoomSettings

from .student_home import home_clock, home_notices, safe_zoom_url


def _pending_by_group(user):
    rows = (AssignmentRecipient.objects
            .filter(assignment__in=staff_scope(Assignment.objects.all(), user),
                    submission__submitted_at__isnull=False, submission__feedback_at__isnull=True)
            .values('assignment__group_id', 'assignment__group__title').annotate(n=Count('pk')).order_by('-n')[:6])
    return [{'title': r['assignment__group__title'] or '반 없음', 'count': r['n'],
             'url': reverse('lms:gradebook') + (f"?group={r['assignment__group_id']}&kind=assignment" if r['assignment__group_id'] else '?kind=assignment')}
            for r in rows]


def _report_drafts(groups):
    from apps.reports.formats import FORMS
    from apps.reports.models import ReportBatch
    batches = (ReportBatch.objects.filter(group__in=groups, published_at__isnull=True).select_related('group')
               .annotate(cards_n=Count('cards')).order_by('-updated_at')[:5])
    return [{'title': f'{b.group.title} · {b.title}', 'form': FORMS.get(b.form, {}).get('label', b.form), 'cards': b.cards_n,
             'url': reverse('reports:batch', args=[b.pk])} for b in batches]


def _upcoming(user, now):
    soon = now + timedelta(days=7)
    items = []
    for a in staff_scope(Assignment.objects.filter(due_at__gte=now, due_at__lte=soon), user).select_related('group').order_by('due_at')[:5]:
        items.append({'kind': '과제', 'title': a.title, 'group': a.group.title if a.group else '', 'due_at': a.due_at,
                      'url': reverse('assignments:detail', args=[a.pk])})
    for q in staff_scope(Quiz.objects.filter(due_at__gte=now, due_at__lte=soon), user).select_related('group').order_by('due_at')[:5]:
        items.append({'kind': '퀴즈', 'title': q.title, 'group': q.group.title if q.group else '', 'due_at': q.due_at,
                      'url': reverse('learning:quiz-detail', args=[q.pk])})
    return sorted(items, key=lambda i: i['due_at'])[:6]


def home_context(user):
    groups = visible_groups(user)
    now = timezone.now()
    rooms = [{'title': s.group.title, 'url': safe_zoom_url(s.zoom_url), 'schedule': s.schedule}
             for s in RoomSettings.objects.filter(group__in=groups).select_related('group')[:8]]
    pending = _pending_by_group(user)
    drafts = _report_drafts(groups)
    return {'teacher_home': {'today': home_clock()[0], 'notices': home_notices(user, groups, 5),
                             'messages': message_summary(user, 5), 'rooms': rooms,
                             'pending': sum(p['count'] for p in pending), 'pending_groups': pending,
                             'drafts': drafts, 'upcoming': _upcoming(user, now), 'group_count': groups.count()}}
