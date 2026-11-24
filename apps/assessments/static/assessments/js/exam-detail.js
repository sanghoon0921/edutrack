document.addEventListener("DOMContentLoaded", () => {
  const viewer = document.querySelector(
    "[data-exam-question-viewer]"
  );

  const dataElement = document.getElementById(
    "exam-question-data"
  );

  if (!viewer || !dataElement) return;

  let questionList = [];

  try {
    questionList = JSON.parse(
      dataElement.textContent
    );
  } catch (error) {
    console.error(
      "시험 문항 데이터를 읽지 못했습니다.",
      error
    );
    return;
  }

  const questionMap = new Map(
    questionList.map((question) => [
      String(question.question_id),
      question,
    ])
  );

  const resultBadge = viewer.querySelector(
    "[data-question-result]"
  );
  const title = viewer.querySelector(
    "[data-question-title]"
  );
  const score = viewer.querySelector(
    "[data-question-score]"
  );
  const meta = viewer.querySelector(
    "[data-question-meta]"
  );
  const questionText = viewer.querySelector(
    "[data-question-text]"
  );
  const mediaLink = viewer.querySelector(
    "[data-question-media]"
  );
  const choices = viewer.querySelector(
    "[data-question-choices]"
  );
  const studentAnswer = viewer.querySelector(
    "[data-student-answer]"
  );
  const correctAnswer = viewer.querySelector(
    "[data-correct-answer]"
  );
  const annotationWrap = viewer.querySelector(
    "[data-question-annotation-wrap]"
  );
  const annotation = viewer.querySelector(
    "[data-question-annotation]"
  );

  const filterButtons = Array.from(
    viewer.querySelectorAll(
      "[data-question-filter]"
    )
  );

  const questionEntries = Array.from(
    viewer.querySelectorAll(
      "[data-question-entry]"
    )
  );

  const filterEmpty = viewer.querySelector(
    "[data-question-filter-empty]"
  );

  let activeFilter = "all";
  let selectedQuestionId = null;

  const escapeHtml = (value) => {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
  };

  const renderMeta = (question) => {
    const values = [
      question.topic,
      question.section_name,
      question.module_name,
      question.duration_label,
    ];

    if (question.bookmark) {
      values.push("북마크");
    }

    meta.innerHTML = values
      .filter(Boolean)
      .map(
        (value) => `<span>${escapeHtml(value)}</span>`
      )
      .join("");
  };

  const renderChoices = (question) => {
    choices.innerHTML = (
      question.choices || []
    )
      .map((choice) => {
        const classes = [
          "exam-choice",
          choice.is_correct
            ? "is-correct"
            : "",
          choice.is_selected
            ? "is-selected"
            : "",
        ]
          .filter(Boolean)
          .join(" ");

        const labels = [
          choice.is_selected
            ? "<small>학생 선택</small>"
            : "",
          choice.is_correct
            ? "<small>정답</small>"
            : "",
        ].join("");

        return `
          <article class="${classes}">
            <span>${escapeHtml(choice.choice_no)}</span>
            <p>${escapeHtml(choice.content)}</p>
            <div>${labels}</div>
          </article>
        `;
      })
      .join("");

    choices.classList.toggle(
      "is-hidden",
      !(question.choices || []).length
    );
  };

  const selectQuestion = (
    questionId,
    updateHistory = true
  ) => {
    const question = questionMap.get(
      String(questionId)
    );

    if (!question) return;

    selectedQuestionId = String(
      questionId
    );

    viewer
      .querySelectorAll("[data-question-select]")
      .forEach((button) => {
        button.classList.toggle(
          "is-selected",
          button.dataset.questionSelect
            === String(questionId)
        );
      });

    resultBadge.className =
      `exam-result-badge is-${question.result_class}`;

    resultBadge.textContent =
      question.result_label;

    title.textContent =
      `${question.question_no}번 문항`;

    score.className =
      `exam-question-status-text is-${question.result_class}`;

    score.textContent =
      question.result_label;

    renderMeta(question);

    questionText.textContent =
      question.question_text
      || "문제 내용이 없습니다.";

    if (question.media_url) {
      mediaLink.href = question.media_url;
      mediaLink.classList.remove("is-hidden");
    } else {
      mediaLink.href = "#";
      mediaLink.classList.add("is-hidden");
    }

    renderChoices(question);

    const mathTargets = [
      questionText,
      choices,
    ];

    if (
      window.MathJax
      && typeof window.MathJax.typesetPromise
        === "function"
    ) {
      if (
        typeof window.MathJax.typesetClear
        === "function"
      ) {
        window.MathJax.typesetClear(
          mathTargets
        );
      }

      window.MathJax.typesetPromise(
        mathTargets
      ).catch((error) => {
        console.warn(
          "수식 렌더링을 완료하지 못했습니다.",
          error
        );
      });
    }

    studentAnswer.textContent =
      question.selected_answer
      || "무응답";

    correctAnswer.textContent =
      question.correct_answer
      || "정답 미등록";

    if (question.annotation) {
      annotation.textContent =
        question.annotation;
      annotationWrap.classList.remove(
        "is-hidden"
      );
    } else {
      annotation.textContent = "";
      annotationWrap.classList.add(
        "is-hidden"
      );
    }

    if (updateHistory) {
      const url = new URL(
        window.location.href
      );

      url.searchParams.set(
        "question",
        String(questionId)
      );

      if (activeFilter === "all") {
        url.searchParams.delete(
          "filter"
        );
      } else {
        url.searchParams.set(
          "filter",
          activeFilter
        );
      }

      url.searchParams.delete("refresh");

      window.history.replaceState(
        {},
        "",
        url
      );
    }
  };

  viewer
    .querySelectorAll("[data-question-select]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        selectQuestion(
          button.dataset.questionSelect
        );
      });
    });

  const filterMatches = (
    entry,
    filterName
  ) => {
    const status =
      entry.dataset.questionStatus;

    if (filterName === "all") {
      return true;
    }

    if (filterName === "review") {
      return [
        "wrong",
        "partial",
        "unanswered",
        "free-response",
      ].includes(status);
    }

    if (filterName === "slow") {
      return (
        entry.dataset.questionSlow
        === "1"
      );
    }

    return status === filterName;
  };

  const visibleQuestionIds = () => {
    return Array.from(
      viewer.querySelectorAll(
        ".exam-question-row[data-question-entry]:not(.is-hidden)"
      )
    ).map(
      (entry) =>
        String(
          entry.dataset.questionSelect
        )
    );
  };

  const applyFilter = (
    filterName,
    updateHistory = true
  ) => {
    activeFilter = filterName;

    filterButtons.forEach((button) => {
      button.classList.toggle(
        "is-active",
        button.dataset.questionFilter
          === filterName
      );
    });

    questionEntries.forEach((entry) => {
      entry.classList.toggle(
        "is-hidden",
        !filterMatches(
          entry,
          filterName
        )
      );
    });

    const visibleIds =
      visibleQuestionIds();

    if (filterEmpty) {
      filterEmpty.classList.toggle(
        "is-hidden",
        visibleIds.length > 0
      );
    }

    if (
      visibleIds.length > 0
      && !visibleIds.includes(
        String(selectedQuestionId)
      )
    ) {
      selectQuestion(
        visibleIds[0],
        false
      );
    }

    if (updateHistory) {
      const url = new URL(
        window.location.href
      );

      if (filterName === "all") {
        url.searchParams.delete(
          "filter"
        );
      } else {
        url.searchParams.set(
          "filter",
          filterName
        );
      }

      if (selectedQuestionId) {
        url.searchParams.set(
          "question",
          selectedQuestionId
        );
      }

      url.searchParams.delete(
        "refresh"
      );

      window.history.replaceState(
        {},
        "",
        url
      );
    }
  };

  filterButtons.forEach((button) => {
    button.addEventListener(
      "click",
      () => {
        applyFilter(
          button.dataset.questionFilter
        );
      }
    );
  });

  document.addEventListener(
    "keydown",
    (event) => {
      if (
        event.target instanceof
          HTMLInputElement
        || event.target instanceof
          HTMLTextAreaElement
        || event.target.isContentEditable
      ) {
        return;
      }

      if (
        event.key !== "ArrowLeft"
        && event.key !== "ArrowRight"
      ) {
        return;
      }

      const visibleIds =
        visibleQuestionIds();

      if (!visibleIds.length) {
        return;
      }

      const currentIndex =
        visibleIds.indexOf(
          String(selectedQuestionId)
        );

      const direction =
        event.key === "ArrowRight"
          ? 1
          : -1;

      const nextIndex =
        currentIndex === -1
          ? 0
          : (
              currentIndex
              + direction
              + visibleIds.length
            ) % visibleIds.length;

      event.preventDefault();

      selectQuestion(
        visibleIds[nextIndex]
      );
    }
  );

  const url = new URL(
    window.location.href
  );

  const initialFilter =
    url.searchParams.get(
      "filter"
    )
    || "all";

  const initialId =
    viewer.dataset.selectedQuestion
    || questionList[0]?.question_id;

  if (initialId) {
    selectQuestion(
      initialId,
      false
    );
  }

  applyFilter(
    [
      "all",
      "review",
      "correct",
      "wrong",
      "unanswered",
      "slow",
    ].includes(initialFilter)
      ? initialFilter
      : "all",
    false
  );
});
