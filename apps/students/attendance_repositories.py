from __future__ import annotations

from datetime import (
    date,
    datetime,
    time,
    timedelta,
)
from typing import Protocol

from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .contracts import AttendanceRecord

KOREA = ZoneInfo("Asia/Seoul")


class AttendanceRepository(Protocol):
    """출결 데이터 저장소의 공통 규격입니다."""

    def list_by_student_and_assign(
        self,
        student_id: str,
        assign_id: str,
        include_carry_over: bool = False,
    ) -> list[AttendanceRecord]:
        ...

    def list_by_student_and_assigns(
        self,
        student_id: str,
        assign_ids: list[str],
        include_carry_over: bool = False,
    ) -> dict[str, list[AttendanceRecord]]:
        ...


def _to_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_date(value) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    cleaned = str(value).strip()

    if not cleaned:
        return None

    for date_format in (
        "%Y-%m-%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(
                cleaned,
                date_format,
            ).date()
        except ValueError:
            continue

    return None


def _format_time(value) -> str:
    if value is None:
        return ""

    cleaned = str(value).strip()

    if not cleaned:
        return ""

    digits = "".join(
        character
        for character in cleaned
        if character.isdigit()
    )

    if not digits:
        return cleaned

    digits = digits.zfill(4)[-4:]

    return f"{digits[:2]}:{digits[2:]}"


def _fetch_all_as_dicts(cursor) -> list[dict]:
    column_names = [
        column[0]
        for column in cursor.description
    ]

    return [
        dict(zip(column_names, row))
        for row in cursor.fetchall()
    ]


def _attendance_label(
    *,
    attendance_code: str,
    lesson_date: date | None,
    is_student_cancelled: bool,
    is_class_cancelled: bool,
) -> tuple[str, str]:
    if is_student_cancelled:
        return "cancelled", "개별취소"

    if is_class_cancelled:
        return "holiday", "학원휴강"

    status_map = {
        "PR": ("present", "출석"),
        "AB": ("absent", "결석"),
        "LT": ("late", "지각"),
        "RC": ("recorded", "녹화"),
        # 인트라넷 code 표 attend_status 그룹: CO 이월, RF 환불 (출석률 계산에서는 빠집니다)
        "CO": ("carried", "이월"),
        "RF": ("refunded", "환불"),
    }

    normalized_code = attendance_code.upper()

    if normalized_code in status_map:
        return status_map[normalized_code]

    if (
        lesson_date is not None
        and lesson_date > date.today()
    ):
        return "upcoming", "예정"

    if (
        lesson_date is not None
        and lesson_date <= date.today()
    ):
        return "unprocessed", "미처리"

    return "other", normalized_code or "미지정"


def _payment_label(payment_code: str) -> str:
    return {
        "PAID": "수납",
        "REFUND": "환불",
        "CARRY_OVER": "이월",
    }.get(
        payment_code.upper(),
        payment_code or "미지정",
    )


def _row_to_attendance_record(
    row: dict,
) -> AttendanceRecord:
    lesson_date = _to_date(
        row.get("lesson_date")
    )

    attendance_code = _to_text(
        row.get("attendance_code")
    )

    is_student_cancelled = bool(
        row.get("is_student_cancelled")
    )

    is_class_cancelled = bool(
        row.get("is_class_cancelled")
    )

    status_kind, attendance_label = (
        _attendance_label(
            attendance_code=attendance_code,
            lesson_date=lesson_date,
            is_student_cancelled=is_student_cancelled,
            is_class_cancelled=is_class_cancelled,
        )
    )

    start_time = _format_time(
        row.get("start_time")
    )
    end_time = _format_time(
        row.get("end_time")
    )

    if start_time and end_time:
        time_summary = (
            f"{start_time}–{end_time}"
        )
    else:
        time_summary = (
            start_time or end_time
        )

    payment_code = _to_text(
        row.get("payment_code")
    )

    return AttendanceRecord(
        assign_id=_to_text(
            row.get("assign_id")
        ),
        lesson_id=_to_text(
            row.get("lesson_id")
        ),
        lesson_date=lesson_date,
        lesson_type=_to_text(
            row.get("lesson_type")
        ),
        time_summary=time_summary,
        lesson_way=_to_text(
            row.get("lesson_way")
        ),
        attendance_code=attendance_code,
        attendance_label=attendance_label,
        status_kind=status_kind,
        attendance_type=_to_text(
            row.get("attendance_type")
        ),
        payment_code=payment_code,
        payment_label=_payment_label(
            payment_code
        ),
        is_student_cancelled=(
            is_student_cancelled
        ),
        is_class_cancelled=(
            is_class_cancelled
        ),
        recording_sent_at=_korea_time(row.get("recording_sent_at")),
    )


def _korea_time(value):
    """인트라넷 DB의 시각(한국 시간, 시간대 없음)을 시간대가 있는 값으로."""
    if not isinstance(value, datetime):
        return None
    return timezone.make_aware(value, KOREA) if timezone.is_naive(value) else value


