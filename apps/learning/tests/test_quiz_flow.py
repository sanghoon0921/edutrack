"""퀴즈 7가지 유형의 화면 흐름: 강사 문항 만들기(유형 카드 + 편집기) → 학생 응시 → 자동 채점 → 결과 화면."""
import json
import random
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.learning import quiz_types as qt
from apps.learning.models import Quiz, QuizAnswer, QuizAttempt, QuizChoice, QuizQuestion, QuizRecipient

SAMPLES = {  # 유형: (문장, 편집기가 보내는 정답 구성)
    qt.CATEGORY: ("품사별로 나누세요.", {"categories": [{"name": "명사", "items": ["apple"]}, {"name": "동사", "items": ["run"]}],
                                   "distractors": ["quickly"]}),
    qt.MCQ: ("2+2는?", {"choices": [{"text": "4", "correct": True}, {"text": "5"}]}),
    qt.MULTI: ("짝수를 모두 고르세요.", {"choices": [{"text": "2", "correct": True}, {"text": "4", "correct": True}, {"text": "5"}]}),
    qt.FILL: ("The capital is `Paris`. He `went` home.", {"blanks": [{"mode": "text"}, {"mode": "dropdown", "options": ["go"]}]}),
    qt.ORDER: ("작은 수부터 놓으세요.", {"items": [{"text": "1"}, {"text": "2"}, {"text": "3"}]}),
    qt.MATCH: ("뜻을 연결하세요.", {"pairs": [{"left": "dog", "right": "개"}, {"left": "cat", "right": "고양이"}], "distractors": ["새"]}),
    qt.TF: ("지구는 둥글다.", {"answer": True}),
}


