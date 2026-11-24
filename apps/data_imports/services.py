from __future__ import annotations

import csv
import hashlib
import io
import secrets
import string
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.operations.models import AccountAuditLog
from apps.students.services import StudentService

from .models import ImportBatch, ImportRowResult, LegacyObjectMap


UserModel = get_user_model()

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 5000

USER_HEADERS = (
    "username",
    "display_name",
    "email",
    "role",
    "student_no",
    "is_primary",
    "temporary_password",
)

ASSIGNMENT_HEADERS = (
    "legacy_assignment_key",
    "title",
    "description",
    "due_at",
    "teacher_username",
    "student_no",
    "student_name",
    "is_published",
    "submitted_at",
    "text_answer",
    "feedback",
    "feedback_by_username",
    "feedback_at",
)

ROLE_ALIASES = {
    "ADMIN": User.Role.ADMIN,
    "관리자": User.Role.ADMIN,
    "TEACHER": User.Role.TEACHER,
    "강사": User.Role.TEACHER,
    "STUDENT": User.Role.STUDENT,
    "학생": User.Role.STUDENT,
    "PARENT": User.Role.PARENT,
    "학부모": User.Role.PARENT,
}

TRUE_VALUES = {"1", "TRUE", "T", "Y", "YES", "예", "활성", "공개"}
FALSE_VALUES = {"0", "FALSE", "F", "N", "NO", "아니오", "비활성", "비공개", ""}


@dataclass(frozen=True)
class ImportIssue:
    row_number: int
    key: str
    message: str


@dataclass
class PreviewResult:
    headers: tuple[str, ...]
    total_rows: int
    source_filename: str
    source_sha256: str
    encoding: str
    items: list[dict] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass
class ApplyOutcome:
    batch: ImportBatch
    credentials: list[dict] = field(default_factory=list)


class ImportValidationError(ValueError):
    pass


def _clean(value) -> str:
    return str(value or "").strip()


def _safe_csv_cell(value) -> str:
    text = _clean(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportValidationError("CSV 파일은 2MB 이하만 업로드할 수 있습니다.")

    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ImportValidationError("CSV 인코딩을 읽지 못했습니다. UTF-8 또는 CP949로 저장해 주세요.")


def parse_csv_upload(uploaded_file, required_headers: Iterable[str]) -> tuple[list[dict], str, str]:
    raw = uploaded_file.read()
    if not isinstance(raw, bytes):
        raw = bytes(raw)
    text, encoding = decode_csv_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()

    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = tuple(_clean(name) for name in (reader.fieldnames or ()))
    missing = [header for header in required_headers if header not in fieldnames]
    if missing:
        raise ImportValidationError("필수 컬럼이 없습니다: " + ", ".join(missing))

    rows: list[dict] = []
    for row_number, row in enumerate(reader, start=2):
        normalized = {key: _clean(value) for key, value in row.items() if key is not None}
        if not any(normalized.values()):
            continue
        normalized["_row_number"] = row_number
        rows.append(normalized)
        if len(rows) > MAX_IMPORT_ROWS:
            raise ImportValidationError("한 번에 최대 5,000행까지 처리할 수 있습니다.")

    if not rows:
        raise ImportValidationError("처리할 데이터 행이 없습니다.")
    return rows, digest, encoding


def parse_bool(value: str, *, field_name: str, default: bool | None = None) -> bool:
    cleaned = _clean(value).upper()
    if not cleaned and default is not None:
        return default
    if cleaned in TRUE_VALUES:
        return True
    if cleaned in FALSE_VALUES:
        return False
    raise ImportValidationError(f"{field_name} 값은 Y/N, TRUE/FALSE 또는 1/0으로 입력해 주세요.")


def parse_role(value: str) -> str:
    cleaned = _clean(value).upper()
    if cleaned in ROLE_ALIASES:
        return ROLE_ALIASES[cleaned]
    original = _clean(value)
    if original in ROLE_ALIASES:
        return ROLE_ALIASES[original]
    raise ImportValidationError("role은 ADMIN, TEACHER, STUDENT, PARENT 중 하나여야 합니다.")


def parse_local_datetime(value: str, *, field_name: str, required: bool = False):
    cleaned = _clean(value)
    if not cleaned:
        if required:
            raise ImportValidationError(f"{field_name}을 입력해 주세요.")
        return None

    candidate = cleaned.replace("/", "-")
    parsed = parse_datetime(candidate)
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d %H%M", "%Y%m%d"):
            try:
                parsed = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ImportValidationError(
            f"{field_name} 형식이 올바르지 않습니다. 예: 2026-08-31 23:59"
        )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    safe_initial = string.ascii_letters + string.digits
    while True:
        # CSV·스프레드시트에서 수식으로 해석될 수 있는 =, +, -, @로
        # 시작하지 않도록 첫 글자는 영문 또는 숫자로 고정합니다.
        password = secrets.choice(safe_initial) + "".join(
            secrets.choice(alphabet) for _ in range(max(0, length - 1))
        )
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(char in "!@#$%" for char in password)
        ):
            return password


