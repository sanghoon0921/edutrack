"""자동 칸 잠금(11/20 사용자: '수정할 수 있게 말고 알아서 채워졌으면, 색깔 표시해서').

SAT·TOEFL 카드에서 인트라넷·DSG·EduTrack 에서 자동으로 채운 칸(학생 정보, Skill Mastery, 과제 PASS/FAIL,
단어 시험 점수·만점, SAT 모의고사)은 편집 화면에서도 입력칸이 아니라 색 표시 글자로 보이고, 저장으로 바뀌지 않습니다.
자동 값이 비어 있는 칸(그날 과제 없음, 수업을 안 고른 Skill Mastery 등)과 수업 태도·코멘트는 그대로 입력합니다.
다시 불러오기는 잠긴 칸을 항상 새 자동 값으로 맞춥니다.
"""
from datetime import timedelta

from django.urls import reverse

from apps.reports.models import ReportBatch
from apps.students.attendance_repositories import DemoAttendanceRepository

from .test_views import ReportFixture


class AutoLockTests(ReportFixture):
    def setUp(self):
        super().setUp()
        records = DemoAttendanceRepository().list_by_student_and_assign('6333', '10001')
        day = min(r.lesson_date for r in records if r.lesson_date)
        monday = day - timedelta(days=day.weekday())
        self.create(form='SAT', course='201', period_start=monday.isoformat(), period_end=(monday + timedelta(4)).isoformat(),
                    week_base=monday.isoformat())
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])
        self.filled = [i for i, v in enumerate(self.card.auto['skill']) if v]

    def test_auto_cells_are_shown_not_typed(self):
        self.assertTrue(self.filled)
        html = self.client.get(self.url).content.decode()
        for i in self.filled:
            self.assertNotIn(f'name="d.skill.{i}"', html)
        self.assertNotIn('name="d.info.country"', html)
        self.assertIn('rc-auto', html)
        self.assertIn('name="d.attitude.0.a"', html)  # 수업 태도는 강사가 입력
        self.assertIn('name="d.personal"', html)

    def test_saving_cannot_change_auto_cells(self):
        i = self.filled[0]
        before = self.card.data['skill'][i]
        self.client.post(self.url, {'save': '1', f'd.skill.{i}': '바꿈', 'd.info.country': '바꿈', 'd.personal': '코멘트'})
        self.card.refresh_from_db()
        self.assertEqual(self.card.data['skill'][i], before)
        self.assertNotEqual(self.card.data['info']['country'], '바꿈')
        self.assertEqual(self.card.data['personal'], '코멘트')

    def test_refresh_brings_locked_cells_back_to_the_auto_value(self):
        i = self.filled[0]
        self.card.data['skill'][i] = '예전에 손으로 고친 값'
        self.card.save()
        self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk})
        self.card.refresh_from_db()
        self.assertEqual(self.card.data['skill'][i], self.card.auto['skill'][i])

    def test_blank_auto_cells_stay_typeable(self):
        blank = [i for i, v in enumerate(self.card.auto['task']) if not v]
        self.assertTrue(blank)
        html = self.client.get(self.url).content.decode()
        self.assertIn(f'name="d.task.{blank[0]}"', html)

    def test_without_a_course_skill_mastery_is_typed(self):
        self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20')
        batch = ReportBatch.objects.exclude(pk=self.batch.pk).get()
        card = batch.cards.get(student_no='6333')
        html = self.client.get(reverse('reports:card', args=[batch.pk, card.pk])).content.decode()
        self.assertIn('name="d.skill.0"', html)

    def test_edit_page_explains_the_colored_cells(self):
        self.assertContains(self.client.get(self.url), '자동으로 채운 칸')
