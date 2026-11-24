"""퀴즈 문항 유형(Canvas 7가지 + 단답형): 정답 설정 검증, 답안 읽기, 부분 점수 채점, 학생 화면 준비, 결과 표시."""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from apps.learning import quiz_types as qt
from apps.learning.models import Quiz, QuizChoice, QuizQuestion


def post(**fields):
    data = QueryDict(mutable=True)
    for key, value in fields.items():
        data.setlist(key, value if isinstance(value, list) else [value])
    return data


class QuizTypeFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        teacher = get_user_model().objects.create_user("qt_teacher", password="x-Quiz!2026", role="TEACHER")
        cls.quiz = Quiz.objects.create(title="유형 퀴즈", created_by=teacher, due_at=timezone.now() + timedelta(days=1))

    def question(self, qtype, prompt="문제", points=4, data=None, correct_text=""):
        config, choices = qt.clean_config(qtype, data or {}, prompt) if qtype != qt.SHORT else ({}, [])
        question = QuizQuestion.objects.create(quiz=self.quiz, question_type=qtype, prompt=prompt, points=points,
                                               config=config, correct_text=correct_text)
        for order, choice in enumerate(choices, start=1):
            QuizChoice.objects.create(question=question, text=choice["text"], is_correct=choice["is_correct"], order=order)
        return question

    def choice_id(self, question, text):
        return str(question.choices.get(text=text).pk)

    def score(self, question, **fields):
        return qt.grade(question, qt.read_response(question, post(**fields)))


class ConfigValidationTests(QuizTypeFixture):
    def test_every_canvas_type_is_offered(self):
        self.assertEqual([value for value, _ in QuizQuestion.Type.choices],
                         ["CATEGORY", "MCQ", "MULTI", "FILL", "ORDER", "MATCH", "TF", "SHORT"])

    def test_multiple_choice_needs_exactly_one_answer(self):
        with self.assertRaisesMessage(ValidationError, "정답"):
            qt.clean_config(qt.MCQ, {"choices": [{"text": "A", "correct": True}, {"text": "B", "correct": True}]}, "문제")
        _, choices = qt.clean_config(qt.MCQ, {"choices": [{"text": "A", "correct": True}, {"text": "B"}, {"text": " "}]}, "문제")
        self.assertEqual(choices, [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}])

    def test_multiple_answers_need_at_least_one_correct_of_two(self):
        with self.assertRaises(ValidationError):
            qt.clean_config(qt.MULTI, {"choices": [{"text": "A"}, {"text": "B"}]}, "문제")
        _, choices = qt.clean_config(qt.MULTI, {"choices": [{"text": "A", "correct": True}, {"text": "B", "correct": True}, {"text": "C"}]}, "문제")
        self.assertEqual(sum(c["is_correct"] for c in choices), 2)

    def test_true_false_becomes_two_fixed_choices(self):
        _, choices = qt.clean_config(qt.TF, {"answer": False}, "지구는 평평하다.")
        self.assertEqual(choices, [{"text": "참", "is_correct": False}, {"text": "거짓", "is_correct": True}])
        with self.assertRaises(ValidationError):
            qt.clean_config(qt.TF, {}, "문제")

    def test_fill_in_the_blank_reads_answers_from_backticks(self):
        config, _ = qt.clean_config(qt.FILL, {"blanks": [{"mode": "text"}, {"mode": "dropdown", "options": ["went", "goes"]}],
                                              "bank": []}, "The capital is `Paris|paris`. He `go` home.")
        self.assertEqual(config["blanks"][0], {"mode": "text", "answers": ["Paris", "paris"], "options": []})
        self.assertEqual(config["blanks"][1], {"mode": "dropdown", "answers": ["go"], "options": ["went", "goes"]})

    def test_fill_in_the_blank_needs_a_blank_and_dropdown_options(self):
        with self.assertRaisesMessage(ValidationError, "빈칸"):
            qt.clean_config(qt.FILL, {"blanks": []}, "빈칸 없는 문장")
        with self.assertRaisesMessage(ValidationError, "드롭다운"):
            qt.clean_config(qt.FILL, {"blanks": [{"mode": "dropdown", "options": []}]}, "He `go` home.")

    def test_ordering_needs_two_items_and_keeps_ids(self):
        with self.assertRaises(ValidationError):
            qt.clean_config(qt.ORDER, {"items": [{"text": "하나"}]}, "문제")
        config, _ = qt.clean_config(qt.ORDER, {"items": [{"id": "o7", "text": "첫째"}, {"text": "둘째"}, {"text": "  "}]}, "문제")
        self.assertEqual([i["text"] for i in config["items"]], ["첫째", "둘째"])
        self.assertEqual(config["items"][0]["id"], "o7")
        self.assertEqual(len({i["id"] for i in config["items"]}), 2)

    def test_matching_needs_two_pairs_and_distinct_distractors(self):
        with self.assertRaises(ValidationError):
            qt.clean_config(qt.MATCH, {"pairs": [{"left": "dog", "right": "개"}]}, "문제")
        config, _ = qt.clean_config(qt.MATCH, {"pairs": [{"left": "dog", "right": "개"}, {"left": "cat", "right": "고양이"}],
                                               "distractors": ["새", "개", "새"]}, "문제")
        self.assertEqual(config["distractors"], ["새"])

    def test_categorization_needs_named_categories_with_items(self):
        with self.assertRaises(ValidationError):
            qt.clean_config(qt.CATEGORY, {"categories": [{"name": "명사", "items": []}]}, "문제")
        config, _ = qt.clean_config(qt.CATEGORY, {"categories": [{"name": "명사", "items": ["apple", "dog"]},
                                                                  {"name": "동사", "items": ["run"]}],
                                                  "distractors": ["quickly"]}, "문제")
        self.assertEqual([c["name"] for c in config["categories"]], ["명사", "동사"])
        noun = config["categories"][0]["id"]
        self.assertEqual([(i["text"], i["category"]) for i in config["items"]],
                         [("apple", noun), ("dog", noun), ("run", config["categories"][1]["id"]), ("quickly", "")])