def default_student_lookup(student_no: str):
    return StudentService().get_student(student_no)


def _validate_student_numbers(
    student_numbers: Iterable[str],
    *,
    lookup_student: Callable[[str], object | None],
) -> dict[str, object | None]:
    cache: dict[str, object | None] = {}
    for student_no in sorted(set(number for number in student_numbers if number)):
        try:
            cache[student_no] = lookup_student(student_no)
        except Exception as error:  # DatabaseError and connector errors are surfaced safely.
            raise ImportValidationError(
                "인트라넷 학생정보를 확인하지 못했습니다. DB 연결 상태를 확인해 주세요."
            ) from error
    return cache


def preview_user_import(
    uploaded_file,
    *,
    mode: str,
    actor: User | None = None,
    lookup_student: Callable[[str], object | None] = default_student_lookup,
) -> PreviewResult:
    rows, digest, encoding = parse_csv_upload(uploaded_file, USER_HEADERS)
    result = PreviewResult(
        headers=USER_HEADERS,
        total_rows=len(rows),
        source_filename=_clean(getattr(uploaded_file, "name", "users.csv")),
        source_sha256=digest,
        encoding=encoding,
    )

    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        username = _clean(row.get("username"))
        grouped.setdefault(username, []).append(row)

    student_numbers = [_clean(row.get("student_no")) for row in rows]
    try:
        student_cache = _validate_student_numbers(student_numbers, lookup_student=lookup_student)
    except ImportValidationError as error:
        result.issues.append(ImportIssue(0, "DB", str(error)))
        return result

    actor_is_superuser = bool(actor and actor.is_superuser)

    for username, group in grouped.items():
        first = group[0]
        row_number = int(first["_row_number"])
        issues: list[str] = []

        if not username:
            issues.append("username을 입력해 주세요.")

        try:
            requested_role = parse_role(first.get("role", ""))
        except ImportValidationError as error:
            requested_role = ""
            issues.append(str(error))

        display_name = _clean(first.get("display_name"))
        email = _clean(first.get("email"))
        if not display_name:
            issues.append("display_name을 입력해 주세요.")

        consistency_fields = ("display_name", "email", "role", "temporary_password")
        for field_name in consistency_fields:
            values = {_clean(row.get(field_name)) for row in group}
            if len(values) > 1:
                issues.append(f"같은 username의 {field_name} 값이 서로 다릅니다.")

        student_nos: list[str] = []
        primary_nos: list[str] = []
        for row in group:
            student_no = _clean(row.get("student_no"))
            if student_no:
                if student_no not in student_nos:
                    student_nos.append(student_no)
                if student_cache.get(student_no) is None:
                    issues.append(f"인트라넷에서 학생번호 {student_no}를 찾지 못했습니다.")
                try:
                    if parse_bool(row.get("is_primary", ""), field_name="is_primary", default=False):
                        primary_nos.append(student_no)
                except ImportValidationError as error:
                    issues.append(str(error))

        if requested_role in {User.Role.STUDENT, User.Role.PARENT} and not student_nos:
            issues.append("학생·학부모 계정에는 student_no가 필요합니다.")
        if requested_role in {User.Role.ADMIN, User.Role.TEACHER} and student_nos:
            issues.append("관리자·강사 계정에는 student_no를 연결하지 않습니다.")
        if requested_role == User.Role.STUDENT and len(student_nos) != 1:
            issues.append("학생 계정에는 한 명의 학생만 연결할 수 있습니다.")
        if len(set(primary_nos)) > 1:
            issues.append("대표 학생은 username당 한 명만 지정할 수 있습니다.")

        existing = UserModel.objects.filter(username__iexact=username).first() if username else None
        effective_role = requested_role
        if existing and mode == ImportBatch.Mode.CREATE_ONLY:
            predicted_action = "SKIP"
        elif existing:
            predicted_action = "UPDATE"
            if existing.is_superuser:
                issues.append("최고관리자 계정은 일괄등록에서 변경할 수 없습니다.")
            elif not actor_is_superuser and existing.role == User.Role.ADMIN:
                issues.append("관리자 계정은 최고관리자만 일괄 수정할 수 있습니다.")
            elif not actor_is_superuser and requested_role and requested_role != existing.role:
                issues.append("역할 변경은 최고관리자만 할 수 있습니다.")
            if not actor_is_superuser:
                effective_role = existing.role
        else:
            predicted_action = "CREATE"
            if requested_role == User.Role.ADMIN and not actor_is_superuser:
                issues.append("관리자 역할 계정은 최고관리자만 일괄 생성할 수 있습니다.")
            password = _clean(first.get("temporary_password")) or generate_temporary_password()
            temporary_user = User(username=username, display_name=display_name, email=email)
            try:
                validate_password(password, user=temporary_user)
            except ValidationError as error:
                issues.extend(error.messages)

        item = {
            "row_number": row_number,
            "username": username,
            "display_name": display_name,
            "email": email,
            "role": effective_role,
            "requested_role": requested_role,
            "role_label": dict(User.Role.choices).get(effective_role, effective_role),
            "student_nos": student_nos,
            "primary_student_no": primary_nos[0] if primary_nos else (student_nos[0] if student_nos else ""),
            "predicted_action": predicted_action,
            "row_count": len(group),
            "source_rows": [int(row["_row_number"]) for row in group],
            "temporary_password": _clean(first.get("temporary_password")),
        }
        result.items.append(item)
        for message in dict.fromkeys(issues):
            result.issues.append(ImportIssue(row_number, username or "(빈 아이디)", message))

    return result

