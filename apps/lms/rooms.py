"""메신저 방 규칙.

- 1:1 방은 두 사람당 하나(direct_key = 작은 id:큰 id). 누가 먼저 말을 걸어도 같은 방에 메시지가 계속 쌓입니다.
- 반 단체방은 반마다 하나. 참여자 = 반 학생(본인 계정) + 반 개설 강사 + 활성 공동 강사·TA. 명단이 바뀌면 sync_class_room 이 맞춥니다.
  나중에 들어온 사람은 joined_after 뒤의 메시지만 봅니다. 학부모는 메신저를 쓰지 않으므로 넣지 않습니다.
- 안 읽음 수: 보낸 사람·보는 사람을 뺀 참여자 중 아직 읽지 않은 사람 수(카카오톡의 숫자 '1').
"""
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.learning.models import LearningGroup
from apps.operations.access import is_admin, is_teacher, learner_student_ids

from .models import Conversation, ConversationMember

DAY_NAMES = "월화수목금토일"


def _pk(user):
    return getattr(user, "pk", user)


def direct_key(user, other):
    low, high = sorted([_pk(user), _pk(other)])
    return f"{low}:{high}"


def direct_room(user, other):
    key = direct_key(user, other)
    room = Conversation.objects.filter(direct_key=key).first()
    if room:
        return room
    # 키가 붙기 전의 옛 1:1 방(같은 두 사람만 있는 방)이 있으면 그 방을 이어 씁니다.
    # 참여자 수를 먼저 세고(전체 참여자 기준) 그다음 두 사람이 모두 있는지 거릅니다.
    legacy = (Conversation.objects.filter(group__isnull=True, direct_key__isnull=True).annotate(n=Count("participants")).filter(n=2)
              .filter(participants__user_id=_pk(user)).filter(participants__user_id=_pk(other))
              .order_by("created_at", "pk").first())
    if legacy and Conversation.objects.filter(pk=legacy.pk, direct_key__isnull=True).update(kind=Conversation.Kind.DIRECT, direct_key=key):
        return Conversation.objects.get(pk=legacy.pk)
    try:
        with transaction.atomic():
            room = Conversation.objects.create(title="개인 대화", kind=Conversation.Kind.DIRECT, direct_key=key, created_by=user)
            ConversationMember.objects.bulk_create([ConversationMember(conversation=room, user=user),
                                                    ConversationMember(conversation=room, user_id=_pk(other))])
    except IntegrityError:
        room = Conversation.objects.get(direct_key=key)
    return room


def class_room_user_ids(group):
    numbers = group.lms_members.filter(active=True).values_list("student_no", flat=True)
    students = User.objects.filter(is_active=True, role=User.Role.STUDENT, student_links__is_active=True,
                                   student_links__relationship=StudentAccountLink.Relationship.SELF,
                                   student_links__student_no__in=numbers)
    staff = User.objects.filter(is_active=True, lms_teaching_groups__group=group, lms_teaching_groups__active=True)
    ids = set(students.values_list("pk", flat=True)) | set(staff.values_list("pk", flat=True))
    creator = group.created_by
    if creator and creator.is_active and creator.role in (User.Role.TEACHER, User.Role.ADMIN):
        ids.add(creator.pk)
    return ids


def sync_class_room(group):
    """반 단체방을 만들거나 참여자를 반 명단에 맞춥니다. 새로 들어온 사람은 지금까지의 메시지를 보지 않습니다."""
    room = Conversation.objects.filter(kind=Conversation.Kind.CLASS, group=group).first()
    if room is None:
        try:
            with transaction.atomic():
                room = Conversation.objects.create(title=group.title[:160], kind=Conversation.Kind.CLASS, group=group,
                                                   created_by_id=group.created_by_id)
        except IntegrityError:
            room = Conversation.objects.get(kind=Conversation.Kind.CLASS, group=group)
    elif room.title != group.title[:160]:
        Conversation.objects.filter(pk=room.pk).update(title=group.title[:160])
    wanted = class_room_user_ids(group)
    present = set(room.participants.values_list("user_id", flat=True))
    last = room.messages.aggregate(last=Max("pk"))["last"] or 0
    ConversationMember.objects.bulk_create([ConversationMember(conversation=room, user_id=uid, joined_after=last, last_read_id=last)
                                            for uid in wanted - present], ignore_conflicts=True)
    room.participants.filter(user_id__in=present - wanted).delete()
    return room


def sync_rooms_for_groups(group_ids):
    """반 명단이 바뀐 반 중 이미 단체방이 있는 반만 맞춥니다(단체방은 처음 열 때 만듭니다)."""
    for group in LearningGroup.objects.filter(pk__in=group_ids, lms_conversations__kind=Conversation.Kind.CLASS).distinct():
        sync_class_room(group)


def _my_groups(user):
    if is_admin(user) or is_teacher(user):
        return LearningGroup.objects.filter(Q(created_by=user) | Q(lms_staff__user=user, lms_staff__active=True)).distinct()
    return LearningGroup.objects.filter(lms_members__active=True, lms_members__student_no__in=learner_student_ids(user)).distinct()


