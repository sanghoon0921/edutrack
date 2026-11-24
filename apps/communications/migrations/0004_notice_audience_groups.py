"""공지 대상을 하나만 고르던 칸(audience)을 대상 그룹 체크 칸 네 개(for_*)로 바꿉니다.

기존 공지는 대상이 그대로 이어지도록 옮깁니다(예: '관리자·강사' → 관리자+강사 체크, '전체' → 네 그룹 모두).
"""
from django.db import migrations, models

ALL_FLAGS = ("for_admin", "for_teacher", "for_student", "for_parent")
FLAGS_FOR_OLD_AUDIENCE = {
    "ALL": ALL_FLAGS,
    "STAFF": ("for_admin", "for_teacher"),
    "LEARNER": ("for_student", "for_parent"),
    "ADMIN": ("for_admin",),
    "TEACHER": ("for_teacher",),
    "STUDENT": ("for_student",),
    "PARENT": ("for_parent",),
}


def old_audience_to_groups(apps, schema_editor):
    Notice = apps.get_model("communications", "Notice")
    for notice in Notice.objects.all():
        flags = FLAGS_FOR_OLD_AUDIENCE.get(notice.audience, ALL_FLAGS)
        for flag in ALL_FLAGS:
            setattr(notice, flag, flag in flags)
        notice.save(update_fields=list(ALL_FLAGS))


def groups_to_old_audience(apps, schema_editor):
    Notice = apps.get_model("communications", "Notice")
    reverse_map = {flags: value for value, flags in FLAGS_FOR_OLD_AUDIENCE.items()}
    for notice in Notice.objects.all():
        flags = tuple(flag for flag in ALL_FLAGS if getattr(notice, flag))
        notice.audience = reverse_map.get(flags, "ALL")
        notice.save(update_fields=["audience"])


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0003_notice_category_group"),
    ]

    operations = [
        migrations.AddField(model_name="notice", name="for_admin", field=models.BooleanField(default=False, verbose_name="대상: 관리자")),
        migrations.AddField(model_name="notice", name="for_teacher", field=models.BooleanField(default=False, verbose_name="대상: 강사")),
        migrations.AddField(model_name="notice", name="for_student", field=models.BooleanField(default=False, verbose_name="대상: 학생")),
        migrations.AddField(model_name="notice", name="for_parent", field=models.BooleanField(default=False, verbose_name="대상: 학부모")),
        migrations.RunPython(old_audience_to_groups, groups_to_old_audience),
        migrations.RemoveIndex(model_name="notice", name="notice_visible_idx"),
        migrations.RemoveField(model_name="notice", name="audience"),
        migrations.AddIndex(
            model_name="notice",
            index=models.Index(fields=["is_published", "-published_at"], name="notice_visible_idx"),
        ),
    ]
