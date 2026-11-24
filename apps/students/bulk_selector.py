"""Bounded, permission-filtered browsing for existing student selection forms.

No writes to external DBs. Intranet rosters are enrollment records,
not imported LMS groups. Final write paths still revalidate their own permissions.
"""
from __future__ import annotations
import math
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.db import DatabaseError
from django.db.models import Q
from django.utils.connection import ConnectionDoesNotExist
from django.http import JsonResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from apps.learning.models import LearningGroup
from apps.lms.access import can_teach_group, staff_group_ids
from apps.lms.models import GroupMember
from apps.operations.access import is_admin, is_ta, is_teacher, teacher_student_ids
from apps.students.repositories import DEMO_STUDENTS
from apps.students.course_repositories import DEMO_COURSES
from apps.students.selection import student_to_selector_item
from apps.operations.models import TeacherStudentAccess
from apps.students.student_rows import decorate, with_classes

PAGE_SIZE = 50
DIRECTORY_SIZES = (20, 50, 100)  # 학생 관리 '20명·50명·100명' 보기(11/11)
MAX_SELECTION = 200
ACTIVE_CLASS_STATUSES = ('P', 'W')


def number(raw, *, default=0):
    value = str(raw or '').strip()
    if not value:
        return default
    if not value.isdigit() or len(value)>18:
        raise ValueError('번호 형식이 올바르지 않습니다.')
    return int(value)


def scope_for(user, mode='activity', group_id=0):
    # 11/24: TA(11/19 권한 '반별 학습 게시')도 과제·퀴즈·토론 대상 학생을 고릅니다. 범위는 맡은 반 학생뿐.
    if not user.is_authenticated or not user.is_active or not (is_admin(user) or is_teacher(user) or is_ta(user)):
        raise PermissionDenied('관리자·강사·TA만 학생을 선택할 수 있습니다.')
    if mode not in {'activity', 'teacher'}:
        raise ValueError('선택 범위를 확인하세요.')
    if mode == 'teacher':
        if not is_teacher(user):
            raise PermissionDenied('담당 학생 지정은 강사 본인만 가능합니다.')
        # Existing self-assignment policy explicitly permits discovering new students.
        return None
    if group_id:
        if not can_teach_group(user, group_id):
            raise Http404('접근 가능한 반이 아닙니다.')
        if GroupMember.objects.filter(group_id=group_id).exists():
            return set(GroupMember.objects.filter(group_id=group_id,active=True).values_list('student_no',flat=True))
    if is_ta(user):
        return set(GroupMember.objects.filter(group_id__in=staff_group_ids(user),active=True).values_list('student_no',flat=True))
    return None if is_admin(user) else set(teacher_student_ids(user))


def data_mode():
    source=str(getattr(settings,'STUDENT_DATA_SOURCE','demo')).lower()
    if source not in {'demo','intranet'}:
        raise ImproperlyConfigured('학생 원장 설정을 확인하세요.')
    return source


def demo_status(course):
    """데모 수업 상태 코드: 진행중=P, 예정=W, 그 밖=E."""
    if course.is_active:
        return 'P'
    return 'W' if course.display_status == '예정' else 'E'


def demo_classes():
    classes={}
    for sid,courses in DEMO_COURSES.items():
        for c in courses:
            info=classes.setdefault(c.class_id, {'id':c.class_id, 'name':c.class_name, 'status':demo_status(c), 'student_ids':set()})
            info['student_ids'].add(sid)
    return list(classes.values())


def classes_for(allowed, q='', status='', page=1):
    if status not in {'','active','P','W','E','C'}:
        raise ValueError('수업 상태를 확인하세요.')
    if allowed is not None and not allowed:
        return [],0
    if data_mode()=='demo':
        items=[x for x in demo_classes() if allowed is None or x['student_ids'] & allowed]
        if q:items=[x for x in items if q.casefold() in (x['name']+' '+x['id']).casefold()]
        if status:items=[x for x in items if x['status'] in ({'P','W'} if status=='active' else {status})]
        n=len(items)
        return [{k:v for k,v in x.items() if k!='student_ids'} for x in items[(page-1)*50:page*50]],n
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('classes_for')


def browse_students(allowed, *, q='', class_id='', grade='', school='', offset=0, limit=50):
    if allowed is not None and not allowed:return [],0
    if data_mode()=='demo':
        items=list(DEMO_STUDENTS)
        if allowed is not None:items=[s for s in items if s.student_id in allowed]
        if class_id:
            members=next((x['student_ids'] for x in demo_classes() if x['id']==class_id),set())
            items=[s for s in items if s.student_id in members]
        if q:
            items=[s for s in items if q.casefold() in ' '.join([s.name,s.student_id,s.english_name,s.grade,s.school,s.branch,s.country,s.city]).casefold()]
        if grade:items=[s for s in items if grade.casefold() in s.grade.casefold()]
        if school:items=[s for s in items if school.casefold() in s.school.casefold()]
        items.sort(key=lambda s:(s.name,s.student_id))
        return [student_to_selector_item(s) for s in items[offset:offset+limit]], len(items)
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('browse_students')


def current_classes_for(student_ids):
    """학생번호별 진행·예정 인트라넷 수업 목록(읽기 전용, 한 번의 조회)."""
    ids=list(dict.fromkeys(str(s).strip() for s in student_ids if str(s).strip()))
    if not ids:
        return {}
    result={sid:[] for sid in ids}
    if data_mode()=='demo':
        for sid in ids:
            for c in DEMO_COURSES.get(sid,()):
                status=demo_status(c)
                if status in ACTIVE_CLASS_STATUSES:
                    result[sid].append({'id':c.class_id,'name':c.class_name,'status':status})
        return result
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('current_classes_for')


