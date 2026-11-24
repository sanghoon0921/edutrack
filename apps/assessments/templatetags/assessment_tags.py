from __future__ import annotations

from django import template
from django.db.utils import DatabaseError
from django.test.testcases import (
    DatabaseOperationForbidden,
)

from apps.assessments.contracts import (
    StudentExamOverview,
)
from apps.assessments.services import (
    AssessmentService,
)


register = template.Library()


@register.inclusion_tag(
    "assessments/student_score_overview.html"
)
def student_score_overview(
    student_id: str,
) -> dict:
    """
    학생 상세의 DSG 성적 블록을 독립적으로 렌더링합니다.

    DSG 장애가 학생 기본정보·수업·출결 화면 전체를
    막지 않도록 성적 영역에서 오류를 격리합니다.
    """

    try:
        overview = (
            AssessmentService()
            .get_student_overview(
                str(student_id)
            )
        )

    except (
        DatabaseError,
        DatabaseOperationForbidden,
    ):
        overview = StudentExamOverview(
            status="error",
            message=(
                "DSG 성적 데이터를 불러오지 못했습니다. "
                "잠시 후 다시 확인해 주세요."
            ),
        )

    return {
        "score_overview": overview,
        "student_id": str(student_id),
    }


@register.simple_tag
def score_trend_chart(points) -> str:
    """전체 SAT 총점 추이. 선·면은 늘어나는 SVG(선 굵기는 그대로), 점·점수·날짜·눈금은 HTML이라
    화면 폭이 달라도 글자 크기가 같습니다(11/10). 세로 눈금은 실제 점수 범위(앞뒤 여유 포함)에 맞춥니다."""
    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    if not points:
        return ''
    scores = [p.score for p in points]
    low = max(400, (min(scores) - 40) // 100 * 100)
    high = min(1600, -(-(max(scores) + 40) // 100) * 100)
    if high - low < 200:
        high = min(1600, low + 200)
        low = max(400, high - 200)
    step = 100 if high - low <= 600 else 200

    def top(score):  # 0(위)~100(아래) %
        return 100 * (1 - (min(max(score, low), high) - low) / (high - low))

    count = len(points)
    xs = [50.0] if count == 1 else [4 + 92 * i / (count - 1) for i in range(count)]
    ticks = list(range(int(low), int(high) + 1, step))
    grid = ''.join(f'<line x1="0" y1="{top(t):.2f}" x2="100" y2="{top(t):.2f}" vector-effect="non-scaling-stroke"/>' for t in ticks)
    coords = [(x, top(p.score)) for x, p in zip(xs, points)]
    shape = ''
    if count > 1:
        line = ' '.join(f'{x:.2f},{y:.2f}' for x, y in coords)
        shape = (f'<polygon class="sat-area" points="{coords[0][0]:.2f},100 {line} {coords[-1][0]:.2f},100"/>'
                 f'<polyline class="sat-line" points="{line}" vector-effect="non-scaling-stroke"/>')
    svg = (f'<svg class="sat-plot-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
           f'<g class="sat-grid">{grid}</g>{shape}</svg>')
    marks = []
    for i, ((x, y), p) in enumerate(zip(coords, points)):
        last = ' is-last' if i == count - 1 else ''
        tip = escape(f'{p.exam_date_label} · {p.exam_name} · {p.score}점')
        marks.append(f'<span class="sat-dot{last}" style="left:{x:.2f}%;top:{y:.2f}%" title="{tip}"></span>'
                     f'<span class="sat-value{last}" style="left:{x:.2f}%;top:{y:.2f}%">{p.score}</span>')
    yaxis = ''.join(f'<span style="top:{top(t):.2f}%">{t}</span>' for t in ticks)
    xaxis = ''.join(f'<span style="left:{x:.2f}%">{escape(p.exam_date_label)}</span>' for x, p in zip(xs, points))
    label = '전체 SAT 점수 추이: ' + ', '.join(f'{p.exam_date_label} {p.score}점' for p in points)
    return mark_safe(f'<div class="sat-chart" role="img" aria-label="{escape(label)}">'
                     f'<div class="sat-y" aria-hidden="true">{yaxis}</div>'
                     f'<div class="sat-plot">{svg}<div class="sat-marks" aria-hidden="true">{"".join(marks)}</div></div>'
                     f'<div class="sat-x" aria-hidden="true">{xaxis}</div></div>')
