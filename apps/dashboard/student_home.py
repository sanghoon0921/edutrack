"""Student home read model. UI permissions are never inferred from names or cached."""
from datetime import datetime, time, timedelta
from urllib.parse import urlsplit
import logging
import re
from django.conf import settings
from django.db.models import Exists, OuterRef, Q
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import StudentAccountLink
from apps.assignments.models import AssignmentRecipient
from apps.communications.models import Notice
from apps.communications.services import visible_notices_for_user
from apps.learning.models import LearningGroup, QuizRecipient, QuizAttempt
from apps.lms.models import ClassPost, RoomSettings
from apps.lms.message_queries import message_summary
from apps.students.course_services import CourseService
from apps.students.attendance_services import AttendanceService

logger = logging.getLogger(__name__)
MAX_COURSES = 100
MAX_STUDENTS = 5


def student_scope(user):
    """Real mode requires active SELF links. Demo-only fallback stays demo-only."""
    ids=list(StudentAccountLink.objects.filter(user=user,is_active=True,relationship='SELF')
             .order_by('-is_primary','pk').values_list('student_no',flat=True))
    if not ids and str(getattr(settings,'STUDENT_DATA_SOURCE','')).lower() == 'demo' and not StudentAccountLink.objects.filter(user=user,is_active=True).exists():
        from apps.operations.access import learner_student_ids
        ids=sorted(learner_student_ids(user))
    return list(dict.fromkeys(str(x).strip() for x in ids if str(x).strip()))


def home_clock(now=None):
    now=now or timezone.now()
    local=timezone.localtime(now,timezone.get_default_timezone())
    beginning=timezone.make_aware(datetime.combine(local.date(),time.min),timezone.get_default_timezone())
    ending=timezone.make_aware(datetime.combine(local.date()+timedelta(days=1),time.min),timezone.get_default_timezone())
    return local,beginning,ending


def safe_zoom_url(value):
    """Allow direct HTTPS Zoom links only; never fetch/resolve links on the server."""
    raw=str(value or '').strip()
    if not raw or len(raw)>2000 or any(c.isspace() or ord(c)<32 for c in raw) or '\\' in raw:
        return ''
    try:
        parsed=urlsplit(raw)
        host=(parsed.hostname or '').lower()
        domains=getattr(settings,'HOME_ZOOM_ALLOWED_DOMAINS',('zoom.us','zoom.com'))
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443):
            return ''
        if not any(host==d or host.endswith('.'+d) for d in domains):
            return ''
    except (ValueError,TypeError):
        return ''
    return raw


def group_scope(ids):
    return LearningGroup.objects.filter(lms_members__active=True,lms_members__student_no__in=ids).distinct()


def home_notices(user,groups,limit=6):
    rows=[]
    for n in visible_notices_for_user(user)[:limit]:
        source='반 공지 · '+n.group.title if n.category==Notice.Category.CLASS and n.group_id else '학원 공지'
        rows.append({'title':n.title,'source':source,'at':n.published_at or n.created_at,
                     'pinned':n.is_pinned,'url':reverse('communications:notice-detail',args=[n.pk])})
    for n in ClassPost.objects.filter(group__in=groups,kind='NOTICE',published=True).select_related('group')[:limit]:
        rows.append({'title':n.title,'source':n.group.title,'at':n.created_at,'pinned':n.pinned,
                     'url':reverse('lms:post',args=[n.pk])})
    rows.sort(key=lambda n:(n['pinned'],n['at']),reverse=True)
    return rows[:limit]


def today_deadlines(ids,beginning,ending,now):
    items=[]
    # Only directly assigned, currently published activities. Never count unassigned learners.
    assignments=AssignmentRecipient.objects.filter(student_id__in=ids,
        assignment__is_published=True,assignment__due_at__gte=beginning,assignment__due_at__lt=ending).filter(
        Q(assignment__available_from__isnull=True)|Q(assignment__available_from__lte=now))
    quizzes=QuizRecipient.objects.filter(student_id__in=ids,
        quiz__is_published=True,quiz__due_at__gte=beginning,quiz__due_at__lt=ending).filter(
        Q(quiz__available_from__isnull=True)|Q(quiz__available_from__lte=now))
    total=assignments.count()+quizzes.count()
    for r in assignments.select_related('assignment','submission').order_by('assignment__due_at','pk')[:30]:
        done=bool(r.submission_object and r.submission_object.submitted_at)
        items.append({'title':r.assignment.title,'kind':'과제','due_at':r.assignment.due_at,
            'label':'제출완료' if done else ('마감지남' if r.assignment.due_at<now else '제출하기'),
            'done':done,'expired':r.assignment.due_at<now,'url':reverse('assignments:my-detail',args=[r.pk])})
    attempted=QuizAttempt.objects.filter(recipient_id=OuterRef('pk'),submitted_at__isnull=False)
    for r in quizzes.select_related('quiz').annotate(done=Exists(attempted)).order_by('quiz__due_at','pk')[:30]:
        items.append({'title':r.quiz.title,'kind':'퀴즈','due_at':r.quiz.due_at,
            'label':'응시완료' if r.done else ('마감지남' if r.quiz.due_at<now else '응시하기'),
            'done':r.done,'expired':r.quiz.due_at<now,'url':reverse('learning:my-quiz-detail',args=[r.pk])})
    items.sort(key=lambda i:(i['done'],i['due_at']))
    return items,total


