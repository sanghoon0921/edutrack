"""Permission-filtered message summaries. Read-only; previews never mark a thread read."""
from django.db.models import Count, Exists, OuterRef, Q, Subquery, Value, BigIntegerField, Prefetch
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from .access import contacts_for, visible_groups
from .models import Conversation, ConversationMember, GroupMember, Message


def accessible_conversations(user):
    if not user.is_authenticated or not user.is_active or user.role == User.Role.PARENT:
        return Conversation.objects.none()
    peers = contacts_for(user).values('pk')
    eligible_peer = ConversationMember.objects.filter(conversation_id=OuterRef('pk')).exclude(user_id=user.pk).filter(
        Q(user_id__in=peers) | Q(user__is_active=True, user__role=User.Role.ADMIN))
    own = ConversationMember.objects.filter(conversation_id=OuterRef('pk'), user_id=user.pk)
    counts = ConversationMember.objects.filter(conversation_id=OuterRef('pk')).order_by().values('conversation_id').annotate(n=Count('pk')).values('n')
    return Conversation.objects.annotate(
        _participant=Exists(own), _eligible_peer=Exists(eligible_peer), _participant_count=Subquery(counts),
    ).filter(_participant=True).filter(
        Q(group_id__in=visible_groups(user).values('pk')) |
        Q(group__isnull=True, _participant_count=2, _eligible_peer=True) |
        Q(group__isnull=True, kind='GROUP', _participant_count__gt=2))


def summary_queryset(user):
    member = ConversationMember.objects.filter(conversation_id=OuterRef('pk'), user_id=user.pk)
    # 반 단체방에 나중에 들어온 사람은 들어온 뒤의 메시지만 미리보기·안 읽음에 셉니다.
    latest = Message.objects.filter(conversation_id=OuterRef('pk'), pk__gt=OuterRef('joined_id')).order_by('-pk')
    # Annotation is expanded into the correlated subquery; no per-row permission cache.
    qs = accessible_conversations(user).select_related('group').prefetch_related(
        Prefetch('participants', queryset=ConversationMember.objects.exclude(user_id=user.pk).select_related('user').prefetch_related('user__student_links'), to_attr='_display_peers')
    ).annotate(
        joined_id=Coalesce(Subquery(member.values('joined_after')[:1]), Value(0), output_field=BigIntegerField()),
    ).annotate(
        read_id=Coalesce(Subquery(member.values('last_read_id')[:1]), Value(0), output_field=BigIntegerField()),
        last_message_id=Subquery(latest.values('pk')[:1]),
        last_body=Subquery(latest.values('body')[:1]),
        last_time=Subquery(latest.values('created_at')[:1]),
    )
    unseen = Message.objects.filter(conversation_id=OuterRef('pk'), pk__gt=OuterRef('read_id')).filter(pk__gt=OuterRef('joined_id')).exclude(sender_id=user.pk)
    return qs.annotate(has_unread=Exists(unseen)).order_by('-updated_at', '-pk')


def chat_filter_groups(user):
    """메시지 화면의 '반' 고르기 목록: 그 사람이 볼 수 있는 반만."""
    return visible_groups(user).order_by('sort_order', 'title', 'pk')


def parse_chat_filter(user, params):
    """주소의 q(이름·학생번호·방 이름)와 group(반 번호)을 읽습니다. 볼 수 없는 반이나 잘못된 값은 무시합니다."""
    q = (params.get('q') or '').strip()[:60]
    raw = (params.get('group') or '').strip()
    group = chat_filter_groups(user).filter(pk=int(raw)).first() if raw.isdigit() and len(raw) < 10 else None
    return q, group


def filter_summaries(qs, user, q='', group=None):
    """메시지 목록 거르기(11/16).

    - group: 그 반의 단체방·그룹 대화, 그리고 그 반 학생과 나눈 1:1·반 없는 그룹 대화
    - q: 방 이름, 반 이름, 또는 나 말고 참여자의 이름·아이디·학생번호
    """
    others = ConversationMember.objects.filter(conversation_id=OuterRef('pk')).exclude(user_id=user.pk)
    if group is not None:
        numbers = GroupMember.objects.filter(group=group, active=True).values('student_no')
        class_peer = others.filter(user__student_links__is_active=True, user__student_links__relationship='SELF',
                                   user__student_links__student_no__in=numbers)
        qs = qs.annotate(_class_peer=Exists(class_peer)).filter(Q(group=group) | Q(group__isnull=True, _class_peer=True))
    if q:
        named = others.filter(Q(user__display_name__icontains=q) | Q(user__username__icontains=q)
                              | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
                              | Q(user__student_links__is_active=True, user__student_links__student_no__icontains=q))
        qs = qs.annotate(_name_hit=Exists(named)).filter(
            Q(custom_title__icontains=q) | Q(group__title__icontains=q) | Q(_name_hit=True))
    return qs


def conversation_name(conv, user):
    if conv.custom_title and conv.kind != Conversation.Kind.DIRECT:
        return conv.custom_title
    if conv.kind == Conversation.Kind.CLASS:
        count = getattr(conv, '_participant_count', None) or conv.participants.count()
        return f"{conv.group.title} · 단체방 {count}명"
    if conv.group_id:
        return conv.group.title
    # summary_queryset()이 미리 불러온 상대 목록(_display_peers)을 쓰고, 없으면 DB에서 읽는다.
    members = conv._display_peers if hasattr(conv, '_display_peers') else conv.participants.select_related('user').prefetch_related('user__student_links')
    names = [m.user.chat_name for m in members if m.user_id != user.pk]
    return peer_label(names) or "대화"


def peer_label(names):
    """그룹 대화 이름: 세 명까지 이름, 나머지는 '외 N명'."""
    return ", ".join(names[:3]) + (f" 외 {len(names) - 3}명" if len(names) > 3 else "")


def serialize_summary(conv, user=None):
    at = conv.last_time or conv.updated_at
    peers = getattr(conv, '_display_peers', [])
    label = (conv.group.title + (' · 단체방' if conv.kind == Conversation.Kind.CLASS else ' · 그룹 대화')) if conv.group_id else (peer_label([m.user.chat_name for m in peers]) or '개인 대화')
    if conv.custom_title and conv.kind != Conversation.Kind.DIRECT:
        label = conv.custom_title
    return {
        'id': conv.pk, 'title': conversation_name(conv, user) if user else label, 'group': conv.group.title if conv.group_id else '개인 대화',
        'kind': conv.kind,
        'url': reverse('lms:conversation', args=[conv.pk]), 'preview': (conv.last_body or '대화를 시작해 보세요.')[:160],
        'unread': bool(conv.has_unread), 'time': timezone.localtime(at).strftime('%m.%d %H:%M'),
        'last_id': conv.last_message_id or 0,
    }


def message_summary(user, limit=5):
    qs = summary_queryset(user)
    return {'items': [serialize_summary(c, user) for c in qs[:limit]], 'unread_count': qs.filter(has_unread=True).count()}