class GradingTests(QuizTypeFixture):
    def test_multiple_choice_and_true_false(self):
        mcq = self.question(qt.MCQ, data={"choices": [{"text": "A", "correct": True}, {"text": "B"}]})
        self.assertEqual(self.score(mcq, **{f"question_{mcq.pk}": self.choice_id(mcq, "A")}), Decimal("4.00"))
        self.assertEqual(self.score(mcq, **{f"question_{mcq.pk}": self.choice_id(mcq, "B")}), Decimal("0.00"))
        tf = self.question(qt.TF, data={"answer": True})
        self.assertEqual(self.score(tf, **{f"question_{tf.pk}": self.choice_id(tf, "참")}), Decimal("4.00"))

    def test_true_false_results_show_english_next_to_korean(self):
        """운영팀 요청(10/29): 참/거짓 옆에 True / False."""
        tf = self.question(qt.TF, data={"answer": True})
        response = {"choice": int(self.choice_id(tf, "거짓"))}
        self.assertEqual(qt.review(tf, response)[0]["given"], "거짓 (False)")
        self.assertEqual(qt.review(tf, response)[0]["expected"], "참 (True)")
        self.assertEqual(qt.answer_text(tf, response), "거짓 (False)")
        self.assertEqual(qt.tf_label("보기"), "보기")

    def test_multiple_answers_partial_credit_subtracts_wrong_picks(self):
        q = self.question(qt.MULTI, data={"choices": [{"text": "A", "correct": True}, {"text": "B", "correct": True},
                                                      {"text": "C"}, {"text": "D"}]})
        name = f"question_{q.pk}"
        a, b, c = (self.choice_id(q, t) for t in "ABC")
        self.assertEqual(self.score(q, **{name: [a, b]}), Decimal("4.00"))
        self.assertEqual(self.score(q, **{name: [a]}), Decimal("2.00"))
        self.assertEqual(self.score(q, **{name: [a, b, c]}), Decimal("2.00"))
        self.assertEqual(self.score(q, **{name: [a, c]}), Decimal("0.00"))
        self.assertEqual(self.score(q, **{name: [c]}), Decimal("0.00"))

    def test_fill_in_the_blank_scores_each_blank(self):
        q = self.question(qt.FILL, prompt="The capital is `Paris|Lutetia`. He `went` home.", points=3,
                          data={"blanks": [{"mode": "text"}, {"mode": "bank"}], "bank": ["goes"]})
        name = f"question_{q.pk}"
        self.assertEqual(self.score(q, **{f"{name}_blank_0": "  paris ", f"{name}_blank_1": "went"}), Decimal("3.00"))
        self.assertEqual(self.score(q, **{f"{name}_blank_0": "Lutetia", f"{name}_blank_1": "goes"}), Decimal("1.50"))
        self.assertEqual(self.score(q), Decimal("0.00"))

    def test_ordering_scores_each_position(self):
        q = self.question(qt.ORDER, points=3, data={"items": [{"text": "1"}, {"text": "2"}, {"text": "3"}]})
        o1, o2, o3 = (i["id"] for i in q.config["items"])
        name = f"question_{q.pk}_order"
        self.assertEqual(self.score(q, **{name: [o1, o2, o3]}), Decimal("3.00"))
        self.assertEqual(self.score(q, **{name: [o1, o3, o2]}), Decimal("1.00"))
        self.assertEqual(self.score(q, **{name: [o1, "zz", o1]}), Decimal("1.00"))

    def test_matching_scores_each_pair(self):
        q = self.question(qt.MATCH, points=3, data={"pairs": [{"left": "dog", "right": "개"}, {"left": "cat", "right": "고양이"},
                                                             {"left": "cow", "right": "소"}], "distractors": ["새"]})
        ids = [p["id"] for p in q.config["pairs"]]
        name = f"question_{q.pk}_match_"
        self.assertEqual(self.score(q, **{name + ids[0]: "개", name + ids[1]: "고양이", name + ids[2]: "새"}), Decimal("2.00"))

    def test_categorization_counts_distractors_left_out(self):
        q = self.question(qt.CATEGORY, points=4, data={"categories": [{"name": "명사", "items": ["apple"]}, {"name": "동사", "items": ["run"]}],
                                                        "distractors": ["quickly", "very"]})
        noun, verb = (c["id"] for c in q.config["categories"])
        apple, run, quickly, very = (i["id"] for i in q.config["items"])
        name = f"question_{q.pk}_cat_"
        self.assertEqual(self.score(q, **{name + apple: noun, name + run: verb}), Decimal("4.00"))
        self.assertEqual(self.score(q, **{name + apple: verb, name + run: verb, name + quickly: noun}), Decimal("2.00"))

    def test_short_answer_keeps_exact_match(self):
        q = self.question(qt.SHORT, correct_text="Answer")
        self.assertEqual(self.score(q, **{f"question_{q.pk}": " answer "}), Decimal("4.00"))
        self.assertEqual(self.score(q, **{f"question_{q.pk}": "answers"}), Decimal("0.00"))