def _record_account_import_audit(*, actor: User, target_user: User, action: str, summary: str, metadata: dict) -> None:
    AccountAuditLog.objects.create(
        actor=actor,
        target_user=target_user,
        action=action,
        summary=summary,
        metadata=metadata,
        ip_address=None,
    )


def _sync_imported_links(user: User, item: dict) -> None:
    active_links = user.student_links.filter(is_active=True)
    if user.role in {User.Role.ADMIN, User.Role.TEACHER}:
        active_links.update(is_active=False, is_primary=False)
        return

    relationship = (
        StudentAccountLink.Relationship.SELF
        if user.role == User.Role.STUDENT
        else StudentAccountLink.Relationship.PARENT
    )
    primary_student_no = item["primary_student_no"]

    # 학생 계정은 한 명만 연결할 수 있으므로 CSV에 없는 기존 연결을 비활성화합니다.
    # 학부모 계정은 형제자매 연결을 안전하게 누적하는 병합 방식으로 처리합니다.
    if user.role == User.Role.STUDENT:
        active_links.exclude(student_no__in=item["student_nos"]).update(
            is_active=False,
            is_primary=False,
        )

    if primary_student_no:
        active_links.update(is_primary=False)

    for student_no in item["student_nos"]:
        link, _ = StudentAccountLink.objects.get_or_create(
            user=user,
            student_no=student_no,
            defaults={
                "relationship": relationship,
                "is_active": True,
                "is_primary": student_no == primary_student_no,
            },
        )
        link.relationship = relationship
        link.is_active = True
        link.is_primary = student_no == primary_student_no
        link.save(update_fields=("relationship", "is_active", "is_primary", "updated_at"))


