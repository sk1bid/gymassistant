/**
 * Мелочи для сборки DOM.
 *
 * Фреймворка нет намеренно: экранов десяток, состояние живёт на сервере, а сборка
 * без npm — это ещё и отсутствие пайплайна, который надо чинить через полгода.
 */
import { haptic } from './tg.js';

/**
 * Две панели экрана.
 *
 * Одна показана, вторая ждёт. Во время свайпа соседний раздел рисуется в ждущую
 * и выезжает из-под пальца, а на переходе панели просто МЕНЯЮТСЯ РОЛЯМИ.
 * Содержимое при этом никуда не переносится — а значит, обработчики, навешанные
 * при отрисовке, остаются на своих узлах. Перенос innerHTML их бы потерял.
 */
const panes = [
  document.getElementById('screen-a'),
  document.getElementById('screen-b'),
];

let shown = 0;

/** Куда пишет render(). Обычно — показанная панель, во время свайпа — ждущая. */
let root = panes[0];

export function activePane() {
  return panes[shown];
}

export function idlePane() {
  return panes[1 - shown];
}

/**
 * Нарисовать что-то в указанную панель.
 *
 * Цель держится на всё время асинхронного вызова: экраны навешивают обработчики
 * уже после await, и on()/onAll() должны искать узлы там же, где рисовали.
 */
export async function withPane(pane, draw) {
  const previous = root;
  root = pane;
  try {
    await draw();
  } finally {
    root = previous;
  }
}

/** Ждущая панель становится показанной: свайп доведён до конца. */
export function swapPanes() {
  panes[shown].hidden = true;
  shown = 1 - shown;
  panes[shown].hidden = false;
  root = panes[shown];
}

/** Экранирование: имена упражнений пользователь вводит сам. */
export function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/**
 * Направление следующего перехода — его ставит роутер перед сменой экрана.
 *
 * Именно «намерение», а не свойство рендера: экран тренировки перерисовывает себя
 * после каждого записанного подхода, и если анимировать любой render(), приложение
 * будет дёргаться весь подход. Флаг одноразовый — перерисовки внутри экрана его
 * не видят и проходят без анимации.
 */
let pendingTransition = null;

export function setTransition(direction) {
  pendingTransition = direction;
}

/**
 * Моторика переходов.
 *
 * Кривая — «emphasized decelerate» из Material 3: резкий старт и долгий мягкий
 * выход. Именно длинный хвост читается как плавность; симметричная ease-in-out
 * на коротких дистанциях выглядит вяло.
 *
 * Возврат короче остальных: движение назад должно ощущаться дешевле, чем вперёд.
 */
const EASE_ENTER = 'cubic-bezier(.05, .7, .1, 1)';

const MOTION = {
  right:   { transform: 'translate3d(18px, 0, 0)',  duration: 280 },
  left:    { transform: 'translate3d(-18px, 0, 0)', duration: 280 },
  deep:    { transform: 'scale(.98)',               duration: 260 },
  shallow: { transform: 'scale(1.02)',              duration: 220 },
};

const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');

export function render(html) {
  const pane = root;
  pane.innerHTML = html;

  const direction = pendingTransition;
  pendingTransition = null;

  // Наверх прокручиваем только при СМЕНЕ экрана. Перерисовка на месте — свежие
  // данные поверх показанных из кэша, записанный подход — не должна утаскивать
  // пользователя от того места, куда он смотрел.
  if (direction) {
    window.scrollTo(0, 0);
    enter(pane, direction);
  }

  return pane;
}

/**
 * Анимация появления экрана.
 *
 * Через Web Animations API, а не переключением CSS-класса. Классовый вариант
 * требовал перезапуска анимации, а перезапуск — чтения offsetWidth, то есть
 * ПРИНУДИТЕЛЬНОГО синхронного пересчёта раскладки ровно после замены всего DOM.
 * Это самый дорогой момент кадра, и первые кадры анимации регулярно терялись —
 * получался рывок вместо движения. WAAPI обходится без этого и отдаёт анимацию
 * композитору.
 */
function enter(pane, direction) {
  const motion = MOTION[direction];
  if (!motion || !pane.animate || reducedMotion?.matches) return;

  pane.animate(
    [
      { opacity: 0, transform: motion.transform },
      { opacity: 1, transform: 'none' },
    ],
    { duration: motion.duration, easing: EASE_ENTER, fill: 'backwards' },
  );
}

/**
 * Спиннер.
 *
 * Намеренно мимо render(): он не должен съедать направление перехода — оно
 * принадлежит тому кадру, который принесёт содержимое. Иначе экран въезжал бы
 * дважды: сперва пустой с крутилкой, потом с данными.
 */
export function loading() {
  root.innerHTML = '<div class="center-screen"><div class="spinner"></div></div>';
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

/**
 * Одинаковы ли два ответа сервера.
 *
 * Сравнение по сериализации: данные тут — простые деревья из JSON, ключи в них
 * идут в одном и том же порядке (их собирает один и тот же код на сервере),
 * поэтому строковое сравнение и корректно, и заметно дешевле обхода.
 */
export function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Дата без времени и года — для подписей на осях графика, где места мало. */
export function shortDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
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
