# CSV 일괄 등록

## 무엇을 하나요

사용자와 예전 과제를 CSV로 한 번에 등록합니다. 올리면 먼저 미리보기로 검사하고, 확인 후 적용합니다. 결과(행별 성공·실패)를 CSV로 다시 내려받을 수 있습니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 데이터 이전 첫 화면 | `/operations/imports/` | `data_imports:dashboard` |
| 사용자 등록 / 과제 등록 | `/operations/imports/users/`, `/operations/imports/assignments/` | `data_imports:user-import`, `data_imports:assignment-import` |
| 양식 CSV 내려받기 | `/operations/imports/templates/users.csv` 등 | `data_imports:user-template` 등 |
| 작업 결과 / 결과 CSV | `/operations/imports/batches/<번호>/`, `…/results.csv` | `data_imports:batch-detail`, `data_imports:batch-results` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/data_imports/views.py` | |
| 검사·적용 | `apps/data_imports/services.py` | 미리보기·적용, CSV 수식 방어 |
| 입력 양식 | `apps/data_imports/forms.py` | |
| DB 표 | `apps/data_imports/models.py` | `ImportBatch`, 행별 결과, 예전 번호 대응표 |
| 명령으로 실행 | `apps/data_imports/management/commands/import_users_csv.py`, `apps/data_imports/management/commands/import_legacy_assignments_csv.py` | |
| 화면(HTML) | `apps/data_imports/templates/data_imports/` (5개 파일) | |
| 테스트 | `apps/data_imports/tests/test_data_imports.py` | |

## 데이터는 어디서 오나요

올린 CSV → 자체 DB.

## 누가 볼 수 있나요

관리자만.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 한글이 깨짐 | CSV를 UTF-8로 저장했는지 |
| 일부 행만 실패 | 작업 결과 화면의 행별 사유 |
