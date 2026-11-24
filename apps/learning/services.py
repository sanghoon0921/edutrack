from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.operations.access import restrict_student_ids_for_user
from apps.students.services import StudentService

from .models import (
    Discussion,
    DiscussionRecipient,
    Quiz,
    QuizAnswer,
    QuizChoice,
    QuizQuestion,
    QuizRecipient,
)


class UnknownStudentsError(ValidationError):
    pass


class QuizQuestionsError(ValidationError):
    """퀴즈 등록 화면에서 문항을 저장할 수 없을 때(예: 응시 기록이 있는 문항 삭제)."""


def can_manage_object(user, obj) -> bool:
    from apps.lms.access import can_manage
    return can_manage(user,obj)


def ensure_manageable(user, obj) -> None:
    if not can_manage_object(user, obj):
        raise PermissionDenied("본인이 등록한 항목만 관리할 수 있습니다.")


def validate_student_scope(user, student_ids: list[str]) -> list[tuple[str, str]]:
    cleaned = list(dict.fromkeys(str(item).strip() for item in student_ids if str(item).strip()))
    allowed = restrict_student_ids_for_user(user, cleaned)
    if set(allowed) != set(cleaned):
        raise PermissionDenied("강사는 담당 학생에게만 학습 활동을 배정할 수 있습니다.")

    service = StudentService()
    students = service.get_students(cleaned)
    student_map = {student.student_id: student for student in students}
    unknown = [student_id for student_id in cleaned if student_id not in student_map]
    if unknown:
        raise UnknownStudentsError("확인되지 않은 학생번호: " + ", ".join(unknown))
    return [
        (student_id, student_map[student_id].name)
        for student_id in cleaned
    ]


@transaction.atomic
def save_discussion(*, form, user) -> Discussion:
    discussion = form.save(commit=False)
    if discussion.pk:
        ensure_manageable(user, discussion)
    else:
        discussion.created_by = user
    discussion.save()
    from apps.lms.integrations import scoped_roster
    recipients = scoped_roster(user, discussion.group, form.cleaned_data["student_ids"])
    if recipients is None:
        recipients = validate_student_scope(user, form.cleaned_data["student_ids"])
    keep_ids = []
    for student_id, student_name in recipients:
        recipient, _ = DiscussionRecipient.objects.update_or_create(
            discussion=discussion,
            student_id=student_id,
            defaults={"student_name": student_name},
        )
        keep_ids.append(recipient.pk)
    discussion.recipients.exclude(pk__in=keep_ids).delete()
    return discussion


@transaction.atomic
def save_quiz(*, form, user) -> Quiz:
    quiz = form.save(commit=False)
    if quiz.pk:
        ensure_manageable(user, quiz)
    else:
        quiz.created_by = user
    quiz.save()
    from apps.lms.integrations import scoped_roster
    recipients = scoped_roster(user, quiz.group, form.cleaned_data["student_ids"])
    if recipients is None:
        recipients = validate_student_scope(user, form.cleaned_data["student_ids"])
    keep_ids = []
    for student_id, student_name in recipients:
        recipient, _ = QuizRecipient.objects.update_or_create(
            quiz=quiz,
            student_id=student_id,
            defaults={"student_name": student_name},
        )
        keep_ids.append(recipient.pk)
    removed=quiz.recipients.exclude(pk__in=keep_ids)
    if removed.filter(attempts__isnull=False).exists():
        raise UnknownStudentsError("응시 기록이 있는 학생은 배정에서 제외할 수 없습니다. 기존 응시·점수를 보존하고 새 퀴즈를 만들어 주세요.")
    removed.delete()
    if form.cleaned_data.get("questions_json") is not None:
        sync_quiz_questions(quiz, form.cleaned_data["questions_json"])
    return quiz


def _sync_choices(question, parsed):
    """보기는 같은 자리끼리 고쳐 씁니다. 지난 응시 답안이 고른 보기(선택 기록)를 잃지 않게 합니다."""
    existing = list(question.choices.order_by("order", "id"))
    for index, choice_data in enumerate(parsed, start=1):
        if index <= len(existing):
            choice = existing[index - 1]
            choice.text, choice.is_correct, choice.order = choice_data["text"], choice_data["is_correct"], index
            choice.save(update_fields=("text", "is_correct", "order"))
        else:
            QuizChoice.objects.create(question=question, text=choice_data["text"], is_correct=choice_data["is_correct"], order=index)
    QuizChoice.objects.filter(pk__in=[choice.pk for choice in existing[len(parsed):]]).delete()


def sync_quiz_questions(quiz, items):
    """퀴즈 등록 화면의 문항 목록대로 맞춥니다: 있던 문항은 고치고, 새 문항은 만들고, 빠진 문항은 지웁니다(순서 = 목록 순서)."""
    existing = {question.pk: question for question in quiz.questions.all()}
    keep = set()
    for order, item in enumerate(items, start=1):
        question = existing.get(item["id"]) or QuizQuestion(quiz=quiz)
        question.question_type, question.prompt, question.points = item["type"], item["prompt"], item["points"]
        question.order, question.correct_text, question.config = order, item["correct_text"], item["config"]
        question.save()
        keep.add(question.pk)
        _sync_choices(question, item["choices"])
    removed = [pk for pk in existing if pk not in keep]
    if QuizAnswer.objects.filter(question_id__in=removed).exists():
        raise QuizQuestionsError("응시 기록이 있는 문항은 삭제할 수 없습니다. 그 문항은 남겨 두거나 새 퀴즈를 만들어 주세요.")
    QuizQuestion.objects.filter(pk__in=removed).delete()


@transaction.atomic
def save_quiz_question(*, form, quiz: Quiz) -> QuizQuestion:
    question = form.save(commit=False)
    question.quiz = quiz
    question.config = form.cleaned_data.get("config", {})
    if question.question_type != QuizQuestion.Type.SHORT_ANSWER:
        question.correct_text = ""
    question.save()
    _sync_choices(question, form.cleaned_data.get("parsed_choices", []))
    return question
