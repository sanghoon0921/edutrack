# 관리자 클래스 검색

## 무엇을 하나요

관리자가 인트라넷의 수업(클래스) 목록을 검색·필터하고, 클래스를 누르면 기본정보·Lesson·휴강일·상태를 읽기 전용으로 봅니다.

- 목록의 **'배정 학생 N명 보기'**를 누르면 그 수업의 인트라넷 배정 학생 명단이 줄 아래로 펼쳐집니다(50명씩 '더 보기', 이름을 누르면 학생 상세). 다시 누르면 접힙니다. (`apps/dashboard/static/dashboard/js/class-roster.js`, 명단은 `students:selector-browse`)

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 클래스 검색(수업 관리) | `/dashboard/admin/classes/` | `admin_classes` |
| 클래스 상세 | `/dashboard/admin/classes/<번호>/` | `admin-class-detail` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 조회 | `apps/dashboard/class_catalog.py` | 인트라넷 수업 원장 검색 (demo/인트라넷 저장소) |
| 상세 | `apps/dashboard/admin_class_detail.py` | 클래스 상세 읽기 |
| 검색 양식 | `apps/dashboard/forms.py` | 검색 조건 |
| 화면(HTML) | `apps/dashboard/templates/dashboard/admin_class_catalog.html`, `apps/dashboard/templates/dashboard/admin_class_detail.html` | |
| CSS | `apps/dashboard/static/dashboard/css/class-catalog.css` | |
| 점검 명령 | `apps/dashboard/management/commands/check_class_catalog.py` | 인트라넷 조회 확인 |
| 테스트 | `apps/dashboard/tests/test_class_catalog.py` | |

## 데이터는 어디서 오나요

인트라넷(읽기 전용). demo 모드는 가짜 클래스 목록을 씁니다(`CLASS_CATALOG_DATA_SOURCE`).

## 누가 볼 수 있나요

관리자만.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 상세가 느림 | `.env`의 `ADMIN_CLASS_DETAIL_CACHE_SECONDS` (캐시 시간) |
