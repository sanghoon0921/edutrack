"""리포트카드 묶음 만들기, 자동 값 채우기·다시 불러오기, 화면 입력 저장."""
from __future__ import annotations

import re

from datetime import date, timedelta
from uuid import uuid4

from django.db import transaction

from . import sources
from .formats import FORMS, OLD_VOCAB_HEADS, TERM_WEEKS, VOCAB_HEADS, default_shared, empty_data, period_label, weekly_sections
from .models import ReportBatch, ReportCard

TEXT_LIMIT = 6000


# ── 경로 도우미: {'weeks': [{'status': ..}]} ↔ 'weeks.0.status' ─────────────

def flatten(value, prefix='') -> dict:
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = enumerate(value)
    else:
        return {prefix: value}
    out = {}
    for key, child in items:
        out.update(flatten(child, f'{prefix}.{key}' if prefix else str(key)))
    return out


def _step(node, key):
    return node[int(key)] if isinstance(node, list) else node[key]


def get_path(root, path: str, default=''):
    node = root
    try:
        for key in path.split('.'):
            node = _step(node, key)
    except (KeyError, IndexError, ValueError, TypeError):
        return default
    return node


def set_path(root, path: str, value) -> bool:
    keys = path.split('.')
    try:
        node = root
        for key in keys[:-1]:
            node = _step(node, key)
        last = int(keys[-1]) if isinstance(node, list) else keys[-1]
        node[last]  # 이미 있는 칸만 바꿉니다
        node[last] = value
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    return True


def apply_post(root: dict, post, prefix: str, skip=()) -> None:
    """화면에서 보낸 칸 중 이미 있는 칸만 고칩니다(새 칸은 만들지 않음). skip 의 칸(자동 잠금)은 건드리지 않습니다."""
    for path in flatten(root):
        name = f'{prefix}{path}'
        if path in skip:
            continue
        if name in post:
            set_path(root, path, str(post.get(name, '')).replace('\r\n', '\n').strip()[:TEXT_LIMIT])


def personalize(text: str, card: ReportCard, batch: ReportBatch) -> str:
    shared = batch.shared or {}
    return (text or '').replace('{이름}', card.student_name).replace('{반}', shared.get('class_name', '')).replace('{강사}', shared.get('teacher', ''))


# ── 자동 칸 잠금(11/20 사용자: '수정할 수 있게 말고 알아서 채워졌으면, 색깔 표시해서') ─────────
# SAT·TOEFL 카드에서 인트라넷·DSG·EduTrack 이 채운 칸. 자동 값이 비어 있는 칸은 잠그지 않습니다(강사가 입력).
LOCKED_AUTO = re.compile(r'^(info\.(name|country|school)|skill\.\d+|task\.\d+|vocab\.\d+\.(score|max)|mock\.(this|last)\.\d+\.\w+)$')


def locked_paths(batch: ReportBatch, auto) -> set[str]:
    """편집 화면에서 입력칸 대신 색 표시로 보이고, 저장으로 바뀌지 않으며, 다시 불러오기 때 항상 새 자동 값으로 맞추는 칸."""
    if FORMS[batch.form]['kind'] != 'weekly':
        return set()
    return {path for path, value in flatten(auto or {}).items() if value not in ('', None) and LOCKED_AUTO.match(path)}


# ── 주차 ─────────────────────────────────────────────────────────────────

def period_weeks(base: date, start: date, end: date) -> list[str]:
    return [f'WEEK{n}' for n in range(sources.week_no(start, base), sources.week_no(end, base) + 1)]


def teacher_names(group) -> str:
    def label(user):
        return getattr(user, 'display_name', '') or user.get_full_name() or user.username
    names = [label(group.created_by)] if group.created_by_id else []
    for staff in group.lms_staff.filter(active=True).select_related('user'):
        name = label(staff.user)
        if name not in names:
            names.append(name)
    return ', '.join(names)


# ── 자동 값 ───────────────────────────────────────────────────────────────

def load_context(batch: ReportBatch, student_nos: list[str]) -> dict:
    """인트라넷·DSG 값을 모읍니다. 하나라도 못 읽으면 첫 실패에서 sources.SourceUnavailable 로 멈춥니다(11/20):
    빈 값으로 계속하면 다시 불러오기가 전에 채운 정보·점수·출결을 빈칸으로 덮어쓰고, 학생마다 15초씩 기다리게 됩니다."""
    ctx = {'info': sources.student_info(student_nos, strict=True), 'lessons': {}, 'records': {}, 'attempts': {}, 'averages': {}}
    if batch.course_class_id:
        for no in student_nos:
            records = sources.course_lessons(no, batch.course_class_id, strict=True)[1]
            ctx['records'][no] = records
            ctx['lessons'][no] = sources.lesson_dates(records)
    if FORMS[batch.form].get('mock') == 'sat':
        ctx['attempts'] = {no: sources.dsg_attempts(no, strict=True) for no in student_nos}
        ctx['averages'] = sources.class_averages(ctx['attempts'].values())
    return ctx


