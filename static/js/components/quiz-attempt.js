/* 퀴즈 응시 화면의 끌어 놓기.
   - 순서 맞추기: 항목을 끌거나 ▲▼ 버튼으로 옮깁니다. 숨은 칸의 순서가 곧 제출 순서입니다.
   - 범주화: 항목을 범주 상자로 끌어 넣습니다. 휴대폰·키보드는 항목을 누른 뒤 상자를 누릅니다(Enter·Space). 숨은 칸 값 = 범주 id. */
(() => {
  'use strict';
  const flash = node => { node.classList.remove('is-moved'); void node.offsetWidth; node.classList.add('is-moved'); setTimeout(() => node.classList.remove('is-moved'), 600); };

  document.querySelectorAll('[data-quiz-order]').forEach(list => {
    let dragging = null;
    list.addEventListener('click', event => {
      const button = event.target.closest('[data-move]');
      if (!button) return;
      const item = button.closest('li');
      const target = Number(button.dataset.move) < 0 ? item.previousElementSibling : item.nextElementSibling?.nextElementSibling;
      if (Number(button.dataset.move) < 0 && !target) return;
      if (Number(button.dataset.move) > 0 && !item.nextElementSibling) return;
      list.insertBefore(item, target || null);
      flash(item);
      button.focus();
    });
    list.addEventListener('dragstart', event => {
      dragging = event.target.closest('li');
      if (!dragging) return;
      dragging.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', '');
    });
    list.addEventListener('dragover', event => {
      if (!dragging) return;
      event.preventDefault();
      const over = event.target.closest('li');
      if (!over || over === dragging) return;
      const box = over.getBoundingClientRect();
      list.insertBefore(dragging, event.clientY > box.top + box.height / 2 ? over.nextElementSibling : over);
    });
    list.addEventListener('dragend', () => { if (dragging) { dragging.classList.remove('is-dragging'); flash(dragging); } dragging = null; });
  });

  document.querySelectorAll('[data-quiz-category]').forEach(root => {
    let selected = null, dragging = null;
    const select = chip => {
      if (selected) selected.setAttribute('aria-pressed', 'false');
      selected = chip === selected ? null : chip;
      if (selected) selected.setAttribute('aria-pressed', 'true');
      root.classList.toggle('has-selection', !!selected);
    };
    const place = (chip, zone) => {
      zone.querySelector('.quiz-zone-items').append(chip);
      chip.querySelector('input').value = zone.dataset.zone;
      flash(chip);
    };
    root.querySelectorAll('[data-item]').forEach(chip => chip.setAttribute('aria-pressed', 'false'));
    root.addEventListener('click', event => {
      const chip = event.target.closest('[data-item]');
      if (chip) { event.stopPropagation(); select(chip); return; }
      const zone = event.target.closest('[data-zone]');
      if (zone && selected) { place(selected, zone); select(selected); }
    });
    root.addEventListener('keydown', event => {
      const zone = event.target.closest('.quiz-bin');
      if (zone && selected && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); place(selected, zone); select(selected); }
    });
    root.addEventListener('dragstart', event => {
      dragging = event.target.closest('[data-item]');
      if (dragging) { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', ''); }
    });
    root.addEventListener('dragover', event => {
      const zone = event.target.closest('[data-zone]');
      if (!dragging || !zone) return;
      event.preventDefault();
      root.querySelectorAll('.is-target').forEach(node => node.classList.toggle('is-target', node === zone));
      zone.classList.add('is-target');
    });
    root.addEventListener('drop', event => {
      const zone = event.target.closest('[data-zone]');
      if (dragging && zone) { event.preventDefault(); place(dragging, zone); }
    });
    root.addEventListener('dragend', () => { dragging = null; root.querySelectorAll('.is-target').forEach(node => node.classList.remove('is-target')); });
  });
})();