def list_selection(user, params):
    mode=params.get('mode','activity')
    gid=number(params.get('activity_group'))
    allowed=scope_for(user,mode,gid)
    source=params.get('source','all')
    if source not in {'all','lms','intranet'}:raise ValueError('학생 조회 방식을 확인하세요.')
    page=max(1,min(number(params.get('page'),default=1),10000))
    all_rows=params.get('all')=='1'
    # Teacher registration writes at most 100 students per transaction, unchanged.
    maximum=100 if mode=='teacher' else MAX_SELECTION
    size=number(params.get('size'),default=PAGE_SIZE) if params.get('size') else PAGE_SIZE
    page_size=size if size in DIRECTORY_SIZES else PAGE_SIZE
    limit=maximum+1 if all_rows else page_size
    q=str(params.get('q','')).strip()[:100]
    grade=str(params.get('grade','')).strip()[:30]
    school=str(params.get('school','')).strip()[:100]
    if source=='lms':
        filter_gid=number(params.get('filter_group'))
        if not filter_gid:return {'results':[],'total':0,'page':1,'pages':1,'has_more':False,'message':'조회할 LMS 반을 선택하세요.'},200
        if not can_teach_group(user,filter_gid):raise Http404('접근 가능한 반이 아닙니다.')
        rows=GroupMember.objects.filter(group_id=filter_gid,active=True)
        if allowed is not None:rows=rows.filter(student_no__in=allowed)
        if q:rows=rows.filter(Q(student_name__icontains=q)|Q(student_no__icontains=q))
        rows=rows.order_by('student_name','student_no');total=rows.count()
        offset=0 if all_rows else (page-1)*page_size
        items=[{'student_id':m.student_no,'name':m.student_name,'school':'','grade':'','status':''} for m in rows[offset:offset+limit]]
    else:
        cid=str(number(params.get('class_id'))) if params.get('class_id') else ''
        if source=='intranet' and not cid:
            return {'results':[],'total':0,'page':1,'pages':1,'has_more':False,'message':'조회할 인트라넷 수업을 선택하세요.'},200
        items,total=browse_students(allowed,q=q,class_id=cid if source=='intranet' else '',grade=grade,school=school,offset=0 if all_rows else (page-1)*page_size,limit=limit)
    if all_rows and total>maximum:
        return {'results':[],'total':total,'message':f'현재 조건은 {total}명입니다. 전체 추가는 한 번에 {maximum}명까지 가능하므로 수업·검색 조건을 좁혀 주세요.'},409
    # 화면의 한 줄 행에 필요한 값(학교·학년, 듣는 수업, 검색어)을 붙인다. '전체 추가'는 행을 그리지 않으므로 수업 조회를 건너뛴다.
    items=[decorate(i) for i in items] if all_rows else with_classes(items)
    if mode=='teacher':
        assigned=set(TeacherStudentAccess.objects.filter(teacher=user,is_active=True).values_list('student_no',flat=True))
        for item in items:item['assigned']=item['student_id'] in assigned
    return {'results':items,'students':items,'total':total,'count':len(items),'page':page,'page_size':page_size,
        'pages':max(1,math.ceil(total/page_size)),'has_more':page*page_size<total,
        'selection_limit':maximum,'message':f'{total}명 중 {len(items)}명 표시' if not all_rows else f'{len(items)}명 전체 선택'},200


@login_required
@require_GET
@never_cache
def selector_browse(request):
    try:
        payload,status=list_selection(request.user,request.GET)
        return JsonResponse(payload,status=status)
    except ValueError as exc:return JsonResponse({'message':str(exc)},status=400)
    except (DatabaseError,ImproperlyConfigured,ConnectionDoesNotExist):
        return JsonResponse({'message':'인트라넷에 연결되지 않아 학생·수업 정보를 불러오지 못했습니다. 잠시 뒤 다시 시도하거나 관리자에게 알려 주세요. 고른 학생은 그대로 둡니다.'},status=503)


@login_required
@require_GET
@never_cache
def selector_options(request):
    try:
        allowed=scope_for(request.user,request.GET.get('mode','activity'),number(request.GET.get('activity_group')))
        if request.GET.get('source')=='all':
            # 공용 거르기 막대의 수업·반 드롭다운: 진행·예정 수업(최대 50개)과 사용자가 가르치는 반
            classes,total=classes_for(allowed,q=str(request.GET.get('q','')).strip()[:100],status='active',page=1)
            groups=LearningGroup.objects.filter(pk__in=staff_group_ids(request.user)).order_by('title','pk')
            return JsonResponse({'classes':classes,'groups':[{'id':str(g.pk),'name':g.title} for g in groups],'total':total,'has_more':total>len(classes)})
        if request.GET.get('source')=='intranet':
            page=max(1,min(number(request.GET.get('page'),default=1),10000))
            items,total=classes_for(allowed,q=str(request.GET.get('q','')).strip()[:100],status=request.GET.get('status',''),page=page)
            return JsonResponse({'items':items,'total':total,'page':page,'has_more':page*50<total})
        groups=LearningGroup.objects.filter(pk__in=staff_group_ids(request.user)).order_by('title','pk')
        return JsonResponse({'items':[{'id':str(g.pk),'name':g.title} for g in groups]})
    except ValueError as exc:return JsonResponse({'message':str(exc)},status=400)
    except (DatabaseError,ImproperlyConfigured,ConnectionDoesNotExist):
        return JsonResponse({'message':'수업 목록을 조회하지 못했습니다. 다시 시도해 주세요.'},status=503)
