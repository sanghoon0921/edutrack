from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse

from apps.accounts.models import StudentAccountLink
from apps.assignments.models import Assignment, AssignmentRecipient, Submission

from .models import Notice, Notification
from .services import (
    create_notification,
    create_notifications,
    invalidate_notification_header_cache,
    learner_users_for_student,
    notify_notice_published,
)


@receiver(post_save, sender=Notice)
def notice_saved(sender, instance: Notice, **kwargs) -> None:
    notify_notice_published(instance)


@receiver(post_save, sender=Notification)
def notification_saved(
    sender,
    instance: Notification,
    **kwargs,
) -> None:
    invalidate_notification_header_cache(instance.user_id)


@receiver(post_delete, sender=Notification)
def notification_deleted(
    sender,
    instance: Notification,
    **kwargs,
) -> None:
    invalidate_notification_header_cache(instance.user_id)


@receiver(post_save, sender=StudentAccountLink)
def student_account_link_saved(
    sender,
    instance: StudentAccountLink,
    **kwargs,
) -> None:
    invalidate_notification_header_cache(instance.user_id)


@receiver(post_delete, sender=StudentAccountLink)
def student_account_link_deleted(
    sender,
    instance: StudentAccountLink,
    **kwargs,
) -> None:
    invalidate_notification_header_cache(instance.user_id)


def _notify_assignment_recipient(recipient: AssignmentRecipient) -> None:
    assignment = recipient.assignment
    if not assignment.is_published:
        return

    create_notifications(
        learner_users_for_student(recipient.student_id).iterator(),
        kind=Notification.Kind.ASSIGNMENT,
        title=f"새 과제: {assignment.title}",
        message=f"마감일은 {assignment.due_at:%Y.%m.%d %H:%M}입니다.",
        target_url=reverse(
            "assignments:my-detail",
            kwargs={"recipient_id": recipient.pk},
        ),
        event_key=(
            f"assignment:{assignment.pk}:recipient:{recipient.pk}"
        ),
    )


@receiver(post_save, sender=AssignmentRecipient)
def assignment_recipient_saved(
    sender,
    instance: AssignmentRecipient,
    **kwargs,
) -> None:
    _notify_assignment_recipient(instance)


@receiver(post_save, sender=Assignment)
def assignment_saved(sender, instance: Assignment, **kwargs) -> None:
    if not instance.is_published:
        return
    for recipient in instance.recipients.all():
        _notify_assignment_recipient(recipient)


@receiver(post_save, sender=Submission)
def submission_saved(sender, instance: Submission, **kwargs) -> None:
    assignment = instance.recipient.assignment

    if instance.submitted_at is not None:
        submitter = getattr(instance, "submitter_label", "")
        if not submitter:
            submitter = "학생 또는 학부모"
        create_notification(
            user=assignment.created_by,
            kind=Notification.Kind.SUBMISSION,
            title=f"과제 제출: {instance.recipient.student_name}",
            message=(
                f"{submitter} 계정에서 ‘{assignment.title}’ 과제를 제출했습니다."
            ),
            target_url=reverse(
                "assignments:review",
                kwargs={"submission_id": instance.pk},
            ),
            event_key=(
                f"submission:{instance.pk}:"
                f"{int(instance.submitted_at.timestamp())}"
            ),
        )

    if instance.feedback_at is not None:
        create_notifications(
            learner_users_for_student(
                instance.recipient.student_id
            ).iterator(),
            kind=Notification.Kind.FEEDBACK,
            title=f"피드백 완료: {assignment.title}",
            message="강사 피드백이 등록되었습니다.",
            target_url=reverse(
                "assignments:my-detail",
                kwargs={"recipient_id": instance.recipient.pk},
            ),
            event_key=(
                f"feedback:{instance.pk}:"
                f"{int(instance.feedback_at.timestamp())}"
            ),
        )
