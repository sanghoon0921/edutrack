"""리포트카드에 자동으로 채울 값을 모읍니다.

- LMS: 그 반에 낸 과제·퀴즈 → 주차별 제출 여부, 점수 목록, 요일별 PASS/FAIL, 요일별 퀴즈 점수
- 인트라넷: 학생 국가·학교·학년, (수업을 고르면) 수업일
- DSG(SAT): 이번 주·지난주 모의고사와 같은 시험을 본 반 학생 평균

순수 계산 함수는 날짜·Task 목록만 받으므로 따로 시험합니다(tests/test_sources.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)
WEEKDAYS = ('월', '화', '수', '목', '금')


@dataclass(frozen=True)
class Task:
    kind: str  # 'HW' 과제, 'QUIZ' 퀴즈
    title: str
    due: date
    submitted: bool
    score: Decimal | None
    points: Decimal | None
    open: bool = False  # 마감 전(아직 안 냈어도 미제출이 아님)

    @property
    def waiting(self) -> bool:
        return self.open and not self.submitted


def number(value) -> str:
    """13.00 → '13', 117.50 → '117.5'."""
    if value is None or value == '':
        return ''
    text = format(Decimal(value).normalize(), 'f')
    return text


def week_no(day: date, base: date) -> int:
    return (day - base).days // 7 + 1


def week_start(n: int, base: date) -> date:
    return base + timedelta(days=7 * (n - 1))


def weeks_label(base: date, start: date, end: date) -> str:
    first, last = week_no(start, base), week_no(end, base)
    return f'WEEK{first}' if first == last else f'WEEK{first}-{last}'


def submit_status(tasks: list[Task]) -> str:
    tasks = [t for t in tasks if not t.waiting]
    if not tasks:
        return '진행중'
    done = sum(1 for t in tasks if t.submitted)
    if done == len(tasks):
        return '제출완료'
    return '미제출' if done == 0 else '일부제출'


def week_status(tasks: list[Task], base: date, start: date, end: date, total: int = 16) -> list[dict]:
    """1주차부터 기간 끝 주차까지 채우고, 그 뒤 주차는 빈 칸(아직 안 온 주)."""
    last = week_no(end, base)
    rows = []
    for n in range(1, total + 1):
        if n > last:
            rows.append({'label': f'WEEK{n}', 'status': ''})
            continue
        week = [t for t in tasks if week_no(t.due, base) == n]
        rows.append({'label': f'WEEK{n}', 'status': submit_status(week) if week else '해당없음'})
    return rows


def lesson_status(tasks: list[Task], lessons, end: date) -> list[dict]:
    """인트라넷 수업을 고르면 WEEK 대신 수업일(개강~종강)마다: 그 수업일부터 다음 수업일 전까지 마감인 과제·퀴즈."""
    days = sorted(set(lessons))
    rows = []
    for i, day in enumerate(days):
        label = f'{day.month}/{day.day}'
        if day > end:
            rows.append({'label': label, 'status': ''})
            continue
        upto = days[i + 1] if i + 1 < len(days) else None
        span = [t for t in tasks if t.due >= day and (upto is None or t.due < upto)]
        rows.append({'label': label, 'status': submit_status(span) if span else '해당없음'})
    return rows


def score_lines(tasks: list[Task], base: date, start: date, end: date) -> str:
    lines = []
    for t in sorted((t for t in tasks if start <= t.due <= end), key=lambda t: (t.due, t.title)):
        if t.waiting:
            result = '마감 전'
        elif not t.submitted:
            result = '미제출'
        elif t.score is None:
            result = '채점 전'
        else:
            result = f'{number(t.score)}/{number(t.points)}'
        lines.append(f'W{week_no(t.due, base)} {t.title} {result}')
    return '\n'.join(lines)


# 출결(인트라넷) → Skill Mastery 칸. 출석·지각은 PASS, 결석은 FAIL, 나머지는 그 상태 이름.
SKILL_BY_STATUS = {'present': 'PASS', 'late': 'PASS', 'absent': 'FAIL', 'recorded': '녹화', 'carried': '이월',
                   'refunded': '환불', 'holiday': '학원휴강', 'cancelled': '개별취소'}
NO_LESSON = '수업미지정일'
# 과제 칸에서도 PASS/FAIL 대신 그대로 보여 줄 날(운영팀 10/29: 이월·환불·수업 미지정일)
DAY_OVERRIDES = ('이월', '환불', NO_LESSON)


# ── 주간·월간 카드의 날짜 5칸 ─────────────────────────────────────────────
# 기간이 한 주 안이면 월~금 하루씩, 그보다 길면(월간 리포트, 운영팀 11/17 새 디자인) 기간 시작일부터 7일씩 5칸.
SLOTS = 5


def daily_spans(monday: date) -> list[tuple[date, date]]:
    return [(monday + timedelta(days=i), monday + timedelta(days=i + 1)) for i in range(SLOTS)]


def card_spans(start: date, end: date) -> list[tuple[date | None, date | None]]:
    """카드의 날짜 칸마다 (시작일, 끝 다음 날). 기간 밖의 칸은 (None, None)."""
    if (end - start).days <= 6:
        return daily_spans(start - timedelta(days=start.weekday()))
    spans = []
    for i in range(SLOTS):
        first = start + timedelta(days=7 * i)
        spans.append((first, min(first + timedelta(days=7), end + timedelta(days=1))) if first <= end else (None, None))
    return spans


def span_labels(start: date, end: date) -> list[str]:
    """날짜 칸 머리: 한 주면 '11/17(월)', 월간이면 칸이 시작하는 날 '9/26'."""
    spans = card_spans(start, end)
    daily = (end - start).days <= 6
    return [(f'{a.month}/{a.day}' + (f'({WEEKDAYS[i]})' if daily else '')) if a else '' for i, (a, _) in enumerate(spans)]


def _kind(record) -> str:
    """출결 종류. 수납 상태가 이월(CARRY_OVER)인 회차는 출결 코드가 아직 없어도 이월로 봅니다(11/20)."""
    return 'carried' if getattr(record, 'payment_code', '') == 'CARRY_OVER' else record.status_kind


def _within(day, span) -> bool:
    a, b = span
    return bool(a and day and a <= day < b)


def span_attendance(records, spans) -> list[str]:
    """Skill Mastery: 그 칸(하루 또는 한 주) 수업 출결. 수업이 없으면 '수업미지정일', 기간 밖 칸은 빈 칸."""
    cells = []
    for span in spans:
        if not span[0]:
            cells.append('')
            continue
        kinds = [_kind(r) for r in records if _within(r.lesson_date, span)]
        if not kinds:
            cells.append(NO_LESSON)
            continue
        labels = [SKILL_BY_STATUS.get(k, '') for k in kinds]
        cells.append('PASS' if 'PASS' in labels else next((label for label in labels if label), ''))
    return cells


def span_marks(tasks: list[Task], spans, attendance: list[str] | None = None) -> list[str]:
    """과제 PASS/FAIL(그 칸에 마감인 과제를 모두 냈는지). 출결을 알면 이월·환불·수업미지정일은 그 이름으로."""
    marks = []
    for i, span in enumerate(spans):
        if attendance and attendance[i] in DAY_OVERRIDES:
            marks.append(attendance[i])
            continue
        due = [t for t in tasks if t.kind == 'HW' and not t.waiting and _within(t.due, span)]
        marks.append('' if not due else ('PASS' if all(t.submitted for t in due) else 'FAIL'))
    return marks


def span_quiz(tasks: list[Task], spans) -> list[dict]:
    """단어 시험: 그 칸의 퀴즈 점수/만점(월간 칸이면 그 주 퀴즈를 모두 더함)."""
    cells = []
    for span in spans:
        due = [t for t in tasks if t.kind == 'QUIZ' and not t.waiting and _within(t.due, span)]
        if not due:
            cells.append({'score': '', 'retest': '', 'max': ''})
            continue
        if len(due) == 1:
            t = due[0]
            score = number(t.score) if t.submitted and t.score is not None else ('미응시' if not t.submitted else '')
            cells.append({'score': score, 'retest': '', 'max': number(t.points)})
            continue
        done = [t for t in due if t.submitted and t.score is not None]
        cells.append({'score': number(sum(t.score for t in done)) if done else '미응시', 'retest': '',
                      'max': number(sum(t.points or 0 for t in due))})
    return cells


def day_attendance(records, monday: date) -> list[str]:
    """월~금 Skill Mastery(예전 이름 그대로 둡니다)."""
    return span_attendance(records, daily_spans(monday))


def day_marks(tasks: list[Task], monday: date, attendance: list[str] | None = None) -> list[str]:
    """월~금 수업 내 과제 PASS/FAIL(예전 이름 그대로 둡니다)."""
    return span_marks(tasks, daily_spans(monday), attendance)


def day_quiz(tasks: list[Task], monday: date) -> list[dict]:
    return span_quiz(tasks, daily_spans(monday))


def lesson_weeks(dates, base: date) -> dict[int, date]:
    first: dict[int, date] = {}
    for d in sorted(dates):
        first.setdefault(week_no(d, base), d)
    return first


def _when(a) -> datetime:
    return a.exam_date or datetime.min


def latest_per_exam(attempts) -> list:
    """같은 시험을 여러 번 끝냈으면 마지막 기록 하나만, 날짜순(11/20: DSG 재응시가 11,535쌍이라 평균·칸이 겹쳤음)."""
    last = {}
    for a in sorted(attempts, key=_when):
        last[str(a.exam_id)] = a
    return sorted(last.values(), key=_when)


def previous_span(start: date, end: date) -> tuple[date, date]:
    """지난주·지난달 칸이 보는 기간: 한 주 카드(7일 이하)는 바로 앞 7일, 월간 카드는 바로 앞 같은 길이(11/20)."""
    days = 7 if (end - start).days <= 6 else (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def class_averages(attempt_lists) -> dict[str, dict]:
    """같은 시험(exam_id)을 본 학생들의 R/W·Math 평균(소수 반올림). 학생마다 그 시험의 마지막 기록 하나만 셉니다."""
    sums: dict[str, dict[str, list[int]]] = {}
    for attempts in attempt_lists:
        for a in latest_per_exam(attempts):
            slot = sums.setdefault(a.exam_id, {'rw': [], 'math': []})
            if a.rw_sat_score is not None:
                slot['rw'].append(a.rw_sat_score)
            if a.math_sat_score is not None:
                slot['math'].append(a.math_sat_score)
    return {exam: {k: (round(sum(v) / len(v)) if v else None) for k, v in parts.items()} for exam, parts in sums.items()}


def _slot(a=None, averages=None) -> dict:
    if a is None:
        return {'date': '', 'rw': '', 'rw_avg': '', 'math': '', 'math_avg': ''}
    avg = (averages or {}).get(a.exam_id, {})
    return {'date': a.exam_date.strftime('%m-%d'), 'rw': number(a.rw_sat_score), 'rw_avg': number(avg.get('rw')),
            'math': number(a.math_sat_score), 'math_avg': number(avg.get('math'))}


def chosen_slots(attempts, exam_ids: list[str], averages, slots: int = 3) -> list[dict]:
    """고른 DSG 모의고사(고른 순서대로) 점수. 여러 번 봤으면 마지막 기록, 안 본 시험은 빈 칸."""
    latest = {str(a.exam_id): a for a in latest_per_exam(attempts)}
    picked = [_slot(latest.get(str(exam_id)), averages) for exam_id in exam_ids[:slots]]
    return picked + [_slot() for _ in range(slots - len(picked))]


def before_chosen_slots(attempts, exam_ids: list[str], fallback: date, averages, count: int, slots: int = 3) -> list[dict]:
    """이번 칸 시험을 골랐을 때 지난 칸: 고른 시험(그 학생이 마지막으로 본 날 중 가장 이른 날)보다 먼저 끝낸
    다른 시험 중 최근 count개(11/20). 고른 시험을 하나도 안 본 학생은 리포트 기간 시작일 전."""
    ids = {str(i) for i in exam_ids}
    shown = [a for a in latest_per_exam(attempts) if str(a.exam_id) in ids and a.exam_date]
    anchor = min((a.exam_date for a in shown), default=datetime.combine(fallback, time.min))
    earlier = [a for a in attempts if a.exam_date and a.exam_date < anchor and str(a.exam_id) not in ids]
    picked = latest_per_exam(earlier)[-count:] if count > 0 else []
    return [_slot(a, averages) for a in picked] + [_slot() for _ in range(slots - len(picked))]


def dsg_slots(attempts, start: date, end: date, averages, slots: int = 3) -> dict:
    """시험을 안 골랐을 때: 이번 칸 = 리포트 기간 안, 지난 칸 = previous_span. 같은 시험은 마지막 기록 하나만."""
    def window(lo, hi):
        picked = latest_per_exam(a for a in attempts if a.exam_date and lo <= a.exam_date.date() <= hi)[-slots:]
        return [_slot(a, averages) for a in picked] + [_slot() for _ in range(slots - len(picked))]
    return {'this': window(start, end), 'last': window(*previous_span(start, end))}


# ── 데이터 읽기 (DB·인트라넷·DSG) ─────────────────────────────────────────

def lms_tasks(group, student_no: str) -> list[Task]:
    """그 반에 낸(공개된) 과제·퀴즈 중 이 학생에게 배정된 것."""
    from apps.assignments.models import AssignmentRecipient
    from apps.learning.models import QuizRecipient
    tasks, now = [], timezone.now()
    for r in AssignmentRecipient.objects.filter(assignment__group=group, assignment__is_published=True, student_id=student_no).select_related('assignment', 'submission'):
        sub = r.submission_object
        submitted = bool(sub and sub.submitted_at)
        tasks.append(Task('HW', r.assignment.title, timezone.localdate(r.assignment.due_at), submitted,
                          sub.score if submitted else None, Decimal(r.assignment.points), r.assignment.due_at > now))
    for r in QuizRecipient.objects.filter(quiz__group=group, quiz__is_published=True, student_id=student_no).select_related('quiz').prefetch_related('attempts', 'quiz__questions'):
        done = [a for a in r.attempts.all() if a.submitted_at]
        best = max(done, key=lambda a: a.final_score, default=None)
        tasks.append(Task('QUIZ', r.quiz.title, timezone.localdate(r.quiz.due_at), bool(best),
                          best.final_score if best else None, best.max_score if best else Decimal(r.quiz.total_points), r.quiz.due_at > now))
    return tasks


class SourceUnavailable(Exception):
    """인트라넷·DSG를 읽지 못했습니다(예: DB 연결이 응답 없이 끊김). 카드 값을 바꾸지 않고 멈출 때 씁니다."""

    def __init__(self, label: str):
        super().__init__(label)
        self.label = label  # 화면에 보일 이름: '인트라넷' 또는 '인트라넷·DSG'


def _unavailable(event: str, label: str, strict: bool, exc: Exception):
    """읽기 실패 기록. 연결 끊김(DB 오류)은 한 줄로만 남겨 서버 창이 오류 줄로 덮이지 않게 하고,
    그 밖의 예상 못 한 오류만 전체 기록을 남깁니다. strict 면 SourceUnavailable 로 알려 멈추게 합니다."""
    from django.db import DatabaseError
    if isinstance(exc, DatabaseError):
        logger.warning('%s error=%s', event, exc)
    else:
        logger.warning(event, exc_info=exc)
    if strict:
        raise SourceUnavailable(label) from exc


def student_info(student_nos: list[str], strict: bool = False) -> dict:
    """학생번호 → StudentSummary. 인트라넷이 안 되면 빈 값(이름은 반 명단으로 채움). strict 면 SourceUnavailable."""
    from apps.students.services import StudentService
    try:
        return {s.student_id: s for s in StudentService().get_students(student_nos)}
    except Exception as exc:
        _unavailable('report_student_info_unavailable', '인트라넷', strict, exc)
        return {}


def student_courses(student_no: str, strict: bool = False) -> list:
    from apps.students.course_services import CourseService
    try:
        return CourseService().get_student_courses(student_no)
    except Exception as exc:
        _unavailable('report_courses_unavailable', '인트라넷', strict, exc)
        return []


def course_lessons(student_no: str, class_id: str, strict: bool = False) -> tuple[object | None, list]:
    """학생의 그 인트라넷 수업(class_id)과 출결 기록(수업마다 한 줄)."""
    from apps.students.attendance_repositories import get_attendance_repository
    course = next((c for c in student_courses(student_no, strict=strict) if c.class_id == class_id), None)
    if not course:
        return None, []
    try:
        # 이월 회차도 받아 Skill Mastery·과제 칸에 '이월'로 보여 줍니다(출결 화면은 계속 뺌, 11/20).
        return course, list(get_attendance_repository().list_by_student_and_assign(student_no, course.assign_id, include_carry_over=True))
    except Exception as exc:
        _unavailable('report_attendance_unavailable', '인트라넷', strict, exc)
        return course, []


def lesson_dates(records) -> list[date]:
    """수업 날짜(학기·주니어 카드의 칸). 휴강과 이월 회차(그 학생이 듣지 않는 날)는 뺍니다."""
    return [r.lesson_date for r in records if r.lesson_date and not r.is_class_cancelled and _kind(r) != 'carried']


def course_lesson_dates(student_no: str, class_id: str) -> tuple[object | None, list[date]]:
    """학생의 그 인트라넷 수업(class_id)과 수업 날짜들."""
    course, records = course_lessons(student_no, class_id)
    return course, lesson_dates(records)


def dsg_attempts(student_no: str, strict: bool = False) -> list:
    """DSG 모의고사 응시 기록. 학생을 인트라넷의 DSG ID로 찾으므로 인트라넷이 끊겨도 못 읽습니다."""
    from apps.assessments.repositories import get_assessment_repository
    try:
        repo = get_assessment_repository()
        profile = repo.get_student_profile(student_no)
        return repo.list_exam_attempts(profile.dsg_student_id) if profile.status == 'ok' else []
    except Exception as exc:
        _unavailable('report_dsg_unavailable', '인트라넷·DSG', strict, exc)
        return []
