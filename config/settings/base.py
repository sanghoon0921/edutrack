"""EduTrack 공통 설정. 직접 쓰지 않고 demo.py / real.py / test.py 가 이 파일을 불러와 필요한 값만 바꿉니다."""
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


# 로컬 개발용 기본값입니다. 배포 환경에서는 환경변수로 반드시 교체합니다.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-this-before-deploy")
DEBUG = _env_bool("DJANGO_DEBUG", True)

# 테스트 기간에만 관리자가 연 학생을 student_test/parent_test에 자동 연결합니다.
ADMIN_AUTO_LINK_TEST_ACCOUNTS = _env_bool(
    "ADMIN_AUTO_LINK_TEST_ACCOUNTS",
    DEBUG,
)
DEMO_STUDENT_USERNAME = os.environ.get(
    "DEMO_STUDENT_USERNAME",
    "student_test",
).strip()
DEMO_PARENT_USERNAME = os.environ.get(
    "DEMO_PARENT_USERNAME",
    "parent_test",
).strip()

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    ).split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.lms",
    "apps.dashboard",
    "apps.students",
    "apps.assessments",
    "apps.assignments",
    "apps.billing",
    "apps.communications",
    "apps.operations",
    "apps.data_imports",
    "apps.learning",
    "apps.content_editor",
    "apps.classroom",
    "apps.reports",
]

MIDDLEWARE = [
    "apps.lms.middleware.PrivateMediaGuardMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.FirstSetupMiddleware",
    "config.middleware.RequestTimingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.navigation",
                "apps.communications.context_processors.communication_summary",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# 로컬 단계에서는 SQLite를 사용합니다. busy timeout과 WAL로 짧은 동시 쓰기
# 충돌을 완화하지만, 실제 운영 다중 사용자 환경에서는 전용 RDS로 교체합니다.
SQLITE_BUSY_TIMEOUT_SECONDS = _env_int(
    "SQLITE_BUSY_TIMEOUT_SECONDS",
    20,
    minimum=1,
)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "demo" / "db.sqlite3",
        "OPTIONS": {
            "timeout": SQLITE_BUSY_TIMEOUT_SECONDS,
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_SECONDS * 1000};"
                "PRAGMA temp_store=MEMORY"
            ),
        },
    }
}

# 11/24 전체 점검: 4자 → 8자 이상, 숫자로만 된 비밀번호 금지(새로 정하거나 바꿀 때 적용, 기존 비밀번호는 그대로).
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "data" / "demo" / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.environ.get(
    "DJANGO_SECURE_REFERRER_POLICY",
    "same-origin",
).strip() or "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.environ.get(
    "DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY",
    "same-origin",
).strip() or "same-origin"

SESSION_COOKIE_SECURE = _env_bool("DJANGO_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", False)
SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = _env_int("DJANGO_SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    False,
)
SECURE_HSTS_PRELOAD = _env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
if _env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# 대용량 요청 하나가 개발 서버 메모리를 과도하게 점유하지 않도록 제한합니다.
MAX_REQUEST_UPLOAD_MB = _env_int("MAX_REQUEST_UPLOAD_MB", 25, minimum=1)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_REQUEST_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = _env_int(
    "FILE_UPLOAD_MEMORY_MB",
    5,
    minimum=1,
) * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = _env_int(
    "DATA_UPLOAD_MAX_NUMBER_FIELDS",
    5000,
    minimum=1000,
)

# ============================================================
# Stage 13 — shared cache with failure-safe fallback
# ============================================================

CACHE_DEFAULT_TIMEOUT = _env_int("CACHE_DEFAULT_TIMEOUT", 300, minimum=1)
CACHE_KEY_PREFIX = os.environ.get("CACHE_KEY_PREFIX", "edutrack").strip() or "edutrack"
CACHE_FAILURE_COOLDOWN_SECONDS = _env_int(
    "CACHE_FAILURE_COOLDOWN_SECONDS",
    30,
    minimum=1,
)
REDIS_URL = os.environ.get("REDIS_URL", "").strip()

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "config.cache_backend.ResilientRedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": CACHE_DEFAULT_TIMEOUT,
            "KEY_PREFIX": CACHE_KEY_PREFIX,
            "OPTIONS": {
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
                "retry_on_timeout": True,
                "health_check_interval": 30,
            },
        }
    }
else:
    # 로컬에서는 별도 설치 없이 동작합니다. 운영 다중 프로세스에서는 REDIS_URL을
    # 지정해야 프로세스 간 캐시를 공유할 수 있습니다.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "edutrack-local-cache-v1",
            "TIMEOUT": CACHE_DEFAULT_TIMEOUT,
            "KEY_PREFIX": CACHE_KEY_PREFIX,
            "OPTIONS": {
                "MAX_ENTRIES": _env_int(
                    "LOCAL_CACHE_MAX_ENTRIES",
                    2000,
                    minimum=200,
                ),
                "CULL_FREQUENCY": 3,
            },
        }
    }

STUDENT_PROFILE_CACHE_SECONDS = _env_int(
    "STUDENT_PROFILE_CACHE_SECONDS",
    60,
)
STUDENT_COURSE_CACHE_SECONDS = _env_int(
    "STUDENT_COURSE_CACHE_SECONDS",
    60,
)
ATTENDANCE_CACHE_SECONDS = _env_int(
    "ATTENDANCE_CACHE_SECONDS",
    60,
)
COMMUNICATION_HEADER_CACHE_SECONDS = _env_int(
    "COMMUNICATION_HEADER_CACHE_SECONDS",
    15,
)
COMMUNICATION_HEADER_SCAN_LIMIT = _env_int(
    "COMMUNICATION_HEADER_SCAN_LIMIT",
    500,
    minimum=100,
)
ADMIN_CLASS_DETAIL_CACHE_SECONDS = _env_int(
    "ADMIN_CLASS_DETAIL_CACHE_SECONDS",
    60,
)


