"""공용 학생 목록 부품(student-browser.js)을 Node.js로 실제 실행해 동작을 확인한다.

브라우저 대신 tests/js/student_browser_harness.js 의 가짜 화면·시계·네트워크를 쓴다.
Node.js가 없는 컴퓨터에서는 이 테스트들을 건너뛴다.
"""
import json
import shutil
import subprocess
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase

NODE = shutil.which("node")
HARNESS = Path(__file__).resolve().parent / "js" / "student_browser_harness.js"
SCRIPT = Path(settings.BASE_DIR) / "static" / "js" / "global" / "student-browser.js"


@skipUnless(NODE, "Node.js가 없어 건너뜀")
class LiveInputScriptTests(SimpleTestCase):
    """즉시 검색: 한글 입력기가 마지막 글자를 조합 중으로 남겨 두어도 멈추면 조회한다."""

    def run_case(self, name):
        done = subprocess.run([NODE, str(HARNESS), str(SCRIPT), name], capture_output=True,
                              text=True, encoding="utf-8", timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_paused_korean_name_queries_once(self):
        self.assertEqual(self.run_case("korean-name-pause"), ["김지훈"])

    def test_unfinished_letter_waits_then_finished_letter_queries(self):
        self.assertEqual(self.run_case("unfinished-letter-waits"), {"afterJamo": [], "runs": ["김"]})

    def test_commit_after_pause_does_not_query_again(self):
        # 조회 뒤 결과 줄을 누르면 조합이 끝나는데, 같은 값으로 다시 조회해 체크한 줄을 다시 그리면 안 된다
        self.assertEqual(self.run_case("commit-after-pause-no-repeat"), ["김지훈"])

    def test_enter_queries_at_once_and_only_once(self):
        self.assertEqual(self.run_case("enter-runs-at-once"), {"atEnter": ["7102"], "runs": ["7102"]})


@skipUnless(NODE, "Node.js가 없어 건너뜀")
class ConnectionFailureScriptTests(SimpleTestCase):
    """연결 실패: '학생 없음'과 구분되는 안내와 다시 시도를 목록 자리에 보여 준다."""

    run_case = LiveInputScriptTests.run_case

    def test_failed_lookup_hands_notice_and_retry_that_also_reloads_options(self):
        result = self.run_case("failure-then-retry")
        self.assertTrue(result["error"])
        self.assertIn("연결", result["message"])
        self.assertNotIn("Failed to fetch", result["message"])
        self.assertEqual(result["retry"], "function")
        self.assertTrue(result["barRetryShown"])  # 수업·반 목록도 못 불러왔으므로 거르기 막대의 다시 시도도 보인다
        self.assertEqual(result["afterRows"], 1)
        self.assertFalse(result["afterError"])
        self.assertIn("class:7", result["options"])
        self.assertFalse(result["barRetryShownAfter"])
        self.assertNotIn("불러오지 못했습니다", result["statusAfter"])  # 회복한 뒤 실패 문구가 남지 않는다

    def test_options_lookup_stops_after_20_seconds_and_offers_retry(self):
        result = self.run_case("options-timeout")
        self.assertFalse(result["shownBefore"])
        self.assertTrue(result["shownAfter"])
        self.assertIn("수업·반 목록", result["status"])

    def test_admin_directory_shows_failure_and_retry_in_place_of_the_list(self):
        result = self.run_case("directory-failure")
        self.assertIn("연결", result["failedText"])
        self.assertNotIn("조건에 맞는 학생이 없습니다", result["failedText"])
        self.assertTrue(result["hasRetry"])
        self.assertEqual(result["afterRetry"], ["6333"])
