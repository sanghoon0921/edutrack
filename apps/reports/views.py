from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.student_links import get_linked_student_nos
from apps.communications.models import Notification
from apps.communications.services import create_notifications, learner_users_for_student

from apps.learning.models import LearningGroup
from apps.lms.access import staff_group_ids
from apps.operations.access import is_admin, is_ta, is_teacher
from apps.lms.models import GroupStaff

from . import charts, services, sources
from .formats import FORMS, MOCK_LIMIT, SUBMIT_CHOICES, season_heading, weekly_sections
from .forms import MockPickForm, ReportBatchForm, group_forms
from .models import ReportBatch, ReportCard

COURSE_SCAN_LIMIT = 40  # 수업 목록을 만들 때 살펴볼 학생 수(반이 커도 화면이 느려지지 않게)
MOCK_SCAN_LIMIT = 30  # DSG 모의고사 목록을 만들 때 살펴볼 학생 수(11/20: 고르는 표에 응시 학생 수를 보이므로 반 대부분)


def _staff(user):
    if not (is_admin(user) or is_teacher(user) or is_ta(user)):
        raise Http404('리포트카드는 강사·TA·관리자만 볼 수 있습니다.')


def report_group_ids(user):
    """리포트카드를 볼 수 있는 반: 관리자·강사는 평소 담당 반, TA 계정은 '명단·TA 지정'에서 맡은 반만."""
    if is_ta(user):
        return GroupStaff.objects.filter(user=user, active=True).values_list('group_id', flat=True)
    return staff_group_ids(user)


def _admin_only(user):
    """공개(발송)·발송 취소·표 바꾸기(행·구역)·지우기는 관리자만 합니다(운영팀 11/17, 11/19 유지).
    만들기·내용 작성·데이터 다시 불러오기는 11/19부터 강사·TA도 자기 반에서 합니다."""
    if not is_admin(user):
        raise Http404('이 작업은 관리자만 할 수 있습니다.')


def _groups(user):
    return LearningGroup.objects.filter(pk__in=staff_group_ids(user)).order_by('sort_order', 'title')


def _batch(user, batch_id):
    _staff(user)
    batch = get_object_or_404(ReportBatch.objects.select_related('group'), pk=batch_id)
    if batch.group_id not in set(report_group_ids(user)):
        raise Http404('접근 가능한 반이 아닙니다.')
    return batch


def _course_options(group) -> tuple[dict, str]:
    """반 학생들이 듣는 인트라넷 수업(같은 class_id는 하나로)과, 못 읽었으면 그 이름('인트라넷').
    인트라넷이 끊기면 첫 학생에서 멈춥니다(학생마다 15초씩 기다리지 않게, 11/20)."""
    options = {}
    try:
        for member in group.lms_members.filter(active=True)[:COURSE_SCAN_LIMIT]:
            for c in sources.student_courses(member.student_no, strict=True):
                if c.class_id and c.class_id not in options:
                    label = ' · '.join(x for x in (c.class_name, c.term_name, c.teacher_names) if x)
                    options[c.class_id] = {'label': label, 'name': c.class_name, 'teacher': c.teacher_names, 'start': c.start_date}
    except sources.SourceUnavailable as exc:
        return options, exc.label
    return options, ''


MOCK_KINDS = {'FULL': '전체', 'RW': 'R/W', 'MATH': 'Math'}


def _short_day(day, year) -> str:
    return day.strftime('%m-%d') if day.year == year else day.strftime('%y-%m-%d')