def _short(day) -> str:
    return f'{day.month}/{day.day}' if day else ''


def auto_values(batch: ReportBatch, student_no: str, student_name: str, ctx: dict) -> dict:
    spec = FORMS[batch.form]
    s = ctx['info'].get(student_no)
    tasks = sources.lms_tasks(batch.group, student_no)
    base, start, end = batch.week_base, batch.period_start, batch.period_end
    if spec['kind'] == 'weekly':
        # 날짜 5칸: 한 주 기간이면 월~금, 그보다 길면 7일씩(월간 리포트, 11/17).
        spans = sources.card_spans(start, end)
        # 인트라넷 수업을 골랐으면 Skill Mastery 는 출결, 과제 칸도 이월·환불·수업미지정일을 그대로 보여 줍니다.
        records = ctx['records'].get(student_no)
        skill = sources.span_attendance(records, spans) if batch.course_class_id and records is not None else None
        auto = {'info': {'name': student_name, 'country': s.country if s else '', 'school': s.school if s else ''},
                'task': sources.span_marks(tasks, spans, attendance=skill), 'vocab': sources.span_quiz(tasks, spans)}
        if skill is not None:
            auto['skill'] = skill
        if spec['mock'] == 'sat':
            attempts = ctx['attempts'].get(student_no, [])
            auto['mock'] = sources.dsg_slots(attempts, start, end, ctx['averages'])
            chosen = [m['id'] for m in batch.shared.get('mock_exams', [])]
            previous = [m['id'] for m in batch.shared.get('mock_prev', [])]
            if chosen:
                auto['mock']['this'] = sources.chosen_slots(attempts, chosen, ctx['averages'])
            # 지난 칸(11/20): 직접 고른 시험 > 고른 이번 시험 바로 전에 본 시험 > 기간 바로 앞 기간(dsg_slots)
            if previous:
                auto['mock']['last'] = sources.chosen_slots(attempts, previous, ctx['averages'])
            elif chosen:
                auto['mock']['last'] = sources.before_chosen_slots(attempts, chosen, start, ctx['averages'], len(chosen))
        return auto
    region = ' '.join(x for x in ((s.country, s.city, s.school) if s else ()) if x)
    auto = {'info': {'name': student_name, 'region': region, 'grade': s.grade if s else ''}}
    if spec['kind'] == 'term':
        lessons = ctx['lessons'].get(student_no) if batch.course_class_id else None
        auto['weeks'] = sources.lesson_status(tasks, lessons, end) if lessons else sources.week_status(tasks, base, start, end, TERM_WEEKS)
        if spec['last'][0] == 'scores':
            auto['scores'] = sources.score_lines(tasks, base, start, end)
        return auto
    lessons = sources.lesson_weeks(ctx['lessons'].get(student_no, []), base)
    rows = []
    # 행 순서는 카드와 같은 반 공통 목록(강사가 더하고 지운 주 포함)을 따라야 칸이 어긋나지 않습니다.
    for label in junior_labels(batch, period_weeks(base, start, end)):
        n = int(label[4:]) if label[4:].isdigit() else 0
        week = [t for t in tasks if sources.week_no(t.due, base) == n]
        homework = [t for t in week if t.kind == 'HW']
        quizzes = [t for t in week if t.kind == 'QUIZ' and t.submitted and t.score is not None]
        rows.append({'label': label, 'date': _short(lessons.get(n)),
                     'homework': ', '.join(t.title for t in homework) or 'N/A',
                     'submitted': sources.submit_status(homework) if homework else '해당없음',
                     'vocab': ', '.join(f'{sources.number(t.score)}/{sources.number(t.points)}' for t in quizzes)})
    auto['rows'] = rows
    return auto


def ensure_block_list(batch: ReportBatch) -> bool:
    """예전 주간 묶음(shared['blocks'] = {칸: 설명})을 칸 목록(block_list) 모양으로 바꿉니다. 바꿨으면 True."""
    spec = FORMS[batch.form]
    if spec['kind'] != 'weekly' or 'block_list' in batch.shared:
        return False
    old = batch.shared.pop('blocks', None) or {}
    batch.shared['block_list'] = [{'key': key, 'title': title, 'desc': old.get(key, desc)} for key, title, desc in spec['blocks']]
    return True


def junior_labels(batch: ReportBatch, labels: list[str]) -> list[str]:
    """주니어 주차 행 목록(반 공통): 강사가 더하거나 지운 행은 shared['contents'] 의 순서를 따릅니다."""
    contents = batch.shared.get('contents')
    return list(contents) if FORMS[batch.form]['kind'] == 'junior' and contents else labels


