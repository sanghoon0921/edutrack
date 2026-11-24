"""쪽 번호(11/19): 모든 목록이 같은 모양 — ‹ 이전 · 1~10 · 다음 ›.

10쪽 묶음으로 보여 주고, 10쪽을 넘어가면 11~20을 보여 줍니다(인트라넷 학생 리스트와 같은 방식, 학생 목록 JS의 pageList와 같은 계산).
주소의 다른 조건(검색어·탭·거르기)은 그대로 두고 쪽 번호만 바꿉니다. 한 쪽뿐이면 아무것도 그리지 않습니다.
"""
from django import template
from django.http import QueryDict

register = template.Library()

BLOCK = 10


def page_block(number, num_pages, size=BLOCK):
    """지금 쪽이 든 묶음의 쪽 번호들. 예: 13쪽(총 25쪽) → 11~20."""
    number = max(1, int(number or 1))
    start = (number - 1) // size * size + 1
    end = min(int(num_pages or 0), start + size - 1)
    return list(range(start, end + 1))


@register.inclusion_tag('components/pager.html', takes_context=True)
def pager(context, page, param='page', label='쪽 이동', caption=''):
    request = context.get('request')
    query = request.GET.copy() if request is not None else QueryDict(mutable=True)
    query.pop(param, None)
    base = query.urlencode()

    def href(n):
        return '?' + (base + '&' if base else '') + f'{param}={n}'

    paginator = page.paginator
    return {
        'show': paginator.num_pages > 1,
        'label': label,
        'caption': caption,
        'nums': [{'n': n, 'href': href(n), 'current': n == page.number} for n in page_block(page.number, paginator.num_pages)],
        'prev': href(page.previous_page_number()) if page.has_previous() else '',
        'next': href(page.next_page_number()) if page.has_next() else '',
    }
