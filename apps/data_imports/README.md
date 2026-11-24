# apps/data_imports — CSV 일괄 등록

사용자·예전 과제를 CSV로 미리보기 후 일괄 등록. 자세한 안내: [docs/features/data-imports.md](../../docs/features/data-imports.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 첫 화면·업로드·결과·양식 내려받기 |
| services.py | CSV 검사(미리보기)·적용, CSV 수식 방어 |
| forms.py | 업로드 입력 칸 |
| models.py | `ImportBatch`(작업), 행별 결과, 예전 번호 대응표 |
| urls.py | `/operations/imports/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "data_imports"` 바꾸지 말 것) |
| management/commands/ | `import_users_csv`, `import_legacy_assignments_csv` |
| `apps/data_imports/templates/data_imports/` | 화면 5개 |
| `apps/data_imports/tests/` | 자동 테스트 |
