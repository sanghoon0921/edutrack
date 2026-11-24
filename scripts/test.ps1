<#
자동 테스트 실행

  .\scripts\test.ps1                전체 테스트
  .\scripts\test.ps1 lms            apps\lms 기능만
  .\scripts\test.ps1 lms students   여러 기능

통과하면 마지막에 OK 가 나옵니다. FAILED 가 나오면 위쪽의 FAIL/ERROR 항목을 확인하세요.
#>
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Apps)
# 한국어 Windows에서도 파이썬이 파일을 UTF-8로 읽게 합니다(일부 테스트가 이 설정을 전제로 합니다).
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "파이썬 가상환경(.venv)이 없습니다. 먼저 .\scripts\setup.ps1 을 실행하세요."
}
$labels = @()
foreach ($app in $Apps) {
    if ($app -match "^[a-z_]+$") { $labels += "apps.$app" } else { $labels += $app }
}
& $python manage.py test @labels --settings=config.settings.test --parallel 4 -v 1
exit $LASTEXITCODE
