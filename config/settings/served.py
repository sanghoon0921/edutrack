"""share 모드: 개발 서버 없이(waitress) 운영과 비슷하게 켤 때 바꾸는 값.

설정 모드가 아니라 share.py 가 가져다 쓰는 도움 함수입니다.
"""
from copy import deepcopy


def with_whitenoise(middleware):
    """CSS·JS를 개발 서버 없이 내보냅니다(collectstatic 이 먼저 필요)."""
    items = list(middleware)
    items.insert(items.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
    return items


def with_log_file(logging, path):
    """오류(500)와 느린 화면을 화면 대신 파일에도 남겨, 테스트 뒤 고칠 곳을 찾습니다."""
    config = deepcopy(logging)
    config["handlers"]["server_file"] = {
        "class": "logging.FileHandler",
        "filename": str(path),
        "encoding": "utf-8",
        "delay": True,
        "formatter": "edutrack",
    }
    config["loggers"]["edutrack.performance"]["handlers"] = ["console", "server_file"]
    config["loggers"]["django.request"] = {"handlers": ["console", "server_file"], "level": "ERROR", "propagate": False}
    return config
