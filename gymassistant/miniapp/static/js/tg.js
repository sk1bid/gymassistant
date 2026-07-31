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

/**
 * Светлая или тёмная схема.
 *
 * По умолчанию решает система: в CSS стоит @media (prefers-color-scheme: dark).
 * Но внутри Telegram системной настройки мало — клиент разрешает держать тёмную тему
 * на светлой системе и наоборот, и тогда media-запрос покажет не то. Поэтому, когда
 * Telegram есть, его выбор ставится в data-theme на <html> и перебивает media в обе
 * стороны. В обычном браузере атрибут не ставится вовсе — работает системная.
 *
 * Заодно красим служебные полосы клиента в цвет своей поверхности: иначе шапка
 * остаётся телеграмовской, а страница под ней — нашей, и стык видно.
 */
function applyTheme() {
  if (!tg) return;

  document.documentElement.dataset.theme = tg.colorScheme === 'dark' ? 'dark' : 'light';

  // Читаем уже применённое значение токена, чтобы не держать второй список цветов.
  const surface = getComputedStyle(document.documentElement)
    .getPropertyValue('--surface').trim();

  if (!surface) return;
  tg.setBackgroundColor?.(surface);
  tg.setHeaderColor?.(surface);
  tg.setBottomBarColor?.(surface);
}

export function ready() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.disableVerticalSwipes?.();   // иначе свайп по степперу закрывает приложение

  applyTheme();
  tg.onEvent?.('themeChanged', applyTheme);   // тему могут переключить, не закрывая нас
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

  // Красим в свою палитру: без setParams Telegram рисует кнопку своим синим,
  // и она выпадает из оформления — единственный чужой цвет на экране.
  // Цвета берём из уже применённых токенов, чтобы не держать их вторым списком.
  const css = getComputedStyle(document.documentElement);
  const color = css.getPropertyValue('--primary').trim();
  const textColor = css.getPropertyValue('--on-primary').trim();

  if (color && textColor) {
    tg.MainButton.setParams({ text, color, text_color: textColor });
  } else {
    tg.MainButton.setText(text);
  }

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
