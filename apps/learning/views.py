from __future__ import annotations

from collections import Counter
from decimal import Decimal
import random

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.utils import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required, teacher_required, class_staff_required
from apps.accounts.models import User
from apps.content_editor.models import PastedImage
from apps.content_editor.services import sync_pasted_images
from apps.operations.access import is_admin
from apps.students.selection import build_student_selector_context
from apps.students.services import StudentService

from . import quiz_types
from .forms import (
    quiz_builder_data,
    DiscussionCommentForm,
    DiscussionForm,
    LearningGroupCreateForm,
    LearningGroupForm,
    QuizForm,
    QuizQuestionForm,
)
from .models import (
    Discussion,
    DiscussionComment,
    DiscussionRecipient,
    LearningGroup,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    QuizRecipient,
)
from .services import (
    QuizQuestionsError,
    UnknownStudentsError,
    can_manage_object,
    ensure_manageable,
    save_discussion,
    save_quiz,
    save_quiz_question,
)


def _current_student_id(request: HttpRequest) -> str:
    student_id = StudentService().get_student_id_for_username(request.user.username)
    if not student_id:
        raise Http404("현재 계정에 연결된 학생번호가 없습니다.")
    return student_id


def _staff_queryset(queryset, user):
    if is_admin(user):
        return queryset
    from apps.lms.access import staff_scope
    return staff_scope(queryset,user)


def _available_filter_kwargs() -> dict:
    now = timezone.now()
    from django.db.models import Q

    return {"availability_q": Q(available_from__isnull=True) | Q(available_from__lte=now)}


@teacher_required
def group_manage(request: HttpRequest) -> HttpResponse:
    """반 만들기(11/20): 반 이름·Term(인트라넷 목록)과 함께 학생(수업·반 통째로 또는 한 명씩)·담당 TA를 한 번에 넣습니다.
    학생 확인(인트라넷)이 안 되면 반을 만들지 않고 알려 줍니다(빈 반이 생기지 않게)."""
    from django.core.exceptions import ValidationError

    from apps.learning.services import validate_student_scope
    from apps.lms.roster_service import apply_roster

    groups = LearningGroup.objects.select_related("created_by")
    if not is_admin(request.user):
        groups = groups.filter(created_by=request.user)
    form = LearningGroupCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            students = validate_student_scope(request.user, form.cleaned_data["student_ids"])
        except PermissionDenied as exc:
            form.add_error("student_ids", f"{exc} 반은 만들지 않았습니다.")
        except ValidationError as exc:
            form.add_error("student_ids", exc)
        except DatabaseError:
            form.add_error("student_ids", "인트라넷에 연결되지 않아 학생을 확인하지 못했습니다. 반은 만들지 않았습니다. "
                                          "학생을 빼고 먼저 만들거나, 잠시 뒤 다시 시도해 주세요.")
        else:
            with transaction.atomic():
                group = form.save(commit=False)
                group.created_by = request.user
                group.save()
                apply_roster(group, students, form.cleaned_data["staff"], actor=request.user, action="room.create")
            staff_count = len(form.cleaned_data["staff"])
            messages.success(request, f"'{group.title}' 반을 만들었습니다. 학생 {len(students)}명"
                                      f"{f', 담당 TA·강사 {staff_count}명' if staff_count else ''}을 함께 넣었습니다.")
            return redirect("learning:group-manage")
    selector = build_student_selector_context(form=form, user=request.user, recipients=[])
    return render(
        request,
        "learning/group_manage.html",
        {"page_title": "반 만들기", "groups": groups, "form": form, "student_selector": selector},
    )


@teacher_required
def group_update(request: HttpRequest, group_id: int) -> HttpResponse:
    group = get_object_or_404(LearningGroup, pk=group_id)
    if not is_admin(request.user) and group.created_by_id != request.user.id:
        raise PermissionDenied("본인이 만든 그룹만 수정할 수 있습니다.")
    form = LearningGroupForm(request.POST or None, instance=group)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "반 정보를 수정했습니다.")
        return redirect("learning:group-manage")
    return render(
        request,
        "learning/group_form.html",
        {"page_title": "반 정보 수정", "form": form, "group": group},
    )


@class_staff_required
def discussion_list(request: HttpRequest) -> HttpResponse:
    discussions = _staff_queryset(
        Discussion.objects.select_related("created_by", "group").prefetch_related("recipients", "comments"),
        request.user,
    )
    rows = [
        {
            "discussion": item,
            "recipient_count": item.recipients.count(),
            "comment_count": item.comments.count(),
        }
        for item in discussions
    ]
    return render(
        request,
        "learning/discussion_list.html",
        {"page_title": "토론", "discussion_rows": rows},
    )


