/* DSG 최근 시험 카드: Exam 시험 / Module 시험 탭 (assessments/_score_attempts_card.html) */
(() => {
  'use strict';
  document.querySelectorAll('[data-score-tabs]').forEach(card => {
    if (card.dataset.tabsReady) return;
    card.dataset.tabsReady = 'true';
    const tabs = card.querySelectorAll('[data-score-tab]');
    const show = name => {
      tabs.forEach(tab => tab.setAttribute('aria-selected', String(tab.dataset.scoreTab === name)));
      card.querySelectorAll('[data-score-panel]').forEach(panel => { panel.hidden = panel.dataset.scorePanel !== name; });
    };
    tabs.forEach(tab => tab.addEventListener('click', () => show(tab.dataset.scoreTab)));
  });
})();
