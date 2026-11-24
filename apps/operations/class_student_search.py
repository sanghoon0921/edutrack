"""Read-only class lookup for teacher self-assignment (① 수업 찾기).
No financial fields, credentials or external writes are exposed.
학생 명단은 공용 학생 목록 부품(students:selector-browse, mode=teacher)이 맡는다.
"""
import logging

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.dashboard.class_catalog import term_subject_options
from apps.students.bulk_selector import demo_status
from apps.students.course_repositories import DEMO_COURSES
from .teacher_self_assignment import _is_teacher

logger = logging.getLogger(__name__)
STATUS = {'W':'대기','P':'진행중','E':'종료','C':'폐강'}
CLASS_PAGE_SIZE = 20


def text(value):
    return str(value or '').strip()[:100]


def page_number(value):
    try: return min(100000, max(1, int(value)))
    except (ValueError, TypeError): return 1


def source():
    value = str(getattr(settings,'STUDENT_DATA_SOURCE','demo')).lower()
    if value not in {'demo','intranet'}: raise ImproperlyConfigured('학생 데이터 조회 설정을 확인하세요.')
    return value


def _demo_class_items():
    """데모 수업 = 학생 명단과 같은 데모 수업(DEMO_COURSES). 그래서 수업을 누르면 명단이 실제로 나온다."""
    items = {}
    for courses in DEMO_COURSES.values():
        for course in courses:
            code = demo_status(course)
            item = items.setdefault(course.class_id, {'id': course.class_id, 'title': course.class_name, 'term': course.term_name,
                'subject': course.subject_name, 'status_code': code, 'status': STATUS.get(code, '미지정'), 'student_count': 0})
            item['student_count'] += 1
    return sorted(items.values(), key=lambda i: i['id'], reverse=True)


def search_classes(query='',status='',term='',subject='',page=1):
    if status and status not in STATUS: raise ValueError('수업 상태를 확인하세요.')
    offset=(page-1)*CLASS_PAGE_SIZE
    options=term_subject_options()
    lists={'terms':list(options.terms),'subjects':list(options.subjects)}
    if source() == 'demo':
        q=query.casefold()
        filtered=[i for i in _demo_class_items() if (not q or q in i['title'].casefold()) and (not status or i['status_code']==status)
                  and (not term or i['term']==term) and (not subject or i['subject']==subject)]
        return {'classes':filtered[offset:offset+CLASS_PAGE_SIZE],'total':len(filtered),'page':page,
                'has_more':len(filtered)>offset+CLASS_PAGE_SIZE,**lists}
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('search_classes')


@require_GET
@never_cache
def class_search(request):
    if not request.user.is_authenticated:return JsonResponse({'ok':False,'message':'다시 로그인하세요.'},status=401)
    if not _is_teacher(request.user):return JsonResponse({'ok':False,'message':'강사만 조회할 수 있습니다.'},status=403)
    try:
        data=search_classes(text(request.GET.get('q')),text(request.GET.get('status')),text(request.GET.get('term')),
                            text(request.GET.get('subject')),page_number(request.GET.get('page')))
        return JsonResponse({'ok':True,**data})
    except ValueError as e:return JsonResponse({'ok':False,'message':str(e)},status=400)
    except Exception as e:
        logger.warning('class_search_unavailable type=%s',type(e).__name__)
        return JsonResponse({'ok':False,'message':'수업 목록을 조회하지 못했습니다. 연결을 확인하고 다시 검색하세요.'},status=503)
