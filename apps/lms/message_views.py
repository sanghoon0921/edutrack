from urllib.parse import urlencode
from uuid import uuid4
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q, Max, Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404,render,redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from .message_queries import (summary_queryset, message_summary, serialize_summary, conversation_name,
                             chat_filter_groups, parse_chat_filter, filter_summaries)
from apps.accounts.models import User,StudentAccountLink
from apps.learning.models import LearningGroup
from apps.operations.access import is_admin,is_teacher
from .access import contacts_for,can_converse,require_group,staff_group_ids
from .forms import MessageForm,ConversationForm
from .models import Conversation,ConversationMember,Message
from .room_views import audit
from . import rooms


def allowed_user(user):
    if user.role==User.Role.PARENT and not is_admin(user):
        raise PermissionDenied('메시지는 학생과 담당 강사·TA가 사용합니다.')


def get_conversation(request,pk):
    conv=get_object_or_404(Conversation.objects.select_related('group'),pk=pk)
    if not can_converse(request.user,conv):raise Http404('접근 가능한 대화가 아닙니다.')
    return conv


def chat_filter_context(request):
    """메시지 화면 왼쪽 목록의 검색어·반 선택. 목록 링크·자동 새로고침·쪽 이동이 같은 조건을 이어 갑니다."""
    q,group=parse_chat_filter(request.user,request.GET)
    params={k:v for k,v in (('q',q),('group',group.pk if group else '')) if v}
    query=urlencode(params)
    can_start=is_admin(request.user) or is_teacher(request.user)
    return {'q':q,'selected_group':group,'filter_groups':chat_filter_groups(request.user),
            'filter_query':query,'filter_keep':('?'+query) if query else '',
            'can_start_class':bool(group and can_start and staff_group_ids(request.user).filter(pk=group.pk).exists())}


def filtered_summaries(request,ctx):
    return filter_summaries(summary_queryset(request.user),request.user,ctx['q'],ctx['selected_group'])


@login_required
def inbox(request):
    allowed_user(request.user)
    rooms.ensure_class_rooms(request.user)
    ctx=chat_filter_context(request)
    page=Paginator(filtered_summaries(request,ctx),25).get_page(request.GET.get('page'))
    rows=[]
    for c in page:
        name=conversation_name(c, request.user)
        rows.append({'conv':c,'unread':c.has_unread,'preview':c.last_body or '','label':name,'title':name})
    # 반별 대화 시작(11/16): 강사·관리자는 자기 반마다 '단체방'과 '학생 골라 대화'를 바로 엽니다.
    class_rows=LearningGroup.objects.filter(pk__in=staff_group_ids(request.user)).annotate(
        n_students=Count('lms_members',filter=Q(lms_members__active=True),distinct=True)).order_by('sort_order','title','pk')
    # 단체방 단추는 내가 참여자인 반에만(11/19): 관리자가 남의 반 단체방을 누르면 404가 나던 문제.
    # 단체방 참여자 = 반 학생 + 개설 강사 + 활성 공동 강사·TA (rooms.class_room_user_ids 와 같은 기준)
    room_group_ids=set(LearningGroup.objects.filter(Q(created_by=request.user)|Q(lms_staff__user=request.user,lms_staff__active=True)).values_list('pk',flat=True))
    feed=reverse('lms:inbox-feed')+f'?page={page.number}'+('&'+ctx['filter_query'] if ctx['filter_query'] else '')
    return render(request,'lms/inbox.html',{'page_title':'메시지','rows':rows,'page':page,'class_rows':class_rows,
      'room_group_ids':room_group_ids,'feed_url':feed,**ctx})


@login_required
@never_cache
@require_GET
def inbox_feed(request):
    allowed_user(request.user)
    if request.GET.get('scope') == 'home':
        result=message_summary(request.user,5)
    else:
        page=Paginator(filtered_summaries(request,chat_filter_context(request)),25).get_page(request.GET.get('page'))
        result={'items':[serialize_summary(c, request.user) for c in page], 'page':page.number,
                'pages':page.paginator.num_pages,
                'unread_count':summary_queryset(request.user).filter(has_unread=True).count()}
    return JsonResponse(result)


def group_people(group,user):
    """반에서 대화에 넣을 수 있는 사람: 반 학생(본인 계정), 반 담당 강사·TA, 반 개설자. 나는 뺍니다."""
    return User.objects.filter(is_active=True).filter(
      Q(role=User.Role.STUDENT,student_links__is_active=True,student_links__relationship='SELF',student_links__student_no__in=group.lms_members.filter(active=True).values_list('student_no',flat=True))
      | Q(role=User.Role.TEACHER,lms_teaching_groups__group=group,lms_teaching_groups__active=True)
      | Q(pk=group.created_by_id)).exclude(pk=user.pk).distinct()