def home_context(user,ids=None):
    ids=student_scope(user) if ids is None else ids
    groups=group_scope(ids)
    local,beginning,ending=home_clock()
    deadlines,due_count=today_deadlines(ids,beginning,ending,local)
    rooms=[]
    for room in RoomSettings.objects.filter(group__in=groups).select_related('group').order_by('group__sort_order','group__title','pk')[:20]:
        url=safe_zoom_url(room.zoom_url)
        rooms.append({'title':room.group.title,'url':url,'schedule':room.schedule,
                      'needs_review':bool(room.zoom_url and not url),'room_url':reverse('lms:room',args=[room.group_id])})
    return {'student_home':{
        'today':local,'timezone':str(timezone.get_default_timezone()),'linked':bool(ids),
        'room_count':groups.count(),'rooms':rooms,'deadlines':deadlines,'due_count':due_count,
        'deadlines_truncated':due_count>len(deadlines),'notices':home_notices(user,groups),
        'messages':message_summary(user),'schedule_url':reverse('home-today'),
    }}


def _zoom_for_lessons(student_no,assign_ids,day):
    if not assign_ids or getattr(settings,'STUDENT_DATA_SOURCE','demo') != 'intranet':return {}
    # Same student/assignment/date scope as the displayed schedule; no unscoped class lookup.
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('_zoom_for_lessons')


def _session_state(record,now):
    if record.is_class_cancelled or record.status_kind=='holiday':return '휴강','cancelled'
    if record.is_student_cancelled or record.status_kind=='cancelled' or record.payment_code=='REFUND':return '취소','cancelled'
    match=re.fullmatch(r'(\d{2}):(\d{2})[–~\-](\d{2}):(\d{2})',record.time_summary.replace(' ',''))
    if not match:return '시간 확인','unknown'
    sh,sm,eh,em=map(int,match.groups())
    if sh>23 or eh>23 or sm>59 or em>59:return '시간 확인','unknown'
    start,end=sh*60+sm,eh*60+em
    clock=now.hour*60+now.minute
    if end<=start:return '시간 확인','unknown' # overnight/ambiguous entries are not guessed
    if clock<start:return '예정','upcoming'
    if clock<end:return '진행 중','ongoing'
    return '종료','finished'


def today_sessions(user,now=None):
    ids=student_scope(user)
    local,_,_=home_clock(now)
    day=local.date()
    result={'items':[],'date':day.isoformat(),'timezone':str(timezone.get_default_timezone()),
            'linked':bool(ids),'partial':len(ids)>MAX_STUDENTS,'zoom_warning':False}
    if not ids:return result
    for sid in ids[:MAX_STUDENTS]:
        all_courses=CourseService().get_student_courses(sid)
        courses=[c for c in all_courses if c.display_status.strip() not in CourseService.EXCLUDED_STATUSES
                 and (c.start_date is None or c.start_date<=day) and (c.end_date is None or c.end_date>=day)]
        result['partial'] |= len(courses)>MAX_COURSES
        courses=courses[:MAX_COURSES]
        assign_ids=list(dict.fromkeys(c.assign_id for c in courses if c.assign_id))
        grouped=AttendanceService().get_attendance_for_courses(sid,assign_ids)
        relevant=[c for c in courses if any(r.lesson_date==day for r in grouped.get(c.assign_id,([],None))[0])]
        try:
            zooms=_zoom_for_lessons(sid,list(dict.fromkeys(c.assign_id for c in relevant)),day)
        except Exception as error:
            # A missing optional zoom column must not suppress otherwise valid schedules.
            logger.warning('home_zoom_unavailable type=%s',type(error).__name__)
            zooms={};result['zoom_warning']=True
        seen=set()
        for course in relevant:
            for record in grouped.get(course.assign_id,([],None))[0]:
                key=(sid,course.assign_id,record.lesson_id,record.lesson_date,record.time_summary)
                if record.lesson_date!=day or record.payment_code=='CARRY_OVER' or key in seen:continue
                seen.add(key)
                label,state=_session_state(record,local)
                url=zooms.get((course.assign_id,record.lesson_id),'') if state not in ('cancelled','finished') else ''
                result['items'].append({'title':course.class_name or course.subject_name or '수업',
                    'time':record.time_summary or '시간 미등록','teacher':course.teacher_names,
                    'label':label,'state':state,'zoom_url':url,'url':reverse('student_classes')})
    result['items'].sort(key=lambda x:(x['time']=='시간 미등록',x['time'],x['title']))
    result['partial'] |= len(result['items'])>100
    result['items']=result['items'][:100]
    return result
