from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError

from apps.data_imports.models import ImportBatch
from apps.data_imports.services import apply_assignment_import, preview_assignment_import


User = get_user_model()


class Command(BaseCommand):
    help = "기존 LMS 과제·제출·피드백 CSV를 검증하거나 실제 이전합니다."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument(
            "--mode",
            choices=[ImportBatch.Mode.CREATE_ONLY, ImportBatch.Mode.UPSERT],
            default=ImportBatch.Mode.CREATE_ONLY,
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--actor", type=str, default="")

    def handle(self, *args, **options):
        path = Path(options["csv_path"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f"CSV 파일을 찾지 못했습니다: {path}")

        def upload():
            return SimpleUploadedFile(path.name, path.read_bytes(), content_type="text/csv")

        if not options["apply"]:
            preview = preview_assignment_import(upload(), mode=options["mode"])
            self.stdout.write(f"파일: {preview.source_filename}")
            self.stdout.write(f"행: {preview.total_rows} | 인코딩: {preview.encoding}")
            for issue in preview.issues:
                self.stdout.write(self.style.ERROR(f"{issue.row_number}행 {issue.key}: {issue.message}"))
            for item in preview.items:
                self.stdout.write(
                    f"{item['predicted_action']:>6} | {item['external_key']} | "
                    f"{item['title']} | 대상 {item['recipient_count']}명"
                )
            if preview.issues:
                raise CommandError(f"검증 오류 {len(preview.issues)}건")
            self.stdout.write(self.style.SUCCESS("검증 통과. --apply와 --actor를 추가하면 실제 반영됩니다."))
            return

        actor_username = options["actor"].strip()
        if not actor_username:
            raise CommandError("실제 반영에는 --actor 관리자 아이디가 필요합니다.")
        actor = User.objects.filter(username=actor_username, is_active=True).first()
        if actor is None or not (actor.is_superuser or actor.role == "ADMIN"):
            raise CommandError("활성 관리자 계정을 --actor로 지정해 주세요.")

        outcome = apply_assignment_import(upload(), mode=options["mode"], actor=actor)
        self.stdout.write(f"작업번호: {outcome.batch.pk} | 상태: {outcome.batch.get_status_display()}")
        self.stdout.write(
            f"생성 {outcome.batch.created_count} | 갱신 {outcome.batch.updated_count} | "
            f"건너뜀 {outcome.batch.skipped_count} | 오류 {outcome.batch.error_count}"
        )
        if outcome.batch.error_count:
            raise CommandError("일부 행 처리에 실패했습니다. 작업 상세를 확인해 주세요.")
