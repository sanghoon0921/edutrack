# apps/billing — 수납 내역(학부모)

학부모가 자녀 수납 내역을 읽기 전용으로 봅니다. 자세한 안내: [docs/features/billing.md](../../docs/features/billing.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 수납 내역 화면 |
| services.py | demo/인트라넷 조회 선택 (demo에서는 실제 기록을 조회하지 않음) |
| repositories.py | 인트라넷 수납 SELECT 조회 |
| contracts.py | 수납 기록 데이터 모양 |
| templatetags/billing_tags.py | 원화 표시 |
| urls.py, apps.py | 주소, 앱 설정(`label = "billing"` 바꾸지 말 것) |
| `apps/billing/templates/billing/` | 수납 내역 화면 |
| `apps/billing/tests/` | 자동 테스트 |