@class_staff_required
def discussion_create(request: HttpRequest) -> HttpResponse:
    from apps.lms.integrations import activity_initial
    form = DiscussionForm(request.POST or None, request.FILES or None, user=request.user,initial=activity_initial(request))
    if request.method == "POST" and form.is_valid():
        try:
            discussion = save_discussion(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            sync_pasted_images(
                text=discussion.content,
                owner=request.user,
                target_type=PastedImage.TargetType.DISCUSSION,
                target_id=discussion.pk,
            )
            messages.success(request, "토론을 등록했습니다.")
            return redirect("learning:discussion-list")  # 11/19: 저장하면 토론 목록으로
    return render(
        request,
        "learning/discussion_form.html",
        {
            "page_title": "토론 등록",
            "form": form,
            "form_mode": "create",
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
            ),
        },
    )


@class_staff_required
def discussion_update(request: HttpRequest, discussion_id: int) -> HttpResponse:
    discussion = get_object_or_404(Discussion, pk=discussion_id)
    ensure_manageable(request.user, discussion)
    form = DiscussionForm(request.POST or None, request.FILES or None, instance=discussion, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            discussion = save_discussion(form=form, user=request.user)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            sync_pasted_images(
                text=discussion.content,
                owner=request.user,
                target_type=PastedImage.TargetType.DISCUSSION,
                target_id=discussion.pk,
            )
            messages.success(request, "토론을 수정했습니다.")
            return redirect("learning:discussion-list")  # 11/19: 저장하면 토론 목록으로
    return render(
        request,
        "learning/discussion_form.html",
        {
            "page_title": "토론 수정",
            "form": form,
            "form_mode": "update",
            "discussion": discussion,
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
                recipients=discussion.recipients.all(),
            ),
        },
    )


