(() => {
  "use strict";

  const EDITOR_SELECTOR = "textarea[data-rich-paste-editor]";
  const ACCEPTED = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);

  function csrfToken(editor) {
    const form = editor.closest("form");
    const input = form ? form.querySelector('input[name="csrfmiddlewaretoken"]') : null;
    return input ? input.value : "";
  }

  function insertAtCursor(editor, value) {
    const start = Number.isInteger(editor.selectionStart) ? editor.selectionStart : editor.value.length;
    const end = Number.isInteger(editor.selectionEnd) ? editor.selectionEnd : start;
    const prefix = editor.value.slice(0, start);
    const suffix = editor.value.slice(end);
    const leading = prefix && !prefix.endsWith("\n") ? "\n" : "";
    const trailing = suffix && !suffix.startsWith("\n") ? "\n" : "";
    const insertion = `${leading}${value}${trailing}`;
    editor.value = `${prefix}${insertion}${suffix}`;
    const cursor = prefix.length + insertion.length;
    editor.setSelectionRange(cursor, cursor);
    editor.dispatchEvent(new Event("input", { bubbles: true }));
    editor.focus();
  }

  function setStatus(wrapper, message, kind = "") {
    const status = wrapper.querySelector("[data-rich-paste-status]");
    if (!status) return;
    status.textContent = message;
    status.dataset.kind = kind;
  }

  function addPreview(wrapper, payload) {
    const strip = wrapper.querySelector("[data-rich-paste-preview-list]");
    if (!strip) return;
    const item = document.createElement("figure");
    item.className = "rich-paste-preview-item";
    const image = document.createElement("img");
    image.src = String(payload.preview_url || "");
    image.alt = "붙여넣은 이미지 미리보기";
    image.loading = "lazy";
    const caption = document.createElement("figcaption");
    caption.textContent = String(payload.name || "붙여넣은 이미지");
    item.append(image, caption);
    strip.append(item);
  }

  async function uploadImage(editor, wrapper, file) {
    const uploadUrl = editor.dataset.richPasteUploadUrl;
    if (!uploadUrl) throw new Error("이미지 업로드 주소가 설정되지 않았습니다.");
    if (!ACCEPTED.has(file.type)) throw new Error("PNG, JPG, GIF, WEBP 이미지만 사용할 수 있습니다.");

    const body = new FormData();
    body.append("image", file, file.name || `pasted-${Date.now()}.png`);
    const response = await fetch(uploadUrl, {
      method: "POST",
      body,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-CSRFToken": csrfToken(editor),
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || "이미지 업로드에 실패했습니다.");
    insertAtCursor(editor, payload.token);
    addPreview(wrapper, payload);
    return payload;
  }

  async function handleFiles(editor, wrapper, files) {
    const images = Array.from(files || []).filter((file) => ACCEPTED.has(file.type));
    if (!images.length) return false;
    setStatus(wrapper, `이미지 ${images.length}장을 업로드하는 중입니다…`, "loading");
    editor.setAttribute("aria-busy", "true");
    try {
      for (const file of images) {
        await uploadImage(editor, wrapper, file);
      }
      setStatus(wrapper, `이미지 ${images.length}장을 본문에 넣었습니다.`, "success");
    } catch (error) {
      setStatus(wrapper, error instanceof Error ? error.message : "이미지 업로드에 실패했습니다.", "error");
    } finally {
      editor.removeAttribute("aria-busy");
    }
    return true;
  }

  function buildWrapper(editor) {
    if (editor.closest("[data-rich-paste-wrapper]")) return editor.closest("[data-rich-paste-wrapper]");
    const wrapper = document.createElement("div");
    wrapper.className = "rich-paste-editor";
    wrapper.dataset.richPasteWrapper = "true";
    editor.parentNode.insertBefore(wrapper, editor);
    wrapper.append(editor);

    const helper = document.createElement("div");
    helper.className = "rich-paste-toolbar";
    helper.innerHTML = `
      <div>
        <strong>사진 바로 붙여넣기</strong>
        <span>캡처하거나 복사한 사진을 본문에서 <kbd>Ctrl</kbd>+<kbd>V</kbd>로 붙여넣으세요.</span>
      </div>
      <label class="rich-paste-file-button">
        <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple data-rich-paste-file hidden>
        사진 선택
      </label>
    `;
    wrapper.insertBefore(helper, editor);

    const status = document.createElement("p");
    status.className = "rich-paste-status";
    status.dataset.richPasteStatus = "true";
    status.setAttribute("aria-live", "polite");
    status.textContent = "사진을 붙여넣으면 현재 커서 위치에 자동으로 들어갑니다.";
    wrapper.append(status);

    const previews = document.createElement("div");
    previews.className = "rich-paste-preview-list";
    previews.dataset.richPastePreviewList = "true";
    wrapper.append(previews);
    return wrapper;
  }

  function init(editor) {
    if (editor.dataset.richPasteReady === "true") return;
    editor.dataset.richPasteReady = "true";
    const wrapper = buildWrapper(editor);

    editor.addEventListener("paste", (event) => {
      const items = Array.from(event.clipboardData?.items || []);
      const files = items
        .filter((item) => item.kind === "file" && ACCEPTED.has(item.type))
        .map((item) => item.getAsFile())
        .filter(Boolean);
      if (!files.length) return;
      event.preventDefault();
      handleFiles(editor, wrapper, files);
    });

    editor.addEventListener("dragover", (event) => {
      const files = Array.from(event.dataTransfer?.items || []);
      if (files.some((item) => item.kind === "file" && ACCEPTED.has(item.type))) {
        event.preventDefault();
        wrapper.classList.add("is-dragging");
      }
    });
    editor.addEventListener("dragleave", () => wrapper.classList.remove("is-dragging"));
    editor.addEventListener("drop", (event) => {
      wrapper.classList.remove("is-dragging");
      const files = Array.from(event.dataTransfer?.files || []);
      if (!files.some((file) => ACCEPTED.has(file.type))) return;
      event.preventDefault();
      handleFiles(editor, wrapper, files);
    });

    const picker = wrapper.querySelector("[data-rich-paste-file]");
    picker?.addEventListener("change", () => {
      handleFiles(editor, wrapper, picker.files);
      picker.value = "";
    });
  }

  function initAll() {
    document.querySelectorAll(EDITOR_SELECTOR).forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll, { once: true });
  } else {
    initAll();
  }
})();