# ============================================================
# Stage 14 — pasted images and course resources
# ============================================================

PASTED_IMAGE_MAX_MB = _env_int("PASTED_IMAGE_MAX_MB", 8, minimum=1)
PASTED_IMAGE_DRAFT_TTL_HOURS = _env_int(
    "PASTED_IMAGE_DRAFT_TTL_HOURS",
    48,
    minimum=1,
)
COURSE_RESOURCE_MAX_MB = _env_int("COURSE_RESOURCE_MAX_MB", 25, minimum=1)

# ============================================================
# External read-only database connections
# ============================================================

EXTERNAL_DB_CONN_MAX_AGE = _env_int("EXTERNAL_DB_CONN_MAX_AGE", 60)
EXTERNAL_DB_CONNECT_TIMEOUT = _env_int(
    "EXTERNAL_DB_CONNECT_TIMEOUT",
    5,
    minimum=1,
)
EXTERNAL_DB_READ_TIMEOUT = _env_int(
    "EXTERNAL_DB_READ_TIMEOUT",
    15,
    minimum=1,
)

DATABASES["dsg"] = {
    "ENGINE": "django.db.backends.mysql",
    "NAME": os.getenv("DSG_DB_NAME", ""),
    "USER": os.getenv("DSG_DB_USER", ""),
    "PASSWORD": os.getenv("DSG_DB_PASSWORD", ""),
    "HOST": os.getenv("DSG_DB_HOST", ""),
    "PORT": os.getenv("DSG_DB_PORT", "3306"),
    "CONN_MAX_AGE": EXTERNAL_DB_CONN_MAX_AGE,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {
        "charset": "utf8mb4",
        "connect_timeout": EXTERNAL_DB_CONNECT_TIMEOUT,
        "read_timeout": EXTERNAL_DB_READ_TIMEOUT,
        "write_timeout": EXTERNAL_DB_READ_TIMEOUT,
    },
}

DATABASES["intranet"] = {
    "ENGINE": "django.db.backends.mysql",
    "NAME": os.getenv("INTRANET_DB_NAME", ""),
    "USER": os.getenv("INTRANET_DB_USER", ""),
    "PASSWORD": os.getenv("INTRANET_DB_PASSWORD", ""),
    "HOST": os.getenv("INTRANET_DB_HOST", ""),
    "PORT": os.getenv("INTRANET_DB_PORT", "3306"),
    "CONN_MAX_AGE": EXTERNAL_DB_CONN_MAX_AGE,
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {
        "charset": "utf8mb4",
        "connect_timeout": EXTERNAL_DB_CONNECT_TIMEOUT,
        "read_timeout": EXTERNAL_DB_READ_TIMEOUT,
        "write_timeout": EXTERNAL_DB_READ_TIMEOUT,
        # 인터넷 구간으로 학생 정보가 오가므로 암호화(TLS)를 필수로 합니다.
        # 비어 있지 않은 ssl 설정 = pymysql 'REQUIRED': 서버가 암호화를 안 하면 평문으로 내려가지 않고 연결을 거부합니다.
        # 서버 인증서 확인은 하지 않습니다(로컬 터널 접속에서도 그대로 쓰기 위해).
        "ssl": {"verify_mode": False},
    },
}

ASSESSMENT_DATA_SOURCE = os.getenv("ASSESSMENT_DATA_SOURCE", "demo")
STUDENT_DATA_SOURCE = os.getenv("STUDENT_DATA_SOURCE", "demo")

EXAM_DETAIL_CACHE_SECONDS = _env_int("EXAM_DETAIL_CACHE_SECONDS", 900)
STUDENT_INSIGHT_CACHE_SECONDS = _env_int(
    "STUDENT_INSIGHT_CACHE_SECONDS",
    1800,
)
STUDENT_INSIGHT_MAX_ATTEMPTS = _env_int(
    "STUDENT_INSIGHT_MAX_ATTEMPTS",
    5,
    minimum=1,
)

# ============================================================
# Request timing / logs
# ============================================================

REQUEST_SLOW_LOG_MS = _env_int("REQUEST_SLOW_LOG_MS", 750, minimum=50)
SERVER_TIMING_ENABLED = _env_bool("SERVER_TIMING_ENABLED", DEBUG)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "edutrack": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "edutrack",
        }
    },
    "loggers": {
        "edutrack.performance": {
            "handlers": ["console"],
            "level": os.environ.get("PERFORMANCE_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "edutrack.cache": {
            "handlers": ["console"],
            "level": os.environ.get("CACHE_LOG_LEVEL", "WARNING"),
            "propagate": False,
        },
        "edutrack.keepalive": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# LMS 운영팀 요구 기능. 기본값은 로컬 변환기 미사용입니다.
LMS_OFFICE_CONVERTER = os.environ.get("LMS_OFFICE_CONVERTER", "")
LMS_UPLOAD_MAX_MB = _env_int("LMS_UPLOAD_MAX_MB", 25, minimum=1)
LMS_DOCUMENT_MAX_PAGES = 100
