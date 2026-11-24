from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TuitionPaymentHistory:
    assign_no: str
    term_name: str
    class_names: str
    registered_amount: int
    refund_amount: int
    carry_over_amount: int
    net_registered_amount: int
    first_payment_at: datetime | None
    last_processed_at: datetime | None
