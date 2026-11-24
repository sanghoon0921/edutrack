from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase

from apps.assessments.contracts import ExamAttemptSummary
from apps.reports.sources import (
    Task, class_averages, day_marks, day_quiz, dsg_slots, lesson_weeks, score_lines, week_no, week_status, weeks_label,
)


def task(kind, title, due, submitted, score=None, points=None):
    return Task(kind=kind, title=title, due=due, submitted=submitted,
                score=None if score is None else Decimal(score), points=None if points is None else Decimal(points))


def attempt(exam_id, when, rw, math):
    return ExamAttemptSummary(
        attempt_id=f'a{exam_id}{when}', exam_id=exam_id, exam_name=f'TEST {exam_id}', exam_date=when,
        rw_sat_score=rw, math_sat_score=math, total_sat_score=(rw or 0) + (math or 0),
        total_questions=98, correct_answers=60, wrong_answers=38, accuracy_rate=None,
        rw_attempted=rw is not None, math_attempted=math is not None,
        score_type='FULL', score_type_label='Full', display_score=None, max_score=1600)


BASE = date(2026, 8, 23)  # 1주차 첫날(일)


class WeekTests(SimpleTestCase):
    def test_week_number_counts_seven_day_blocks_from_base(self):
        self.assertEqual(week_no(BASE, BASE), 1)
        self.assertEqual(week_no(date(2026, 8, 29), BASE), 1)
        self.assertEqual(week_no(date(2026, 8, 30), BASE), 2)
        self.assertEqual(week_no(date(2026, 9, 13), BASE), 4)

    def test_weeks_label_covers_period(self):
        self.assertEqual(weeks_label(BASE, date(2026, 9, 13), date(2026, 10, 11)), 'WEEK4-8')
        self.assertEqual(weeks_label(BASE, date(2026, 9, 13), date(2026, 9, 18)), 'WEEK4')


class WeekStatusTests(SimpleTestCase):
    def test_grid_shows_history_until_period_end_and_blank_after(self):
        tasks = [
            task('HW', 'W1 숙제', date(2026, 8, 25), True),
            task('HW', 'W2 숙제', date(2026, 9, 1), False),
            task('HW', 'W3 숙제 a', date(2026, 9, 7), True),
            task('QUIZ', 'W3 단어', date(2026, 9, 9), False),
        ]
        grid = week_status(tasks, BASE, date(2026, 8, 30), date(2026, 9, 19), total=6)
        self.assertEqual([w['label'] for w in grid], ['WEEK1', 'WEEK2', 'WEEK3', 'WEEK4', 'WEEK5', 'WEEK6'])
        self.assertEqual([w['status'] for w in grid], ['제출완료', '미제출', '일부제출', '해당없음', '', ''])


class OpenTaskTests(SimpleTestCase):
    """마감 전이라 아직 안 낸 과제는 '미제출'로 치지 않습니다."""

    def test_open_tasks_are_not_counted_as_missing(self):
        open_hw = Task(kind='HW', title='이번 주 숙제', due=date(2026, 9, 16), submitted=False, score=None, points=Decimal('10'), open=True)
        done = task('HW', '낸 숙제', date(2026, 9, 14), True, '9', '10')
        grid = week_status([open_hw], BASE, date(2026, 9, 13), date(2026, 9, 19), total=4)
        self.assertEqual(grid[3]['status'], '진행중')
        grid = week_status([open_hw, done], BASE, date(2026, 9, 13), date(2026, 9, 19), total=4)
        self.assertEqual(grid[3]['status'], '제출완료')
        self.assertEqual(score_lines([open_hw], BASE, date(2026, 9, 13), date(2026, 9, 19)), 'W4 이번 주 숙제 마감 전')
        self.assertEqual(day_marks([open_hw], date(2026, 9, 14)), ['', '', '', '', ''])


