/* EduTrack intranet-v2: scoped navigation, no business-data mutations. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const button = document.querySelector("[data-mobile-menu-button]");
  const sidebar = document.querySelector("[data-mobile-menu]");
  const overlay = document.querySelector("[data-mobile-menu-overlay]");
  const closeButton = document.querySelector("[data-mobile-menu-close]");
  const narrow = window.matchMedia("(max-width: 1024px)");
  const focusable = () => sidebar ? Array.from(sidebar.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), [tabindex="0"]'
  )).filter(node => node.getClientRects().length) : [];

  const setOpen = (open, restoreFocus = false) => {
    if (!button || !sidebar) return;
    const active = Boolean(open && narrow.matches);
    sidebar.classList.toggle("is-open", active);
    button.classList.toggle("is-open", active);
    button.setAttribute("aria-expanded", String(active));
    button.setAttribute("aria-label", active ? "메뉴 닫기" : "메뉴 열기");
    document.body.classList.toggle("intranet-nav-open", active);
    if (overlay) {
      overlay.hidden = !active;
      overlay.classList.toggle("is-open", active);
    }
    sidebar.inert = narrow.matches && !active;
    if (narrow.matches && !active) sidebar.setAttribute("aria-hidden", "true");
    else sidebar.removeAttribute("aria-hidden");
    if (active) {
      const first = focusable()[0];
      if (first) first.focus({preventScroll: true});
    } else if (restoreFocus && narrow.matches) button.focus({preventScroll: true});
  };
  if (button && sidebar) {
    setOpen(false);
    button.addEventListener("click", () => setOpen(!sidebar.classList.contains("is-open"), true));
    closeButton?.addEventListener("click", () => setOpen(false, true));
    overlay?.addEventListener("click", () => setOpen(false, true));
    sidebar.addEventListener("click", event => {
      if (event.target.closest("a")) setOpen(false);
    });
    narrow.addEventListener("change", () => setOpen(false));
    document.addEventListener("keydown", event => {
      if (!narrow.matches || !sidebar.classList.contains("is-open")) return;
      if (event.key === "Escape") { event.preventDefault(); setOpen(false, true); }
      if (event.key !== "Tab") return;
      const controls = focusable();
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }

  const search = document.querySelector(".intranet-topbar-search");
  if (search) document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault(); window.location.assign(search.href);
    }
  });
  document.querySelectorAll("[data-smart-back]").forEach(control => {
    control.addEventListener("click", event => {
      let valid = false;
      try {
        const referrer = new URL(document.referrer);
        valid = referrer.origin === window.location.origin &&
          !/\/accounts\/(?:login|logout)\//.test(referrer.pathname);
      } catch (_) { /* Empty referrer: keep the explicit fallback link. */ }
      if (valid && window.history.length > 1) {
        event.preventDefault(); window.history.back();
      }
    });
  });
  document.querySelectorAll("[data-confirm-message]").forEach(control => {
    control.addEventListener("click", event => {
      if (!window.confirm(control.dataset.confirmMessage || "이 작업을 진행할까요?")) event.preventDefault();
    });
  });
  document.querySelectorAll("[data-reveal]").forEach(node => node.classList.add("is-revealed"));
  const percentage = raw => {
    const value = Number(raw);
    return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
  };
  document.querySelectorAll("[data-progress-value]").forEach(node => { node.style.width = `${percentage(node.dataset.progressValue)}%`; });
  document.querySelectorAll("[data-ring-value]").forEach(node => { node.style.setProperty("--ring-value", `${percentage(node.dataset.ringValue) * 3.6}deg`); });
});

// 공지사항 하위 메뉴(11/10): 마우스를 올리면 CSS로 펼쳐지고, 화살표를 누르면(터치 화면 포함) 펼침·접힘을 고정합니다.
document.addEventListener("click", event => {
  const toggle = event.target.closest("[data-nav-flyout-toggle]");
  if (!toggle) return;
  const box = toggle.closest("[data-nav-flyout]");
  const open = !box.classList.contains("is-open");
  box.classList.toggle("is-open", open);
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
});
