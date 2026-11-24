from django.core.exceptions import PermissionDenied
from django.urls import reverse
from apps.operations.access import is_admin, restrict_student_ids_for_user
from .access import can_teach_group,staff_group_ids
from .models import GroupMember


def activity_initial(request):
    raw=request.GET.get('group','')
    if raw.isdigit() and can_teach_group(request.user,int(raw)):
        return {'group':int(raw),'student_ids':list(GroupMember.objects.filter(group_id=int(raw),active=True).values_list('student_no',flat=True))}
    return {}


def scoped_roster(user,group,ids):
    """Return local roster names only when an explicitly managed class is selected."""
    if not group:return None
    if not can_teach_group(user,group.pk):raise PermissionDenied('선택한 반에 대한 권한이 없습니다.')
    rows=GroupMember.objects.filter(group=group)
    if not rows.exists():return None  # preserve legacy groups without class enrollment
    names=dict(rows.filter(active=True).values_list('student_no','student_name'))
    if not set(ids).issubset(names):raise PermissionDenied('선택한 반의 현재 학생에게만 배정할 수 있습니다.')
    return [(sid,names[sid]) for sid in ids]


def selector_scope(form,user):
    raw=form.data.get('group') if form.is_bound else (form.initial.get('group') or getattr(form.instance,'group_id',None))
    try:gid=int(raw)
    except (ValueError,TypeError):return None
    if not can_teach_group(user,gid):return None
    members=GroupMember.objects.filter(group_id=gid,active=True)
    if not GroupMember.objects.filter(group_id=gid).exists():return None
    return gid,dict(members.values_list('student_no','student_name'))
