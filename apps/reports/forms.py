from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.learning.models import LearningGroup

from .formats import COURSE_TYPES, FORM_CHOICES, FORMS, MOCK_LIMIT, season_title, title_from_exam

# 양식별로 반 이름에 들어 있으면 그 양식의 반으로 봅니다(운영팀 11/17: SAT 리포트 → SAT 반만).
FORM_KEYWORDS = {
    'SAT': (r'SAT',),
    'TOEFL': (r'TOEFL', r'토플'),
    'AP': (r'(?<![A-Z])AP(?![A-Z])',),
    'GPA_ESSAY': (r'GPA', r'ESSAY', r'에세이'),
    'JUNIOR': (r'JUNIOR', r'MIDDLE', r'주니어', r'미들'),
}


def group_forms(group) -> list[str]:
    """반 이름으로 맞는 양식 목록. 예: '26FW SAT(RW)' → ['SAT']."""
    import re
    title = (group.title or '').upper()
    return [key for key, words in FORM_KEYWORDS.items() if any(re.search(w, title) for w in words)]


def mock_label(value) -> str:
    """고르는 표의 시험 정보(dict) 또는 예전 글자 → 저장할 이름('시험 이름 · 응시일')."""
    return value.get('label') or value.get('name', '') if isinstance(value, dict) else str(value)


class MockPickForm(forms.Form):
    """SAT 모의고사(DSG) 고르기(11/20): 이번 칸·지난 칸 시험을 표에서 고릅니다(종류·응시일·응시 학생 수).
    새 리포트 화면(ReportBatchForm)과 만든 뒤 '모의고사 고르기' 화면이 같이 씁니다."""
    mock_exams = forms.MultipleChoiceField(label='SAT 모의고사 (DSG)', required=False, widget=forms.CheckboxSelectMultiple,
                                           help_text='정규는 1개, 특강은 2개까지 고릅니다. 이번 칸을 안 고르면 리포트 기간 안에 본 시험, '
                                                     '지난 칸을 안 고르면 고른 시험 바로 전에 본 시험(이번 칸도 안 골랐으면 기간 바로 앞에 본 시험)이 '
                                                     '들어갑니다. 같은 시험을 여러 번 봤으면 마지막 기록을 씁니다.')
    mock_prev = forms.MultipleChoiceField(label='비교할 지난 시험', required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, mocks=None, course_type='정규', **kwargs):
        super().__init__(*args, **kwargs)
        self.course_type = course_type
        self.mock_options = mocks or {}
        choices = [(key, mock_label(value)) for key, value in self.mock_options.items()]
        self.fields['mock_exams'].choices = choices
        self.fields['mock_prev'].choices = choices

    @property
    def mock_rows(self) -> list[dict]:
        """고르는 표의 줄: 시험마다 이름·종류·응시일·응시 학생 수와 이번/지난 칸 체크 상태."""
        this, prev = set(self['mock_exams'].value() or []), set(self['mock_prev'].value() or [])
        rows = []
        for key, value in self.mock_options.items():
            info = value if isinstance(value, dict) else {'name': str(value)}
            rows.append({'id': key, 'name': info.get('name') or key, 'kind': info.get('kind', ''), 'dates': info.get('dates', ''),
                         'count': info.get('count'), 'this': key in this, 'prev': key in prev})
        return rows

    def clean_mocks(self, data: dict, course_type: str, use: bool = True) -> None:
        """개수 제한(정규 1·특강 2)과 같은 시험 겹침을 검사하고 [(id, 이름)] 으로 바꿉니다. use=False 면 비웁니다(SAT 아님)."""
        picked, previous = data.get('mock_exams') or [], data.get('mock_prev') or []
        limit = MOCK_LIMIT.get(course_type, MOCK_LIMIT['정규'])
        if use:
            if len(picked) > limit:
                self.add_error('mock_exams', f'{course_type} 수업은 모의고사를 {limit}개까지 고를 수 있습니다.')
            if len(previous) > limit:
                self.add_error('mock_prev', f'{course_type} 수업은 비교할 지난 시험을 {limit}개까지 고를 수 있습니다.')
            if set(picked) & set(previous):
                self.add_error('mock_prev', '같은 시험을 이번 칸과 지난 칸에 함께 고를 수 없습니다.')
        named = lambda keys: [(key, mock_label(self.mock_options.get(key, key))) for key in keys] if use else []  # noqa: E731
        data['mock_exams'], data['mock_prev'] = named(picked), named(previous)

    def clean(self):
        data = super().clean()
        self.clean_mocks(data, self.course_type)
        return data


