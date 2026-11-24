from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import (
    StudentAccountLink,
    User,
)
from apps.billing.contracts import (
    TuitionPaymentHistory,
)
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import StudentService


class FakeBillingService:
    def get_payment_histories(
        self,
        student_no: str,
    ):
        return [
            TuitionPaymentHistory(
                assign_no="10001",
                term_name="2026 여름특강",
                class_names="SAT Advanced",
                registered_amount=700000,
                refund_amount=0,
                carry_over_amount=0,
                net_registered_amount=700000,
                first_payment_at=datetime(
                    2026,
                    7,
                    1,
                    9,
                    0,
                    0,
                ),
                last_processed_at=datetime(
                    2026,
                    7,
                    1,
                    9,
                    0,
                    0,
                ),
            )
        ]

    def build_totals(self, histories):
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


class BillingPermissionTests(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(
            username="billing_student",
            password="StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.parent_user = User.objects.create_user(
            username="billing_parent",
            password="StrongPass!2026",
            role=User.Role.PARENT,
        )
        self.teacher_user = User.objects.create_user(
            username="billing_teacher",
            password="StrongPass!2026",
            role=User.Role.TEACHER,
        )
        self.admin_user = User.objects.create_user(
            username="billing_admin",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )

        StudentAccountLink.objects.create(
            user=self.parent_user,
            student_no="6333",
            relationship=(
                StudentAccountLink
                .Relationship.PARENT
            ),
            is_primary=True,
            is_active=True,
        )

        student_service = StudentService(
            repository=DemoStudentRepository()
        )

        self.student_service_patcher = patch(
            "apps.billing.views.get_student_service",
            return_value=student_service,
        )
        self.student_service_patcher.start()
        self.addCleanup(
            self.student_service_patcher.stop
        )

    def test_parent_can_view_billing_history(self):
        self.client.force_login(
            self.parent_user
        )

        with patch(
            "apps.billing.views.get_billing_service",
            return_value=FakeBillingService(),
        ):
            response = self.client.get(
                reverse(
                    "billing:my-history"
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "SAT Advanced",
        )
        self.assertContains(
            response,
            "premium-billing-hero",
        )

    def test_student_cannot_view_billing_history(self):
        self.client.force_login(
            self.student_user
        )

        response = self.client.get(
            reverse("billing:my-history")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_teacher_cannot_view_billing_history(self):
        self.client.force_login(
            self.teacher_user
        )

        response = self.client.get(
            reverse("billing:my-history")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_admin_cannot_view_parent_billing_history(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse("billing:my-history")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_parent_without_student_link_gets_404(self):
        parent_without_link = (
            User.objects.create_user(
                username="parent_without_link",
                password="StrongPass!2026",
                role=User.Role.PARENT,
            )
        )
        self.client.force_login(
            parent_without_link
        )

        response = self.client.get(
            reverse("billing:my-history")
        )

        self.assertEqual(
            response.status_code,
            404,
        )
