# 수납 내역 (학부모)

## 무엇을 하나요

학부모가 연결된 자녀의 수납 내역을 읽기 전용으로 봅니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 수납 내역 | `/billing/my/` | `billing:my-history` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/billing/views.py` | |
| 조회 선택 | `apps/billing/services.py` | demo 모드에서는 실제 수납 기록을 절대 조회하지 않음 |
| 인트라넷 조회 | `apps/billing/repositories.py` | SELECT 전용 |
| 데이터 모양 | `apps/billing/contracts.py` | |
| 금액 표시 | `apps/billing/templatetags/billing_tags.py` | 원화 표시 |
| 화면(HTML) | `apps/billing/templates/billing/my_payment_history.html` | |
| 테스트 | `apps/billing/tests/test_billing.py`, `apps/billing/tests/test_demo_isolation.py` | |

## 데이터는 어디서 오나요

인트라넷(읽기 전용). demo 모드는 가짜 데이터.

## 누가 볼 수 있나요

학부모(연결 자녀), 관리자.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 내역이 비어 있음 | 학부모 계정의 자녀 학생번호 연결, real 모드 인트라넷 연결 |