def group_room(creator,users,group=None):
    """같은 사람들끼리의 그룹 대화가 있으면 그 방, 없으면 새로 만듭니다."""
    with transaction.atomic():
        # Lock participants consistently on databases that support row locks.
        user_ids = sorted({creator.pk, *(u.pk for u in users)})
        list(User.objects.select_for_update().filter(pk__in=user_ids).order_by('pk'))
        candidates = Conversation.objects.filter(group=group,kind=Conversation.Kind.GROUP).annotate(n_members=Count('participants')).filter(n_members=len(user_ids))
        for uid in user_ids:
            candidates = candidates.filter(participants__user_id=uid)
        conv = candidates.order_by('-updated_at', '-pk').first()
        if not conv or not can_converse(creator, conv):
            # 반 없이 여러 명을 고른 그룹 대화는 제목 대신 참여자 이름을 보여 줍니다(conversation_name).
            conv=Conversation.objects.create(title=group.title[:160] if group else '그룹 대화',kind=Conversation.Kind.GROUP,group=group,created_by=creator)
            ConversationMember.objects.bulk_create([ConversationMember(conversation=conv,user=u) for u in [creator,*users]])
            audit(creator,'message.create',conv.pk,count=len(users)+1)
    return conv


@login_required
def new_conversation(request):
    allowed_user(request.user)
    raw=request.GET.get('group',request.POST.get('group',''))
    group=None
    allowed=contacts_for(request.user)
    if raw:
        if not raw.isdigit():raise Http404
        group=get_object_or_404(LearningGroup,pk=int(raw));require_group(request.user,group,write=True)
        allowed=group_people(group,request.user)
    form=ConversationForm(request.POST or None)
    form.fields['recipients'].queryset=allowed
    if request.method=='POST' and form.is_valid():
        users=list(form.cleaned_data['recipients'])
        if not group and len(users)==1:
            # 1:1 은 두 사람당 한 방: 누가 먼저 시작해도 같은 방에 대화가 계속 쌓입니다.
            conv=rooms.direct_room(request.user,users[0])
            return redirect('lms:conversation',conv.pk)
        if not group and not (is_admin(request.user) or is_teacher(request.user)):
            form.add_error('recipients','학생은 한 명과만 대화를 시작할 수 있습니다. 한 명만 골라 주세요.')
        elif len(users)>200:form.add_error('recipients','참여자는 최대 200명입니다.')
        else:
            conv=group_room(request.user,users,group)
            return redirect('lms:conversation',conv.pk)
    return render(request,'lms/new_chat.html',{'page_title':'그룹 대화' if group else '새 대화','form':form,'group':group,
      'can_group':is_admin(request.user) or is_teacher(request.user)})


@login_required
def conversation(request,conversation_id):
    conv=get_conversation(request,conversation_id)
    form=MessageForm(request.POST or None,initial={'client_token':uuid4()})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            # Membership re-check within save transaction.
            conv=Conversation.objects.select_for_update().get(pk=conv.pk)
            if not can_converse(request.user,conv):raise PermissionDenied
            token=form.cleaned_data['client_token']
            existing,created=Message.objects.get_or_create(client_token=token,defaults={
                'conversation':conv,'sender':request.user,'body':form.cleaned_data['body']})
            if existing.conversation_id!=conv.pk or existing.sender_id!=request.user.pk or existing.body != form.cleaned_data['body']:
                raise PermissionDenied('메시지 요청이 일치하지 않습니다.')
            if created:
                Conversation.objects.filter(pk=conv.pk).update(updated_at=timezone.now())
        if request.headers.get('Accept') == 'application/json':
            response=JsonResponse({'ok':True,'id':existing.pk,'client_token':str(uuid4()), 'message':serialize_message(existing, request.user)})
            response['Cache-Control']='private, no-store'
            return response
        return redirect('lms:conversation',conv.pk)
    if request.method=='POST' and request.headers.get('Accept') == 'application/json':
        return JsonResponse({'ok':False,'error':'내용 또는 요청을 확인하세요. 입력한 메시지는 유지됩니다.'},status=400)
    qs=rooms.visible_messages(conv,request.user).select_related('sender').prefetch_related('sender__student_links')
    before=request.GET.get('before','')
    if before.isdigit():qs=qs.filter(pk__lt=int(before))
    records=list(qs.order_by('-pk')[:100]);records.reverse()
    newest=records[-1].pk if records else 0
    if not before:
        ConversationMember.objects.filter(conversation=conv,user=request.user,last_read_id__lt=newest).update(last_read_id=newest)
    older=bool(records and qs.filter(pk__lt=records[0].pk).exists())
    marks=rooms.read_marks(conv,request.user)
    display_title=conversation_name(conv,request.user)
    ctx=chat_filter_context(request)
    return render(request,'lms/conversation.html',{**ctx,'members_action':members_action(request.user,conv),'can_delete':is_admin(request.user),
      'feed_url':reverse('lms:inbox-feed')+('?'+ctx['filter_query'] if ctx['filter_query'] else ''),'page_title':display_title,'conversation_label':display_title,'display_title':display_title,'conv':conv,'records':records,
      'can_rename':can_rename(request.user,conv),
      'form':form,'last_id':newest,'before':records[0].pk if older else '','blocks':rooms.message_blocks(records,request.user,marks),
      'read_marks':marks,'room_kind':conv.kind,'members':rooms.member_list(conv,request.user),
      'poll':not before,'participants':conv.participants.select_related('user').prefetch_related('user__student_links'), 'chat_rows':[serialize_summary(c,request.user) for c in filtered_summaries(request,ctx)[:25]]})