@override_settings(STUDENT_DATA_SOURCE="demo", STUDENT_TEST_STUDENT_ID="6333")
class QuizFlowFixture(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("flow_teacher", password="x-Flow!2026", role=User.Role.TEACHER)
        self.student = User.objects.create_user("flow_student", password="x-Flow!2026", role=User.Role.STUDENT)
        StudentAccountLink.objects.create(user=self.student, student_no="6333", relationship=StudentAccountLink.Relationship.SELF,
                                          is_primary=True, is_active=True)
        lookup = patch("apps.students.services.StudentService.get_student",
                       side_effect=lambda no: SimpleNamespace(student_id=str(no), name="김지훈") if str(no) == "6333" else None)
        lookup.start()
        self.addCleanup(lookup.stop)
        self.quiz = Quiz.objects.create(title="유형 퀴즈", created_by=self.teacher, due_at=timezone.now() + timedelta(days=2),
                                        available_from=timezone.now() - timedelta(hours=1), max_attempts=2)
        self.recipient = QuizRecipient.objects.create(quiz=self.quiz, student_id="6333", student_name="김지훈")

    def add(self, kind, order=1, points=2):
        prompt, data = SAMPLES[kind]
        config, choices = qt.clean_config(kind, data, prompt)
        question = QuizQuestion.objects.create(quiz=self.quiz, question_type=kind, prompt=prompt, points=points, order=order, config=config)
        for index, choice in enumerate(choices, start=1):
            QuizChoice.objects.create(question=question, text=choice["text"], is_correct=choice["is_correct"], order=index)
        return question

    def perfect_answers(self, question):
        name, config = f"question_{question.pk}", question.config
        choices = list(question.choices.all())
        if question.question_type in (qt.MCQ, qt.TF):
            return {name: [str(next(c.pk for c in choices if c.is_correct))]}
        if question.question_type == qt.MULTI:
            return {name: [str(c.pk) for c in choices if c.is_correct]}
        if question.question_type == qt.FILL:
            return {f"{name}_blank_{i}": [b["answers"][0]] for i, b in enumerate(config["blanks"])}
        if question.question_type == qt.ORDER:
            return {f"{name}_order": [item["id"] for item in config["items"]]}
        if question.question_type == qt.MATCH:
            return {f"{name}_match_{p['id']}": [p["right"]] for p in config["pairs"]}
        return {f"{name}_cat_{i['id']}": [i["category"]] for i in config["items"] if i["category"]}


class TeacherQuestionEditorTests(QuizFlowFixture):
    def create(self, kind, data, prompt=None, **extra):
        self.client.force_login(self.teacher)
        return self.client.post(reverse("learning:quiz-question-create", args=[self.quiz.pk]), {
            "question_type": kind, "prompt": prompt or SAMPLES.get(kind, ("문제",))[0], "points": "3", "order": "1",
            "correct_text": "", "config_json": json.dumps(data), **extra})

    def test_each_type_can_be_created_from_the_editor(self):
        for kind, (prompt, data) in SAMPLES.items():
            with self.subTest(kind=kind):
                self.assertEqual(self.create(kind, data, prompt).status_code, 302)
                question = QuizQuestion.objects.filter(quiz=self.quiz, question_type=kind).get()
                expected_config, expected_choices = qt.clean_config(kind, data, prompt)
                self.assertEqual(question.config, expected_config)
                self.assertEqual([(c.text, c.is_correct) for c in question.choices.all()],
                                 [(c["text"], c["is_correct"]) for c in expected_choices])

    def test_editor_problem_is_shown_and_nothing_is_saved(self):
        response = self.create(qt.ORDER, {"items": [{"text": "하나"}]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "순서 맞추기는 항목을 두 개 이상 입력하세요.")
        self.assertFalse(QuizQuestion.objects.exists())

    def test_old_star_list_still_makes_a_multiple_choice_question(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("learning:quiz-question-create", args=[self.quiz.pk]), {
            "question_type": "MCQ", "prompt": "옛 방식", "points": "1", "order": "1", "choices_text": "*정답\n오답"})
        self.assertEqual([(c.text, c.is_correct) for c in QuizQuestion.objects.get().choices.all()], [("정답", True), ("오답", False)])

    def test_editing_round_trips_every_type(self):
        self.client.force_login(self.teacher)
        for order, kind in enumerate(SAMPLES, start=1):
            question = self.add(kind, order)
            with self.subTest(kind=kind):
                response = self.client.get(reverse("learning:quiz-question-update", args=[self.quiz.pk, question.pk]))
                self.assertContains(response, 'id="quiz-editor-data"')
                data = response.context["editor"]["config"]
                self.assertEqual(qt.clean_config(kind, data, question.prompt)[0], question.config)

    def test_type_cards_list_all_seven_canvas_types(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("learning:quiz-question-create", args=[self.quiz.pk]))
        for label in ["범주화", "객관식", "복수 응답", "빈칸 채우기", "순서 맞추기", "짝 맞추기", "참/거짓"]:
            self.assertContains(response, label)


class StudentAttemptTests(QuizFlowFixture):
    def setUp(self):
        super().setUp()
        self.questions = [self.add(kind, order) for order, kind in enumerate(SAMPLES, start=1)]
        self.url = reverse("learning:my-quiz-detail", args=[self.recipient.pk])

    def test_attempt_page_shows_a_widget_for_every_type(self):
        self.client.force_login(self.student)
        html = self.client.get(self.url).content.decode()
        by_kind = {q.question_type: q for q in self.questions}
        self.assertIn("data-quiz-category", html)
        self.assertIn("data-quiz-order", html)
        self.assertIn(f'type="checkbox" name="question_{by_kind[qt.MULTI].pk}"', html)
        self.assertIn(f'name="question_{by_kind[qt.FILL].pk}_blank_0"', html)
        self.assertIn(f'<select name="question_{by_kind[qt.FILL].pk}_blank_1"', html)
        self.assertIn(f'name="question_{by_kind[qt.MATCH].pk}_match_', html)
        self.assertNotIn("`Paris`", html)
        self.assertIn("참 (True)", html)
        self.assertIn("거짓 (False)", html)

    def test_perfect_answers_score_full_marks_and_keep_each_response(self):
        self.client.force_login(self.student)
        data = {}
        for question in self.questions:
            data.update(self.perfect_answers(question))
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        attempt = QuizAttempt.objects.get(recipient=self.recipient)
        self.assertEqual(attempt.score, Decimal("14.00"))
        self.assertEqual(attempt.max_score, Decimal("14.00"))
        mcq = QuizAnswer.objects.get(attempt=attempt, question__question_type=qt.MCQ)
        self.assertTrue(mcq.selected_choice.is_correct)
        order = QuizAnswer.objects.get(attempt=attempt, question__question_type=qt.ORDER)
        self.assertEqual(len(order.response["order"]), 3)

    def test_partly_right_answers_get_partial_credit(self):
        self.client.force_login(self.student)
        match = next(q for q in self.questions if q.question_type == qt.MATCH)
        first, second = (p["id"] for p in match.config["pairs"])
        self.client.post(self.url, {f"question_{match.pk}_match_{first}": "개", f"question_{match.pk}_match_{second}": "새"})
        answer = QuizAnswer.objects.get(question=match)
        self.assertEqual(answer.earned_points, Decimal("1.00"))


class ResultScreenTests(QuizFlowFixture):
    def setUp(self):
        super().setUp()
        self.fill = self.add(qt.FILL)
        self.client.force_login(self.student)
        self.client.post(reverse("learning:my-quiz-detail", args=[self.recipient.pk]),
                         {f"question_{self.fill.pk}_blank_0": "paris", f"question_{self.fill.pk}_blank_1": "go"})
        self.attempt = QuizAttempt.objects.get()

    def test_teacher_sees_each_part_marked_right_or_wrong(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("lms:quiz-review", args=[self.attempt.pk]))
        self.assertContains(response, "빈칸 1")
        self.assertContains(response, 'class="quiz-part is-right"')
        self.assertContains(response, 'class="quiz-part is-wrong"')
        self.assertContains(response, "went")

    def test_student_sees_correct_answers_only_after_the_quiz_closes(self):
        review = reverse("lms:quiz-review", args=[self.attempt.pk])
        open_page = self.client.get(review)
        self.assertContains(open_page, 'class="quiz-part is-wrong"')
        self.assertNotContains(open_page, "went")
        Quiz.objects.filter(pk=self.quiz.pk).update(due_at=timezone.now() - timedelta(minutes=1))
        self.assertContains(self.client.get(review), "went")

    def test_answer_text_for_the_annotation_copy(self):
        from apps.lms.documents import quiz_text
        self.assertIn("빈칸 1: paris · 빈칸 2: go", quiz_text(self.attempt))