class ReportBatchForm(MockPickForm):
    # 고르는 순서(운영팀 11/17): 양식 → Term → 반 → 기간 → 정규/특강. 제목(시즌)은 따로 쓰지 않고 Term 을 씁니다.
    form = forms.ChoiceField(label='양식', choices=FORM_CHOICES, widget=forms.RadioSelect)
    term = forms.ChoiceField(label='Term', required=False)
    group = forms.ModelChoiceField(label='반', queryset=LearningGroup.objects.none(), empty_label='반을 고르세요')
    period_start = forms.DateField(label='기간 시작', widget=forms.DateInput(attrs={'type': 'date', 'data-quick-ready': 'true'}))
    period_end = forms.DateField(label='기간 끝', widget=forms.DateInput(attrs={'type': 'date', 'data-quick-ready': 'true'}))
    course = forms.ChoiceField(label='인트라넷 수업 (선택)', required=False,
                               help_text='고르면 수업일과 1주차 시작일을 그 수업에서 가져옵니다.')
    week_base = forms.DateField(label='1주차 시작일 (선택)', required=False, widget=forms.DateInput(attrs={'type': 'date', 'data-quick-ready': 'true'}),
                                help_text='비우면 수업 시작일, 수업을 안 골랐으면 기간 시작일입니다.')
    course_type = forms.ChoiceField(label='수업 유형 (SAT·TOEFL)', choices=[(t, t) for t in COURSE_TYPES], initial='정규',
                                    required=False, widget=forms.RadioSelect)

    def __init__(self, *args, groups=None, courses=None, mocks=None, **kwargs):
        super().__init__(*args, mocks=mocks, **kwargs)
        self.fields['group'].queryset = groups if groups is not None else LearningGroup.objects.none()
        terms = sorted({g.term for g in self.fields['group'].queryset if g.term}, reverse=True)
        self.fields['term'].choices = [('', 'Term을 고르세요' if terms else '반에 정한 Term이 없습니다')] + [(t, t) for t in terms]
        self.course_options = courses or {}
        self.fields['course'].choices = [('', '고르지 않음')] + [(key, c['label']) for key, c in self.course_options.items()]
        if not self.is_bound:
            today = timezone.localdate()
            self.initial.setdefault('period_start', today - timedelta(days=today.weekday()))
            self.initial.setdefault('period_end', today)

    def clean(self):
        data = forms.Form.clean(self)  # 모의고사 검사는 수업 유형을 안 뒤 아래에서(clean_mocks)
        start, end = data.get('period_start'), data.get('period_end')
        if start and end:
            if end < start:
                self.add_error('period_end', '기간 끝이 시작보다 빠릅니다.')
            elif (end - start).days > 200:
                self.add_error('period_end', '기간은 200일 이내로 골라 주세요.')
            course = self.course_options.get(data.get('course') or '')
            base = data.get('week_base') or (course and course.get('start')) or start
            if base > start:
                base = start
            data['week_base'] = base
            if (end - base).days > 7 * 52:
                self.add_error('week_base', '1주차 시작일이 너무 이릅니다.')
            group = data.get('group')
            # 제목(시즌) = 고른 Term → 반의 Term → (SAT) 고른 모의고사 시즌 → 기간으로 정한 시즌 코드. 카드에서 고칠 수 있습니다.
            data['title'] = data.get('term') or (group.term if group else '') or ''
            data['course_info'] = course or {}
        course_type = data.get('course_type') or '정규'
        data['course_type'] = course_type
        self.clean_mocks(data, course_type, use=data.get('form') == 'SAT')
        if start and end and not data.get('title'):
            exam_season = next((title_from_exam(name) for _, name in data['mock_exams'] if title_from_exam(name)), '')
            data['title'] = exam_season or season_title(start)
        return data
