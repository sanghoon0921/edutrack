from pathlib import Path
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.db.utils import DatabaseError
from django.http import FileResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from apps.learning.models import LearningGroup
from apps.learning.services import validate_student_scope
from apps.operations.access import is_admin, is_teacher, learner_student_ids
from apps.students.selection import build_student_selector_context
from .access import visible_groups, require_group, can_teach_group, staff_scope
from .forms import RoomForm, RosterForm, PostForm
from .models import RoomSettings, GroupMember, GroupStaff, ClassPost, PostFile, ChangeLog


def audit(user,action,target,**detail):
    ChangeLog.objects.create(actor=user,action=action,target=str(target),detail=detail)


def get_group(request,group_id,**kwargs):
    group=get_object_or_404(LearningGroup,pk=group_id)
    require_group(request.user,group,**kwargs)
    return group


@login_required
def rooms(request):
    visible=visible_groups(request.user)
    # 반 바로 가기(11/19): 드롭다운에서 고르면 ?go=<반> 으로 와서 바로 그 반으로 갑니다. 볼 수 없는 반이면 404.
    go=request.GET.get('go','')
    if go:
        if not go.isdigit() or not visible.filter(pk=int(go)).exists():raise Http404('접근 가능한 반이 아닙니다.')
        return redirect('lms:room',int(go))
    groups=visible.select_related('created_by')
    q=request.GET.get('q','').strip()[:100]
    if q:groups=groups.filter(title__icontains=q)
    # Term·강사로 거르기(운영팀 10/29). 강사는 개설자 또는 공동 강사·TA로 지정된 반.
    term=request.GET.get('term','').strip()[:20]
    if term:groups=groups.filter(term=term)
    teacher=request.GET.get('teacher','')
    if teacher.isdigit():groups=groups.filter(Q(created_by_id=teacher)|Q(lms_staff__user_id=teacher,lms_staff__active=True)).distinct()
    terms=sorted({t for t in visible.values_list('term',flat=True) if t},reverse=True)
    teachers=get_user_model().objects.filter(Q(created_learning_groups__in=visible)|Q(lms_teaching_groups__group__in=visible,lms_teaching_groups__active=True)).distinct().order_by('display_name','username')
    return render(request,'lms/rooms.html',{'page_title':'반별 학습 공간','groups':groups,'jump_groups':visible.order_by('sort_order','title','pk'),
      'can_create':is_admin(request.user) or is_teacher(request.user),'q':q,'term':term,'teacher':teacher,'terms':terms,'teachers':teachers})


# 반 화면 탭(운영팀 10/29: 과제·토론·퀴즈·성적제출현황·자료·반 공지를 반 하나에). 성적·제출현황은 성적표 화면(그 반으로 거름)으로 갑니다.
ROOM_TABS=(('','반 홈'),('assignments','과제'),('discussions','토론'),('quizzes','퀴즈'),('grades','성적·제출현황'),('materials','자료'),('notices','반 공지'))
ROOM_ACTIVITIES={'assignments':'과제','quizzes':'퀴즈','discussions':'토론'}


@login_required
def room(request,group_id):
    group=get_group(request,group_id)
    staff=can_teach_group(request.user,group.pk)
    tab=request.GET.get('tab','')
    if tab not in {key for key,_ in ROOM_TABS} or tab=='grades':tab=''
    posts=group.lms_posts.all()
    if not staff:posts=posts.filter(published=True)
    kind=request.GET.get('kind','')
    if tab=='materials':posts=posts.filter(kind__in=('PAGE','FILE'))
    elif tab=='notices':posts=posts.filter(kind='NOTICE')
    elif kind in {'NOTICE','PAGE','FILE'}:posts=posts.filter(kind=kind)
    q=request.GET.get('q','').strip()[:100]
    if q:posts=posts.filter(Q(title__icontains=q)|Q(body__icontains=q))
    activities=[]
    limit=200 if tab in ROOM_ACTIVITIES else 30
    for label,rel,staff_url,my_url in [
      ('과제',group.assignments,'assignments:detail','assignments:my-detail'),
      ('퀴즈',group.quizzes,'learning:quiz-detail','learning:my-quiz-detail'),
      ('토론',group.discussions,'learning:discussion-detail','learning:my-discussion-detail')]:
        if tab in ROOM_ACTIVITIES and ROOM_ACTIVITIES[tab]!=label:continue
        for obj in rel.all().order_by('-created_at')[:limit]:
            if staff:url=reverse(staff_url,args=[obj.pk])
            else:
                recipient=obj.recipients.filter(student_id__in=learner_student_ids(request.user)).first()
                if not recipient or not obj.is_available:continue
                url=reverse(my_url,args=[recipient.pk])
            activities.append({'label':label,'title':obj.title,'due_at':obj.due_at,'url':url})
    class_notices=[]
    if tab=='notices':
        from apps.communications.services import visible_notices_for_user
        class_notices=visible_notices_for_user(request.user).filter(group=group)[:50]
    return render(request,'lms/room.html',{'page_title':group.title,'group':group,'jump_groups':visible_groups(request.user).order_by('sort_order','title','pk'),
      'settings':RoomSettings.objects.filter(group=group).first(),'staff':staff,
      'roster_allowed':is_admin(request.user) or group.created_by_id==request.user.pk,
      'page':Paginator(posts.prefetch_related('files'),20).get_page(request.GET.get('page')),
      'kind':kind,'q':q,'activities':activities,'tab':tab,'tabs':ROOM_TABS,'activity_label':ROOM_ACTIVITIES.get(tab,''),
      'class_notices':class_notices})


