"""학생 상세의 SAT 총점 추이 그래프.
11/10: 화면이 넓어지면 글자가 같이 커지던 문제(SVG 안 글자) → 선·면만 SVG가 늘어나고, 점·점수·날짜·눈금은
HTML이라 화면 폭과 상관없이 같은 크기. 점은 동그라미 그대로, 점마다 점수가 위에, 눈금은 실제 점수 범위에 맞춤."""
import re

from django.test import SimpleTestCase

from apps.assessments.contracts import ScoreChartPoint
from apps.assessments.templatetags.assessment_tags import score_trend_chart


def points(*pairs):
    return [ScoreChartPoint(x=0, y=0, score=score, exam_name='TEST', exam_date_label=label) for score, label in pairs]


def svg_part(html):
    return re.search(r'<svg.*?</svg>', html, re.S).group(0)


class ScoreTrendChartTests(SimpleTestCase):
    def test_labels_and_dots_live_outside_the_stretching_svg(self):
        html = score_trend_chart(points((1190, '03.10'), (1250, '05.08'), (1190, '06.12'), (1330, '07.20')))
        svg = svg_part(html)
        self.assertIn('preserveAspectRatio="none"', svg)
        self.assertIn('vector-effect="non-scaling-stroke"', svg)
        self.assertNotIn('<text', svg)
        self.assertNotIn('<circle', svg)
        for text in ('1190', '1250', '1330', '03.10', '07.20'):
            self.assertIn(f'>{text}<', html)
        self.assertEqual(html.count('class="sat-dot'), 4)
        self.assertIn('sat-dot is-last', html)

    def test_scale_follows_the_scores_instead_of_400_to_1600(self):
        html = score_trend_chart(points((1190, '03.10'), (1330, '07.20')))
        for tick in ('1100', '1200', '1300', '1400'):
            self.assertIn(f'>{tick}<', html)
        self.assertNotIn('>1600<', html)
        self.assertNotIn('>400<', html)

    def test_single_exam_and_no_exam(self):
        self.assertEqual(score_trend_chart([]), '')
        html = score_trend_chart(points((1000, '09.01')))
        self.assertEqual(html.count('class="sat-dot'), 1)
        self.assertNotIn('<polyline', html)

    def test_reads_as_one_image_for_screen_readers(self):
        html = score_trend_chart(points((1190, '03.10'), (1330, '07.20')))
        self.assertIn('role="img"', html)
        self.assertIn('03.10 1190점', html)
