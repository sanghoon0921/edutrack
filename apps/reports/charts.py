"""리포트카드 그래프(SVG). 카드에 적힌 값으로 그리므로 강사가 점수를 고치면 그래프도 따라 바뀝니다."""
from __future__ import annotations

from django.utils.html import escape
from django.utils.safestring import mark_safe

STUDENT, AVERAGE, LAST = '#1d4ed8', '#f59e0b', '#94a3b8'


def _int(value):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _frame(width, height, body, legend):
    items = ''.join(f'<span><i style="background:{color}"></i>{escape(label)}</span>' for label, color in legend)
    return mark_safe(f'<div class="rc-chart-legend">{items}</div>'
                     f'<svg viewBox="0 0 {width} {height}" role="img" class="rc-chart-svg">{body}</svg>')


def sat_trend(slots_last, slots_this, part: str, title: str):
    """지난주·이번 주 모의고사(날짜순): 학생 점수 막대 + 반 평균 막대. part='rw'|'math'."""
    points = [(s['date'], _int(s[part]), _int(s[f'{part}_avg'])) for s in [*slots_last, *slots_this] if s.get('date')]
    if not points:
        return ''
    width, height, top, bottom, left = 400, 180, 20, 26, 36
    scale = lambda v: top + (height - top - bottom) * (1 - min(max(v, 0), 800) / 800)
    body = [f'<line x1="{left}" y1="{scale(0):.0f}" x2="{width - 6}" y2="{scale(0):.0f}" class="rc-axis"/>']
    for mark in (200, 400, 600, 800):
        y = scale(mark)
        body.append(f'<line x1="{left}" y1="{y:.0f}" x2="{width - 6}" y2="{y:.0f}" class="rc-gridline"/><text x="{left - 4}" y="{y + 4:.0f}" class="rc-tick" text-anchor="end">{mark}</text>')
    slot = (width - left - 6) / len(points)
    for i, (label, mine, avg) in enumerate(points):
        x = left + slot * i + slot / 2
        for value, color, dx in ((mine, STUDENT, -24), (avg, AVERAGE, 2)):
            if value is None:
                continue
            y = scale(value)
            body.append(f'<rect x="{x + dx:.0f}" y="{y:.0f}" width="22" height="{scale(0) - y:.0f}" rx="2" fill="{color}"/>'
                        f'<text x="{x + dx + 11:.0f}" y="{y - 3:.0f}" class="rc-val" text-anchor="middle">{value}</text>')
        body.append(f'<text x="{x:.0f}" y="{height - 8}" class="rc-tick" text-anchor="middle">{escape(label)}</text>')
    return _frame(width, height, ''.join(body), [(f'{title} 학생 점수', STUDENT), ('반 평균', AVERAGE)])


def toefl_bars(this: dict, last: dict):
    """영역별 이번 주 vs 지난주 막대."""
    parts = (('r', 'Reading'), ('l', 'Listening'), ('s', 'Speaking'), ('w', 'Writing'))
    values = [(label, _int(this.get(key)), _int(last.get(key))) for key, label in parts]
    if all(a is None and b is None for _, a, b in values):
        return ''
    width, height, top, bottom = 400, 180, 20, 26
    scale = lambda v: top + (height - top - bottom) * (1 - min(max(v, 0), 30) / 30)
    body = [f'<line x1="8" y1="{scale(0):.0f}" x2="{width - 8}" y2="{scale(0):.0f}" class="rc-axis"/>']
    slot = (width - 16) / 4
    for i, (label, now, before) in enumerate(values):
        x = 8 + slot * i + slot / 2
        for value, color, dx in ((before, LAST, -24), (now, STUDENT, 2)):
            if value is None:
                continue
            y = scale(value)
            body.append(f'<rect x="{x + dx:.0f}" y="{y:.0f}" width="22" height="{scale(0) - y:.0f}" rx="2" fill="{color}"/>'
                        f'<text x="{x + dx + 11:.0f}" y="{y - 3:.0f}" class="rc-val" text-anchor="middle">{value}</text>')
        body.append(f'<text x="{x:.0f}" y="{height - 8}" class="rc-tick" text-anchor="middle">{label}</text>')
    return _frame(width, height, ''.join(body), [('지난주', LAST), ('이번 주', STUDENT)])
