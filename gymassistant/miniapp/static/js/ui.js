/**
 * Мелочи для сборки DOM.
 *
 * Фреймворка нет намеренно: экранов десяток, состояние живёт на сервере, а сборка
 * без npm — это ещё и отсутствие пайплайна, который надо чинить через полгода.
 */
import { haptic } from './tg.js';

export const root = document.getElementById('app');

/** Экранирование: имена упражнений пользователь вводит сам. */
export function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

export function render(html) {
  root.innerHTML = html;
  window.scrollTo(0, 0);
  return root;
}

export function loading() {
  render('<div class="center-screen"><div class="spinner"></div></div>');
}

export function errorScreen(message, retry) {
  render(`
    <div class="empty">
      <p>${escape(message)}</p>
      <button class="btn secondary small" id="retry">Ещё раз</button>
    </div>
  `);
  if (retry) on('#retry', 'click', retry);
}

/** Обработчик на первый совпавший элемент. */
export function on(selector, event, handler) {
  const node = root.querySelector(selector);
  if (node) node.addEventListener(event, handler);
  return node;
}

/** Обработчик на все совпавшие; в handler приезжает сам элемент. */
export function onAll(selector, event, handler) {
  root.querySelectorAll(selector).forEach((node) => {
    node.addEventListener(event, (e) => handler(node, e));
  });
}

/** Кнопки, которые что-то меняют на сервере: блокируем на время запроса. */
export function onAction(selector, handler) {
  onAll(selector, 'click', async (node, event) => {
    if (node.disabled) return;
    node.disabled = true;
    haptic('light');
    try {
      await handler(node, event);
    } finally {
      node.disabled = false;
    }
  });
}

export function plural(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} ${one}`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${n} ${few}`;
  return `${n} ${many}`;
}

export function clock(seconds) {
  const safe = Math.max(0, Math.round(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}

/** Вес: 60 вместо 60.0, но 62.5 остаётся 62.5. */
export function weight(value) {
  return Number(value).toFixed(1).replace(/\.0$/, '');
}

export function volume(kg) {
  return kg >= 1000 ? `${(kg / 1000).toFixed(1)} т` : `${Math.round(kg)} кг`;
}

export function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  });
}

/** Нижняя шторка — для форм, которые не заслуживают отдельного экрана. */
export function sheet(html) {
  const backdrop = document.createElement('div');
  backdrop.className = 'sheet-backdrop';
  backdrop.innerHTML = `<div class="sheet">${html}</div>`;
  document.body.appendChild(backdrop);

  const close = () => backdrop.remove();
  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();   // тап мимо шторки закрывает её
  });

  return { node: backdrop, close };
}
