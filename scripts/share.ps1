<#
EduTrack 운영팀 테스트 서버 (가짜 데이터, 운영과 비슷한 방식)

  .\scripts\share.ps1          테스트 서버를 켭니다 (이 PC 안 http://127.0.0.1:8010/)
  .\scripts\share.ps1 -Reset   운영팀 테스트 내용을 지우고 데모 DB에서 새로 시작합니다

- 가짜(demo) 학생·성적 데이터만 씁니다. 실제 인트라넷·DSG에는 접속하지 않습니다.
- 운영팀이 만든 과제·메시지 등은 테스트용 사본 data\share\ 에 저장됩니다(data\demo\ 는 그대로).
- 오류 상세는 화면에 보이지 않고, 오류·느린 화면은 data\share\server.log 에 남습니다.
- 다른 PC에서 들어오는 주소는 docs\share-test.md 의 '외부 주소 열기'를 보고 직접 엽니다.
끄기: 이 창에서 Ctrl + C
#>
param(
    [switch]$Reset
)
# 한국어 Windows에서도 파이썬이 파일을 UTF-8로 읽게 합니다.
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "파이썬 가상환경(.venv)이 없습니다. 먼저 .\scripts\setup.ps1 을 실행하세요."
}

$settings = "config.settings.share"
$copyArgs = @("-m", "config.share_copy")
if ($Reset) { $copyArgs += "--reset" }
& $python @copyArgs
if ($LASTEXITCODE -ne 0) { throw "테스트용 사본(data\share)을 만들지 못했습니다." }
& $python manage.py migrate --noinput --verbosity 0 --settings=$settings
if ($LASTEXITCODE -ne 0) { throw "DB 준비(migrate)에 실패했습니다." }
& $python manage.py collectstatic --noinput --verbosity 0 --settings=$settings
if ($LASTEXITCODE -ne 0) { throw "정적 파일 준비(collectstatic)에 실패했습니다." }

Write-Host "[EduTrack] 운영팀 테스트 서버: http://127.0.0.1:8010/ (이 PC 안에서만 열림, 끄기: Ctrl + C)"
$env:DJANGO_SETTINGS_MODULE = $settings
& $python -m waitress --host=127.0.0.1 --port=8010 --threads=8 config.wsgi:application
exit $LASTEXITCODE
