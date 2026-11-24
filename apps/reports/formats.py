"""리포트카드 양식 5가지(data/report-examples/ 예시 PDF 기준)와 빈 칸 모양.

kind: term(AP·GPA ESSAY) / junior(주니어미들) / weekly(SAT·TOEFL 주간)
카드 값(data)과 반 공통 글(shared)은 여기서 정한 모양 그대로 저장되고, 화면에서 고칠 수 있는 칸도 이 모양 안의 칸뿐입니다.
"""
from __future__ import annotations

import re
from datetime import date

NOTICE = '해당 리포트는 학생에 대한 정량적인 평가를 다루고 있습니다.\n디테일한 상담을 희망하실 경우 언제든 문의 바랍니다.'
CLOSING = '앞으로도 {이름} 학생이 꾸준히 성장할 수 있도록 세심하게 지도하겠습니다.\n가정에서도 많은 관심과 격려 부탁드립니다.\n감사합니다.'

SAT_BLOCKS = (
    ('laser', 'Laser Focus', '과학·사회과학 지문의 핵심 구조를 마인드맵으로 정리하며 지문 분석 능력을 기르는 과제'),
    ('poetry', 'Poetry', '시를 문장 단위로 분석하며 주어–동사–목적어를 파악하고 주제와 상징을 해석하는 과제'),
    ('guided', 'Guided Reading', '고난도 비문학 텍스트를 바탕으로 저자의 주장과 논리 전개를 분석하는 독서 과제'),
    ('correction', 'Correction Note', '모의고사 및 수업 중 틀린 문제를 분석하며 사고 과정을 점검하는 오답노트 과제'),
    ('reflection', 'Mocktest Reflection', '매 모의고사 이후 약점 유형을 스스로 돌아보고 다음 학습 방향을 정하는 과제'),
)
TOEFL_BLOCKS = (
    ('writing', 'Writing Assignment', '다양한 주제에 대해 생각을 글로 표현하고, 첨삭과 오답노트로 부족한 부분을 보완하는 과제'),
    ('reading', 'Reading Assignments', '매일 지문을 풀고 틀린 문제의 근거를 다시 찾으며 독해 사고 과정을 점검하는 과제'),
    ('listening', 'Listening Assignments', '문제 풀이, 채점, 스크립트 분석과 녹음으로 Listening 정확도를 높이는 과제'),
    ('speaking', 'Speaking Assignments', 'BEFORE & AFTER 녹음과 BEST 녹음으로 답변 구조, 발음, 전달력을 높이는 과제'),
)

# 주간 카드의 표(반 공통으로 이름을 고치고, 빼거나 다시 넣을 수 있음 — 운영팀 10/29)
# 11/17 새 디자인: 표 이름은 영문 대문자(HOMEWORK STATUS …). 예전 묶음은 저장된 이름을 그대로 씁니다.
SECTION_TITLES = {'skill': 'Skill Mastery', 'task': 'Homework Status', 'attitude': 'Class Attitude', 'vocab': 'Vocabulary Test',
                  'mock': 'Mock Test Scores', 'mock_comment': 'Mock Test Comments'}
VOCAB_HEADS = ['날짜', '단어시험 이행 현황', '재시험', '완료 구분']
OLD_VOCAB_HEADS = ['요일', '점수', '재시험', '만점']  # 11/17 전 기본값(그대로면 새 이름으로 바꿔 보여 줍니다)


def weekly_sections(form: str) -> dict:
    return {k: v for k, v in SECTION_TITLES.items() if k != 'mock_comment' or FORMS[form].get('mock') == 'toefl'}