def can_rename(user,conv):
    """방 이름은 관리자·강사만 바꿉니다(1:1 대화 제외, 참여 중인 방만)."""
    if conv.kind==Conversation.Kind.DIRECT:return False
    return user.role in (User.Role.ADMIN,User.Role.TEACHER) and can_converse(user,conv)


@login_required
@require_POST
def conversation_rename(request,conversation_id):
    conv=get_object_or_404(Conversation,pk=conversation_id)
    if conv.kind==Conversation.Kind.DIRECT:raise Http404('1:1 대화는 이름을 바꾸지 않습니다.')
    if not can_rename(request.user,conv):raise PermissionDenied('방 이름은 관리자·강사만 바꿀 수 있습니다.')
    conv.custom_title=request.POST.get('title','').strip()[:80]
    conv.save(update_fields=['custom_title','updated_at'])
    messages.success(request,f"방 이름을 '{conv.custom_title}'(으)로 바꿨습니다. 참여자 모두에게 보입니다." if conv.custom_title else '방 이름을 기본 이름으로 되돌렸습니다.')
    return redirect('lms:conversation',conv.pk)


@login_required
@never_cache
@require_GET
def conversation_feed(request,conversation_id):
    conv=get_conversation(request,conversation_id)
    raw=request.GET.get('before') or request.GET.get('after','0')
    if not raw.isdigit() or len(raw)>18:return JsonResponse({'error':'올바르지 않은 메시지 위치입니다.'},status=400)
    older = bool(request.GET.get('before'))
    qs=rooms.visible_messages(conv,request.user).filter(**{'pk__lt' if older else 'pk__gt':int(raw)}).select_related('sender').prefetch_related('sender__student_links')
    rows=list(qs.order_by('-pk' if older else 'pk')[:101])
    has_more=len(rows)>100
    rows=rows[:100]
    if older:rows.reverse()
    marks=rooms.read_marks(conv,request.user)
    return JsonResponse({'messages':[serialize_message(r,request.user,marks) for r in rows], 'has_more':has_more, 'older':older,'read_marks':marks})


@login_required
@never_cache
@require_POST
def conversation_read(request,conversation_id):
    """Acknowledge only messages actually displayed, with CSRF and current membership."""
    conv=get_conversation(request,conversation_id)
    raw=request.POST.get('up_to','')
    if not raw.isdigit() or len(raw)>18:
        return JsonResponse({'error':'올바르지 않은 메시지 위치입니다.'},status=400)
    target=int(raw)
    if target and not conv.messages.filter(pk=target).exists():
        return JsonResponse({'error':'이 대화의 메시지가 아닙니다.'},status=400)
    ConversationMember.objects.filter(conversation=conv,user=request.user,last_read_id__lt=target).update(last_read_id=target)
    return JsonResponse({'ok':True})


def serialize_message(record, user, marks=None):
    return rooms.message_row(record,user,marks if marks is not None else rooms.read_marks(record.conversation,user))