def apply_user_import(
    uploaded_file,
    *,
    mode: str,
    actor: User,
    lookup_student: Callable[[str], object | None] = default_student_lookup,
) -> ApplyOutcome:
    preview = preview_user_import(
        uploaded_file,
        mode=mode,
        actor=actor,
        lookup_student=lookup_student,
    )
    batch = ImportBatch.objects.create(
        kind=ImportBatch.Kind.USERS,
        mode=mode,
        source_filename=preview.source_filename,
        source_sha256=preview.source_sha256,
        actor=actor,
        total_rows=preview.total_rows,
    )

    if preview.issues:
        for issue in preview.issues:
            ImportRowResult.objects.create(
                batch=batch,
                row_number=max(issue.row_number, 1),
                external_key=issue.key,
                action=ImportRowResult.Action.ERROR,
                message=issue.message,
                safe_data={},
            )
        batch.status = ImportBatch.Status.FAILED
        batch.error_count = len(preview.issues)
        batch.completed_at = timezone.now()
        batch.summary = {"encoding": preview.encoding, "validation_failed": True}
        batch.save()
        return ApplyOutcome(batch=batch)

    credentials: list[dict] = []
    counters = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

    for item in preview.items:
        username = item["username"]
        try:
            with transaction.atomic():
                user = UserModel.objects.filter(username__iexact=username).first()
                if user and mode == ImportBatch.Mode.CREATE_ONLY:
                    action = ImportRowResult.Action.SKIPPED
                    message = "이미 존재하는 계정이라 건너뛰었습니다."
                    counters["skipped"] += 1
                elif user:
                    if user.is_superuser:
                        raise ImportValidationError("최고관리자 계정은 일괄등록에서 변경할 수 없습니다.")
                    if not actor.is_superuser and user.role == User.Role.ADMIN:
                        raise ImportValidationError("관리자 계정은 최고관리자만 일괄 수정할 수 있습니다.")
                    if not actor.is_superuser and item["requested_role"] != user.role:
                        raise ImportValidationError("역할 변경은 최고관리자만 할 수 있습니다.")
                    before = {
                        "display_name": user.display_name,
                        "email": user.email,
                        "role": user.role,
                    }
                    user.display_name = item["display_name"]
                    user.email = item["email"]
                    if actor.is_superuser:
                        user.role = item["requested_role"]
                    user.save(update_fields=("display_name", "email", "role"))
                    item["role"] = user.role
                    _sync_imported_links(user, item)
                    _record_account_import_audit(
                        actor=actor,
                        target_user=user,
                        action=AccountAuditLog.Action.USER_UPDATED,
                        summary=f"{username} 계정을 CSV 일괄등록으로 갱신했습니다.",
                        metadata={"source": "workflow_user_import", "before": before},
                    )
                    action = ImportRowResult.Action.UPDATED
                    message = "기존 계정 정보를 갱신했습니다. 비밀번호는 변경하지 않았습니다."
                    counters["updated"] += 1
                else:
                    if item["requested_role"] == User.Role.ADMIN and not actor.is_superuser:
                        raise ImportValidationError("관리자 역할 계정은 최고관리자만 생성할 수 있습니다.")
                    password = item["temporary_password"] or generate_temporary_password()
                    user = UserModel.objects.create_user(
                        username=username,
                        password=password,
                        display_name=item["display_name"],
                        email=item["email"],
                        role=item["requested_role"],
                        is_active=True,
                        needs_first_setup=item["requested_role"] == User.Role.STUDENT,
                    )
                    item["role"] = user.role
                    _sync_imported_links(user, item)
                    _record_account_import_audit(
                        actor=actor,
                        target_user=user,
                        action=AccountAuditLog.Action.USER_CREATED,
                        summary=f"{username} 계정을 CSV 일괄등록으로 생성했습니다.",
                        metadata={
                            "source": "workflow_user_import",
                            "role": user.role,
                            "student_nos": item["student_nos"],
                        },
                    )
                    credentials.append(
                        {
                            "username": username,
                            "display_name": item["display_name"],
                            "role": user.role,
                            "temporary_password": password,
                            "student_nos": "|".join(item["student_nos"]),
                        }
                    )
                    action = ImportRowResult.Action.CREATED
                    message = "새 계정과 학생 연결을 생성했습니다."
                    counters["created"] += 1

                for source_row in item["source_rows"]:
                    ImportRowResult.objects.create(
                        batch=batch,
                        row_number=source_row,
                        external_key=username,
                        action=action,
                        target_type="accounts.User",
                        target_id=str(user.pk),
                        message=message,
                        safe_data={
                            "username": username,
                            "role": user.role,
                            "student_nos": item["student_nos"],
                        },
                    )
        except Exception as error:
            counters["errors"] += 1
            ImportRowResult.objects.create(
                batch=batch,
                row_number=item["row_number"],
                external_key=username,
                action=ImportRowResult.Action.ERROR,
                message=str(error)[:500],
                safe_data={"username": username, "role": item.get("role", "")},
            )

    batch.created_count = counters["created"]
    batch.updated_count = counters["updated"]
    batch.skipped_count = counters["skipped"]
    batch.error_count = counters["errors"]
    batch.status = (
        ImportBatch.Status.COMPLETED_WITH_ERRORS
        if counters["errors"]
        else ImportBatch.Status.COMPLETED
    )
    batch.completed_at = timezone.now()
    batch.summary = {"encoding": preview.encoding, "credentials_generated": len(credentials)}
    batch.save()
    return ApplyOutcome(batch=batch, credentials=credentials)

