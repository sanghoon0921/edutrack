"""첨삭 채점 화면(Canvas SpeedGrader 방식): 색 7개·굵기 3단계, '의견 제출' 한 번에 첨삭·점수·총평 저장, 학생 이동, 파일 탭."""
import json
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from apps.assignments.models import Submission
from apps.lms.documents import clean_annotations, version_token
from apps.lms.grade_views import review_version
from apps.lms.models import ReviewDocument
from apps.lms.tests.test_lms import LmsFixture, pdf_bytes


class PaletteAndWidthTests(LmsFixture):
    def test_seven_colours_and_three_widths_are_accepted(self):
        for color in ["#dc2626", "#ea580c", "#eab308", "#16a34a", "#2563eb", "#7c3aed", "#111827"]:
            for width in (2, 4, 7):
                with self.subTest(color=color, width=width):
                    mark = {**self.mark("area"), "color": color, "width": width}
                    self.assertEqual(clean_annotations([mark], 1)[0]["width"], width)

    def test_old_marks_without_width_are_drawn_normal(self):
        mark = self.mark("strikeout")
        mark.pop("width", None)
        self.assertEqual(clean_annotations([mark], 1)[0]["width"], 4)

    def test_unknown_width_is_rejected(self):
        with self.assertRaises(ValidationError):
            clean_annotations([{**self.mark("freehand"), "width": 5}], 1)


class SubmitOpinionTests(LmsFixture):
    def opinion(self, doc=None, marks=None, revision=0, score="9", feedback="잘했어요", user=None):
        self.login(user or self.teacher)
        data = {"score": score, "feedback": feedback, "version": review_version(self.sub)}
        if doc is not None:
            data.update({"document": str(doc.pk), "document_revision": str(revision),
                         "annotations": json.dumps(marks if marks is not None else [self.mark()])})
        return self.client.post(reverse("lms:submission-review", args=[self.sub.pk]) + "?file=text", data)

    def test_one_submit_saves_marks_score_and_comment(self):
        doc = self.doc()
        response = self.opinion(doc, [self.mark("highlight"), self.mark("area")])
        self.assertRedirects(response, reverse("assignments:detail", args=[self.sub.recipient.assignment_id]), fetch_redirect_response=False)  # 11/19: 제출 현황으로
        self.sub.refresh_from_db()
        doc.refresh_from_db()
        self.assertEqual(self.sub.score, Decimal("9"))
        self.assertEqual(self.sub.feedback, "잘했어요")
        self.assertEqual([m["type"] for m in doc.annotations], ["highlight", "area"])
        self.assertEqual(doc.revision, 1)

    def test_grade_without_document_returns_to_assignment_status(self):
        response = self.post_grade("7")
        self.assertRedirects(response, reverse("assignments:detail", args=[self.sub.recipient.assignment_id]), fetch_redirect_response=False)  # 11/19

    def test_marks_saved_elsewhere_first_save_nothing(self):
        doc = self.doc()
        ReviewDocument.objects.filter(pk=doc.pk).update(revision=1, annotations=[self.mark()])
        response = self.opinion(doc, [self.mark("area")], revision=0)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "다른 사용자가 먼저 첨삭을 저장했습니다")
        self.sub.refresh_from_db()
        doc.refresh_from_db()
        self.assertIsNone(self.sub.score)
        self.assertEqual(doc.revision, 1)
        self.assertEqual(doc.annotations[0]["type"], "point")

    def test_invalid_marks_save_nothing(self):
        doc = self.doc()
        response = self.opinion(doc, [{**self.mark(), "color": "#ff00ff"}])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "첨삭 도구·좌표·색상·굵기를 확인하세요")
        self.sub.refresh_from_db()
        self.assertIsNone(self.sub.score)

    def test_document_of_another_submission_is_refused(self):
        other_sub = Submission.objects.create(recipient=self.recipient2, text_answer="B 답안", submitted_at=timezone.now())
        other = ReviewDocument(submission=other_sub, original_name="b.pdf", source_key="text",
                               source_token=version_token(other_sub), page_count=1)
        other.pdf.save("b.pdf", ContentFile(pdf_bytes()))
        response = self.opinion(other, [self.mark()])
        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(other.annotations, [])
        self.assertIsNone(self.sub.score)

    def test_marks_on_an_older_submission_are_refused(self):
        doc = self.doc()
        Submission.objects.filter(pk=self.sub.pk).update(text_answer="다시 낸 답안")
        self.sub.refresh_from_db()
        response = self.opinion(doc, [self.mark()])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "재제출")
        doc.refresh_from_db()
        self.assertEqual(doc.annotations, [])

    def test_learners_cannot_submit_an_opinion(self):
        doc = self.doc()
        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                self.assertEqual(self.opinion(doc, user=user).status_code, 404)
        doc.refresh_from_db()
        self.assertEqual(doc.annotations, [])


class GraderScreenTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.sub2 = Submission.objects.create(recipient=self.recipient2, text_answer="B 답안", submitted_at=timezone.now(),
                                              feedback="확인", feedback_at=timezone.now())

    def review(self, sub=None, user=None, query=""):
        self.login(user or self.teacher)
        return self.client.get(reverse("lms:submission-review", args=[(sub or self.sub).pk]) + query)

    def test_switcher_moves_between_submitted_students(self):
        switcher = self.review().context["switcher"]
        self.assertEqual(switcher["position"], 1)
        self.assertEqual(switcher["total"], 2)
        self.assertEqual(switcher["graded"], 1)
        self.assertIsNone(switcher["prev"])
        self.assertEqual(switcher["next"], reverse("lms:submission-review", args=[self.sub2.pk]))
        self.assertEqual([o["label"] for o in switcher["options"]], ["학생 A · 제출완료", "학생 B · 피드백완료"])
        back = self.review(self.sub2).context["switcher"]
        self.assertEqual(back["prev"], reverse("lms:submission-review", args=[self.sub.pk]))
        self.assertIsNone(back["next"])

    def test_each_submitted_file_gets_a_tab_and_opens_its_marks(self):
        doc = self.doc()
        response = self.review()
        files = response.context["files"]
        self.assertEqual([(f["source"], f["label"]) for f in files], [("text", "텍스트 답안")])
        self.assertTrue(files[0]["selected"])
        data = response.context["document_data"]
        self.assertEqual(data["documentId"], doc.pk)
        self.assertTrue(data["editable"])
        self.assertEqual(data["mode"], "review")
        self.assertContains(response, "의견 제출")
        self.assertContains(response, 'data-tool="highlight"')

    def test_file_without_preview_offers_to_open_it(self):
        response = self.review()
        self.assertIsNone(response.context["document_data"])
        self.assertContains(response, 'name="return" value="review"')

    def test_learner_sees_marks_read_only(self):
        self.doc()
        response = self.review(user=self.student)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["document_data"]["editable"])
        self.assertNotContains(response, "의견 제출")
        self.assertNotContains(response, 'data-tool="highlight"')
        self.assertNotIn("switcher", response.context)

    def test_opening_a_file_from_the_review_returns_to_it(self):
        self.login()
        response = self.client.post(reverse("lms:prepare-submission", args=[self.sub.pk]), {"source": "text", "return": "review"})
        self.assertRedirects(response, reverse("lms:submission-review", args=[self.sub.pk]) + "?file=text",
                             fetch_redirect_response=False)
        self.assertEqual(ReviewDocument.objects.filter(submission=self.sub).count(), 1)


class CommentMarginAssetTests(LmsFixture):
    """첨삭 설명은 문서 밖 오른쪽 여백에 번호와 같은 높이로 놓이고 점선으로 번호와 이어집니다(본문을 가리지 않음, 학생 화면도). 운영팀 요청 10.29."""

    def test_annotation_script_puts_comments_in_the_margin_with_links(self):
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / 'apps/lms/static/lms/js/annotation.js').read_text(encoding='utf-8')
        css = (Path(settings.BASE_DIR) / 'apps/lms/static/lms/css/workspace.css').read_text(encoding='utf-8')
        self.assertIn('function openComment(', js)
        self.assertIn('function anchorOf(', js)
        self.assertIn("'ann-margin'", js)
        self.assertIn("'ann-links'", js)
        self.assertIn('function placeMargin(', js)
        self.assertIn('openComment(mark)', js)  # 표시를 만들면 여백의 입력칸이 바로 열림
        self.assertIn('commentId=mark.id;margin.append(box)', js)  # 설명 입력칸은 문서 위가 아니라 여백에(글씨 도구만 문서에 직접)
        self.assertIn('.ann-margin .ann-bubble', css)
        self.assertIn('.ann-margin textarea.ann-inline-comment', css)
        self.assertIn('.ann-links', css)

    def test_pages_load_the_new_assets(self):
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR) / 'apps/lms/templates/lms'
        for name in ('document.html', 'review.html'):
            self.assertIn("annotation.js' %}?v=1117", (base / name).read_text(encoding='utf-8'))  # 11/17 첨삭 번호 표기
        self.assertIn("workspace.css' %}?v=20261104-rename", (base / 'base.html').read_text(encoding='utf-8'))
