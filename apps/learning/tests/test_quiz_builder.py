"""등록 화면 정리: 퀴즈와 문항을 한 화면에서 한 번에 저장, 쓰지 않는 '제한 시간' 칸 제거, '그룹'→'반', 공개 시간 예약은 선택."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.forms import AssignmentForm
from apps.learning import quiz_types as qt
from apps.learning.forms import DiscussionForm, QuizForm
from apps.learning.models import Quiz, QuizAnswer, QuizAttempt, QuizChoice, QuizQuestion, QuizRecipient
from apps.operations.models import TeacherStudentAccess

DATE = "%Y-%m-%dT%H:%M"


def question(kind, prompt, points=2, qid=None, config=None, correct_text=""):
    item = {"type": kind, "prompt": prompt, "points": points, "config": config or {}, "correct_text": correct_text}
    if qid:
        item["id"] = qid
    return item


@override_settings(STUDENT_DATA_SOURCE="demo")
class QuizBuilderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("qb_admin", password="x-Qb!2026", role=User.Role.ADMIN)
        self.teacher = User.objects.create_user("qb_teacher", password="x-Qb!2026", role=User.Role.TEACHER)
        self.student = User.objects.create_user("qb_student", password="x-Qb!2026", role=User.Role.STUDENT)
        StudentAccountLink.objects.create(user=self.student, student_no="6333", relationship="SELF", is_primary=True, is_active=True)
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈", assigned_by=self.admin)
        lookup = patch("apps.students.services.StudentService.get_student",
                       side_effect=lambda no: SimpleNamespace(student_id=str(no), name="김지훈") if str(no) == "6333" else None)
        lookup.start()
        self.addCleanup(lookup.stop)
        self.client.force_login(self.teacher)

    def post_quiz(self, questions=None, url=None, **extra):
        data = {"title": "단어 퀴즈", "description": "", "due_at": (timezone.localtime() + timedelta(days=3)).strftime(DATE),
                "max_attempts": "1", "student_ids": "6333", "is_published": "on", **extra}
        if questions is not None:
            data["questions_json"] = json.dumps(questions)
        return self.client.post(url or reverse("learning:quiz-create"), data)

    def test_quiz_and_its_questions_are_saved_in_one_submit(self):
        response = self.post_quiz([
            question(qt.MCQ, "2+2는?", config={"choices": [{"text": "4", "correct": True}, {"text": "5"}]}),
            question(qt.SHORT, "apple의 뜻", points=3, correct_text="사과"),
            question(qt.ORDER, "순서대로", config={"items": [{"text": "1"}, {"text": "2"}]}),
        ])
        quiz = Quiz.objects.get(title="단어 퀴즈")
        self.assertRedirects(response, reverse("learning:quiz-detail", args=[quiz.pk]), fetch_redirect_response=False)
        saved = list(quiz.questions.order_by("order"))
        self.assertEqual([(q.order, q.question_type, q.points) for q in saved], [(1, "MCQ", 2), (2, "SHORT", 3), (3, "ORDER", 2)])
        self.assertEqual([(c.text, c.is_correct) for c in saved[0].choices.all()], [("4", True), ("5", False)])
        self.assertEqual(saved[1].correct_text, "사과")
        self.assertEqual([i["text"] for i in saved[2].config["items"]], ["1", "2"])

    def test_editing_updates_adds_removes_and_reorders(self):
        self.post_quiz([question(qt.TF, "참?", config={"answer": True}), question(qt.SHORT, "뜻", correct_text="사과")])
        quiz = Quiz.objects.get()
        tf, short = quiz.questions.order_by("order")
        url = reverse("learning:quiz-update", args=[quiz.pk])
        self.post_quiz([question(qt.MULTI, "짝수", config={"choices": [{"text": "2", "correct": True}, {"text": "3"}]}),
                        question(qt.TF, "거짓?", qid=tf.pk, config={"answer": False}, points=5)], url=url)
        saved = list(quiz.questions.order_by("order"))
        self.assertEqual([(q.question_type, q.prompt, q.points) for q in saved], [("MULTI", "짝수", 2), ("TF", "거짓?", 5)])
        self.assertEqual(saved[1].pk, tf.pk)
        self.assertFalse(QuizQuestion.objects.filter(pk=short.pk).exists())
        self.assertEqual([(c.text, c.is_correct) for c in saved[1].choices.all()], [("참", False), ("거짓", True)])

    def test_question_with_student_answers_cannot_be_removed(self):
        self.post_quiz([question(qt.SHORT, "뜻", correct_text="사과"), question(qt.SHORT, "둘째", correct_text="b")])
        quiz = Quiz.objects.get()
        first, second = quiz.questions.order_by("order")
        attempt = QuizAttempt.objects.create(recipient=quiz.recipients.get(), user=self.student, attempt_no=1, submitted_at=timezone.now())
        QuizAnswer.objects.create(attempt=attempt, question=first, text_answer="사과", earned_points=2)
        response = self.post_quiz([question(qt.SHORT, "둘째", qid=second.pk, correct_text="b")], url=reverse("learning:quiz-update", args=[quiz.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "응시 기록이 있는 문항")
        self.assertEqual(quiz.questions.count(), 2)

    def test_problem_in_a_question_names_its_number_and_saves_nothing(self):
        response = self.post_quiz([question(qt.SHORT, "뜻", correct_text="사과"), question(qt.ORDER, "순서", config={"items": [{"text": "1"}]})])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2번 문항: 순서 맞추기는 항목을 두 개 이상 입력하세요.")
        self.assertFalse(Quiz.objects.exists())

    def test_blank_question_text_is_refused(self):
        response = self.post_quiz([question(qt.SHORT, "  ", correct_text="a")])
        self.assertContains(response, "1번 문항: 문제를 입력하세요.")

    def test_without_question_list_questions_are_left_alone(self):
        self.post_quiz([question(qt.SHORT, "뜻", correct_text="사과")])
        quiz = Quiz.objects.get()
        self.post_quiz(None, url=reverse("learning:quiz-update", args=[quiz.pk]), title="이름만 변경")
        quiz.refresh_from_db()
        self.assertEqual(quiz.title, "이름만 변경")
        self.assertEqual(quiz.questions.count(), 1)

    def test_edit_page_carries_existing_questions_for_the_builder(self):
        self.post_quiz([question(qt.MCQ, "2+2는?", config={"choices": [{"text": "4", "correct": True}, {"text": "5"}]})])
        quiz = Quiz.objects.get()
        response = self.client.get(reverse("learning:quiz-update", args=[quiz.pk]))
        items = response.context["form"].question_items()
        self.assertEqual(items[0]["prompt"], "2+2는?")
        self.assertEqual(items[0]["config"]["choices"][0], {"text": "4", "correct": True})
        self.assertContains(response, 'id="quiz-builder-data"')

    def test_schedule_is_optional_and_empty_means_open_now(self):
        self.post_quiz([question(qt.SHORT, "뜻", correct_text="사과")], available_from="")
        quiz = Quiz.objects.get()
        self.assertIsNone(quiz.available_from)
        self.assertTrue(quiz.is_available)


class SimplerFormsTests(TestCase):
    def test_quiz_form_drops_the_unused_time_limit(self):
        self.assertNotIn("time_limit_minutes", QuizForm().fields)

    def test_class_field_is_called_class_everywhere(self):
        for form in (AssignmentForm(), QuizForm(), DiscussionForm()):
            with self.subTest(form=type(form).__name__):
                self.assertEqual(form.fields["group"].label, "반")
                self.assertFalse(form.fields["available_from"].initial)


@override_settings(STUDENT_DATA_SOURCE="demo")
class BuilderLayoutTests(TestCase):
    def test_questions_live_in_their_own_full_width_area_with_number_tabs(self):
        teacher = User.objects.create_user("qb_layout", password="x-Qb!2026", role=User.Role.TEACHER)
        self.client.force_login(teacher)
        html = self.client.get(reverse("learning:quiz-create")).content.decode()
        columns_end = html.index("</aside>", html.index('class="ux-editor-students"'))
        builder = html.index('class="quiz-builder')
        self.assertGreater(builder, columns_end)  # 위 칸(설정·대상 학생)과 따로, 아래 칸 전체 폭
        self.assertIn("data-quiz-builder-nav", html)