@login_required
def room_settings(request,group_id):
    group=get_group(request,group_id,write=True)
    instance=RoomSettings.objects.filter(group=group).first() or RoomSettings(group=group)
    form=RoomForm(request.POST or None,instance=instance)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():form.save();audit(request.user,'room.settings',group.pk)
        messages.success(request,'수업 스케줄과 링크를 저장했습니다.')
        return redirect('lms:room',group.pk)
    return render(request,'lms/form.html',{'page_title':'반 기본 안내 설정','form':form,'group':group})


@login_required
def roster(request,group_id):
    group=get_group(request,group_id,roster=True)
    existing=group.lms_members.filter(active=True)
    form=RosterForm(request.POST or None,initial={
      'student_ids':list(existing.values_list('student_no',flat=True)),
      'staff':list(group.lms_staff.filter(active=True).values_list('user_id',flat=True))})
    if request.method=='POST' and form.is_valid():
        try:
            resolved=validate_student_scope(request.user,form.cleaned_data['student_ids'])
        except ValidationError as exc:form.add_error('student_ids',exc)
        except DatabaseError:form.add_error('student_ids','학생 원장 연결을 확인하지 못했습니다. 명단은 변경하지 않았습니다.')
        else:
            from .roster_service import apply_roster
            apply_roster(group,resolved,form.cleaned_data['staff'],actor=request.user)
            messages.success(request,'반 명단과 공동 작업 담당자를 저장했습니다. 기존 과제 배정·제출 기록은 유지됩니다.')
            return redirect('lms:room',group.pk)
    fallback=[type('R',(),{'student_id':m.student_no,'student_name':m.student_name})() for m in existing]
    selector=build_student_selector_context(form=form,user=request.user,recipients=fallback)
    return render(request,'lms/roster.html',{'page_title':'반 명단·TA 지정','form':form,'group':group,'student_selector':selector})


@login_required
def group_students(request,group_id):
    group=get_group(request,group_id,write=True)
    if not group.lms_members.exists():
        from apps.students.views import student_selector_search
        return student_selector_search(request)
    members=group.lms_members.filter(active=True)
    q=request.GET.get('q','').strip()[:100]
    if q:members=members.filter(Q(student_name__icontains=q)|Q(student_no__icontains=q))
    items=[{'student_id':m.student_no,'name':m.student_name,'english_name':'','grade':'','school':'','country':'','city':'','branch':'','status':''} for m in members[:30]]
    return JsonResponse({'results':items,'students':items,'count':len(items),'has_more':members.count()>30})


@login_required
def post_edit(request,group_id,post_id=None):
    group=get_group(request,group_id,write=True)
    post=get_object_or_404(ClassPost,pk=post_id,group=group) if post_id else ClassPost(group=group,created_by=request.user)
    initial={'kind':request.GET.get('kind','NOTICE')}
    form=PostForm(request.POST or None,request.FILES or None,instance=post,initial=initial)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            post=form.save()
            for file in form.cleaned_data['uploads']:
                PostFile.objects.create(post=post,file=file,original_name=Path(file.name).name[:255],size=file.size)
            audit(request.user,'post.save',post.pk,kind=post.kind)
        messages.success(request,'반 게시물을 저장했습니다.')
        return redirect('lms:post',post.pk)
    return render(request,'lms/form.html',{'page_title':'반 게시물 수정' if post_id else '반 게시물 등록','form':form,'group':group,'post':post})


@login_required
def post_detail(request,post_id):
    post=get_object_or_404(ClassPost.objects.select_related('group','created_by').prefetch_related('files'),pk=post_id)
    require_group(request.user,post.group)
    staff=can_teach_group(request.user,post.group_id)
    if not post.published and not staff:raise Http404
    return render(request,'lms/post.html',{'page_title':post.title,'post':post,'group':post.group,'staff':staff})


@login_required
@require_POST
def post_delete(request,post_id):
    post=get_object_or_404(ClassPost.objects.select_related('group'),pk=post_id)
    require_group(request.user,post.group,write=True);gid=post.group_id
    with transaction.atomic():
        audit(request.user,'post.delete',post.pk);post.delete()
    messages.success(request,'게시물을 삭제했습니다.')
    return redirect('lms:room',gid)


@login_required
def post_file(request,file_id):
    f=get_object_or_404(PostFile.objects.select_related('post__group'),pk=file_id)
    require_group(request.user,f.post.group)
    if not f.post.published and not can_teach_group(request.user,f.post.group_id):raise Http404
    response=FileResponse(f.file.open('rb'),as_attachment=True,filename=f.original_name)
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


@login_required
@require_POST
def post_file_delete(request,file_id):
    f=get_object_or_404(PostFile.objects.select_related('post__group'),pk=file_id)
    require_group(request.user,f.post.group,write=True)
    pid=f.post_id
    with transaction.atomic():
        f.delete();audit(request.user,'post.file.delete',file_id)
    return redirect('lms:post',pid)