def ensure_weekly_layout(batch: ReportBatch) -> bool:
    """예전에 만든 주간 묶음에 표 이름·빠진 표·단어 시험 열 이름 칸을 채웁니다. 바꿨으면 True."""
    if FORMS[batch.form]['kind'] != 'weekly':
        return False
    changed = False
    for key, default in (('hidden', []), ('titles', weekly_sections(batch.form)), ('vocab_heads', list(VOCAB_HEADS))):
        if key not in batch.shared:
            batch.shared[key] = default
            changed = True
    # 11/17 새 디자인: 단어 시험 열 이름을 고치지 않은 예전 묶음은 새 열 이름(날짜·이행 현황·완료 구분)으로.
    if batch.shared.get('vocab_heads') == OLD_VOCAB_HEADS:
        batch.shared['vocab_heads'] = list(VOCAB_HEADS)
        changed = True
    return changed


def toggle_section(batch: ReportBatch, key: str) -> bool:
    """표 빼기·다시 넣기(반 전체). 지금 빠져 있으면 True."""
    hidden = batch.shared.setdefault('hidden', [])
    if key in hidden:
        hidden.remove(key)
    else:
        hidden.append(key)
    batch.save(update_fields=['shared', 'updated_at'])
    return key in hidden


def _empty(batch: ReportBatch, labels: list[str]) -> dict:
    data = empty_data(batch.form, week_labels=junior_labels(batch, labels))
    if 'blocks' in data:
        data['blocks'] = {b['key']: '' for b in batch.shared.get('block_list', [])}
    return data


@transaction.atomic
def add_block(batch: ReportBatch) -> str:
    """과제별 코멘트 칸을 하나 더합니다(반 전체). 새 칸의 key 를 돌려줍니다."""
    ensure_block_list(batch)
    key = f'b{uuid4().hex[:8]}'
    batch.shared['block_list'].append({'key': key, 'title': '새 과제', 'desc': ''})
    batch.save(update_fields=['shared', 'updated_at'])
    for card in batch.cards.select_for_update():
        card.data.setdefault('blocks', {})[key] = ''
        card.save(update_fields=['data', 'updated_at'])
    return key


@transaction.atomic
def delete_block(batch: ReportBatch, key: str) -> None:
    """과제별 코멘트 칸을 반 전체에서 지웁니다(그 칸에 쓴 학생 코멘트도 함께). 없는 칸이면 LookupError."""
    ensure_block_list(batch)
    blocks = batch.shared['block_list']
    if not any(b['key'] == key for b in blocks):
        raise LookupError(key)
    batch.shared['block_list'] = [b for b in blocks if b['key'] != key]
    batch.save(update_fields=['shared', 'updated_at'])
    for card in batch.cards.select_for_update():
        card.data.get('blocks', {}).pop(key, None)
        card.save(update_fields=['data', 'updated_at'])


JUNIOR_ROW = {'date': '', 'homework': '', 'submitted': '', 'attitude': '', 'vocab': '', 'comment': ''}


@transaction.atomic
def add_junior_row(batch: ReportBatch) -> str:
    """주니어 카드에 주차 행을 하나 더합니다(반 전체, WEEK 다음 번호). 새 행 이름을 돌려줍니다."""
    numbers = [int(label[4:]) for label in batch.shared.get('contents', {}) if label[4:].isdigit()]
    label = f'WEEK{max(numbers, default=0) + 1}'
    batch.shared.setdefault('contents', {})[label] = ''
    batch.save(update_fields=['shared', 'updated_at'])
    for card in batch.cards.select_for_update():
        card.data.setdefault('rows', []).append({'label': label, **JUNIOR_ROW})
        card.save(update_fields=['data', 'updated_at'])
    return label


@transaction.atomic
def delete_junior_row(batch: ReportBatch, label: str) -> None:
    """주니어 주차 행을 반 전체에서 지웁니다(그 주에 쓴 내용도 함께). 없는 행이면 LookupError."""
    if label not in batch.shared.get('contents', {}):
        raise LookupError(label)
    batch.shared['contents'].pop(label)
    batch.save(update_fields=['shared', 'updated_at'])
    for card in batch.cards.select_for_update():
        card.data['rows'] = [r for r in card.data.get('rows', []) if r.get('label') != label]
        if isinstance(card.auto.get('rows'), list):
            card.auto['rows'] = [r for r in card.auto['rows'] if r.get('label') != label]
        card.save(update_fields=['data', 'auto', 'updated_at'])


def _fit_weeks(data: dict, auto: dict) -> None:
    """수업일 기준 학기 카드는 수업 수만큼 칸이 생깁니다. 인트라넷에 수업이 늘면 빈 칸을 더합니다."""
    weeks, wanted = data.get('weeks'), auto.get('weeks')
    if isinstance(weeks, list) and isinstance(wanted, list) and len(weeks) != len(wanted):
        data['weeks'] = [weeks[i] if i < len(weeks) else {'label': w['label'], 'status': ''} for i, w in enumerate(wanted)]