def _mock_options(group) -> tuple[dict, str]:
    """반 학생들이 본 DSG 모의고사(최근 시험 먼저)와, 못 읽었으면 그 이름.
    {exam_id: {'name', 'kind', 'dates', 'count', 'label'}} — 고르는 표에 종류·응시일(반 학생들이 본 날)·응시 학생 수를 보입니다(11/20).
    같은 시험을 여러 번 본 학생은 마지막 기록 하나로 셉니다."""
    found, down = {}, ''
    try:
        for member in group.lms_members.filter(active=True)[:MOCK_SCAN_LIMIT]:
            for a in sources.latest_per_exam(sources.dsg_attempts(member.student_no, strict=True)):
                if not a.exam_id:
                    continue
                row = found.setdefault(str(a.exam_id), {'name': a.exam_name, 'kind': MOCK_KINDS.get(a.score_type, ''), 'days': [], 'count': 0})
                row['count'] += 1
                if a.exam_date:
                    row['days'].append(a.exam_date)
    except sources.SourceUnavailable as exc:
        down = exc.label
    year = timezone.localdate().year
    options = {}
    for key, row in sorted(found.items(), key=lambda kv: max(kv[1]['days'], default=datetime.min), reverse=True):
        days = row['days']
        dates = ''
        if days:
            first, last = min(days), max(days)
            dates = _short_day(first, year) if first.date() == last.date() else f'{_short_day(first, year)}~{_short_day(last, year)}'
        options[key] = {'name': row['name'], 'kind': row['kind'], 'dates': dates, 'count': row['count'],
                        'label': ' · '.join(x for x in (row['name'], dates) if x)}
    return options, down


# 코멘트 칸(TA 계정이 쓸 수 있는 칸). 're:'로 시작하면 이름 전체가 맞아야 합니다.
COMMENT_SCOPE = {
    'weekly': ('d.blocks.', 'd.personal', 'd.mock_comment.'),
    'term': ('d.comment',),
    'junior': (r're:d\.rows\.\d+\.comment', 'd.achievement', 'd.overall'),
}


# 강사·TA가 쓰는 칸(11/19): 카드 내용(d.)과 반 공통 내용(s.) 전부. 표 바꾸기(행·구역 더하기·빼기, 제목)는 관리자만.
STAFF_SCOPE = ('d.', 's.')


def edit_scope(user, batch):
    """카드 쓰기 권한. None = 제한 없음(관리자, 표 바꾸기 포함).
    11/19 TA 권한 결정: 강사·TA는 자기 반 리포트카드를 만들고 모든 칸을 씁니다. 발송·삭제·표 바꾸기는 관리자만."""
    if is_admin(user):
        return None
    return STAFF_SCOPE


def scope_note(user, batch):
    scope = edit_scope(user, batch)
    if scope is None:
        return ''
    return '학부모 발송(공개)과 표 바꾸기는 관리자가 검토한 뒤 합니다.'


def _full_access(user, batch):
    if edit_scope(user, batch) is not None:
        raise Http404('이 작업은 관리자만 할 수 있습니다.')


SEND_FILTERS = {'sent': '발송', 'unsent': '미발송'}


def batch_term(batch):
    """묶음의 Term: 반에 정한 Term, 없으면 묶음 제목(시즌 코드)."""
    return batch.group.term or batch.title


@login_required
def report_list(request):
    """리포트카드 목록: Term·반·학부모 발송 상태로 거르고, 반별 묶음마다 발송 현황을 보여 줍니다(운영팀 11/17)."""
    _staff(request.user)
    visible = ReportBatch.objects.filter(group_id__in=report_group_ids(request.user)).select_related('group')
    term = (request.GET.get('term') or '').strip()[:20]
    raw_group = (request.GET.get('group') or '').strip()
    send = request.GET.get('send') if request.GET.get('send') in SEND_FILTERS else ''
    batches = visible
    if term:
        batches = batches.filter(Q(group__term=term) | Q(group__term='', title=term))
    if raw_group.isdigit():
        batches = batches.filter(group_id=int(raw_group))
    if send:
        batches = batches.filter(published_at__isnull=(send == 'unsent'))
    batches = batches.annotate(card_count=Count('cards'), first_card=Min('cards__pk'),
                               saved_count=Count('cards', filter=Q(cards__saved_at__isnull=False)))
    rows = [{'batch': b, 'form_label': FORMS.get(b.form, {}).get('label', b.form), 'term': batch_term(b)} for b in batches[:200]]
    terms = sorted({batch_term(b) for b in visible.only('title', 'group__term')} - {''}, reverse=True)
    groups = LearningGroup.objects.filter(pk__in=visible.values('group_id')).order_by('sort_order', 'title')
    return render(request, 'reports/list.html', {
        'page_title': '리포트카드', 'rows': rows, 'is_ta': is_ta(request.user), 'is_admin': is_admin(request.user),
        'terms': terms, 'filter_groups': groups, 'send_filters': SEND_FILTERS,
        'f_term': term, 'f_group': int(raw_group) if raw_group.isdigit() else None, 'f_send': send,
        'filtered': bool(term or raw_group or send)})