class ScoreLineTests(SimpleTestCase):
    def test_lists_period_tasks_with_week_and_score(self):
        tasks = [
            task('HW', '옛 과제', date(2026, 8, 25), True, '9', '10'),
            task('HW', 'Unit 1 HW', date(2026, 9, 15), True, '13', '15'),
            task('QUIZ', 'Mid-Term', date(2026, 10, 9), True, '117.50', '120'),
            task('HW', 'Unit 2 HW', date(2026, 9, 22), False, None, '15'),
            task('HW', '채점 전 과제', date(2026, 9, 29), True, None, '30'),
        ]
        lines = score_lines(tasks, BASE, date(2026, 9, 13), date(2026, 10, 11)).splitlines()
        self.assertEqual(lines, ['W4 Unit 1 HW 13/15', 'W5 Unit 2 HW 미제출', 'W6 채점 전 과제 채점 전', 'W7 Mid-Term 117.5/120'])


class DayTests(SimpleTestCase):
    MONDAY = date(2026, 7, 13)

    def test_day_marks_pass_fail_or_blank(self):
        tasks = [
            task('HW', 'a', date(2026, 7, 13), True),
            task('HW', 'b', date(2026, 7, 14), True), task('HW', 'c', date(2026, 7, 14), False),
            task('QUIZ', 'q', date(2026, 7, 15), True, '20', '20'),
            task('HW', 'd', date(2026, 7, 17), True),
        ]
        self.assertEqual(day_marks(tasks, self.MONDAY), ['PASS', 'FAIL', '', '', 'PASS'])

    def test_day_quiz_scores(self):
        tasks = [
            task('QUIZ', 'Vocab Mon', date(2026, 7, 13), True, '28', '30'),
            task('QUIZ', 'Vocab Wed', date(2026, 7, 15), False, None, '30'),
            task('HW', 'not a quiz', date(2026, 7, 14), True, '5', '5'),
        ]
        self.assertEqual(day_quiz(tasks, self.MONDAY), [
            {'score': '28', 'retest': '', 'max': '30'}, {'score': '', 'retest': '', 'max': ''},
            {'score': '미응시', 'retest': '', 'max': '30'}, {'score': '', 'retest': '', 'max': ''},
            {'score': '', 'retest': '', 'max': ''}])


class LessonWeekTests(SimpleTestCase):
    def test_first_lesson_date_per_week(self):
        dates = [date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 23), date(2026, 8, 24)]
        self.assertEqual(lesson_weeks(dates, BASE), {1: date(2026, 8, 24), 4: date(2026, 9, 14), 5: date(2026, 9, 21)})


class DsgTests(SimpleTestCase):
    def test_this_week_and_last_week_slots_with_class_average(self):
        mine = [
            attempt('1', datetime(2026, 7, 7, 10), 500, 560),
            attempt('2', datetime(2026, 7, 9, 10), 530, 550),
            attempt('3', datetime(2026, 7, 14, 10), 540, 630),
            attempt('4', datetime(2026, 7, 16, 10), 620, 670),
            attempt('0', datetime(2026, 6, 1, 10), 400, 400),
        ]
        other = [attempt('3', datetime(2026, 7, 14, 11), 600, 650), attempt('4', datetime(2026, 7, 16, 11), 560, None)]
        averages = class_averages([mine, other])
        self.assertEqual(averages['3'], {'rw': 570, 'math': 640})
        self.assertEqual(averages['4'], {'rw': 590, 'math': 670})
        slots = dsg_slots(mine, date(2026, 7, 13), date(2026, 7, 17), averages)
        self.assertEqual(slots['this'][0], {'date': '07-14', 'rw': '540', 'rw_avg': '570', 'math': '630', 'math_avg': '640'})
        self.assertEqual(slots['this'][1]['date'], '07-16')
        self.assertEqual(slots['this'][2], {'date': '', 'rw': '', 'rw_avg': '', 'math': '', 'math_avg': ''})
        self.assertEqual([s['date'] for s in slots['last']], ['07-07', '07-09', ''])
        self.assertEqual(slots['last'][0]['rw_avg'], '500')  # 반에서 혼자 본 시험은 본인 점수가 평균