def _fill(data: dict, auto: dict) -> dict:
    _fit_weeks(data, auto)
    for path, value in flatten(auto).items():
        set_path(data, path, value)
    return data


def create_batch(*, group, form, title, period_start, period_end, week_base, user, course_class_id='', course_label='', course_name='', course_teacher='',
                 course_type='', mock_exams=(), mock_prev=()) -> ReportBatch:
    members = list(group.lms_members.filter(active=True).order_by('student_name', 'student_no'))
    labels = period_weeks(week_base, period_start, period_end)
    batch = ReportBatch(
        group=group, form=form, title=title, period_start=period_start, period_end=period_end, week_base=week_base,
        course_class_id=course_class_id, course_label=course_label, created_by=user,
        shared=default_shared(form, class_name=course_name or group.title, teacher=course_teacher or teacher_names(group), week_labels=labels))
    batch.shared['period'] = period_label(period_start, period_end)
    batch.shared['weeks_label'] = sources.weeks_label(week_base, period_start, period_end)
    if FORMS[form]['kind'] == 'weekly':
        batch.shared['course_type'] = course_type or '정규'
        if form == 'TOEFL' and batch.shared['course_type'] == '정규':
            batch.shared['hidden'] = ['skill']  # 정규 수업에는 Skill Mastery 가 없습니다(운영팀 10/29)
            batch.shared['intro'] = batch.shared['intro'].replace('Skill Mastery 시간에', '수업 시간에')
        batch.shared['mock_exams'] = [{'id': str(i), 'name': n} for i, n in mock_exams]
        batch.shared['mock_prev'] = [{'id': str(i), 'name': n} for i, n in mock_prev]
    # 인트라넷·DSG 읽기는 저장 전에 끝냅니다. SQLite 쓰기 잠금을 쥔 채 바깥 DB를 기다리면
    # 그동안 다른 사람의 저장·로그아웃이 'database is locked'로 실패합니다.
    ctx = load_context(batch, [m.student_no for m in members])
    autos = [(m, auto_values(batch, m.student_no, m.student_name, ctx)) for m in members]
    with transaction.atomic():
        batch.save()
        for m, auto in autos:
            ReportCard.objects.create(batch=batch, student_no=m.student_no, student_name=m.student_name,
                                      data=_fill(_empty(batch, labels), auto), auto=auto, updated_by=user)
    return batch


def refresh_batch(batch: ReportBatch, user) -> int:
    """자동 값을 다시 불러옵니다. 강사가 고친 칸(지난 자동 값과 다른 칸)과 코멘트는 그대로 둡니다.
    반에 새로 들어온 학생은 카드를 새로 만듭니다. 바뀐 칸 수를 돌려줍니다."""
    members = list(batch.group.lms_members.filter(active=True))
    # 인트라넷·DSG 읽기는 거래 밖에서 먼저 끝냅니다(create_batch 와 같은 이유).
    ctx = load_context(batch, [m.student_no for m in members])
    with transaction.atomic():
        return _apply_refresh(batch, user, members, ctx)


def _apply_refresh(batch: ReportBatch, user, members, ctx) -> int:
    cards = {c.student_no: c for c in batch.cards.select_for_update()}
    labels = period_weeks(batch.week_base, batch.period_start, batch.period_end)
    changed = 0
    for m in members:
        new = auto_values(batch, m.student_no, m.student_name, ctx)
        card = cards.get(m.student_no)
        if card is None:
            ReportCard.objects.create(batch=batch, student_no=m.student_no, student_name=m.student_name,
                                      data=_fill(_empty(batch, labels), new), auto=new, updated_by=user)
            continue
        _fit_weeks(card.data, new)
        old = flatten(card.auto)
        locked = locked_paths(batch, new)  # 잠긴 칸은 예전에 손으로 고친 값이 있어도 새 자동 값으로
        for path, value in flatten(new).items():
            current = get_path(card.data, path, None)
            if (path in locked or path not in old or current == old[path]) and current != value and set_path(card.data, path, value):
                changed += 1
        card.auto = new
        card.save(update_fields=['data', 'auto', 'updated_at'])
    return changed


def scope_allows(name: str, scope) -> bool:
    """권한이 나뉜 카드에서 이 칸(name)을 쓸 수 있는지. scope 항목은 앞부분 일치, 're:'로 시작하면 전체 일치 정규식."""
    if scope is None:
        return True
    for rule in scope:
        if rule.startswith('re:'):
            if re.fullmatch(rule[3:], name):
                return True
        elif name.startswith(rule):
            return True
    return False
