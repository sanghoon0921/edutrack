"""share 모드(운영팀 외부 공유)에서 쓸 테스트용 사본을 만듭니다. 가짜(demo) 데이터만 씁니다.

데모 DB(data/demo/db.sqlite3)와 업로드 파일(data/demo/media/)을 data/share/ 로 복사합니다.
원본은 읽기 전용으로 열어 바꾸지 않습니다. 사본이 이미 있으면 그대로 써서
운영팀이 만든 테스트 내용이 서버를 다시 켜도 남습니다(--reset 이면 지우고 새로 복사).

실행: python -m config.share_copy [--reset]   (보통 .\\scripts\\share.ps1 이 대신 실행)
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ShareCopyError(Exception):
    pass


def make_share_copy(root: Path = ROOT, *, reset: bool = False) -> str:
    """사본을 만들었으면 "copied", 기존 사본을 그대로 두면 "kept"."""
    demo = root / "data" / "demo"
    share = root / "data" / "share"
    source_db, target_db = demo / "db.sqlite3", share / "db.sqlite3"
    if target_db.exists() and not reset:
        return "kept"
    if not source_db.is_file():
        raise ShareCopyError(f"데모 DB가 없습니다: {source_db} (README의 '처음 설치'를 확인하세요)")
    if share.exists():
        shutil.rmtree(share)
    share.mkdir(parents=True)
    source = sqlite3.connect(source_db.resolve().as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(target_db)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    if (demo / "media").is_dir():
        shutil.copytree(demo / "media", share / "media")
    return "copied"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="운영팀 테스트용 사본(data/share) 만들기")
    parser.add_argument("--reset", action="store_true", help="기존 사본을 지우고 데모 DB에서 새로 복사")
    args = parser.parse_args(argv)
    try:
        result = make_share_copy(reset=args.reset)
    except ShareCopyError as error:
        print(error, file=sys.stderr)
        return 1
    if result == "copied":
        print("[EduTrack] 데모 DB를 테스트용 사본(data/share)으로 복사했습니다.")
    else:
        print("[EduTrack] 기존 테스트용 사본(data/share)을 그대로 씁니다. 새로 시작하려면 -Reset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