# 테스트에서 같은 날짜 묶음과 예정 구분을 검증할 수 있도록
# 현재 날짜를 기준으로 동적 모의 데이터를 구성합니다.
_DEMO_TODAY = date.today()
_DEMO_SHARED_DATE = (
    _DEMO_TODAY - timedelta(days=3)
)

DEMO_ATTENDANCE: dict[
    tuple[str, str],
    tuple[AttendanceRecord, ...],
] = {
    (
        "6333",
        "10001",
    ): (
        # 녹화 회차 2개(발송 완료 1, 발송 전 1): 테스트 서버에서 학부모 '녹화' 카드를 볼 수 있게(운영팀 요청 10.29).
        AttendanceRecord(
            assign_id="10001",
            lesson_id="49901",
            lesson_date=_DEMO_TODAY - timedelta(days=14),
            lesson_type="READING",
            time_summary="09:00–10:30",
            lesson_way="ONLINE",
            attendance_code="RC",
            attendance_label="녹화",
            status_kind="recorded",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
            recording_sent_at=datetime.combine(
                _DEMO_TODAY - timedelta(days=13), time(14, 20), tzinfo=KOREA
            ),
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="49902",
            lesson_date=_DEMO_TODAY - timedelta(days=10),
            lesson_type="MATH",
            time_summary="11:00–12:30",
            lesson_way="ONLINE",
            attendance_code="RC",
            attendance_label="녹화",
            status_kind="recorded",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50001",
            lesson_date=(
                _DEMO_TODAY
                - timedelta(days=7)
            ),
            lesson_type="WRITING",
            time_summary="09:00–10:30",
            lesson_way="ONLINE",
            attendance_code="PR",
            attendance_label="출석",
            status_kind="present",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50002",
            lesson_date=_DEMO_SHARED_DATE,
            lesson_type="READING",
            time_summary="09:00–10:30",
            lesson_way="ONLINE",
            attendance_code="LT",
            attendance_label="지각",
            status_kind="late",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50003",
            lesson_date=_DEMO_SHARED_DATE,
            lesson_type="MATH",
            time_summary="11:00–12:30",
            lesson_way="ONLINE",
            attendance_code="PR",
            attendance_label="출석",
            status_kind="present",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50004",
            lesson_date=(
                _DEMO_TODAY
                - timedelta(days=1)
            ),
            lesson_type="MATH",
            time_summary="09:00–10:30",
            lesson_way="ONLINE",
            attendance_code="AB",
            attendance_label="결석",
            status_kind="absent",
            attendance_type="MANUAL",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50005",
            lesson_date=(
                _DEMO_TODAY
                + timedelta(days=2)
            ),
            lesson_type="READING",
            time_summary="09:00–10:30",
            lesson_way="ONLINE",
            attendance_code="",
            attendance_label="예정",
            status_kind="upcoming",
            attendance_type="",
            payment_code="PAID",
            payment_label="수납",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
        AttendanceRecord(
            assign_id="10001",
            lesson_id="50006",
            lesson_date=(
                _DEMO_TODAY
                + timedelta(days=5)
            ),
            lesson_type="MATH",
            time_summary="11:00–12:30",
            lesson_way="ONLINE",
            attendance_code="",
            attendance_label="예정",
            status_kind="upcoming",
            attendance_type="",
            payment_code="CARRY_OVER",
            payment_label="이월",
            is_student_cancelled=False,
            is_class_cancelled=False,
        ),
    ),
}


class DemoAttendanceRepository:
    """자동 테스트용 모의 출결 저장소입니다."""

    def list_by_student_and_assign(
        self,
        student_id: str,
        assign_id: str,
        include_carry_over: bool = False,
    ) -> list[AttendanceRecord]:
        key = (
            student_id.strip(),
            assign_id.strip(),
        )

        records = list(
            DEMO_ATTENDANCE.get(
                key,
                (),
            )
        )

        return [
            record
            for record in records
            if include_carry_over or record.payment_code != "CARRY_OVER"
        ]

    def list_by_student_and_assigns(
        self,
        student_id: str,
        assign_ids: list[str],
        include_carry_over: bool = False,
    ) -> dict[str, list[AttendanceRecord]]:
        ordered_ids = list(
            dict.fromkeys(
                str(assign_id).strip()
                for assign_id in assign_ids
                if str(assign_id).strip()
            )
        )
        return {
            assign_id: self.list_by_student_and_assign(student_id, assign_id, include_carry_over)
            for assign_id in ordered_ids
        }


class IntranetAttendanceRepository:
    """실제 서비스에서는 사내 인트라넷 DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def get_attendance_repository() -> (
    AttendanceRepository
):
    data_source = getattr(
        settings,
        "STUDENT_DATA_SOURCE",
        "demo",
    ).strip().lower()

    if data_source == "demo":
        return DemoAttendanceRepository()

    if data_source == "intranet":
        return IntranetAttendanceRepository()

    raise ImproperlyConfigured(
        "STUDENT_DATA_SOURCE는 "
        "'demo' 또는 'intranet'이어야 합니다."
    )