@class_staff_required
def discussion_detail(request: HttpRequest, discussion_id: int) -> HttpResponse:
    discussion = get_object_or_404(
        Discussion.objects.select_related("created_by", "group").prefetch_related(
            "recipients", "comments__author"
        ),
        pk=discussion_id,
    )
    ensure_manageable(request.user, discussion)
    comment_form = DiscussionCommentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and comment_form.is_valid():
        comment = comment_form.save(commit=False)
        comment.discussion = discussion
        comment.author = request.user
        comment.save()
        messages.success(request, "댓글을 등록했습니다.")
        return redirect("learning:discussion-detail", discussion_id=discussion.pk)
    return render(
        request,
        "learning/discussion_detail.html",
        {
            "page_title": discussion.title,
            "discussion": discussion,
            "recipients": discussion.recipients.all(),
            "comments": discussion.comments.select_related("author"),
            "comment_form": comment_form,
            "staff_view": True,
        },
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_discussions(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q

    student_id = _current_student_id(request)
    now = timezone.now()
    recipients = (
        DiscussionRecipient.objects.select_related("discussion", "discussion__created_by", "discussion__group")
        .filter(
            student_id=student_id,
            discussion__is_published=True,
        )
        .filter(Q(discussion__available_from__isnull=True) | Q(discussion__available_from__lte=now))
        .order_by("discussion__due_at", "discussion__id")
    )
    return render(
        request,
        "learning/my_discussions.html",
        {"page_title": "내 토론", "recipients": recipients, "student_id": student_id},
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_discussion_detail(request: HttpRequest, recipient_id: int) -> HttpResponse:
    from django.db.models import Q

    student_id = _current_student_id(request)
    recipient = get_object_or_404(
        DiscussionRecipient.objects.select_related("discussion", "discussion__created_by", "discussion__group").filter(
            Q(discussion__available_from__isnull=True) | Q(discussion__available_from__lte=timezone.now())
        ),
        pk=recipient_id,
        student_id=student_id,
        discussion__is_published=True,
    )
    discussion = recipient.discussion
    can_comment = request.user.role == User.Role.STUDENT and discussion.can_comment
    form = DiscussionCommentForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if not can_comment:
            raise PermissionDenied("학부모이거나 댓글 마감 이후에는 댓글을 등록할 수 없습니다.")
        if form.is_valid():
            comment = form.save(commit=False)
            comment.discussion = discussion
            comment.author = request.user
            comment.student_id = student_id
            comment.save()
            messages.success(request, "토론 댓글을 등록했습니다.")
            return redirect("learning:my-discussion-detail", recipient_id=recipient.pk)
    return render(
        request,
        "learning/discussion_detail.html",
        {
            "page_title": discussion.title,
            "discussion": discussion,
            "recipient": recipient,
            "comments": discussion.comments.select_related("author"),
            "comment_form": form,
            "can_comment": can_comment,
            "staff_view": False,
        },
    )


@class_staff_required
def quiz_list(request: HttpRequest) -> HttpResponse:
    quizzes = _staff_queryset(
        Quiz.objects.select_related("created_by", "group").prefetch_related("recipients", "questions", "recipients__attempts"),
        request.user,
    )
    rows = []
    for quiz in quizzes:
        recipients = list(quiz.recipients.all())
        rows.append(
            {
                "quiz": quiz,
                "recipient_count": len(recipients),
                "attempt_count": sum(recipient.attempts.count() for recipient in recipients),
                "question_count": quiz.questions.count(),
            }
        )
    return render(request, "learning/quiz_list.html", {"page_title": "퀴즈", "quiz_rows": rows})


@class_staff_required
def quiz_create(request: HttpRequest) -> HttpResponse:
    from apps.lms.integrations import activity_initial
    form = QuizForm(request.POST or None, user=request.user,initial=activity_initial(request))
    if request.method == "POST" and form.is_valid():
        try:
            quiz = save_quiz(form=form, user=request.user)
        except QuizQuestionsError as error:
            form.add_error(None, error)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            messages.success(request, "퀴즈를 등록했습니다." if quiz.questions.exists() else "퀴즈를 등록했습니다. 문항을 추가해 주세요.")
            return redirect("learning:quiz-detail", quiz_id=quiz.pk)
    return render(
        request,
        "learning/quiz_form.html",
        {
            "page_title": "퀴즈 등록",
            "form": form,
            "form_mode": "create",
            "builder": quiz_builder_data(form),
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
            ),
        },
    )


@class_staff_required
def quiz_update(request: HttpRequest, quiz_id: int) -> HttpResponse:
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    ensure_manageable(request.user, quiz)
    form = QuizForm(request.POST or None, instance=quiz, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            quiz = save_quiz(form=form, user=request.user)
        except QuizQuestionsError as error:
            form.add_error(None, error)
        except UnknownStudentsError as error:
            form.add_error("student_ids", error)
        except DatabaseError:
            form.add_error(
                "student_ids",
                "학생 정보를 확인하지 못했습니다. 잠시 후 다시 검색해 주세요.",
            )
        else:
            messages.success(request, "퀴즈를 수정했습니다.")
            return redirect("learning:quiz-list")  # 11/19: 고치면 퀴즈 목록으로(새 퀴즈는 문항 넣으러 퀴즈 화면)
    return render(
        request,
        "learning/quiz_form.html",
        {
            "page_title": "퀴즈 수정",
            "form": form,
            "form_mode": "update",
            "builder": quiz_builder_data(form),
            "quiz": quiz,
            "student_selector": build_student_selector_context(
                form=form,
                user=request.user,
                recipients=quiz.recipients.all(),
            ),
        },
    )


@class_staff_required
def quiz_detail(request: HttpRequest, quiz_id: int) -> HttpResponse:
    quiz = get_object_or_404(
        Quiz.objects.select_related("created_by", "group").prefetch_related(
            "questions__choices", "recipients__attempts"
        ),
        pk=quiz_id,
    )
    ensure_manageable(request.user, quiz)
    return render(
        request,
        "learning/quiz_detail.html",
        {
            "page_title": quiz.title,
            "quiz": quiz,
            "questions": quiz.questions.all(),
            "recipients": quiz.recipients.all(),
        },
    )


@class_staff_required
def quiz_question_create(request: HttpRequest, quiz_id: int) -> HttpResponse:
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    ensure_manageable(request.user, quiz)
    form = QuizQuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        save_quiz_question(form=form, quiz=quiz)
        messages.success(request, "문항을 추가했습니다.")
        return redirect("learning:quiz-detail", quiz_id=quiz.pk)
    return render(
        request,
        "learning/quiz_question_form.html",
        {"page_title": "퀴즈 문항 추가", "quiz": quiz, "form": form, "editor": form.editor()},
    )


@class_staff_required
def quiz_question_update(request: HttpRequest, quiz_id: int, question_id: int) -> HttpResponse:
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    ensure_manageable(request.user, quiz)
    question = get_object_or_404(QuizQuestion, pk=question_id, quiz=quiz)
    form = QuizQuestionForm(request.POST or None, instance=question)
    if request.method == "POST" and form.is_valid():
        save_quiz_question(form=form, quiz=quiz)
        messages.success(request, "문항을 수정했습니다.")
        return redirect("learning:quiz-detail", quiz_id=quiz.pk)
    return render(
        request,
        "learning/quiz_question_form.html",
        {"page_title": "퀴즈 문항 수정", "quiz": quiz, "question": question, "form": form, "editor": form.editor()},
    )


@class_staff_required
@require_POST
def quiz_question_delete(request: HttpRequest, quiz_id: int, question_id: int) -> HttpResponse:
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    ensure_manageable(request.user, quiz)
    get_object_or_404(QuizQuestion, pk=question_id, quiz=quiz).delete()
    messages.success(request, "문항을 삭제했습니다.")
    return redirect("learning:quiz-detail", quiz_id=quiz.pk)


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_quizzes(request: HttpRequest) -> HttpResponse:
    from django.db.models import Q

    student_id = _current_student_id(request)
    now = timezone.now()
    recipients = (
        QuizRecipient.objects.select_related("quiz", "quiz__created_by", "quiz__group")
        .prefetch_related("attempts")
        .filter(student_id=student_id, quiz__is_published=True)
        .filter(Q(quiz__available_from__isnull=True) | Q(quiz__available_from__lte=now))
        .order_by("quiz__due_at", "quiz__id")
    )
    return render(
        request,
        "learning/my_quizzes.html",
        {"page_title": "내 퀴즈", "recipients": recipients, "student_id": student_id},
    )


@role_required(User.Role.STUDENT, User.Role.PARENT)
def my_quiz_detail(request: HttpRequest, recipient_id: int) -> HttpResponse:
    from django.db.models import Q

    student_id = _current_student_id(request)
    recipient = get_object_or_404(
        QuizRecipient.objects.select_related("quiz", "quiz__created_by", "quiz__group")
        .prefetch_related("quiz__questions__choices", "attempts__answers" )
        .filter(Q(quiz__available_from__isnull=True) | Q(quiz__available_from__lte=timezone.now())),
        pk=recipient_id,
        student_id=student_id,
        quiz__is_published=True,
    )
    quiz = recipient.quiz
    attempts = recipient.attempts.prefetch_related("answers").all()
    can_attempt = (
        request.user.role == User.Role.STUDENT
        and quiz.can_attempt
        and attempts.count() < quiz.max_attempts
        and quiz.questions.exists()
    )

    if request.method == "POST":
        if not can_attempt:
            raise PermissionDenied("현재는 이 퀴즈에 응시할 수 없습니다.")
        with transaction.atomic():
            locked_recipient = QuizRecipient.objects.select_for_update().get(pk=recipient.pk)
            attempt_count = locked_recipient.attempts.count()
            if attempt_count >= quiz.max_attempts or not quiz.can_attempt:
                raise PermissionDenied("응시 가능 횟수 또는 기간을 초과했습니다.")
            attempt = QuizAttempt.objects.create(
                recipient=locked_recipient,
                user=request.user,
                attempt_no=attempt_count + 1,
                submitted_at=timezone.now(),
            )
            score = Decimal("0")
            max_score = Decimal("0")
            for question in quiz.questions.prefetch_related("choices").all():
                max_score += Decimal(question.points)
                response = quiz_types.read_response(question, request.POST)
                selected_choice = next((c for c in question.choices.all() if c.pk == response.get("choice")), None)
                if "choice" in response and selected_choice is None:
                    response = {}
                earned = quiz_types.grade(question, response)
                QuizAnswer.objects.create(
                    attempt=attempt,
                    question=question,
                    selected_choice=selected_choice,
                    text_answer=response.get("text", "") if question.question_type == QuizQuestion.Type.SHORT_ANSWER else "",
                    response=response,
                    earned_points=earned,
                )
                score += earned
            attempt.score = score
            attempt.max_score = max_score
            attempt.save(update_fields=("score", "max_score"))
        messages.success(request, "퀴즈 답안을 제출했습니다.")
        return redirect("learning:my-quiz-detail", recipient_id=recipient.pk)

    return render(
        request,
        "learning/my_quiz_detail.html",
        {
            "page_title": quiz.title,
            "recipient": recipient,
            "quiz": quiz,
            # 학생 화면용: 순서 항목은 항상 섞고, 짝 보기·범주 항목·단어 은행도 열 때마다 섞습니다.
            "questions": [(question, quiz_types.prepare(question, random.Random()))
                          for question in quiz.questions.prefetch_related("choices").all()] if can_attempt else [],
            "attempts": attempts,
            "can_attempt": can_attempt,
        },
    )