@login_required
def class_chat(request,group_id):
    """반 단체방 열기: 없으면 만들고 참여자를 반 명단에 맞춘 뒤 들어갑니다."""
    allowed_user(request.user)
    group=get_object_or_404(LearningGroup,pk=group_id)
    require_group(request.user,group)
    conv=rooms.sync_class_room(group)
    if not conv.participants.filter(user=request.user).exists():
        raise Http404('이 반 단체방의 참여자가 아닙니다.')
    return redirect('lms:conversation',conv.pk)


def members_action(user,conv):
    """대화 머리의 '인원 추가' 버튼. 반 단체방은 반 명단을 따르므로 명단 수정 화면으로 보냅니다."""
    if not (is_admin(user) or is_teacher(user)):
        return None
    if conv.kind==Conversation.Kind.CLASS:
        if is_admin(user) or conv.group.created_by_id==user.pk:
            return {'url':reverse('lms:roster',args=[conv.group_id]),'label':'반 명단 수정'}
        return None
    return {'url':reverse('lms:conversation-members',args=[conv.pk]),'label':'인원 추가'}


@login_required
def conversation_members(request,conversation_id):
    """인원 추가(11/16). 그룹 대화는 그 방에 바로 넣고, 1:1 대화는 카카오톡처럼 새 그룹 대화를 만듭니다.
    새로 들어온 사람은 들어온 뒤의 메시지부터 봅니다(반 단체방과 같은 규칙)."""
    conv=get_conversation(request,conversation_id)
    if not (is_admin(request.user) or is_teacher(request.user)):
        raise PermissionDenied('인원 추가는 관리자·강사만 할 수 있습니다.')
    if conv.kind==Conversation.Kind.CLASS:
        require_group(request.user,conv.group,roster=True)
        return redirect('lms:roster',conv.group_id)
    if conv.group_id:
        require_group(request.user,conv.group,write=True)
        allowed=group_people(conv.group,request.user)
    else:
        allowed=contacts_for(request.user)
    current=list(conv.participants.values_list('user_id',flat=True))
    form=ConversationForm(request.POST or None)
    form.fields['recipients'].queryset=allowed.exclude(pk__in=current)
    if request.method=='POST' and form.is_valid():
        users=list(form.cleaned_data['recipients'])
        if len(current)+len(users)>200:
            form.add_error('recipients','참여자는 최대 200명입니다.')
        elif conv.kind==Conversation.Kind.DIRECT:
            others=list(User.objects.filter(pk__in=current).exclude(pk=request.user.pk))
            target=group_room(request.user,[*others,*users])
            messages.success(request,'1:1 대화는 그대로 두고, 새 그룹 대화를 만들었습니다.')
            return redirect('lms:conversation',target.pk)
        else:
            with transaction.atomic():
                conv=Conversation.objects.select_for_update().get(pk=conv.pk)
                last=conv.messages.order_by('-pk').values_list('pk',flat=True).first() or 0
                ConversationMember.objects.bulk_create([ConversationMember(conversation=conv,user=u,joined_after=last,last_read_id=last) for u in users],ignore_conflicts=True)
                Conversation.objects.filter(pk=conv.pk).update(updated_at=timezone.now())
                audit(request.user,'message.members_add',conv.pk,count=len(users))
            messages.success(request,f'{len(users)}명을 추가했습니다. 추가된 사람은 지금부터 오는 메시지를 봅니다.')
            return redirect('lms:conversation',conv.pk)
    title=conversation_name(conv,request.user)
    return render(request,'lms/conversation_members.html',{'page_title':'인원 추가','form':form,'conv':conv,
      'conversation_label':title,'is_direct':conv.kind==Conversation.Kind.DIRECT,'current_count':len(current)})


@login_required
@require_POST
def conversation_delete(request,conversation_id):
    """관리자만 대화방을 지웁니다(운영팀 11/17). 메시지도 함께 지워지고 되돌릴 수 없습니다.
    반 단체방은 반 명단을 따라 빈 방으로 다시 만들어집니다."""
    if not is_admin(request.user):
        raise PermissionDenied('대화방 삭제는 관리자만 할 수 있습니다.')
    conv=get_object_or_404(Conversation.objects.select_related('group'),pk=conversation_id)
    name=conversation_name(conv,request.user)
    count=conv.messages.count()
    was_class=conv.kind==Conversation.Kind.CLASS
    audit(request.user,'message.delete',conv.pk,kind=conv.kind,messages=count,title=name[:80])
    conv.delete()
    messages.success(request,f"'{name}' 대화방을 지웠습니다(메시지 {count}개)."+(' 반 단체방은 반 명단대로 빈 방이 다시 만들어집니다.' if was_class else ''))
    return redirect('lms:inbox')
