"""Compact messenger read API. Shares all existing conversation authorization."""
from uuid import uuid4
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from apps.communications.services import visible_unread_notification_count
from .message_queries import message_summary, summary_queryset, serialize_summary
from .message_views import allowed_user, get_conversation
from . import rooms


def conversation_label(conv, user):
    if conv.group_id:
        return conv.group.title + (' · 단체방' if conv.kind == 'CLASS' else ' · 그룹 대화')
    peers = [m.user.chat_name for m in conv.participants.select_related('user').prefetch_related('user__student_links') if m.user_id != user.pk]
    return ', '.join(peers) or '개인 대화'


def row_payload(row, user):
    return {'id': row.pk, 'body': row.body, 'sender': row.sender.chat_name,
            'own': row.sender_id == user.pk,
            'time': timezone.localtime(row.created_at).strftime('%m.%d %H:%M')}


@login_required
@never_cache
@require_GET
def summary(request):
    allowed_user(request.user)
    rooms.ensure_class_rooms(request.user, throttle=True)
    data = message_summary(request.user, 8)
    data['unread_items'] = [serialize_summary(c) for c in summary_queryset(request.user).filter(has_unread=True)[:8]]
    data['notification_count'] = visible_unread_notification_count(request.user)
    data['total_unread'] = data['notification_count'] + data['unread_count']
    response = JsonResponse(data)
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@never_cache
@require_GET
def snapshot(request, conversation_id):
    conv = get_conversation(request, conversation_id)
    before = request.GET.get('before', '')
    if before and (not before.isdigit() or len(before) > 18):
        return JsonResponse({'error':'메시지 위치를 확인하세요.'}, status=400)
    qs = rooms.visible_messages(conv, request.user).select_related('sender').prefetch_related('sender__student_links')
    if before:
        qs = qs.filter(pk__lt=int(before))
    rows = list(qs.order_by('-pk')[:61]); has_older = len(rows) > 60
    rows = rows[:60]; rows.reverse()
    data = {'id':conv.pk, 'title':conversation_label(conv,request.user),
            'messages':[row_payload(row,request.user) for row in rows],
            'members':[m['name'] for m in rooms.member_list(conv,request.user)],
            'last_id':rows[-1].pk if rows else 0,
            'before':rows[0].pk if rows and has_older else None,
            'client_token':str(uuid4()),
            'url':reverse('lms:conversation',args=[conv.pk]),
            'feed_url':reverse('lms:conversation-feed',args=[conv.pk]),
            'read_url':reverse('lms:conversation-read',args=[conv.pk])}
    response=JsonResponse(data); response['Cache-Control']='private, no-store'; return response
