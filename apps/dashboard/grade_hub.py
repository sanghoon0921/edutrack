"""성적 분석(11/19): 학생관리처럼 학생 목록 → 반 고르기·이름/번호 검색·쪽 번호 → 줄을 누르면 아래에 DSG 분석.

보이는 학생: 관리자 = 모든 반 학생 + 모든 담당 지정, 강사 = 담당 지정 + 자기 반 학생, TA = 담당 반 학생(pool_student_pairs).
학생 정보(학교·학년)는 지금 쪽 20명만 인트라넷에서 한 번에 읽습니다.
"""
from django.core.exceptions import ImproperlyConfigured
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import class_staff_required
from apps.learning.models import LearningGroup
from apps.lms.access import staff_group_ids
from apps.lms.models import GroupMember
from apps.operations.access import require_student_access
from apps.students.services import StudentService
from apps.students.student_rows import pool_student_pairs

PAGE_SIZE = 20


@class_staff_required
@never_cache
def teacher_grades(request):
    user = request.user
    groups = list(LearningGroup.objects.filter(pk__in=staff_group_ids(user)).order_by('sort_order', 'title', 'pk'))
    raw_group = str(request.GET.get('group', '')).strip()
    selected_group = next((g for g in groups if raw_group.isdigit() and g.pk == int(raw_group)), None)
    q = str(request.GET.get('q', '')).strip()[:100]

    pairs = pool_student_pairs(user, selected_group.pk if selected_group else None)
    if q:
        needle = q.casefold()
        pairs = [(no, name) for no, name in pairs if needle in no.casefold() or needle in name.casefold()]
    page = Paginator(pairs, PAGE_SIZE).get_page(request.GET.get('page'))
    page_nos = [no for no, _ in page.object_list]

    lookup_error = False
    student_map = {}
    try:
        student_map = {s.student_id: s for s in StudentService().get_students(page_nos)}
    except (DatabaseError, ImproperlyConfigured):
        lookup_error = True
    group_titles: dict[str, list[str]] = {}
    visible_ids = [g.pk for g in groups]
    for no, title in GroupMember.objects.filter(student_no__in=page_nos, group_id__in=visible_ids, active=True).values_list('student_no', 'group__title'):
        group_titles.setdefault(no, []).append(title)
    rows = []
    for index, (no, name) in enumerate(page.object_list, start=page.start_index()):
        info = student_map.get(no)
        rows.append({'index': index, 'student_no': no, 'name': (info.name if info else '') or name or f'학생 {no}',
                     'school': info.school if info else '', 'grade': info.grade if info else '',
                     'groups': ', '.join(sorted(group_titles.get(no, [])))})

    selected = str(request.GET.get('student_no', '')).strip()[:50]
    if not selected and len(pairs) == 1:
        selected = pairs[0][0]  # 학생이 한 명뿐이면 바로 고릅니다
    ctx = {'page_title': '성적 분석', 'rows': rows, 'page': page, 'total': len(pairs), 'q': q, 'groups': groups,
           'selected_group': selected_group, 'selected_student_no': selected, 'student': None,
           'lookup_error': lookup_error, 'missing_student': False}
    if selected:
        require_student_access(user, selected, conceal=True)
        try:
            ctx['student'] = StudentService().get_student(selected)
            ctx['missing_student'] = ctx['student'] is None
        except (DatabaseError, ImproperlyConfigured):
            ctx['lookup_error'] = True
    return render(request, 'dashboard/teacher_grades_live.html', ctx)
