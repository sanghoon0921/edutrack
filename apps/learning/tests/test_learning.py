from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess

from apps.learning.models import (
    Discussion,
    DiscussionComment,
    DiscussionRecipient,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    QuizRecipient,
)


@override_settings(STUDENT_DATA_SOURCE="demo", STUDENT_TEST_STUDENT_ID="6333")
class LearningActivityPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="learning_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="learning_teacher", password="1234", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="learning_other_teacher", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="student_test", password="1234", role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username="learning_other_student", password="1234", role=User.Role.STUDENT
        )
        self.parent = User.objects.create_user(
            username="learning_parent", password="1234", role=User.Role.PARENT
        )
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.other_student,
            student_no="7102",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.parent,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.PARENT,
            is_primary=True,
            is_active=True,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )
        self.lookup = patch(
            "apps.students.services.StudentService.get_student",
            side_effect=lambda student_no: SimpleNamespace(
                student_id=str(student_no),
                name={"6333": "김지훈", "7102": "박서연"}.get(str(student_no), ""),
            )
            if str(student_no) in {"6333", "7102"}
            else None,
        )
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def discussion(self, *, due_delta=timedelta(days=2)):
        discussion = Discussion.objects.create(
            title="문학 토론",
            content="작품의 핵심 갈등을 설명하세요.",
            available_from=timezone.now() - timedelta(hours=1),
            due_at=timezone.now() + due_delta,
            created_by=self.teacher,
            is_published=True,
        )
        recipient = DiscussionRecipient.objects.create(
            discussion=discussion,
            student_id="6333",
            student_name="김지훈",
        )
        return discussion, recipient

    def quiz(self, *, due_delta=timedelta(days=2)):
        quiz = Quiz.objects.create(
            title="어휘 퀴즈",
            description="정답을 선택하세요.",
            available_from=timezone.now() - timedelta(hours=1),
            due_at=timezone.now() + due_delta,
            time_limit_minutes=20,
            max_attempts=1,
            created_by=self.teacher,
            is_published=True,
        )
        recipient = QuizRecipient.objects.create(
            quiz=quiz,
            student_id="6333",
            student_name="김지훈",
        )
        question = QuizQuestion.objects.create(
            quiz=quiz,
            question_type=QuizQuestion.Type.MULTIPLE_CHOICE,
            prompt="정답은 무엇인가요?",
            points=5,
            order=1,
        )
        correct = QuizChoice.objects.create(
            question=question, text="정답", is_correct=True, order=1
        )
        QuizChoice.objects.create(
            question=question, text="오답", is_correct=False, order=2
        )
        return quiz, recipient, question, correct

    def test_teacher_can_create_discussion_for_assigned_student(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("learning:discussion-create"),
            {
                "title": "새 토론",
                "content": "의견을 작성하세요.",
                "available_from": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "due_at": timezone.localtime(timezone.now() + timedelta(days=2)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "student_ids": "6333",
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            DiscussionRecipient.objects.filter(
                discussion__title="새 토론", student_id="6333"
            ).exists()
        )

    def test_teacher_cannot_assign_discussion_or_quiz_to_unassigned_student(self):
        self.client.force_login(self.teacher)
        common = {
            "available_from": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "due_at": timezone.localtime(timezone.now() + timedelta(days=2)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "student_ids": "7102",
            "is_published": "on",
        }
        discussion_response = self.client.post(
            reverse("learning:discussion-create"),
            {"title": "담당 외 토론", "content": "내용", **common},
        )
        quiz_response = self.client.post(
            reverse("learning:quiz-create"),
            {
                "title": "담당 외 퀴즈",
                "description": "내용",
                "time_limit_minutes": "20",
                "max_attempts": "1",
                **common,
            },
        )
        self.assertEqual(discussion_response.status_code, 403)
        self.assertEqual(quiz_response.status_code, 403)
        self.assertFalse(Discussion.objects.filter(title="담당 외 토론").exists())
        self.assertFalse(Quiz.objects.filter(title="담당 외 퀴즈").exists())

    def test_student_can_comment_on_assigned_discussion(self):
        _, recipient = self.discussion()
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("learning:my-discussion-detail", kwargs={"recipient_id": recipient.pk}),
            {"content": "학생 의견입니다."},
        )
        self.assertEqual(response.status_code, 302)
        comment = DiscussionComment.objects.get(discussion=recipient.discussion)
        self.assertEqual(comment.author, self.student)
        self.assertEqual(comment.student_id, "6333")

    def test_parent_can_read_but_cannot_comment(self):
        _, recipient = self.discussion()
        self.client.force_login(self.parent)
        detail_url = reverse(
            "learning:my-discussion-detail", kwargs={"recipient_id": recipient.pk}
        )
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(
            self.client.post(detail_url, {"content": "학부모 댓글"}).status_code, 403
        )
        self.assertFalse(DiscussionComment.objects.exists())

    def test_student_cannot_comment_after_deadline(self):
        _, recipient = self.discussion(due_delta=timedelta(minutes=-1))
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("learning:my-discussion-detail", kwargs={"recipient_id": recipient.pk}),
            {"content": "늦은 댓글"},
        )
        self.assertEqual(response.status_code, 403)

    def test_other_student_cannot_open_discussion_or_quiz(self):
        _, discussion_recipient = self.discussion()
        _, quiz_recipient, _, _ = self.quiz()
        self.client.force_login(self.other_student)
        self.assertEqual(
            self.client.get(
                reverse(
                    "learning:my-discussion-detail",
                    kwargs={"recipient_id": discussion_recipient.pk},
                )
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "learning:my-quiz-detail",
                    kwargs={"recipient_id": quiz_recipient.pk},
                )
            ).status_code,
            404,
        )

    def test_student_can_attempt_assigned_quiz_and_score_is_saved(self):
        _, recipient, question, correct = self.quiz()
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("learning:my-quiz-detail", kwargs={"recipient_id": recipient.pk}),
            {f"question_{question.pk}": str(correct.pk)},
        )
        self.assertEqual(response.status_code, 302)
        attempt = QuizAttempt.objects.get(recipient=recipient)
        self.assertEqual(attempt.user, self.student)
        self.assertEqual(float(attempt.score), 5.0)
        self.assertEqual(float(attempt.max_score), 5.0)
        self.assertEqual(QuizAnswer.objects.get(attempt=attempt).selected_choice, correct)

    def test_parent_can_view_quiz_result_but_cannot_attempt(self):
        _, recipient, question, correct = self.quiz()
        QuizAttempt.objects.create(
            recipient=recipient,
            user=self.student,
            attempt_no=1,
            submitted_at=timezone.now(),
            score=5,
            max_score=5,
        )
        self.client.force_login(self.parent)
        url = reverse("learning:my-quiz-detail", kwargs={"recipient_id": recipient.pk})
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(
            self.client.post(url, {f"question_{question.pk}": str(correct.pk)}).status_code,
            403,
        )

    def test_teacher_cannot_manage_other_teachers_learning_object(self):
        discussion, _ = self.discussion()
        self.client.force_login(self.other_teacher)
        self.assertEqual(
            self.client.get(
                reverse(
                    "learning:discussion-update",
                    kwargs={"discussion_id": discussion.pk},
                )
            ).status_code,
            403,
        )