@login_required
def batch_detail(request, batch_id):
    """리포트 열기: 학생 목록부터 보여 주고, 학생을 누르면 카드(화살표로 다음 학생)."""
    batch = _ready(_batch(request.user, batch_id))
    cards = batch.cards.select_related('updated_by')
    return render(request, 'reports/batch.html', {'page_title': f'{batch.group.title} 리포트카드', 'batch': batch, 'cards': cards,
                                                  'form_label': FORMS[batch.form]['label'], 'is_ta': is_ta(request.user),
                                                  'is_admin': is_admin(request.user),
                                                  'saved_count': sum(1 for c in cards if c.saved_at or batch.published_at)})


def _status_row(card, batch):
    who = card.updated_by and (card.updated_by.display_name or card.updated_by.username)
    at = timezone.localtime(card.updated_at)
    # 공개(발송)한 묶음의 카드는 편집 화면에서 저장하지 않았어도 완성으로 봅니다(11/10과 같은 규칙).
    return {'id': card.pk, 'saved': bool(card.saved_at or batch.published_at), 'updated': f'{at.month}/{at.day} {at:%H:%M}', 'by': who or ''}


@login_required
def batch_status(request, batch_id):
    """학생 카드 저장 현황(관리자가 묶음 화면을 열어 둔 채로 강사·TA의 저장을 바로 보게, 15초마다 읽음)."""
    batch = _batch(request.user, batch_id)
    cards = batch.cards.select_related('updated_by')
    rows = [_status_row(c, batch) for c in cards]
    response = JsonResponse({'cards': rows, 'saved': sum(1 for r in rows if r['saved']), 'total': len(rows)})
    response['Cache-Control'] = 'private, no-store'
    return response


def _notify_published(batch):
    """공개할 때마다 새 알림(같은 카드라도 공개 시각이 다르면 따로)으로 학생·학부모에게 알립니다."""
    stamp = batch.published_at.strftime('%Y%m%d%H%M%S%f')
    label = FORMS[batch.form]['label']
    for card in batch.cards.all():
        create_notifications(learner_users_for_student(card.student_no), kind=Notification.Kind.SYSTEM,
                             title='리포트카드가 업데이트되었습니다', message=f'{batch.group.title} · {label} · {batch.title}',
                             target_url=reverse('reports:my-card', args=[card.pk]), event_key=f'report:{card.pk}:{stamp}')


@login_required
@require_POST
def batch_publish(request, batch_id):
    batch = _batch(request.user, batch_id)
    _admin_only(request.user)
    batch.published_at = timezone.now()
    batch.save(update_fields=['published_at', 'updated_at'])
    _notify_published(batch)
    messages.success(request, f'{batch.cards.count()}명의 학생·학부모에게 공개하고 알림을 보냈습니다. 고친 내용은 바로 보입니다.')
    return redirect('reports:batch', batch.pk)


@login_required
@require_POST
def batch_unpublish(request, batch_id):
    batch = _batch(request.user, batch_id)
    _admin_only(request.user)
    batch.published_at = None
    batch.save(update_fields=['published_at', 'updated_at'])
    messages.success(request, '공개를 취소했습니다. 학생·학부모 화면에서 보이지 않습니다.')
    return redirect('reports:batch', batch.pk)


def _my_cards(user):
    return (ReportCard.objects.filter(student_no__in=get_linked_student_nos(user), batch__published_at__isnull=False)
            .select_related('batch', 'batch__group'))


@login_required
def my_reports(request):
    """학생·학부모: 공개된 리포트카드를 반별로."""
    groups = {}
    for card in _my_cards(request.user).order_by('batch__group__title', '-batch__period_end'):
        groups.setdefault(card.batch.group.title, []).append({'card': card, 'form_label': FORMS.get(card.batch.form, {}).get('label', card.batch.form)})
    return render(request, 'reports/my_list.html', {'page_title': '리포트카드', 'groups': groups})


