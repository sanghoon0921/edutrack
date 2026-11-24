from __future__ import annotations

from typing import Protocol


from .contracts import TuitionPaymentHistory


class BillingRepository(Protocol):
    def list_payment_histories(
        self,
        student_no: str,
    ) -> list[TuitionPaymentHistory]:
        ...


def _to_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_int(value) -> int:
    if value is None:
        return 0

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _fetch_all_as_dicts(cursor) -> list[dict]:
    columns = [
        column[0]
        for column in cursor.description
    ]

    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


class IntranetBillingRepository:
    """실제 서비스에서는 사내 인트라넷 DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)
