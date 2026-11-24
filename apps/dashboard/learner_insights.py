"""학생·학부모 홈 '한눈에 보기'(11/10): 최근 본 시험, 평균 점수·출석률·과제 제출률 도넛, 최근 리포트카드.
DSG·인트라넷을 읽으므로 홈이 먼저 뜬 뒤 /home/insights/ 로 따로 불러옵니다. 한 곳이 실패해도 나머지는 보입니다."""
from __future__ import annotations

import logging

from django.urls import reverse
from django.utils import timezone

from apps.accounts.student_links import get_linked_student_nos

logger = logging.getLogger(__name__)
SAT_MAX = 1600


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _exam(student_no):
    from apps.assessments.services import AssessmentService
    try:
        overview = AssessmentService().get_student_overview(student_no)
    except Exception as error:  # DSG 장애가 홈을 막지 않게
        logger.warning('home_insight_exam_unavailable type=%s', type(error).__name__)
        return {'state': 'error'}
    if overview.status != 'ok':
        return {'state': overview.status}
    latest = next((a for a in overview.recent_attempts if a.total_sat_score), None) or (overview.recent_attempts[0] if overview.recent_attempts else None)
    average = round(overview.average_total_score) if overview.average_total_score is not None else None
    return {
        'state': 'ok',
        'name': latest.exam_name if latest else '',
        'date': timezone.localtime(latest.exam_date) if latest and latest.exam_date and timezone.is_aware(latest.exam_date) else (latest.exam_date if latest else None),
        'total': overview.latest_total_score,
        'rw': overview.latest_rw_score,
        'math': overview.latest_math_score,
        'rw_pct': _pct(overview.latest_rw_score or 0, 800),
        'math_pct': _pct(overview.latest_math_score or 0, 800),
        'delta': overview.previous_delta,
        'average': average,
        'average_pct': _pct(average or 0, SAT_MAX) if average else None,
        'highest': overview.highest_total_score,
        'count': overview.full_sat_count,
    }


def _attendance(student_no):
    from apps.students.views import get_attendance_service, get_course_service
    try:
        groups = get_course_service().get_student_course_groups(student_no)
        current = groups['current'] or groups['completed'][:1]
        results = get_attendance_service().get_attendance_for_courses(student_no, [c.assign_id for c in current])
    except Exception as error:
        logger.warning('home_insight_attendance_unavailable type=%s', type(error).__name__)
        return {'state': 'error'}
    done = attended = 0
    for _records, summary in results.values():
        done += summary.completed_count
        attended += summary.present_count + summary.late_count + summary.recorded_count
    return {'state': 'ok' if done else 'empty', 'value': _pct(attended, done), 'attended': attended, 'done': done,
            'courses': len(current)}


def _assignments(student_nos):
    from apps.assignments.models import AssignmentRecipient
    due = (AssignmentRecipient.objects.filter(student_id__in=student_nos, assignment__is_published=True,
                                              assignment__due_at__lte=timezone.now()))
    total = due.count()
    submitted = due.filter(submission__submitted_at__isnull=False).count()
    return {'state': 'ok' if total else 'empty', 'value': _pct(submitted, total), 'submitted': submitted, 'total': total}


def _report_card(student_nos):
    from apps.reports.formats import FORMS
    from apps.reports.models import ReportCard
    card = (ReportCard.objects.filter(student_no__in=student_nos, batch__published_at__isnull=False)
            .select_related('batch', 'batch__group').order_by('-batch__published_at').first())
    if not card:
        return None
    return {'url': reverse('reports:my-card', args=[card.pk]), 'group': card.batch.group.title, 'title': card.batch.title,
            'form': FORMS.get(card.batch.form, {}).get('label', card.batch.form), 'published_at': card.batch.published_at}


def insight_context(user) -> dict:
    nos = get_linked_student_nos(user)
    if not nos:
        return {'linked': False}
    primary = nos[0]
    return {'linked': True, 'exam': _exam(primary), 'attendance': _attendance(primary), 'assignments': _assignments(nos),
            'report': _report_card(nos)}
