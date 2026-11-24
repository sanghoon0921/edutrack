from unittest.mock import Mock

from django.core.cache import cache
from django.test import (
    SimpleTestCase,
    override_settings,
)

from apps.assessments.detail_repositories import (
    DemoExamDetailRepository,
)
from apps.assessments.detail_services import (
    ExamDetailService,
)


@override_settings(
    EXAM_DETAIL_CACHE_SECONDS=900,
)
class ExamDetailPerformanceTests(
    SimpleTestCase
):
    def setUp(self):
        cache.clear()

    def test_second_request_uses_cache(self):
        repository = (
            DemoExamDetailRepository()
        )

        repository.get_student_profile = Mock(
            wraps=(
                repository
                .get_student_profile
            )
        )
        repository.get_attempt = Mock(
            wraps=repository.get_attempt
        )
        repository.list_questions = Mock(
            wraps=repository.list_questions
        )

        service = ExamDetailService(
            repository=repository
        )

        first = service.get_attempt_detail(
            "6333",
            "919696",
        )

        second = service.get_attempt_detail(
            "6333",
            "919696",
        )

        self.assertEqual(
            first,
            second,
        )

        repository.get_student_profile.assert_called_once()
        repository.get_attempt.assert_called_once()
        repository.list_questions.assert_called_once()

    def test_force_refresh_runs_repository_again(self):
        repository = (
            DemoExamDetailRepository()
        )

        repository.list_questions = Mock(
            wraps=repository.list_questions
        )

        service = ExamDetailService(
            repository=repository
        )

        service.get_attempt_detail(
            "6333",
            "919696",
        )

        service.get_attempt_detail(
            "6333",
            "919696",
            force_refresh=True,
        )

        self.assertEqual(
            repository.list_questions.call_count,
            2,
        )
