"""반 명단·담당자 저장(11/20): '명단·TA 지정' 화면과 '반 만들기' 화면이 같이 씁니다."""
from django.db import transaction

from .models import ChangeLog, GroupMember, GroupStaff


@transaction.atomic
def apply_roster(group, students, staff, *, actor, action='room.roster'):
    """반 명단을 students[(학생번호, 이름)] 로, 담당자(TA·공동 강사)를 staff 로 맞춥니다.
    빠진 학생·담당자는 지우지 않고 비활성(active=False)으로 둡니다. 반 개설자는 담당자 목록에 따로 넣지 않습니다."""
    group.lms_members.update(active=False)
    for student_no, name in students:
        GroupMember.objects.update_or_create(group=group, student_no=student_no, defaults={'student_name': name, 'active': True})
    group.lms_staff.update(active=False)
    for user in staff:
        if user.pk == group.created_by_id:
            continue
        GroupStaff.objects.update_or_create(group=group, user=user, defaults={'active': True, 'duty': 'TA'})
    ChangeLog.objects.create(actor=actor, action=action, target=str(group.pk), detail={'students': len(students), 'staff': len(staff)})
