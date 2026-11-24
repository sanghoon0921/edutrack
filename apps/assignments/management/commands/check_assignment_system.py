from django.core.management.base import BaseCommand

from apps.assignments.models import (
    Assignment,
    AssignmentRecipient,
    Submission,
)


class Command(BaseCommand):
    help = "과제 기능의 모델과 저장상태를 확인합니다."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(
                "과제 기능 연결 성공"
            )
        )

        self.stdout.write(
            f"과제: "
            f"{Assignment.objects.count()}건"
        )
        self.stdout.write(
            f"학생 배정: "
            f"{AssignmentRecipient.objects.count()}건"
        )
        self.stdout.write(
            f"제출: "
            f"{Submission.objects.count()}건"
        )
