from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = "로컬 개발용 관리자·강사·학생 데모 계정을 생성합니다."

    def handle(self, *args, **options):
        users = [
            {
                "username": "admin_test",
                "password": "Admin!2026",
                "role": User.Role.ADMIN,
                "display_name": "운영 관리자",
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "username": "teacher_test",
                "password": "Teacher!2026",
                "role": User.Role.TEACHER,
                "display_name": "김지연 강사",
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "student_test",
                "password": "Student!2026",
                "role": User.Role.STUDENT,
                "display_name": "김지훈 학생",
                "is_staff": False,
                "is_superuser": False,
            },
        ]

        for data in users:
            user, _ = User.objects.get_or_create(username=data["username"])
            user.role = data["role"]
            user.display_name = data["display_name"]
            user.is_staff = data["is_staff"]
            user.is_superuser = data["is_superuser"]
            user.is_active = True
            user.set_password(data["password"])
            user.save()
            self.stdout.write(self.style.SUCCESS(f"생성/갱신: {user.username}"))

        self.stdout.write(self.style.WARNING("운영 배포 전 데모 계정을 삭제하거나 비밀번호를 변경하세요."))