@login_required
def my_card(request, card_id):
    card = get_object_or_404(_my_cards(request.user), pk=card_id)
    batch = _ready(card.batch)
    context = _card_context(batch, card, editing=False)
    if request.GET.get('print') == '1':
        return render(request, 'reports/print.html', {'batch': batch, 'sheets': [context], 'page_title': f'{card.student_name} 리포트카드'})
    context.update({'page_title': f'{card.student_name} 리포트카드', 'form_label': FORMS[batch.form]['label']})
    return render(request, 'reports/my_card.html', context)


@login_required
def report_new(request):
    _staff(request.user)  # 11/19: 관리자·강사·TA. 반 선택지는 _groups(자기 반)로 제한
    groups = _groups(request.user)
    raw = request.POST.get('group') or request.GET.get('group') or ''
    group = groups.filter(pk=raw).first() if raw.isdigit() else None
    courses, down = _course_options(group) if group else ({}, '')
    # DSG 학생 찾기도 인트라넷을 거치므로, 인트라넷이 이미 끊겼으면 다시 기다리지 않습니다.
    mocks, mock_down = _mock_options(group) if group and not down else ({}, '')
    down = down or mock_down
    if down:
        messages.warning(request, f'{down}에 연결되지 않아 수업·DSG 모의고사 목록을 불러오지 못했습니다. '
                                  '잠시 뒤 다시 열거나 관리자에게 알려 주세요.')
    # 반을 나중에 골라도 먼저 고른 양식·유형·기간·제목이 남도록, 화면을 새로 열 때 주소로 받은 값을 채웁니다(11/10).
    initial = {'group': group}
    for key in ('form', 'term', 'course_type', 'period_start', 'period_end', 'week_base'):
        if request.GET.get(key):
            initial[key] = request.GET[key][:60]
    if group and 'term' not in initial and group.term:
        initial['term'] = group.term
    # 이 반 학생들이 듣는 인트라넷 수업이 하나뿐이면 미리 골라 둡니다(AP·GPA ESSAY 는 WEEK 대신 수업일, 11/17).
    if len(courses) == 1:
        initial['course'] = next(iter(courses))
    form = ReportBatchForm(request.POST or None, groups=groups, courses=courses, mocks=mocks, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        course = data['course_info']
        try:
            batch = services.create_batch(
                group=data['group'], form=data['form'], title=data['title'], period_start=data['period_start'],
                period_end=data['period_end'], week_base=data['week_base'], user=request.user,
                course_class_id=data['course'] or '', course_label=course.get('label', ''),
                course_name=course.get('name', ''), course_teacher=course.get('teacher', ''),
                course_type=data['course_type'], mock_exams=data['mock_exams'], mock_prev=data['mock_prev'])
        except sources.SourceUnavailable as exc:
            # 읽기는 저장 전에 끝나므로 아무것도 만들어지지 않았습니다. 고른 값은 화면에 그대로 둡니다.
            messages.error(request, f'{exc.label}에 연결되지 않아 리포트카드를 만들지 않았습니다. '
                                    '잠시 뒤 다시 만들거나 관리자에게 알려 주세요.')
        else:
            first = batch.cards.first()
            if not first:
                messages.warning(request, '이 반에 학생이 없어 카드를 만들지 못했습니다. 반 명단을 먼저 채워 주세요.')
                return redirect('reports:list')
            messages.success(request, f'{batch.cards.count()}명의 리포트카드를 만들고 데이터를 불러왔습니다.')
            return redirect('reports:card', batch.pk, first.pk)
    group_meta = [{'pk': g.pk, 'title': g.title, 'term': g.term, 'forms': ' '.join(group_forms(g))} for g in groups]
    selected = form['group'].value()
    return render(request, 'reports/new.html', {'page_title': '새 리포트카드', 'form': form, 'group': group,
                                                'has_groups': groups.exists(), 'group_meta': group_meta,
                                                'selected_group': str(selected or ''), 'form_specs': FORMS})


def _card_context(batch, card, editing):
    spec = FORMS[batch.form]
    data = card.data
    context = {'batch': batch, 'card': card, 'card_data': data, 'shared': batch.shared, 'spec': spec, 'editing': editing,
               'kind': spec['kind'], 'days': sources.WEEKDAYS, 'submit_choices': SUBMIT_CHOICES,
               'auto_locked': services.locked_paths(batch, card.auto)}
    if spec['kind'] == 'weekly':
        context['day_labels'] = sources.span_labels(batch.period_start, batch.period_end)
        context['monthly'] = (batch.period_end - batch.period_start).days > 6
        context['season'] = season_heading(batch.title)
        if spec['mock'] == 'sat':
            context['chart_rw'] = charts.sat_trend(data['mock']['last'], data['mock']['this'], 'rw', 'R/W')
            context['chart_math'] = charts.sat_trend(data['mock']['last'], data['mock']['this'], 'math', 'Math')
        else:
            context['chart_toefl'] = charts.toefl_bars(data['mock']['this'], data['mock']['last'])
    if spec['kind'] == 'term':
        # 수업일(또는 WEEK)을 5칸씩 한 줄(운영팀 11/17: 20회차면 1~5 / 6~10 / 11~15 / 16~20). 마지막 줄은 빈 칸으로 맞춥니다.
        weeks = list(enumerate(data['weeks']))
        rows = [weeks[i:i + 5] for i in range(0, len(weeks), 5)]
        if rows and len(rows[-1]) < 5:
            rows[-1] = rows[-1] + [(None, None)] * (5 - len(rows[-1]))
        context['week_rows'] = rows
        context['last_key'], context['last_label'] = spec['last']
    return context


def _ready(batch):
    """예전 모양으로 저장된 묶음을 지금 모양으로 맞춥니다(주간 코멘트 칸 목록)."""
    changed = services.ensure_block_list(batch)
    changed = services.ensure_weekly_layout(batch) or changed
    if changed:
        batch.save(update_fields=['shared', 'updated_at'])
    return batch


def _save_card(request, batch, card):
    scope = edit_scope(request.user, batch)
    locked = services.locked_paths(batch, card.auto)  # 자동 칸은 화면을 고쳐 보내도 그대로(11/20)
    if scope is not None:
        # 권한이 나뉜 카드는 맡은 칸만 저장합니다(화면을 고쳐 보내도 다른 칸은 그대로).
        allowed = {k: v for k, v in request.POST.items() if services.scope_allows(k, scope)}
        services.apply_post(card.data, allowed, 'd.', skip=locked)
        # 강사·TA(11/19)는 반 공통 글(공지·수업내용 등)도 씁니다. 제목(시즌)과 표 바꾸기는 관리자만.
        services.apply_post(batch.shared, allowed, 's.')
    else:
        services.apply_post(card.data, request.POST, 'd.', skip=locked)
        services.apply_post(batch.shared, request.POST, 's.')
        # 제목(시즌: 26FW, 2627WT …)은 카드 머리에서 바로 고칩니다. 비워 두면 그대로.
        title = request.POST.get('batch_title', '').strip()[:60]
        if title:
            batch.title = title
    card.updated_by = request.user
    if card.saved_at is None:
        card.saved_at = timezone.now()
    card.save(update_fields=['data', 'updated_by', 'updated_at', 'saved_at'])
    batch.save(update_fields=['shared', 'title', 'updated_at'])


def _save_posted(request, batch):
    """편집 화면의 다른 단추(다시 불러오기·칸 더하기·지우기)를 눌러도 지금 입력한 내용부터 저장합니다."""
    current = batch.cards.filter(pk=request.POST.get('card') or 0).first()
    if current:
        _save_card(request, batch, current)
    return current


def _back(batch, current):
    card = current or batch.cards.first()
    return redirect('reports:card', batch.pk, card.pk) if card else redirect('reports:list')


@login_required
def card_edit(request, batch_id, card_id):
    batch = _ready(_batch(request.user, batch_id))
    card = get_object_or_404(ReportCard, pk=card_id, batch=batch)
    cards = list(batch.cards.only('pk', 'student_name', 'student_no'))
    index = next(i for i, c in enumerate(cards) if c.pk == card.pk)
    if request.method == 'POST':
        _save_card(request, batch, card)
        messages.success(request, f'{card.student_name} 리포트카드를 저장했습니다.')
        # '저장 후 다음 학생'은 다음 학생을 이어서 고치고, 그냥 저장은 리포트카드 첫 목록으로 갑니다(11/19 사용자 요청).
        if 'next' in request.POST and index + 1 < len(cards):
            return redirect('reports:card', batch.pk, cards[index + 1].pk)
        return redirect('reports:list')
    context = _card_context(batch, card, editing=True)
    context['edit_scope'] = edit_scope(request.user, batch)
    context['scope_note'] = scope_note(request.user, batch)
    context['is_ta'] = is_ta(request.user)
    context.update(_neighbours(cards, index))
    context.update({'page_title': f'{card.student_name} 리포트카드', 'form_label': FORMS[batch.form]['label']})
    return render(request, 'reports/edit.html', context)


def _neighbours(cards, index):
    return {'cards': cards, 'position': index + 1, 'prev': cards[index - 1] if index > 0 else None,
            'next': cards[index + 1] if index + 1 < len(cards) else None}


@login_required
def card_view(request, batch_id, card_id):
    """리포트 열기: 학생·학부모가 보는 것과 같은 읽기 전용 카드(링크 활성). 고치려면 '수정'."""
    batch = _ready(_batch(request.user, batch_id))
    card = get_object_or_404(ReportCard, pk=card_id, batch=batch)
    cards = list(batch.cards.only('pk', 'student_name', 'student_no'))
    index = next(i for i, c in enumerate(cards) if c.pk == card.pk)
    context = _card_context(batch, card, editing=False)
    context.update(_neighbours(cards, index))
    context.update({'page_title': f'{card.student_name} 리포트카드', 'form_label': FORMS[batch.form]['label']})
    return render(request, 'reports/view.html', context)


@login_required
def batch_mocks(request, batch_id):
    """만든 뒤 SAT 모의고사(이번 칸·지난 칸) 바꾸기(11/20). 저장하면 바로 다시 불러오고, 강사가 고친 칸은 그대로 둡니다.
    다시 불러오기와 같은 사람(관리자, 그 반 강사·TA)이 씁니다."""
    batch = _ready(_batch(request.user, batch_id))
    if FORMS[batch.form].get('mock') != 'sat':
        raise Http404('SAT 리포트만 DSG 모의고사를 고릅니다.')
    cards = batch.cards.order_by('student_name', 'student_no')
    back = cards.filter(pk=request.GET.get('card') or request.POST.get('card') or 0).first() or cards.first()
    back_url = reverse('reports:card', args=[batch.pk, back.pk]) if back else reverse('reports:list')
    mocks, down = _mock_options(batch.group)
    if down:
        messages.warning(request, f'{down}에 연결되지 않아 모의고사 목록을 불러오지 못했습니다. 잠시 뒤 다시 열거나 관리자에게 알려 주세요.')
    saved = {key: batch.shared.get(key, []) for key in ('mock_exams', 'mock_prev')}
    for item in saved['mock_exams'] + saved['mock_prev']:  # 지금 목록에 없는 예전 선택도 표에 남깁니다
        mocks.setdefault(item['id'], {'name': item['name'], 'label': item['name']})
    course_type = batch.shared.get('course_type') or '정규'
    form = MockPickForm(request.POST or None, mocks=mocks, course_type=course_type,
                        initial={key: [item['id'] for item in items] for key, items in saved.items()})
    if request.method == 'POST' and form.is_valid():
        for key in ('mock_exams', 'mock_prev'):
            batch.shared[key] = [{'id': str(i), 'name': n} for i, n in form.cleaned_data[key]]
        batch.save(update_fields=['shared', 'updated_at'])
        try:
            changed = services.refresh_batch(batch, request.user)
        except sources.SourceUnavailable as exc:
            messages.error(request, f'고른 시험은 저장했지만 {exc.label}에 연결되지 않아 점수를 불러오지 못했습니다. '
                                    '연결되면 데이터 다시 불러오기를 눌러 주세요.')
        else:
            messages.success(request, f'모의고사를 바꾸고 데이터를 다시 불러왔습니다. 바뀐 칸 {changed}개 (직접 고친 칸은 그대로 둡니다).')
        return redirect(back_url)
    return render(request, 'reports/mocks.html', {'page_title': '모의고사 고르기', 'batch': batch, 'form': form, 'back_url': back_url,
                                                  'back': back, 'limit': MOCK_LIMIT.get(course_type, 1), 'course_type': course_type})


@login_required
@require_POST
def batch_refresh(request, batch_id):
    batch = _ready(_batch(request.user, batch_id))  # 11/19: 다시 불러오기는 만드는 사람(강사·TA)도
    current = _save_posted(request, batch)
    try:
        changed = services.refresh_batch(batch, request.user)
    except sources.SourceUnavailable as exc:
        # 빈 값으로 덮어쓰지 않도록 카드는 건드리지 않습니다(방금 입력한 내용은 위에서 이미 저장됨, 11/20).
        messages.error(request, f'{exc.label}에 연결되지 않아 데이터를 불러오지 않았습니다. 카드 내용은 그대로입니다. '
                                '잠시 뒤 다시 누르거나 관리자에게 알려 주세요.')
        return _back(batch, current)
    messages.success(request, f'데이터를 다시 불러왔습니다. 바뀐 칸 {changed}개 (직접 고친 칸과 코멘트는 그대로 둡니다).')
    return _back(batch, current)


@login_required
@require_POST
def block_add(request, batch_id):
    batch = _ready(_batch(request.user, batch_id))
    if FORMS[batch.form]['kind'] != 'weekly':
        raise Http404('주간 리포트에만 과제별 코멘트 칸이 있습니다.')
    _full_access(request.user, batch)
    current = _save_posted(request, batch)
    services.add_block(batch)
    messages.success(request, '과제 코멘트 칸을 더했습니다. 이름과 설명을 고쳐 쓰세요(반 학생 모두에게 같은 칸이 생깁니다).')
    return _back(batch, current)


@login_required
@require_POST
def block_delete(request, batch_id, key):
    batch = _ready(_batch(request.user, batch_id))
    if not any(b['key'] == key for b in batch.shared.get('block_list', [])):
        raise Http404('없는 코멘트 칸입니다.')
    _full_access(request.user, batch)
    current = _save_posted(request, batch)
    services.delete_block(batch, key)
    messages.success(request, '과제 코멘트 칸을 지웠습니다.')
    return _back(batch, current)


@login_required
@require_POST
def section_toggle(request, batch_id, key):
    batch = _ready(_batch(request.user, batch_id))
    if FORMS[batch.form]['kind'] != 'weekly' or key not in weekly_sections(batch.form):
        raise Http404('없는 표입니다.')
    _full_access(request.user, batch)
    current = _save_posted(request, batch)
    title = batch.shared.get('titles', {}).get(key, key)
    hidden = services.toggle_section(batch, key)
    messages.success(request, f"'{title}' 표를 {'뺐습니다' if hidden else '다시 넣었습니다'}(반 학생 모두 같이 바뀝니다).")
    return _back(batch, current)


@login_required
@require_POST
def row_add(request, batch_id):
    batch = _batch(request.user, batch_id)
    _admin_only(request.user)
    if FORMS[batch.form]['kind'] != 'junior':
        raise Http404('주니어미들 카드에만 주차 행을 더합니다.')
    current = _save_posted(request, batch)
    label = services.add_junior_row(batch)
    messages.success(request, f'{label} 행을 더했습니다(반 학생 모두에게 같은 행이 생깁니다).')
    return _back(batch, current)


@login_required
@require_POST
def row_delete(request, batch_id, label):
    batch = _batch(request.user, batch_id)
    _admin_only(request.user)
    if FORMS[batch.form]['kind'] != 'junior' or label not in batch.shared.get('contents', {}):
        raise Http404('없는 주차 행입니다.')
    current = _save_posted(request, batch)
    services.delete_junior_row(batch, label)
    messages.success(request, f'{label} 행을 지웠습니다.')
    return _back(batch, current)


@login_required
def batch_print(request, batch_id, card_id=None):
    batch = _ready(_batch(request.user, batch_id))
    cards = batch.cards.all() if card_id is None else [get_object_or_404(ReportCard, pk=card_id, batch=batch)]
    sheets = [_card_context(batch, card, editing=False) for card in cards]
    return render(request, 'reports/print.html', {'batch': batch, 'sheets': sheets, 'page_title': f'{batch.title} 리포트카드 인쇄'})


@login_required
@require_POST
def batch_delete(request, batch_id):
    batch = _batch(request.user, batch_id)
    _admin_only(request.user)
    batch.delete()
    messages.success(request, '리포트카드 묶음을 지웠습니다.')
    return redirect('reports:list')
