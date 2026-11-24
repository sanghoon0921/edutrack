"""카드 칸 하나를 그립니다: 편집 화면이면 입력칸, 인쇄 화면이면 글자.

{% cell "d" "weeks" forloop.counter0 "status" %}  → 학생 카드 값(data)의 weeks.N.status
{% cell "s" "content" area=1 %}                   → 반 공통 글(shared)의 content, 여러 줄 입력칸
{% cell "d" "weeks" i "status" choices=submit_choices %} → 고르는 칸(목록에 없는 지금 값도 그대로 보여 줌)
보기·인쇄 화면에서는 글 속 주소(https://…)가 새 창으로 열리는 링크가 됩니다.
"""
from django import template
from django.template.defaultfilters import linebreaksbr
from django.utils.html import format_html, format_html_join, urlize
from django.utils.safestring import mark_safe

from apps.reports.services import get_path, personalize, scope_allows

register = template.Library()


def _links(value: str):
    """주소를 새 창 링크로. urlize 가 나머지 글을 이스케이프합니다."""
    html = urlize(value, nofollow=True, autoescape=True)
    return mark_safe(html.replace(' rel="nofollow"', ' target="_blank" rel="nofollow noopener"'))


def _select(name, value, choices, cls):
    options = [''] + [c for c in choices]
    if value and value not in options:
        options.insert(1, value)
    items = ((o, mark_safe(' selected') if o == value else '', o or '—') for o in options)
    return format_html('<select name="{}" class="rc-input rc-select {}">{}</select>', name, cls,
                       format_html_join('', '<option value="{}"{}>{}</option>', items))


@register.filter
def item(mapping, key):
    """{{ shared.titles|item:"vocab" }}, 목록이면 번호로 {{ card_data.vocab|item:0 }}"""
    if isinstance(mapping, (list, tuple)):
        return mapping[key] if isinstance(key, int) and 0 <= key < len(mapping) else ''
    return (mapping or {}).get(key, '') if hasattr(mapping, 'get') else ''


def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


@register.filter
def vocab_status(cell):
    """단어 시험 완료 구분(11/17 새 디자인): 만점과 같으면 PASS, 0점·미응시는 FAIL, 그 사이는 PARTIAL. 비어 있으면 빈칸."""
    if not hasattr(cell, 'get'):
        return ''
    score, top = str(cell.get('score', '')).strip(), _num(cell.get('max'))
    if not score:
        return ''
    if score == '미응시':
        return 'FAIL'
    got = _num(score)
    if got is None or not top:
        return ''
    if got >= top:
        return 'PASS'
    return 'FAIL' if got <= 0 else 'PARTIAL'


@register.simple_tag(takes_context=True)
def cell(context, root, *parts, area=False, rows=3, placeholder='', cls='', personal=False, choices=None):
    path = '.'.join(str(p) for p in parts)
    source = context['card_data'] if root == 'd' else context['shared']
    value = get_path(source, path)
    value = '' if value is None else str(value)
    name = f'{root}.{path}'
    shared = ' is-shared' if root == 's' else ''
    scope = context.get('edit_scope')
    editable = context.get('editing') and scope_allows(name, scope)
    if editable and root == 'd' and path in context.get('auto_locked', ()):
        # 자동으로 채운 칸(11/20): 입력칸 대신 색 표시 글자. 바꾸려면 원본(인트라넷·DSG·EduTrack)을 고친 뒤 다시 불러오기.
        return format_html('<span class="rc-text rc-auto {}" data-v="{}" title="자동으로 채운 칸입니다. 원본이 바뀌면 데이터 다시 불러오기로 맞춥니다.">{}</span>',
                           cls, value if len(value) < 12 else '', value)
    if editable:
        if choices:
            return _select(name, value, choices, cls)
        if area:
            return format_html('<textarea name="{}" class="rc-input rc-area{} {}" rows="{}" placeholder="{}" data-autogrow>{}</textarea>',
                               name, shared, cls, rows, placeholder, value)
        return format_html('<input name="{}" value="{}" class="rc-input{} {}" placeholder="{}" autocomplete="off">', name, value, shared, cls, placeholder)
    if personal:
        value = personalize(value, context['card'], context['batch'])
    return format_html('<span class="rc-text {}" data-v="{}">{}</span>', cls, value if len(value) < 12 else '', linebreaksbr(_links(value)))
