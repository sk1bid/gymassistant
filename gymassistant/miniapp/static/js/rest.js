/**
 * Отдых на клиенте.
 *
 * Важно понимать, кто здесь главный: таймер живёт на сервере (таблица rest_timer),
 * а это — всего лишь его отображение. Мы получаем «осталось N секунд» и тикаем локально,
 * чтобы цифры шли плавно, но истина — на сервере. Поэтому:
 *
 *   - при возврате в приложение состояние перезапрашивается, а не досчитывается
 *     (пока вкладка была скрыта, setInterval в вебвью мог и не тикать);
 *   - «Закончить отдых» — это запрос к API, а не просто clearInterval: ту же кнопку
 *     надо погасить и в чате, где пинги шлёт бот.
 */
import { api } from './api.js';
import { haptic } from './tg.js';
import { clock, escape } from './ui.js';

const bar = document.getElementById('rest-bar');

let left = 0;
let total = 0;
let nextUp = '';
let ticker = null;
const listeners = new Set();

/** Экран тренировки подписывается сюда, чтобы рисовать своё кольцо. */
export function onTick(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function emit() {
  listeners.forEach((handler) => handler(left, total));
}

export function isResting() {
  return left > 0;
}

export function secondsLeft() {
  return left;
}

/** rest — объект из API: { left, total, next_up } либо null. */
export function sync(rest) {
  stopTicking();

  if (!rest || rest.left <= 0) {
    left = 0;
    total = 0;
    bar.classList.add('hidden');
    emit();
    return;
  }

  left = rest.left;
  total = rest.total || rest.left;
  nextUp = rest.next_up || '';

  draw();
  emit();

  ticker = setInterval(() => {
    left -= 1;

    if (left <= 0) {
      // Локальный ноль. Уведомление о конце отдыха всё равно пришлёт бот — здесь
      // мы только убираем плашку и даём вибрацию тем, у кого приложение открыто.
      haptic('success');
      stop({ silent: true });
      return;
    }

    if (left <= 3) haptic('light');
    draw();
    emit();
  }, 1000);
}

function stopTicking() {
  if (ticker) clearInterval(ticker);
  ticker = null;
}

/** Прекращает отдых: гасит и серверный таймер, а значит, и пинги в чате. */
export async function stop({ silent = false } = {}) {
  stopTicking();
  left = 0;
  bar.classList.add('hidden');
  emit();

  try {
    await api.rest.stop();
  } catch {
    // Не достучались — не страшно: таймер всё равно истечёт сам.
  }

  if (!silent) haptic('medium');
}

export async function refresh() {
  try {
    const { rest } = await api.rest.get();
    sync(rest);
  } catch { /* оффлайн — пусть тикает то, что есть */ }
}

function draw() {
  // На экране тренировки отдых нарисован крупным кольцом — плашка там лишняя.
  if (location.hash.startsWith('#/workout')) {
    bar.classList.add('hidden');
    return;
  }

  bar.classList.remove('hidden');
  bar.innerHTML = `
    <div class="grow">
      <div class="time">Отдых ${clock(left)}</div>
      ${nextUp ? `<div style="font-size:13px;opacity:.85">Дальше: ${escape(nextUp)}</div>` : ''}
    </div>
    <button id="rest-skip">Закончить</button>
  `;
  bar.querySelector('#rest-skip').onclick = () => stop();
}

// Вебвью замораживает таймеры в фоне: вернулись — спрашиваем сервер, а не гадаем.
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && left > 0) refresh();
});