def preview_assignment_import(
    uploaded_file,
    *,
    mode: str,
    lookup_student: Callable[[str], object | None] = default_student_lookup,
) -> PreviewResult:
    rows, digest, encoding = parse_csv_upload(uploaded_file, ASSIGNMENT_HEADERS)
    result = PreviewResult(
        headers=ASSIGNMENT_HEADERS,
        total_rows=len(rows),
        source_filename=_clean(getattr(uploaded_file, "name", "assignments.csv")),
        source_sha256=digest,
        encoding=encoding,
    )

    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        key = _clean(row.get("legacy_assignment_key"))
        grouped.setdefault(key, []).append(row)

    student_numbers = [_clean(row.get("student_no")) for row in rows]
    try:
        student_cache = _validate_student_numbers(student_numbers, lookup_student=lookup_student)
    except ImportValidationError as error:
        result.issues.append(ImportIssue(0, "DB", str(error)))
        return result

    for external_key, group in grouped.items():
        first = group[0]
        row_number = int(first["_row_number"])
        issues: list[str] = []

        if not external_key:
            issues.append("legacy_assignment_key를 입력해 주세요.")
        title = _clean(first.get("title"))
        description = _clean(first.get("description"))
        teacher_username = _clean(first.get("teacher_username"))
        if not title:
            issues.append("title을 입력해 주세요.")
        if not description:
            issues.append("description을 입력해 주세요.")

        try:
            due_at = parse_local_datetime(first.get("due_at", ""), field_name="due_at", required=True)
        except ImportValidationError as error:
            due_at = None
            issues.append(str(error))
        try:
            is_published = parse_bool(
                first.get("is_published", ""), field_name="is_published", default=True
            )
        except ImportValidationError as error:
            is_published = True
            issues.append(str(error))

        teacher = UserModel.objects.filter(username__iexact=teacher_username).first()
        if teacher is None or teacher.role not in {User.Role.ADMIN, User.Role.TEACHER}:
            issues.append("teacher_username에 등록된 관리자 또는 강사 계정을 찾지 못했습니다.")

        for field_name in ("title", "description", "due_at", "teacher_username", "is_published"):
            if len({_clean(row.get(field_name)) for row in group}) > 1:
                issues.append(f"같은 legacy_assignment_key의 {field_name} 값이 서로 다릅니다.")

        recipients: list[dict] = []
        seen_students: set[str] = set()
        for row in group:
            source_row = int(row["_row_number"])
            student_no = _clean(row.get("student_no"))
            student_name = _clean(row.get("student_name"))
            row_issues: list[str] = []
            if not student_no:
                row_issues.append("student_no를 입력해 주세요.")
            elif student_no in seen_students:
                row_issues.append("같은 과제에 동일 학생번호가 중복되었습니다.")
            elif student_cache.get(student_no) is None:
                row_issues.append(f"인트라넷에서 학생번호 {student_no}를 찾지 못했습니다.")
            seen_students.add(student_no)

            student_obj = student_cache.get(student_no)
            if not student_name and student_obj is not None:
                student_name = _clean(getattr(student_obj, "name", ""))
            if not student_name:
                row_issues.append("student_name을 입력해 주세요.")

            try:
                submitted_at = parse_local_datetime(
                    row.get("submitted_at", ""), field_name="submitted_at"
                )
            except ImportValidationError as error:
                submitted_at = None
                row_issues.append(str(error))
            try:
                feedback_at = parse_local_datetime(
                    row.get("feedback_at", ""), field_name="feedback_at"
                )
            except ImportValidationError as error:
                feedback_at = None
                row_issues.append(str(error))

            feedback_by_username = _clean(row.get("feedback_by_username"))
            feedback_by = None
            if feedback_by_username:
                feedback_by = UserModel.objects.filter(
                    username__iexact=feedback_by_username
                ).first()
                if feedback_by is None or feedback_by.role not in {
                    User.Role.ADMIN,
                    User.Role.TEACHER,
                }:
                    row_issues.append(
                        "feedback_by_username에 등록된 관리자 또는 강사 계정을 찾지 못했습니다."
                    )

            text_answer = _clean(row.get("text_answer"))
            feedback = _clean(row.get("feedback"))
            if (text_answer or feedback or feedback_at) and not submitted_at:
                row_issues.append("제출 또는 피드백 데이터가 있으면 submitted_at이 필요합니다.")
            if feedback and not feedback_by_username:
                row_issues.append("feedback이 있으면 feedback_by_username이 필요합니다.")

            recipients.append(
                {
                    "row_number": source_row,
                    "student_no": student_no,
                    "student_name": student_name,
                    "submitted_at": submitted_at,
                    "text_answer": text_answer,
                    "feedback": feedback,
                    "feedback_by": feedback_by,
                    "feedback_by_username": feedback_by_username,
                    "feedback_at": feedback_at,
                }
            )
            for message in row_issues:
                result.issues.append(ImportIssue(source_row, external_key or "(빈 과제키)", message))

        existing_map = LegacyObjectMap.objects.filter(
            source_system="LEGACY_LMS",
            object_type=LegacyObjectMap.ObjectType.ASSIGNMENT,
            external_key=external_key,
        ).first()
        predicted_action = (
            "SKIP"
            if existing_map and mode == ImportBatch.Mode.CREATE_ONLY
            else "UPDATE"
            if existing_map
            else "CREATE"
        )
        result.items.append(
            {
                "row_number": row_number,
                "external_key": external_key,
                "title": title,
                "description": description,
                "due_at": due_at,
                "teacher": teacher,
                "teacher_username": teacher_username,
                "is_published": is_published,
                "recipients": recipients,
                "recipient_count": len(recipients),
                "predicted_action": predicted_action,
                "source_rows": [int(row["_row_number"]) for row in group],
            }
        )
        for message in dict.fromkeys(issues):
            result.issues.append(ImportIssue(row_number, external_key or "(빈 과제키)", message))

    return result


