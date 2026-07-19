/**
 * Обёртка над Telegram WebApp SDK.
 *
 * Всё, что знает про Telegram на фронте, живёт здесь: остальной код вызывает
 * haptic() и mainButton(), не думая о том, что бывает и обычный браузер, где
 * window.Telegram отсутствует (локальная отладка через http://127.0.0.1:8099).
 */
export const tg = window.Telegram?.WebApp;

/**
 * initData текущего запуска.
 *
 * Фолбэк на localStorage — для отладки в обычном браузере, где Telegram не подставит
 * ничего. Дырой это не является: сервер всё равно проверяет HMAC-подпись, а подписать
 * initData можно только токеном бота. Без валидной подписи фолбэк даёт ровно 401.
 */
export const initData = tg?.initData || localStorage.getItem('devInitData') || '';

/**
 * Часовой пояс пользователя (IANA, напр. "Asia/Novosibirsk").
 *
 * Telegram не кладёт пояс в initData, но его знает сам телефон. Отсюда «сегодня»
 * считается по месту пользователя, а не по серверу (который стоит в НСК, а контейнер
 * вообще в UTC). Уходит заголовком X-Timezone на каждом запросе (api.js).
 */
export const timeZone = (() => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; }
  catch { return ''; }
})();

export function ready() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.disableVerticalSwipes?.();   // иначе свайп по степперу закрывает приложение
}

/** Вибрация. Без неё степперы ощущаются мёртвыми. */
export function haptic(style = 'light') {
  try {
    if (style === 'success' || style === 'error' || style === 'warning') {
      tg.HapticFeedback.notificationOccurred(style);
    } else {
      tg.HapticFeedback.impactOccurred(style);
    }
  } catch { /* в браузере хаптики нет — и не надо */ }
}

/**
 * Главная кнопка внизу экрана. Telegram рисует её сам, поверх нашей вёрстки.
 * onClick накапливает обработчики, поэтому перед каждой установкой снимаем прошлый.
 */
let mainButtonHandler = null;

export function mainButton(text, handler) {
  if (!tg?.MainButton) return;

  if (mainButtonHandler) tg.MainButton.offClick(mainButtonHandler);

  if (!handler) {
    tg.MainButton.hide();
    mainButtonHandler = null;
    return;
  }

  mainButtonHandler = handler;
  tg.MainButton.setText(text);
  tg.MainButton.onClick(mainButtonHandler);
  tg.MainButton.show();
}

export function mainButtonProgress(on) {
  if (!tg?.MainButton) return;
  on ? tg.MainButton.showProgress() : tg.MainButton.hideProgress();
}

/** Кнопка «назад» в шапке Telegram. */
let backHandler = null;

export function backButton(handler) {
  if (!tg?.BackButton) return;

  if (backHandler) tg.BackButton.offClick(backHandler);

  if (!handler) {
    tg.BackButton.hide();
    backHandler = null;
    return;
  }

  backHandler = handler;
  tg.BackButton.onClick(backHandler);
  tg.BackButton.show();
}

export function alert(message) {
  if (tg?.showAlert) tg.showAlert(message);
  else window.alert(message);
}

export function confirm(message) {
  return new Promise((resolve) => {
    if (tg?.showConfirm) tg.showConfirm(message, resolve);
    else resolve(window.confirm(message));
  });
}
