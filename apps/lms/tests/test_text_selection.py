"""글자가 들어 있는 PDF·텍스트 답안: 단어 위치(글자 층)를 뽑아, 형광펜·취소선을 글자 드래그로 정확히 긋게 합니다."""
import json
from pathlib import Path
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.lms.documents import clean_annotations, page_words, run_worker, version_token
from apps.lms.models import ReviewDocument
from apps.lms.tests.test_lms import LmsFixture, pdf_bytes


def text_pdf_bytes(lines):
    """Helvetica 글자가 실제로 들어 있는 1쪽 PDF(612×792pt). 첫 줄은 (72, 720)에서 시작."""
    content = "BT /F1 24 Tf 72 720 Td " + " ".join(f"({line}) Tj 0 -40 Td" for line in lines) + " ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    return out + f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class WordExtractionTests(LmsFixture):
    def test_pdf_words_come_with_page_relative_boxes_and_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "text.pdf"
            source.write_bytes(text_pdf_bytes(["Hello world", "Second line"]))
            out = Path(folder) / "words.json"
            run_worker("words", source, out, page=1)
            words = json.loads(out.read_text())["words"]
        self.assertEqual([w["t"] for w in words], ["Hello", "world", "Second", "line"])
        self.assertEqual([w["line"] for w in words], [0, 0, 1, 1])
        hello = words[0]
        self.assertAlmostEqual(hello["x"], 72 / 612, delta=0.01)
        self.assertTrue(0 < hello["y"] < 0.15 and hello["w"] > 0 and hello["h"] > 0)
        self.assertTrue(all(0 <= w["x"] and w["x"] + w["w"] <= 1 and 0 <= w["y"] and w["y"] + w["h"] <= 1 for w in words))

    def test_punctuation_stays_on_its_word_and_line(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "text.pdf"
            source.write_bytes(text_pdf_bytes(["We swim. Then eat, too.", "Next line"]))
            out = Path(folder) / "words.json"
            run_worker("words", source, out, page=1)
            words = json.loads(out.read_text())["words"]
        self.assertEqual([(w["t"], w["line"]) for w in words],
                         [("We", 0), ("swim.", 0), ("Then", 0), ("eat,", 0), ("too.", 0), ("Next", 1), ("line", 1)])

    def test_image_only_pdf_has_no_words(self):
        doc = ReviewDocument(submission=self.sub, original_name="scan.pdf", source_key="text", source_token=version_token(self.sub), page_count=1)
        doc.pdf.save("scan.pdf", ContentFile(pdf_bytes()))
        self.assertEqual(page_words(doc, 1), [])

    def test_words_are_cached_per_page(self):
        doc = ReviewDocument(submission=self.sub, original_name="essay.pdf", source_key="text", source_token=version_token(self.sub), page_count=1)
        doc.pdf.save("essay.pdf", ContentFile(text_pdf_bytes(["Hello world"])))
        self.assertEqual([w["t"] for w in page_words(doc, 1)], ["Hello", "world"])
        doc.refresh_from_db()
        self.assertEqual([w["t"] for w in doc.text_layer["1"]], ["Hello", "world"])

    def test_text_answer_preview_knows_where_its_words_are(self):
        self.sub.text_answer = "I thinked about it\nSecond line here"
        self.sub.save()
        self.login()
        self.client.post(reverse("lms:prepare-submission", args=[self.sub.pk]), {"source": "text"})
        doc = ReviewDocument.objects.get(submission=self.sub)
        words = page_words(doc, 1)
        self.assertEqual([w["t"] for w in words], ["I", "thinked", "about", "it", "Second", "line", "here"])
        self.assertEqual(words[1]["line"], 0)
        self.assertEqual(words[4]["line"], 1)
        self.assertLess(words[0]["x"], words[1]["x"])

    def test_words_endpoint_respects_access(self):
        doc = ReviewDocument(submission=self.sub, original_name="essay.pdf", source_key="text", source_token=version_token(self.sub), page_count=1)
        doc.pdf.save("essay.pdf", ContentFile(text_pdf_bytes(["Hello world"])))
        url = reverse("lms:document-words", args=[doc.pk, 1])
        self.login()
        self.assertEqual([w["t"] for w in self.client.get(url).json()["words"]], ["Hello", "world"])
        self.login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login()
        self.assertEqual(self.client.get(reverse("lms:document-words", args=[doc.pk, 2])).status_code, 404)


class TextMarkValidationTests(LmsFixture):
    def test_text_highlight_keeps_line_rects_and_quote(self):
        mark = {**self.mark("highlight"), "rects": [[.1, .2, .3, .02], [.1, .23, .15, .02]], "quote": "I thinked about"}
        cleaned = clean_annotations([mark], 1)[0]
        self.assertEqual(cleaned["rects"], [[.1, .2, .3, .02], [.1, .23, .15, .02]])
        self.assertEqual(cleaned["quote"], "I thinked about")

    def test_rects_must_stay_on_the_page_and_only_on_text_tools(self):
        with self.assertRaises(ValidationError):
            clean_annotations([{**self.mark("strikeout"), "rects": [[.9, .2, .3, .02]]}], 1)
        with self.assertRaises(ValidationError):
            clean_annotations([{**self.mark("highlight"), "rects": [[.1, .1, .1, .1]] * 201}], 1)
        self.assertNotIn("rects", clean_annotations([{**self.mark("area"), "rects": [[.1, .1, .1, .1]]}], 1)[0])

    def test_old_marks_without_rects_are_unchanged(self):
        cleaned = clean_annotations([self.mark("highlight")], 1)[0]
        self.assertNotIn("rects", cleaned)
        self.assertNotIn("quote", cleaned)
