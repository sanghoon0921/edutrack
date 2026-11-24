from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError

from apps.dashboard.class_catalog import (
    ClassCatalogFilters,
    IntranetClassCatalogRepository,
)


class Command(BaseCommand):
    help = "인트라넷 수업 목록을 조회해 관리자 수업 검색 데이터 연결을 확인합니다."

    def add_arguments(self, parser):
        parser.add_argument("--q", default="", help="수업명, 번호, Term, Subject, 강사, 지점")
        parser.add_argument("--status", default="", choices=("", "W", "P", "E", "C"))
        parser.add_argument(
            "--method",
            default="",
            choices=("", "ONLINE", "OFFLINE", "ALL"),
        )
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        repository = IntranetClassCatalogRepository()
        filters = ClassCatalogFilters(
            status=options["status"],
            learning_method=options["method"],
            keyword=options["q"],
        )
        try:
            classes, total = repository.search(
                filters,
                limit=max(1, min(options["limit"], 100)),
                offset=0,
            )
        except DatabaseError as error:
            self.stderr.write(self.style.ERROR("인트라넷 수업 조회 실패"))
            raise error

        self.stdout.write(self.style.SUCCESS(f"수업 검색 성공: 전체 {total}개"))
        for item in classes:
            self.stdout.write(
                " | ".join(
                    (
                        item.class_id,
                        item.term_name or "-",
                        item.subject_name or "-",
                        item.class_name or "-",
                        item.teacher_names or "-",
                        item.status_label or "-",
                        item.learning_methods or "-",
                        f"{item.assigned_student_count}명",
                    )
                )
            )
