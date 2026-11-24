from __future__ import annotations

import csv
import io

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import admin_required

from .forms import AssignmentImportUploadForm, UserImportUploadForm
from .models import ImportBatch
from .services import (
    ASSIGNMENT_HEADERS,
    USER_HEADERS,
    ImportValidationError,
    apply_assignment_import,
    apply_user_import,
    build_batch_result_csv,
    build_credentials_csv,
    preview_assignment_import,
    preview_user_import,
)


def _csv_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _template_csv(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


@admin_required
def import_dashboard(request: HttpRequest) -> HttpResponse:
    batches = ImportBatch.objects.select_related("actor")[:12]
    context = {
        "page_title": "데이터 이전 센터",
        "batches": batches,
        "total_batch_count": ImportBatch.objects.count(),
        "completed_count": ImportBatch.objects.filter(
            status=ImportBatch.Status.COMPLETED
        ).count(),
        "error_batch_count": ImportBatch.objects.filter(
            status__in=(
                ImportBatch.Status.FAILED,
                ImportBatch.Status.COMPLETED_WITH_ERRORS,
            )
        ).count(),
        "user_batch_count": ImportBatch.objects.filter(
            kind=ImportBatch.Kind.USERS
        ).count(),
        "assignment_batch_count": ImportBatch.objects.filter(
            kind=ImportBatch.Kind.ASSIGNMENTS
        ).count(),
    }
    return render(request, "data_imports/dashboard.html", context)


@admin_required
def user_import(request: HttpRequest) -> HttpResponse:
    preview = None
    form = UserImportUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "preview")
        uploaded = form.cleaned_data["csv_file"]
        mode = form.cleaned_data["mode"]
        try:
            if action == "apply":
                form.require_apply_confirmation()
                if form.errors:
                    raise ImportValidationError("실제 반영 확인이 필요합니다.")
                outcome = apply_user_import(
                    uploaded,
                    mode=mode,
                    actor=request.user,
                )
                if outcome.batch.status == ImportBatch.Status.FAILED:
                    messages.error(request, "검증 오류로 계정 일괄등록을 실행하지 않았습니다.")
                    return redirect("data_imports:batch-detail", batch_id=outcome.batch.pk)
                if outcome.credentials:
                    response = _csv_response(
                        build_credentials_csv(outcome.credentials),
                        f"edutrack_initial_credentials_batch_{outcome.batch.pk}.csv",
                    )
                    response["X-Import-Batch-Id"] = str(outcome.batch.pk)
                    return response
                messages.success(request, "사용자 일괄등록을 완료했습니다.")
                return redirect("data_imports:batch-detail", batch_id=outcome.batch.pk)

            preview = preview_user_import(uploaded, mode=mode, actor=request.user)
        except ImportValidationError as error:
            form.add_error("csv_file", str(error))

    return render(
        request,
        "data_imports/user_import.html",
        {
            "page_title": "사용자 일괄등록",
            "form": form,
            "preview": preview,
        },
    )


@admin_required
def assignment_import(request: HttpRequest) -> HttpResponse:
    preview = None
    form = AssignmentImportUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "preview")
        uploaded = form.cleaned_data["csv_file"]
        mode = form.cleaned_data["mode"]
        try:
            if action == "apply":
                form.require_apply_confirmation()
                if form.errors:
                    raise ImportValidationError("실제 반영 확인이 필요합니다.")
                outcome = apply_assignment_import(
                    uploaded,
                    mode=mode,
                    actor=request.user,
                )
                if outcome.batch.status == ImportBatch.Status.FAILED:
                    messages.error(request, "검증 오류로 기존 과제 이전을 실행하지 않았습니다.")
                else:
                    messages.success(request, "기존 과제·제출 이력 이전을 완료했습니다.")
                return redirect("data_imports:batch-detail", batch_id=outcome.batch.pk)

            preview = preview_assignment_import(uploaded, mode=mode)
        except ImportValidationError as error:
            form.add_error("csv_file", str(error))

    return render(
        request,
        "data_imports/assignment_import.html",
        {
            "page_title": "기존 과제 데이터 이전",
            "form": form,
            "preview": preview,
        },
    )


@admin_required
def batch_detail(request: HttpRequest, batch_id: int) -> HttpResponse:
    batch = get_object_or_404(ImportBatch.objects.select_related("actor"), pk=batch_id)
    rows = batch.row_results.all()[:500]
    return render(
        request,
        "data_imports/batch_detail.html",
        {
            "page_title": f"이전 작업 #{batch.pk}",
            "batch": batch,
            "rows": rows,
            "row_limit_reached": batch.row_results.count() > 500,
        },
    )


@admin_required
def batch_results(request: HttpRequest, batch_id: int) -> HttpResponse:
    batch = get_object_or_404(ImportBatch, pk=batch_id)
    return _csv_response(
        build_batch_result_csv(batch),
        f"edutrack_import_batch_{batch.pk}_results.csv",
    )


@admin_required
def user_template(request: HttpRequest) -> HttpResponse:
    return _csv_response(
        _template_csv(USER_HEADERS, ()),
        "edutrack_user_import_template.csv",
    )


@admin_required
def user_example(request: HttpRequest) -> HttpResponse:
    rows = [
        (
            "student_3228",
            "김민준",
            "student@example.com",
            "STUDENT",
            "3228",
            "Y",
            "1234",
        ),
        (
            "parent_3228",
            "김민준 학부모",
            "parent@example.com",
            "PARENT",
            "3228",
            "Y",
            "1234",
        ),
        (
            "teacher_sample",
            "김강사",
            "teacher@example.com",
            "TEACHER",
            "",
            "",
            "1234",
        ),
    ]
    return _csv_response(
        _template_csv(USER_HEADERS, rows),
        "edutrack_user_import_example.csv",
    )


@admin_required
def assignment_template(request: HttpRequest) -> HttpResponse:
    rows = [
        (
            "LEGACY-HW-0001",
            "문법 오답 정리",
            "틀린 문항의 근거와 수정 이유를 작성하세요.",
            "2026-08-31 23:59",
            "teacher_test",
            "3228",
            "김민준",
            "Y",
            "2026-08-29 20:10",
            "오답 정리를 완료했습니다.",
            "근거가 명확합니다.",
            "teacher_test",
            "2026-08-30 10:00",
        ),
    ]
    return _csv_response(
        _template_csv(ASSIGNMENT_HEADERS, rows),
        "edutrack_legacy_assignment_import_template.csv",
    )
