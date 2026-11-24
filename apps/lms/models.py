from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.db import models
from django.db.models import Q


def protected_path(instance, filename):
    return f"lms_private/{uuid4().hex}{Path(filename).suffix.lower()}"


class RoomSettings(models.Model):
    group = models.OneToOneField("learning.LearningGroup", on_delete=models.CASCADE, related_name="room_settings")
    schedule = models.TextField("수업 스케줄", blank=True)
    zoom_url = models.URLField("Zoom 링크", max_length=500, blank=True)
    dsg_guide = models.TextField("DSG 가입·이용 안내", blank=True)
    classroom_url = models.URLField("Google Classroom 링크", max_length=500, blank=True)
    canvas_url = models.URLField("Canvas 링크", max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class GroupMember(models.Model):
    group = models.ForeignKey("learning.LearningGroup", on_delete=models.CASCADE, related_name="lms_members")
    student_no = models.CharField("학생번호", max_length=50)
    student_name = models.CharField("학생명", max_length=100)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "student_no"], name="lms_unique_group_student")]
        ordering = ["student_name", "student_no"]


class GroupStaff(models.Model):
    group = models.ForeignKey("learning.LearningGroup", on_delete=models.CASCADE, related_name="lms_staff")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lms_teaching_groups")
    duty = models.CharField("담당", max_length=10, choices=[("TEACHER", "공동 강사"), ("TA", "TA")], default="TA")
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "user"], name="lms_unique_group_staff")]


class ClassPost(models.Model):
    group = models.ForeignKey("learning.LearningGroup", on_delete=models.CASCADE, related_name="lms_posts")
    kind = models.CharField("분류", max_length=10, choices=[("NOTICE", "반 공지"), ("PAGE", "페이지·단어장"), ("FILE", "수업 자료")])
    title = models.CharField("제목", max_length=200)
    body = models.TextField("내용", blank=True)
    published = models.BooleanField("학생 공개", default=True)
    pinned = models.BooleanField("상단 고정", default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-pinned", "-created_at", "-pk"]


class PostFile(models.Model):
    post = models.ForeignKey(ClassPost, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=protected_path)
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    @property
    def audio(self):
        return Path(self.original_name).suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


class SubmissionFile(models.Model):
    submission = models.ForeignKey("assignments.Submission", on_delete=models.CASCADE, related_name="extra_files")
    file = models.FileField(upload_to=protected_path)
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["pk"]


class ReviewDocument(models.Model):
    submission = models.ForeignKey("assignments.Submission", on_delete=models.CASCADE, null=True, blank=True, related_name="review_documents")
    attempt = models.ForeignKey("learning.QuizAttempt", on_delete=models.CASCADE, null=True, blank=True, related_name="review_documents")
    original_name = models.CharField(max_length=255)
    source_key = models.CharField(max_length=500)
    source_token = models.CharField(max_length=64, db_index=True)
    pdf = models.FileField(upload_to=protected_path)
    page_count = models.PositiveIntegerField(default=1)
    annotations = models.JSONField(default=list)
    # 쪽별 단어 위치 {"쪽 번호": [{"t","x","y","w","h","line"}]}. 처음 볼 때 채워 둡니다(글자 드래그 형광펜·취소선용).
    text_layer = models.JSONField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(submission__isnull=False, attempt__isnull=True) | Q(submission__isnull=True, attempt__isnull=False)), name="lms_doc_one_target"),
          models.UniqueConstraint(fields=["submission", "source_key", "source_token"], name="lms_doc_submission_version"),
          models.UniqueConstraint(fields=["attempt", "source_key", "source_token"], name="lms_doc_attempt_version")]
        ordering = ["-created_at", "-pk"]


class Conversation(models.Model):
    class Kind(models.TextChoices):
        DIRECT = "DIRECT", "1:1 대화"        # 두 사람당 하나(direct_key), 카카오톡처럼 계속 쌓임
        GROUP = "GROUP", "그룹 대화"         # 강사가 반 학생 일부를 골라 만든 방
        CLASS = "CLASS", "반 단체방"         # 반마다 하나, 참여자는 반 명단을 따라감(apps/lms/rooms.py)

    title = models.CharField("제목", max_length=160)
    # 관리자·강사가 바꾼 방 이름(운영팀 10/29). 비어 있으면 반 이름·참여자 이름으로 정합니다. 1:1 대화에는 쓰지 않습니다.
    custom_title = models.CharField("바꾼 방 이름", max_length=80, blank=True)
    kind = models.CharField("방 종류", max_length=10, choices=Kind.choices, default=Kind.GROUP, db_index=True)
    direct_key = models.CharField("1:1 두 사람", max_length=40, null=True, blank=True, unique=True)
    group = models.ForeignKey("learning.LearningGroup", null=True, blank=True, on_delete=models.CASCADE, related_name="lms_conversations")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-updated_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["group"], condition=models.Q(kind="CLASS"), name="lms_one_class_room")]


class ConversationMember(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_read_id = models.PositiveBigIntegerField(default=0)
    # 반 단체방에 나중에 들어온 사람은 이 번호보다 뒤의 메시지만 봅니다(카카오톡과 같음).
    joined_after = models.PositiveBigIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="lms_conversation_user")]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField("메시지")
    client_token = models.UUIDField(default=uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["pk"]


class ChangeLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=120)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-pk"]
