"""Current membership is checked on every read/write; no cached authorization."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from apps.accounts.models import User, StudentAccountLink
from apps.learning.models import LearningGroup
from apps.operations.access import is_admin, is_ta, is_teacher, learner_student_ids, teacher_student_ids
from .models import GroupMember, GroupStaff


def staff_group_ids(user):
    if not user.is_authenticated or not user.is_active:
        return LearningGroup.objects.none().values_list('pk', flat=True)
    if is_admin(user):
        return LearningGroup.objects.values_list('pk', flat=True)
    if is_ta(user):
        # TA 계정(11/17): '명단·TA 지정'에서 맡은 반에서만 과제 첨삭·댓글·과제 올리기를 합니다.
        return LearningGroup.objects.filter(lms_staff__user=user, lms_staff__active=True).distinct().values_list('pk', flat=True)
    if not is_teacher(user):
        return LearningGroup.objects.none().values_list('pk', flat=True)
    return LearningGroup.objects.filter(Q(created_by=user) | Q(lms_staff__user=user, lms_staff__active=True)).distinct().values_list('pk', flat=True)


def can_teach_group(user, group_id):
    return bool(group_id and staff_group_ids(user).filter(pk=group_id).exists())


def can_manage(user, obj):
    if not user.is_authenticated or not user.is_active:
        return False
    if is_admin(user):
        return True
    if not (is_teacher(user) or is_ta(user)):
        return False
    # Explicit TA/co-teacher appointment grants access only to this class.
    group_id = getattr(obj, 'group_id', None)
    if group_id:
        if GroupStaff.objects.filter(group_id=group_id, user=user, active=False).exists():
            return False  # revoked assistants cannot keep old author privileges
        return can_teach_group(user, group_id)
    return obj.created_by_id == user.pk


def staff_scope(qs, user):
    if is_admin(user):
        return qs
    return qs.filter(Q(group_id__in=staff_group_ids(user)) | Q(group__isnull=True, created_by=user)).distinct()


def visible_groups(user):
    if is_admin(user) or is_teacher(user) or is_ta(user):
        return LearningGroup.objects.filter(pk__in=staff_group_ids(user))
    return LearningGroup.objects.filter(lms_members__active=True, lms_members__student_no__in=learner_student_ids(user)).distinct()


def require_group(user, group, write=False, roster=False):
    if roster:
        if is_admin(user) or (is_teacher(user) and group.created_by_id == user.pk):
            return
        raise PermissionDenied('반 담당자 지정과 명단 변경은 관리자 또는 반 개설자만 가능합니다.')
    if write:
        if can_teach_group(user, group.pk):
            return
        raise PermissionDenied('이 반의 담당 강사·TA만 변경할 수 있습니다.')
    if not visible_groups(user).filter(pk=group.pk).exists():
        raise Http404('접근 가능한 반이 아닙니다.')


def require_submission(user, submission, write=False):
    assignment = submission.recipient.assignment
    if can_manage(user, assignment):
        return True
    if not write and assignment.is_available and submission.recipient.student_id in learner_student_ids(user):
        return False
    raise Http404('접근 가능한 제출물이 아닙니다.')


def require_attempt(user, attempt, write=False):
    quiz = attempt.recipient.quiz
    if can_manage(user, quiz):
        return True
    if not write and quiz.is_available and attempt.recipient.student_id in learner_student_ids(user):
        return False
    raise Http404('접근 가능한 퀴즈 응시가 아닙니다.')


def contacts_for(user):
    """Only active student self-links and currently assigned teaching staff."""
    if not user.is_authenticated or user.role == User.Role.PARENT:
        return User.objects.none()
    if is_admin(user):
        return User.objects.filter(is_active=True, role__in=[User.Role.TEACHER, User.Role.STUDENT]).exclude(pk=user.pk)
    if is_ta(user):
        # TA(11/19): 담당 반 학생 + 그 반의 개설 강사·공동 강사·TA
        groups = list(staff_group_ids(user))
        ids = set(GroupMember.objects.filter(group_id__in=groups, active=True).values_list('student_no', flat=True))
        students = User.objects.filter(is_active=True, role=User.Role.STUDENT, student_links__is_active=True,
          student_links__relationship=StudentAccountLink.Relationship.SELF, student_links__student_no__in=ids)
        staff = User.objects.filter(is_active=True, role__in=[User.Role.TEACHER, User.Role.TA]).filter(
          Q(created_learning_groups__pk__in=groups) | Q(lms_teaching_groups__group_id__in=groups, lms_teaching_groups__active=True))
        return User.objects.filter(pk__in=set(students.values_list('pk', flat=True)) | set(staff.values_list('pk', flat=True))).exclude(pk=user.pk)
    if is_teacher(user):
        ids = set(teacher_student_ids(user)) | set(GroupMember.objects.filter(
            group_id__in=staff_group_ids(user), active=True).values_list('student_no', flat=True))
        return User.objects.filter(is_active=True, role=User.Role.STUDENT, student_links__is_active=True,
          student_links__relationship=StudentAccountLink.Relationship.SELF, student_links__student_no__in=ids).distinct()
    ids = learner_student_ids(user)
    groups = GroupMember.objects.filter(active=True, student_no__in=ids).values_list('group_id', flat=True)
    return User.objects.filter(is_active=True, role__in=[User.Role.TEACHER, User.Role.TA]).filter(
      Q(teacher_student_accesses__student_no__in=ids, teacher_student_accesses__is_active=True)
      | Q(created_learning_groups__pk__in=groups)
      | Q(lms_teaching_groups__group_id__in=groups, lms_teaching_groups__active=True)).distinct()


def can_converse(user, conversation):
    if not user.is_authenticated or not user.is_active or user.role == User.Role.PARENT:
        return False
    if not conversation.participants.filter(user=user).exists():
        return False
    if conversation.group_id:
        return visible_groups(user).filter(pk=conversation.group_id).exists()
    # 반 없이 강사·관리자가 여러 명을 골라 만든 그룹 대화: 참여자라면 열 수 있습니다.
    if conversation.kind == 'GROUP' and conversation.participants.count() > 2:
        return True
    others = list(conversation.participants.exclude(user=user).values_list('user_id', flat=True))
    return len(others) == 1 and (contacts_for(user).filter(pk=others[0]).exists() or (
        User.objects.filter(pk=others[0], is_active=True, role=User.Role.ADMIN).exists()))