FORMS = {
    'SAT': {'label': 'SAT 주간 리포트', 'kind': 'weekly', 'heading': 'SAT Weekly Report', 'subject': 'SAT',
            'roles': ('Reading', 'Writing'), 'blocks': SAT_BLOCKS, 'mock': 'sat',
            'intro': '{반} {이름} 학생을 담당하고 있는 {강사}입니다.\n{이름} 학생이 Skill Mastery 시간에 진행하고 있는 과제들을 바탕으로, 이번 주 과제별 학습 내용과 코멘트를 정리하여 전달드립니다.'},
    'TOEFL': {'label': 'TOEFL 주간 리포트', 'kind': 'weekly', 'heading': 'TOEFL Weekly Report Card', 'subject': 'TOEFL',
              'roles': ('R/W', 'L/S'), 'blocks': TOEFL_BLOCKS, 'mock': 'toefl',
              'intro': '안녕하세요! {반} {이름} 학생을 담당하고 있는 {강사}입니다.\n{이름} 학생이 Skill Mastery 시간에 수행하고 있는 과제 내용을 바탕으로 영역별 학습 코멘트를 정리하여 전달드립니다.'},
    'AP': {'label': 'AP 리포트카드', 'kind': 'term', 'heading': 'AP REPORT CARD', 'last': ('scores', '점수')},
    'GPA_ESSAY': {'label': 'GPA ESSAY 리포트카드', 'kind': 'term', 'heading': 'GPA ESSAY REPORT CARD', 'last': ('review', '첨삭 확인')},
    'JUNIOR': {'label': 'Junior & Middle 리포트카드', 'kind': 'junior', 'heading': 'Junior & Middle Report Card'},
}
FORM_CHOICES = [(key, spec['label']) for key, spec in FORMS.items()]
# 주간(SAT·TOEFL) 수업 유형. SAT 모의고사는 정규 1개·특강 2개를 고릅니다(운영팀 10/29).
COURSE_TYPES = ('정규', '특강')
MOCK_LIMIT = {'정규': 1, '특강': 2}
TERM_WEEKS = 16
# 과제 제출 여부 칸에서 고르는 값(운영팀 요청 10/29). 자동 값 '해당없음'도 고를 수 있게 둡니다.
SUBMIT_CHOICES = ('제출완료', '미제출', '일부제출', '수업미지정일', '환불', '이월', '해당없음')
REVIEW_TEXT = '모든 에세이 첨삭은 EduTrack 과제 화면에서 확인할 수 있습니다. 매주 제출한 에세이는 모두 피드백되었습니다.'


def season_title(day: date) -> str:
    """회사 시즌 코드(11/10): 3~5월 26SP, 6~8월 26SM, 9~11월 26FW, 12~2월 2627WT(겨울은 두 해에 걸침)."""
    yy = day.year % 100
    if 3 <= day.month <= 5:
        return f'{yy:02d}SP'
    if 6 <= day.month <= 8:
        return f'{yy:02d}SM'
    if 9 <= day.month <= 11:
        return f'{yy:02d}FW'
    start = yy if day.month == 12 else (yy - 1) % 100
    return f'{start:02d}{(start + 1) % 100:02d}WT'


SEASON_NAMES = {'SP': 'SPRING', 'SM': 'SUMMER', 'FW': 'FALL / WINTER', 'WT': 'WINTER'}
INTRANET_SEASONS = {'봄': SEASON_NAMES['SP'], '여름': SEASON_NAMES['SM'], '가을': SEASON_NAMES['FW'], '겨울': SEASON_NAMES['WT']}


def season_heading(code: str) -> str:
    """시즌 코드를 리포트 머리 제목으로(11/17 새 디자인): 26FW → '2026 FALL / WINTER', 2627WT → '2026–2027 WINTER'.
    코드 모양이 아니면 받은 글자를 그대로 돌려줍니다."""
    found = re.fullmatch(r'(\d{2})(\d{2})?(SP|SM|FW|WT)', (code or '').strip().upper())
    if not found:
        # 11/20: 반 Term 을 인트라넷 이름(예: '2026 가을 정규', '2026 여름특강')으로 고르면 계절 낱말로 맞춥니다.
        named = re.match(r'\s*(\d{4})\s*(봄|여름|가을|겨울)', code or '')
        if named:
            return f'{named.group(1)} {INTRANET_SEASONS[named.group(2)]}'
        return (code or '').strip()
    first, second, season = found.groups()
    years = f'20{first}' + (f'–20{second}' if second else '')
    return f'{years} {SEASON_NAMES[season]}'