def ensure_class_rooms(user, throttle=False):
    """내 반들의 단체방이 있고 내가 참여자인지 확인합니다. throttle=True 면 사용자마다 5분에 한 번만(자주 불리는 요약 API용)."""
    if user.role == User.Role.PARENT or (throttle and not cache.add(f"lms:class-rooms:{user.pk}", 1, 300)):
        return
    missing = _my_groups(user).exclude(lms_conversations__kind=Conversation.Kind.CLASS,
                                       lms_conversations__participants__user=user)
    for group in missing[:50]:
        sync_class_room(group)


def merge_duplicate_direct_rooms(Conversation, ConversationMember, Message):
    """같은 두 사람의 1:1 방이 여러 개면 가장 오래된 방 하나로 합칩니다(메시지·읽음 위치 보존). 마이그레이션에서도 씁니다."""
    kept = {}
    for conv in Conversation.objects.filter(group__isnull=True).order_by("created_at", "pk"):
        users = sorted(ConversationMember.objects.filter(conversation_id=conv.pk).values_list("user_id", flat=True))
        if len(users) != 2:
            continue
        key = f"{users[0]}:{users[1]}"
        keep = kept.get(key)
        if keep is None:
            kept[key] = conv
            Conversation.objects.filter(pk=conv.pk).update(kind="DIRECT", direct_key=key)
            continue
        Message.objects.filter(conversation_id=conv.pk).update(conversation_id=keep.pk)
        for member in ConversationMember.objects.filter(conversation_id=conv.pk):
            ConversationMember.objects.filter(conversation_id=keep.pk, user_id=member.user_id,
                                              last_read_id__lt=member.last_read_id).update(last_read_id=member.last_read_id)
        if conv.updated_at > keep.updated_at:
            Conversation.objects.filter(pk=keep.pk).update(updated_at=conv.updated_at)
        Conversation.objects.filter(pk=conv.pk).delete()


def visible_messages(conv, user):
    joined = conv.participants.filter(user=user).values_list("joined_after", flat=True).first() or 0
    return conv.messages.filter(pk__gt=joined) if joined else conv.messages.all()


def read_marks(conv, viewer):
    """보는 사람을 뺀 참여자의 (user, joined_after, last_read_id). 화면이 안 읽음 숫자를 다시 셀 때 씁니다."""
    return [{"u": u, "j": j, "r": r} for u, j, r in
            conv.participants.exclude(user=viewer).values_list("user_id", "joined_after", "last_read_id")]


def unread_for(message, marks):
    return sum(1 for m in marks if m["u"] != message.sender_id and m["j"] < message.pk and m["r"] < message.pk)


def clock(moment):
    local = timezone.localtime(moment)
    return f"{'오전' if local.hour < 12 else '오후'} {local.hour % 12 or 12}:{local.minute:02d}"


def day_label(moment):
    local = timezone.localtime(moment)
    return f"{local.year}년 {local.month}월 {local.day}일 {DAY_NAMES[local.weekday()]}요일"


def message_row(record, viewer, marks):
    return {"id": record.pk, "body": record.body, "sender": record.sender.chat_name, "sender_id": record.sender_id,
            "own": record.sender_id == viewer.pk, "time": clock(record.created_at), "day": day_label(record.created_at),
            "minute": timezone.localtime(record.created_at).strftime("%Y%m%d%H%M"), "unread": unread_for(record, marks)}


def message_blocks(records, viewer, marks):
    """날짜별 묶음. 같은 사람이 같은 분에 이어 보낸 메시지는 이름을 처음에만, 시간을 마지막에만 보여 줍니다."""
    rows = [message_row(record, viewer, marks) for record in records]
    for index, row in enumerate(rows):
        before = rows[index - 1] if index else None
        after = rows[index + 1] if index + 1 < len(rows) else None
        same = lambda other: other is not None and other["sender_id"] == row["sender_id"] and other["minute"] == row["minute"]
        row["first_in_run"], row["last_in_run"] = not same(before), not same(after)
    blocks = []
    for row in rows:
        if not blocks or blocks[-1]["label"] != row["day"]:
            blocks.append({"label": row["day"], "messages": []})
        blocks[-1]["messages"].append(row)
    return blocks


def member_list(conv, viewer):
    """그룹 대화·반 단체방 참여자 명단(강사·관리자 먼저, 그다음 학생 이름순). 1:1 방은 빈 목록."""
    if conv.kind == Conversation.Kind.DIRECT:
        return []
    order = {User.Role.ADMIN: 0, User.Role.TEACHER: 1, User.Role.STUDENT: 2}
    users = [m.user for m in conv.participants.select_related("user").prefetch_related("user__student_links")]
    users.sort(key=lambda u: (order.get(u.role, 3), u.chat_name))
    return [{"name": u.chat_name, "role": u.get_role_display(), "staff": u.role != User.Role.STUDENT, "me": u.pk == viewer.pk}
            for u in users]
