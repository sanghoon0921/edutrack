from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "복구된 학생 포털의 핵심 설정과 파일을 확인합니다."

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR)

        required_files = (
            "apps/students/templates/students/student_list.html",
            "apps/students/templates/students/student_detail.html",
            "apps/students/templates/students/attendance_detail.html",
            "templates/components/header.html",
            "apps/assessments/templates/assessments/student_score_overview.html",
            "static/css/layers/10-premium-portal.css",
            "apps/students/views.py",
            "apps/students/course_repositories.py",
            "apps/students/attendance_repositories.py",
            "apps/assessments/repositories.py",
        )

        self.stdout.write("DB 별칭")
        for alias in ("default", "intranet", "dsg"):
            exists = alias in settings.DATABASES
            style = (
                self.style.SUCCESS
                if exists
                else self.style.ERROR
            )
            self.stdout.write(
                style(
                    f"- {alias}: "
                    f"{'존재' if exists else '없음'}"
                )
            )

        self.stdout.write("")
        self.stdout.write("핵심 파일")

        missing = []

        for relative_path in required_files:
            exists = (
                project_root / relative_path
            ).exists()

            if not exists:
                missing.append(relative_path)

            style = (
                self.style.SUCCESS
                if exists
                else self.style.ERROR
            )

            self.stdout.write(
                style(
                    f"- {relative_path}: "
                    f"{'존재' if exists else '없음'}"
                )
            )

        self.stdout.write("")

        if missing:
            self.stdout.write(
                self.style.ERROR(
                    "복구 상태 확인 실패"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "복구 상태 확인 성공"
                )
            )
