from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError

from apps.students.attendance_services import (
    AttendanceService,
)
from apps.students.attendance_repositories import (
    IntranetAttendanceRepository,
)


class Command(BaseCommand):
    help = "실제 인트라넷 수업별 출결을 조회합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "student_id",
            type=str,
            help="인트라넷 학생번호",
        )
        parser.add_argument(
            "assign_id",
            type=str,
            help="수업 배정번호",
        )

    def handle(self, *args, **options):
        service = AttendanceService(
            repository=IntranetAttendanceRepository()
        )

        try:
            records, summary = service.get_attendance(
                options["student_id"],
                options["assign_id"],
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "출결 조회 실패"
                )
            )
            self.stdout.write(
                str(error)
            )
            raise

        self.stdout.write(
            self.style.SUCCESS(
                f"출결 조회 성공: {len(records)}회"
            )
        )

        self.stdout.write(
            (
                f"출석률: "
                f"{summary.attendance_rate:.1f}%"
                if summary.attendance_rate is not None
                else "출석률: —"
            )
        )

        self.stdout.write(
            (
                f"출석 {summary.present_count}"
                f" | 결석 {summary.absent_count}"
                f" | 지각 {summary.late_count}"
                f" | 녹화 {summary.recorded_count}"
                f" | 예정 {summary.upcoming_count}"
                f" | 미처리 {summary.unprocessed_count}"
                f" | 개별취소 {summary.cancelled_count}"
                f" | 학원휴강 {summary.holiday_count}"
            )
        )

        for record in records:
            self.stdout.write(
                (
                    f"- {record.lesson_date or '-'}"
                    f" | {record.lesson_type or '-'}"
                    f" | {record.attendance_label}"
                    f" | {record.payment_label}"
                )
            )
