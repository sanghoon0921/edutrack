(() => {
  "use strict";

  const TYPE_CONFIG = {
    PDF: {
      fileLabel: "PDF 파일 선택",
      fileHelp: "교재·문제집 PDF를 선택하세요. 업로드 시 실제 PDF 파일인지 자동 검사합니다.",
      accept: ".pdf,application/pdf",
      submit: "PDF 자료 등록",
      guide: "PDF 파일을 선택한 뒤 아래 ‘PDF 자료 등록’ 버튼을 누르면 등록이 완료됩니다.",
    },
    FILE: {
      fileLabel: "일반 파일 선택",
      fileHelp: "DOCX·XLSX·PPTX·TXT·CSV·이미지·ZIP 파일을 등록할 수 있습니다.",
      accept: ".doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.jpg,.jpeg,.png,.webp,.zip",
      submit: "파일 자료 등록",
      guide: "파일을 선택한 뒤 아래 ‘파일 자료 등록’ 버튼을 누르면 등록이 완료됩니다.",
    },
    LINK: {
      fileLabel: "파일 선택",
      fileHelp: "외부 링크 등록에서는 파일을 선택하지 않습니다.",
      accept: "",
      submit: "링크 자료 등록",
      guide: "외부 링크 주소를 입력한 뒤 아래 ‘링크 자료 등록’ 버튼을 누르세요.",
    },
  };

  function init(form) {
    if (form.dataset.resourceFormReady === "true") return;
    form.dataset.resourceFormReady = "true";

    const type = form.querySelector("[data-resource-type]");
    const file = form.querySelector("[data-resource-file]");
    const url = form.querySelector("[data-resource-url]");
    const fileField = form.querySelector("[data-resource-file-field]") || file?.closest(".workflow-field");
    const urlField = form.querySelector("[data-resource-url-field]") || url?.closest(".workflow-field");
    const fileLabel = form.querySelector("[data-resource-file-label]");
    const fileHelp = form.querySelector("[data-resource-file-help]");
    const guide = form.querySelector("[data-resource-submit-guide]");
    const submit = form.querySelector("[data-resource-submit-button]");
    const choices = Array.from(form.querySelectorAll("[data-resource-type-choice]"));

    if (!type || !file || !url || !fileField || !urlField) return;

    const update = () => {
      const selected = TYPE_CONFIG[type.value] ? type.value : "PDF";
      const config = TYPE_CONFIG[selected];
      const isLink = selected === "LINK";

      form.dataset.selectedType = selected;
      fileField.classList.toggle("is-hidden", isLink);
      urlField.classList.toggle("is-hidden", !isLink);
      file.required = !isLink && form.dataset.hasExistingFile !== "true";
      url.required = isLink;
      file.accept = config.accept;

      if (fileLabel) fileLabel.textContent = config.fileLabel;
      if (fileHelp) fileHelp.textContent = config.fileHelp;
      if (guide) guide.textContent = config.guide;
      if (submit && form.dataset.formMode !== "update") {
        submit.textContent = config.submit;
      }

      choices.forEach((choice) => {
        const active = choice.dataset.resourceTypeChoice === selected;
        choice.classList.toggle("is-active", active);
        choice.setAttribute("aria-pressed", active ? "true" : "false");
      });
    };

    choices.forEach((choice) => {
      choice.addEventListener("click", () => {
        const selected = choice.dataset.resourceTypeChoice || "PDF";
        if (!TYPE_CONFIG[selected]) return;
        type.value = selected;
        type.dispatchEvent(new Event("change", { bubbles: true }));
        if (selected === "LINK") {
          url.focus();
        } else {
          file.focus();
        }
      });
    });

    type.addEventListener("change", update);
    update();
  }

  function initAll() {
    document.querySelectorAll("form[data-course-resource-form]").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll, { once: true });
  } else {
    initAll();
  }
})();