class StudentViewTests(QuizTypeFixture):
    def test_ordering_is_always_shuffled(self):
        q = self.question(qt.ORDER, data={"items": [{"text": "1"}, {"text": "2"}]})
        correct = [i["id"] for i in q.config["items"]]
        for seed in range(30):
            with self.subTest(seed=seed):
                self.assertNotEqual([i["id"] for i in qt.prepare(q, random.Random(seed))["items"]], correct)

    def test_fill_in_the_blank_splits_the_sentence(self):
        q = self.question(qt.FILL, prompt="He `went` to `school`.", data={
            "blanks": [{"mode": "dropdown", "options": ["go"]}, {"mode": "bank"}], "bank": ["home"]})
        view = qt.prepare(q, random.Random(1))
        self.assertEqual([s.get("text") for s in view["segments"]], ["He ", None, " to ", None, "."])
        self.assertEqual(sorted(view["segments"][1]["options"]), ["go", "went"])
        self.assertEqual(view["segments"][3]["mode"], "bank")
        self.assertEqual(sorted(view["bank"]), ["home", "school"])

    def test_matching_offers_every_answer_and_distractor(self):
        q = self.question(qt.MATCH, data={"pairs": [{"left": "dog", "right": "개"}, {"left": "cat", "right": "고양이"}],
                                          "distractors": ["새"]})
        view = qt.prepare(q, random.Random(2))
        self.assertEqual([p["left"] for p in view["lefts"]], ["dog", "cat"])
        self.assertEqual(sorted(view["options"]), sorted(["개", "고양이", "새"]))


class ReviewTests(QuizTypeFixture):
    def test_review_rows_compare_each_part(self):
        q = self.question(qt.FILL, prompt="He `went` to `school`.", data={"blanks": [{"mode": "text"}, {"mode": "text"}]})
        response = qt.read_response(q, post(**{f"question_{q.pk}_blank_0": "went", f"question_{q.pk}_blank_1": "home"}))
        rows = qt.review(q, response)
        self.assertEqual([(r["given"], r["expected"], r["ok"]) for r in rows], [("went", "went", True), ("home", "school", False)])
        self.assertEqual(qt.answer_text(q, response), "빈칸 1: went · 빈칸 2: home")

    def test_category_review_names_where_each_item_went(self):
        q = self.question(qt.CATEGORY, data={"categories": [{"name": "명사", "items": ["apple"]}], "distractors": ["fast"]})
        apple, fast = (i["id"] for i in q.config["items"])
        response = qt.read_response(q, post(**{f"question_{q.pk}_cat_{fast}": q.config["categories"][0]["id"]}))
        self.assertEqual([(r["label"], r["given"], r["expected"], r["ok"]) for r in qt.review(q, response)],
                         [("apple", "분류 안 함", "명사", False), ("fast", "명사", "분류 안 함", False)])
