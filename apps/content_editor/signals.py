from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.assignments.models import Assignment
from apps.communications.models import Notice
from apps.learning.models import Discussion

from .models import PastedImage
from .services import delete_target_images


@receiver(post_delete, sender=PastedImage)
def delete_pasted_image_file(sender, instance: PastedImage, **kwargs) -> None:
    if not instance.image:
        return
    storage = instance.image.storage
    name = instance.image.name
    transaction.on_commit(lambda: storage.delete(name))


@receiver(post_delete, sender=Assignment)
def delete_assignment_pasted_images(sender, instance: Assignment, **kwargs) -> None:
    delete_target_images(
        target_type=PastedImage.TargetType.ASSIGNMENT,
        target_id=instance.pk,
    )


@receiver(post_delete, sender=Discussion)
def delete_discussion_pasted_images(sender, instance: Discussion, **kwargs) -> None:
    delete_target_images(
        target_type=PastedImage.TargetType.DISCUSSION,
        target_id=instance.pk,
    )


@receiver(post_delete, sender=Notice)
def delete_notice_pasted_images(sender, instance: Notice, **kwargs) -> None:
    delete_target_images(
        target_type=PastedImage.TargetType.NOTICE,
        target_id=instance.pk,
    )
