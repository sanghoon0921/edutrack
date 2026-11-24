from __future__ import annotations

from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from django.db import transaction

from apps.accounts.models import (
    StudentAccountLink,
    User,
)


class Command(BaseCommand):
    help = (
        "학생·학부모 테스트 계정을 "
        "같은 학생번호에 연결합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--student-no",
            required=True,
        )
        parser.add_argument(
            "--student-username",
            default="student_test",
        )
        parser.add_argument(
            "--student-password",
            default="Student!2026",
        )
        parser.add_argument(
            "--parent-username",
            default="parent_test",
        )
        parser.add_argument(
            "--parent-password",
            default="Parent!2026",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        student_no = str(
            options["student_no"]
        ).strip()

        if not student_no:
            raise CommandError(
                "학생번호를 입력해 주세요."
            )

        student_user, student_created = (
            User.objects.get_or_create(
                username=(
                    options[
                        "student_username"
                    ]
                ),
                defaults={
                    "role": User.Role.STUDENT,
                    "display_name": "학생 테스트",
                },
            )
        )

        if student_created:
            student_user.set_password(
                options["student_password"]
            )

        changed_student_fields = []

        if student_user.role != User.Role.STUDENT:
            student_user.role = User.Role.STUDENT
            changed_student_fields.append(
                "role"
            )

        if student_created:
            changed_student_fields.append(
                "password"
            )

        if changed_student_fields:
            student_user.save(
                update_fields=(
                    changed_student_fields
                )
            )

        parent_user, parent_created = (
            User.objects.get_or_create(
                username=(
                    options[
                        "parent_username"
                    ]
                ),
                defaults={
                    "role": User.Role.PARENT,
                    "display_name": "학부모 테스트",
                },
            )
        )

        parent_user.role = User.Role.PARENT
        parent_user.set_password(
            options["parent_password"]
        )
        parent_user.save(
            update_fields=(
                "role",
                "password",
            )
        )

        StudentAccountLink.objects.filter(
            user=student_user,
        ).update(
            is_primary=False,
        )
        StudentAccountLink.objects.filter(
            user=parent_user,
        ).update(
            is_primary=False,
        )

        StudentAccountLink.objects.update_or_create(
            user=student_user,
            student_no=student_no,
            defaults={
                "relationship": (
                    StudentAccountLink
                    .Relationship.SELF
                ),
                "is_primary": True,
                "is_active": True,
            },
        )
        StudentAccountLink.objects.update_or_create(
            user=parent_user,
            student_no=student_no,
            defaults={
                "relationship": (
                    StudentAccountLink
                    .Relationship.PARENT
                ),
                "is_primary": True,
                "is_active": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "학부모 테스트 계정 연결 완료"
            )
        )
        self.stdout.write(
            f"학생번호: {student_no}"
        )
        self.stdout.write(
            f"학생 계정: {student_user.username}"
        )
        self.stdout.write(
            f"학부모 계정: {parent_user.username}"
        )
