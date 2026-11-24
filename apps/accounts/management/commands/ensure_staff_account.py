"""직원 계정을 만들거나 고칩니다(11/19). 있으면 역할·비밀번호를 맞추고, 없으면 새로 만듭니다.

예) 최고관리자:  manage.py ensure_staff_account sm --role ADMIN --superuser --password <비밀번호> [--force-change]
    TA:          manage.py ensure_staff_account TA --role TA --password <비밀번호> --force-change --group "SAT 정규반"

--force-change 를 주면 첫 로그인 때 새 비밀번호(8자 이상, 영문+숫자)로 바꾸는 화면부터 나옵니다(실제 자료가 있는 서버용).
--group 은 반 이름 일부로 반을 찾아 TA(또는 공동 강사)로 지정합니다. 반이 여러 개 걸리면 지정하지 않고 알려 줍니다.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.learning.models import LearningGroup
from apps.lms.models import GroupStaff

User = get_user_model()
STAFF_ROLES = {"ADMIN": User.Role.ADMIN, "TEACHER": User.Role.TEACHER, "TA": User.Role.TA}


class Command(BaseCommand):
    help = "직원(관리자·강사·TA) 계정을 만들거나 고칩니다."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--role", required=True, choices=sorted(STAFF_ROLES))
        parser.add_argument("--password", required=True)
        parser.add_argument("--superuser", action="store_true", help="최고관리자(관리자 역할에만)")
        parser.add_argument("--force-change", action="store_true", help="첫 로그인 때 비밀번호를 바꾸게 함")
        parser.add_argument("--name", default="", help="화면에 보일 이름")
        parser.add_argument("--group", default="", help="TA·공동 강사로 지정할 반 이름 일부")

    def handle(self, *args, **opts):
        role = STAFF_ROLES[opts["role"]]
        if opts["superuser"] and role != User.Role.ADMIN:
            raise CommandError("--superuser 는 --role ADMIN 과 함께만 씁니다.")
        user, created = User.objects.get_or_create(username=opts["username"], defaults={"role": role})
        user.role = role
        user.is_active = True
        user.is_superuser = bool(opts["superuser"])
        user.is_staff = bool(opts["superuser"])
        if opts["name"]:
            user.display_name = opts["name"]
        user.set_password(opts["password"])
        user.needs_first_setup = bool(opts["force_change"])
        user.save()
        self.stdout.write(f"{'만들었습니다' if created else '고쳤습니다'}: {user.username} ({user.get_role_display()}"
                          f"{', 최고관리자' if user.is_superuser else ''}{', 첫 로그인 때 비밀번호 변경' if user.needs_first_setup else ''})")
        if opts["group"]:
            groups = list(LearningGroup.objects.filter(title__icontains=opts["group"])[:2])
            if len(groups) != 1:
                self.stdout.write(f"반 '{opts['group']}'을(를) 하나로 찾지 못해 지정하지 않았습니다({len(groups)}개).")
                return
            duty = "TA" if role == User.Role.TA else "TEACHER"
            GroupStaff.objects.update_or_create(group=groups[0], user=user, defaults={"duty": duty, "active": True})
            self.stdout.write(f"반 지정: {groups[0].title} ({duty})")
