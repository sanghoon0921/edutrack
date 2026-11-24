# apps/classroom — 과목 자료

과목별 자료 공간(카테고리·PDF·파일·링크). 자세한 안내: [docs/features/course-resources.md](../../docs/features/course-resources.md)

| 파일 | 하는 일 |
|---|---|
| models.py | `CourseBoard`(과목), `CourseCategory`, `CourseResource`(자료), 대상 학생 |
| views.py | 과목·카테고리·자료 화면, 미리보기·내려받기 |
| services.py | 관리 권한, 대상 학생 저장 |
| forms.py | 입력 칸 (일반 화면은 항상 공개로 저장) |
| signals.py | 자료를 지우면 파일도 지움 |
| urls.py | `/courses/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "classroom"` 바꾸지 말 것) |
| `apps/classroom/templates/classroom/` | 과목 자료 화면 6개 |
| `apps/classroom/static/classroom/js/resource-form.js` | 자료 올리기 화면 동작 |
| `apps/classroom/tests/` | 자동 테스트 |