def apply_assignment_import(
    uploaded_file,
    *,
    mode: str,
    actor: User,
    lookup_student: Callable[[str], object | None] = default_student_lookup,
) -> ApplyOutcome:
    preview = preview_assignment_import(uploaded_file, mode=mode, lookup_student=lookup_student)
    batch = ImportBatch.objects.create(
        kind=ImportBatch.Kind.ASSIGNMENTS,
        mode=mode,
        source_filename=preview.source_filename,
        source_sha256=preview.source_sha256,
        actor=actor,
        total_rows=preview.total_rows,
    )

    if preview.issues:
        for issue in preview.issues:
            ImportRowResult.objects.create(
                batch=batch,
                row_number=max(issue.row_number, 1),
                external_key=issue.key,
                action=ImportRowResult.Action.ERROR,
                message=issue.message,
                safe_data={},
            )
        batch.status = ImportBatch.Status.FAILED
        batch.error_count = len(preview.issues)
        batch.completed_at = timezone.now()
        batch.summary = {"encoding": preview.encoding, "validation_failed": True}
        batch.save()
        return ApplyOutcome(batch=batch)

    counters = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    for item in preview.items:
        external_key = item["external_key"]
        try:
            with transaction.atomic():
                legacy_map = LegacyObjectMap.objects.select_for_update().filter(
                    source_system="LEGACY_LMS",
                    object_type=LegacyObjectMap.ObjectType.ASSIGNMENT,
                    external_key=external_key,
                ).first()

                assignment = None
                if legacy_map:
                    assignment = Assignment.objects.filter(pk=legacy_map.target_object_id).first()
                    if assignment is None:
                        raise ImportValidationError("기존 연결 대상 과제를 찾지 못했습니다.")

                if assignment and mode == ImportBatch.Mode.CREATE_ONLY:
                    action = ImportRowResult.Action.SKIPPED
                    message = "이미 이전된 과제라 건너뛰었습니다."
                    counters["skipped"] += 1
                elif assignment:
                    assignment.title = item["title"]
                    assignment.description = item["description"]
                    assignment.due_at = item["due_at"]
                    assignment.created_by = item["teacher"]
                    assignment.is_published = item["is_published"]
                    assignment.save(
                        update_fields=(
                            "title",
                            "description",
                            "due_at",
                            "created_by",
                            "is_published",
                            "updated_at",
                        )
                    )
                    action = ImportRowResult.Action.UPDATED
                    message = "기존 과제와 제출 이력을 갱신했습니다."
                    counters["updated"] += 1
                else:
                    assignment = Assignment.objects.create(
                        title=item["title"],
                        description=item["description"],
                        due_at=item["due_at"],
                        created_by=item["teacher"],
                        is_published=item["is_published"],
                    )
                    legacy_map = LegacyObjectMap.objects.create(
                        source_system="LEGACY_LMS",
                        object_type=LegacyObjectMap.ObjectType.ASSIGNMENT,
                        external_key=external_key,
                        target_object_id=assignment.pk,
                        import_batch=batch,
                    )
                    action = ImportRowResult.Action.CREATED
                    message = "과제와 제출 이력을 생성했습니다."
                    counters["created"] += 1

                if action != ImportRowResult.Action.SKIPPED:
                    for recipient_data in item["recipients"]:
                        recipient, _ = AssignmentRecipient.objects.get_or_create(
                            assignment=assignment,
                            student_id=recipient_data["student_no"],
                            defaults={"student_name": recipient_data["student_name"]},
                        )
                        if recipient.student_name != recipient_data["student_name"]:
                            recipient.student_name = recipient_data["student_name"]
                            recipient.save(update_fields=("student_name",))

                        has_submission_data = any(
                            (
                                recipient_data["submitted_at"],
                                recipient_data["text_answer"],
                                recipient_data["feedback"],
                                recipient_data["feedback_at"],
                            )
                        )
                        if has_submission_data:
                            submission, _ = Submission.objects.get_or_create(recipient=recipient)
                            submission.submitted_at = recipient_data["submitted_at"]
                            submission.text_answer = recipient_data["text_answer"]
                            submission.feedback = recipient_data["feedback"]
                            submission.feedback_by = recipient_data["feedback_by"]
                            submission.feedback_at = recipient_data["feedback_at"]
                            submission.save()

                for recipient_data in item["recipients"]:
                    ImportRowResult.objects.create(
                        batch=batch,
                        row_number=recipient_data["row_number"],
                        external_key=external_key,
                        action=action,
                        target_type="assignments.Assignment",
                        target_id=str(assignment.pk),
                        message=message,
                        safe_data={
                            "title": item["title"],
                            "student_no": recipient_data["student_no"],
                        },
                    )
        except Exception as error:
            counters["errors"] += 1
            ImportRowResult.objects.create(
                batch=batch,
                row_number=item["row_number"],
                external_key=external_key,
                action=ImportRowResult.Action.ERROR,
                message=str(error)[:500],
                safe_data={"title": item["title"]},
            )

    batch.created_count = counters["created"]
    batch.updated_count = counters["updated"]
    batch.skipped_count = counters["skipped"]
    batch.error_count = counters["errors"]
    batch.status = (
        ImportBatch.Status.COMPLETED_WITH_ERRORS
        if counters["errors"]
        else ImportBatch.Status.COMPLETED
    )
    batch.completed_at = timezone.now()
    batch.summary = {
        "encoding": preview.encoding,
        "attachments_imported": False,
    }
    batch.save()
    return ApplyOutcome(batch=batch)


def build_credentials_csv(credentials: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("username", "display_name", "role", "temporary_password", "student_nos"))
    for item in credentials:
        writer.writerow(
            (
                _safe_csv_cell(item["username"]),
                _safe_csv_cell(item["display_name"]),
                _safe_csv_cell(item["role"]),
                _safe_csv_cell(item["temporary_password"]),
                _safe_csv_cell(item["student_nos"]),
            )
        )
    return output.getvalue().encode("utf-8-sig")


def build_batch_result_csv(batch: ImportBatch) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("row_number", "external_key", "action", "target_type", "target_id", "message"))
    for row in batch.row_results.all():
        writer.writerow(
            (
                row.row_number,
                _safe_csv_cell(row.external_key),
                row.action,
                _safe_csv_cell(row.target_type),
                _safe_csv_cell(row.target_id),
                _safe_csv_cell(row.message),
            )
        )
    return output.getvalue().encode("utf-8-sig")