_EXAM_SEASON = re.compile(r'(\d{2}(?:\d{2})?[A-Z]{2,3}\d?)-')


def title_from_exam(name: str) -> str:
    """DSG 모의고사 이름의 시즌 부분: '26FW-TEST02 · 11-05' → '26FW'. 없으면 ''."""
    found = _EXAM_SEASON.search(name or '')
    return found.group(1) if found else ''


def period_label(start: date, end: date) -> str:
    return f'{start.month}/{start.day} ~ {end.month}/{end.day}'


def default_shared(form: str, *, class_name: str, teacher: str, week_labels: list[str]) -> dict:
    spec = FORMS[form]
    shared = {'class_name': class_name, 'teacher': teacher}
    if spec['kind'] == 'term':
        shared['content'] = ''
    elif spec['kind'] == 'junior':
        shared.update({'focus': '', 'next_plan': '', 'contents': {label: '' for label in week_labels}})
    else:
        shared.update({
            'notice': NOTICE, 'intro': spec['intro'], 'closing': CLOSING,
            'teachers': [{'role': role, 'name': teacher if i == 0 else ''} for i, role in enumerate(spec['roles'])],
            # 과제별 코멘트 칸 목록(반 공통): 편집 화면에서 더하고·지우고·이름을 바꿉니다. 학생 코멘트는 data['blocks'][key].
            'block_list': [{'key': key, 'title': title, 'desc': desc} for key, title, desc in spec['blocks']],
            'hidden': [], 'titles': weekly_sections(form), 'vocab_heads': list(VOCAB_HEADS),
        })
    return shared


def empty_data(form: str, *, week_labels: list[str]) -> dict:
    """학생 카드의 빈 모양. 자동 값은 services.auto_values 가 같은 모양으로 덮어씁니다."""
    spec = FORMS[form]
    if spec['kind'] == 'term':
        data = {'info': {'name': '', 'region': '', 'grade': ''},
                'weeks': [{'label': f'WEEK{n}', 'status': ''} for n in range(1, TERM_WEEKS + 1)], 'comment': ''}
        key = spec['last'][0]
        data[key] = REVIEW_TEXT if key == 'review' else ''
        return data
    if spec['kind'] == 'junior':
        row = {'date': '', 'homework': '', 'submitted': '', 'attitude': '', 'vocab': '', 'comment': ''}
        return {'info': {'name': '', 'region': '', 'grade': ''}, 'rows': [{'label': label, **row} for label in week_labels],
                'drive': '', 'achievement': '', 'overall': ''}
    five = range(5)
    data = {'info': {'name': '', 'country': '', 'school': ''},
            'skill': ['' for _ in five], 'task': ['' for _ in five],
            'attitude': [{'a': '', 'b': ''} for _ in five],
            'vocab': [{'score': '', 'retest': '', 'max': ''} for _ in five],
            'blocks': {key: '' for key, _, _ in spec['blocks']}, 'personal': ''}
    if spec['mock'] == 'sat':
        slot = {'date': '', 'rw': '', 'rw_avg': '', 'math': '', 'math_avg': ''}
        data['mock'] = {'this': [dict(slot) for _ in range(3)], 'last': [dict(slot) for _ in range(3)]}
    else:
        part = {'r': '', 'l': '', 's': '', 'w': '', 'total': ''}
        data['mock'] = {'this': dict(part), 'last': dict(part)}
        data['mock_comment'] = {'rw': '', 'ls': ''}
    return data
