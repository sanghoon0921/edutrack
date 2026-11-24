from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.connection import ConnectionDoesNotExist

from apps.accounts.models import StudentAccountLink, User
from apps.billing.services import BillingService, DemoBillingRepository
from apps.billing.repositories import IntranetBillingRepository


class MeetingBillingIsolationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="ui_v2_parent",password="test-only",role=User.Role.PARENT)
        StudentAccountLink.objects.create(user=self.parent,student_no="6333",relationship=StudentAccountLink.Relationship.PARENT,is_primary=True,is_active=True)


    @override_settings(STUDENT_DATA_SOURCE="intranet", BILLING_DATA_SOURCE="demo")
    def test_explicit_demo_mode_takes_precedence(self):
        self.assertIsInstance(BillingService().repository, DemoBillingRepository)

    @override_settings(STUDENT_DATA_SOURCE="demo")
    def test_missing_connection_shows_503_not_500(self):
        self.client.force_login(self.parent)
        with patch("apps.billing.views.get_billing_service",side_effect=ConnectionDoesNotExist("missing")), self.assertLogs("apps.billing.views", level="ERROR"):
            response = self.client.get(reverse("billing:my-history"))
        self.assertEqual(response.status_code,503)

    def test_student_still_cannot_view_parent_billing(self):
        user=User.objects.create_user(username="ui_v2_student",password="test-only",role=User.Role.STUDENT)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("billing:my-history")).status_code,403)
