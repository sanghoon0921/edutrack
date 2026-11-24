from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .contracts import TuitionPaymentHistory
from .repositories import (
    BillingRepository,
    IntranetBillingRepository,
)


class DemoBillingRepository:
    """A demo screen must never query real tuition records.

    No example balances are fabricated: the page shows an explicit demo notice.
    """

    def list_payment_histories(self, student_no: str) -> list[TuitionPaymentHistory]:
        return []


def _default_repository() -> BillingRepository:
    source = getattr(settings, "BILLING_DATA_SOURCE", None)
    if source is None:
        source = getattr(settings, "STUDENT_DATA_SOURCE", "intranet")
    source = str(source).strip().lower()
    if source == "demo":
        return DemoBillingRepository()
    if source == "intranet":
        return IntranetBillingRepository()
    raise ImproperlyConfigured("BILLING_DATA_SOURCE must be demo or intranet.")


class BillingService:
    def __init__(
        self,
        repository: BillingRepository | None = None,
    ) -> None:
        self.repository = (
            repository
            or _default_repository()
        )

    @property
    def is_demo(self) -> bool:
        return isinstance(self.repository, DemoBillingRepository)

    def get_payment_histories(
        self,
        student_no: str,
    ) -> list[TuitionPaymentHistory]:
        return (
            self.repository
            .list_payment_histories(
                student_no
            )
        )

    def build_totals(
        self,
        histories: list[TuitionPaymentHistory],
    ) -> dict[str, int]:
        return {
            "registered_amount": sum(
                row.registered_amount
                for row in histories
            ),
            "refund_amount": sum(
                row.refund_amount
                for row in histories
            ),
            "carry_over_amount": sum(
                row.carry_over_amount
                for row in histories
            ),
            "net_registered_amount": sum(
                row.net_registered_amount
                for row in histories
            ),
        }
