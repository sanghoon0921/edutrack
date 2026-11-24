# apps/assessments — DSG 성적·분석

DSG 시험 점수 요약, 시험 상세, 누적 학습 분석(DSG DB 읽기 전용). 자세한 안내: [docs/features/assessments.md](../../docs/features/assessments.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 시험 상세·누적 분석 화면 (학생·학부모·담당 강사 권한 검사) |
| urls.py | `/assessments/…` 주소 |
| services.py, repositories.py | 학생별 DSG 점수 요약 (demo/DSG 저장소 선택) |
| detail_services.py, detail_repositories.py | 시험 상세·문항별 결과 (캐시) |
| insight_services.py | 시험별 영역 인사이트 |
| cumulative_services.py | 여러 시험을 합친 누적 추세 |
| contracts.py, detail_contracts.py, insight_contracts.py, cumulative_contracts.py | 화면에 넘기는 데이터 모양 |
| templatetags/assessment_tags.py | 학생 상세 화면의 점수 요약 조각 |
| apps.py | 앱 설정(`label = "assessments"` 바꾸지 말 것) |
| management/commands/ | DSG 연결·매핑 점검, 성능 측정, 캐시 비우기 명령 |
| `apps/assessments/templates/assessments/` | 시험 상세·분석·점수 요약 화면 |
| `apps/assessments/static/assessments/js/` | 시험 상세·분석 화면 동작 |
| `apps/assessments/tests/` | 자동 테스트 |
