"""Delete private derivatives only after the database transaction commits; keep class chat rooms in step with rosters."""
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from apps.accounts.models import StudentAccountLink
from apps.learning.models import LearningGroup
from .models import PostFile,SubmissionFile,ReviewDocument,GroupMember,GroupStaff

@receiver(post_delete,sender=PostFile)
@receiver(post_delete,sender=SubmissionFile)
@receiver(post_delete,sender=ReviewDocument)
def cleanup_private_file(sender,instance,**kwargs):
    field=instance.pdf if isinstance(instance,ReviewDocument) else instance.file
    if field and field.name:
        storage,name=field.storage,field.name
        transaction.on_commit(lambda:storage.delete(name),robust=True)


# 반 명단·강사·학생 계정 연결이 바뀌면, 이미 있는 반 단체방의 참여자를 바로 맞춥니다(apps/lms/rooms.py).
@receiver(post_save,sender=GroupMember)
@receiver(post_delete,sender=GroupMember)
@receiver(post_save,sender=GroupStaff)
@receiver(post_delete,sender=GroupStaff)
def roster_changed(sender,instance,**kwargs):
    from .rooms import sync_rooms_for_groups
    sync_rooms_for_groups([instance.group_id])


@receiver(post_save,sender=LearningGroup)
def class_renamed(sender,instance,created,**kwargs):
    if not created:
        from .rooms import sync_rooms_for_groups
        sync_rooms_for_groups([instance.pk])


@receiver(post_save,sender=StudentAccountLink)
@receiver(post_delete,sender=StudentAccountLink)
def student_link_changed(sender,instance,**kwargs):
    from .rooms import sync_rooms_for_groups
    sync_rooms_for_groups(GroupMember.objects.filter(student_no=instance.student_no).values_list('group_id',flat=True))
