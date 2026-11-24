from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import CourseResource


@receiver(post_delete, sender=CourseResource)
def delete_resource_file(sender, instance: CourseResource, **kwargs) -> None:
    if not instance.file:
        return
    storage = instance.file.storage
    name = instance.file.name
    transaction.on_commit(lambda: storage.delete(name))
