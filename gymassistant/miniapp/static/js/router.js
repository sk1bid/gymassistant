/**
 * Роутинг по хэшу: #/workout, #/day/12, #/program/3/settings.
 *
 * Хэш, а не History API, по двум причинам: приложение живёт на подпути (/gym/),
 * и в вебвью Telegram нет адресной строки — назад ходят системной кнопкой,
 * которую мы вешаем на history.back().
 */
import * as nav from './nav.js';
import { backButton, mainButton } from './tg.js';
import { errorScreen, loading, setTransition, withPane } from './ui.js';

const routes = [];

/**
 * Через сколько ожидания показывать спиннер.
 *
 * Порог, а не ноль: вспышка крутилки на 40 мс раздражает сильнее, чем те же 40 мс
 * неподвижного экрана — глаз читает её как сбой. Четверть секунды — граница, за
 * которой отсутствие отклика начинает восприниматься как зависание.
 */
const SPINNER_DELAY = 250;

/** path — шаблон вида '/day/:id'. */
export function route(path, screen) {
  const names = [];
  const pattern = path.replace(/:(\w+)/g, (_, name) => {
    names.push(name);
    return '([^/]+)';
  });
  routes.push({ regex: new RegExp(`^${pattern}$`), names, screen });
}

/**
 * Направление следующего перехода.
 *
 * Разбирать «вперёд или назад» из самой истории нечем: хэш-навигация не позволяет
 * положить своё состояние в запись. Поэтому намерение помечает тот, кто навигирует.
 * Всё, что пришло без пометки, — это системная кнопка «назад» или свайп, и трактуем
 * это как возврат: единственный способ сменить хэш мимо go() и back().
 */
let pendingDirection = null;

export function go(path, { replace = false, direction = 'deep' } = {}) {
  pendingDirection = direction;

  const target = `#${path}`;
  if (location.hash === target) return handle();
  if (replace) location.replace(target);
  else location.hash = target;
}

export function back() {
  pendingDirection = 'shallow';
  history.back();
}

/**
 * Нарисовать раздел в отдельную панель, не меняя адрес.
 *
 * Нужно свайпу: пока палец ведёт, соседний раздел уже должен быть виден. Данные
 * почти всегда берутся из кэша api.js, поэтому отрисовка укладывается в тот же кадр.
 */
export async function paintInto(path, pane) {
  const found = match(path);
  if (!found) return false;

  await withPane(pane, () => found.screen(found.params));
  return true;
}

/**
 * Принять экран, который уже нарисован свайпом.
 *
 * Адрес меняется, но screen() повторно не зовётся — иначе после каждого свайпа
 * шёл бы лишний запрос и экран перерисовывался бы поверх того, что пользователь
 * уже видит.
 */
let assumed = false;

export function assume(path) {
  assumed = true;
  pendingDirection = null;
  location.hash = `#${path}`;
}

function match(path) {
  for (const { regex, names, screen } of routes) {
    const found = path.match(regex);
    if (!found) continue;

    const params = {};
    names.forEach((name, i) => { params[name] = found[i + 1]; });
    return { screen, params };
  }
  return null;
}

let current = 0;

/** Кнопки клиента и нижняя панель — то, что обновляется при любой смене адреса. */
function chrome(path) {
  // Экраны сами решают, что показывать в главной кнопке и нужна ли «назад».
  // Сбрасываем обе, чтобы кнопка предыдущего экрана не осталась висеть на этом.
  mainButton(null, null);

  // «Назад» — только на вложенных экранах. Разделы верхнего уровня достижимы
  // панелью снизу, и стрелка в шапке над ними ведёт в непредсказуемое место
  // истории вместо ожидаемого «на уровень выше».
  backButton(nav.SECTIONS.includes(path) ? null : back);

  nav.sync(path, go);
}

async function handle() {
  const path = location.hash.slice(1) || '/';

  // Экран уже нарисован свайпом: обновляем только обвязку и выходим, не трогая
  // содержимое и не делая повторный запрос.
  if (assumed) {
    assumed = false;
    current += 1;   // отменяем возможный незавершённый переход
    return chrome(path);
  }

  const found = match(path);

  chrome(path);

  if (!found) return go('/', { replace: true });

  // Пользователь мог уйти с экрана, пока грузились его данные, — тогда рисовать
  // уже нечего: за это время успел отработать более свежий переход.
  const token = ++current;
  const direction = pendingDirection || 'shallow';
  pendingDirection = null;

  /*
    Экран НЕ стирается на время запроса.

    Раньше здесь сразу вызывался loading(), и любой переход — даже когда ответ
    приходит за сорок миллисекунд — начинался с пустой страницы и вспышки спиннера.
    Теперь старый экран остаётся на месте до готовности данных, а крутилка
    появляется, только если ожидание реально затянулось. На быстрой сети её
    не видно ни разу: переход выглядит как одно движение, а не как перезагрузка.
  */
  const spinner = setTimeout(() => {
    if (token === current) loading();
  }, SPINNER_DELAY);

  setTransition(direction);

  try {
    await found.screen(found.params);
  } catch (error) {
    if (token !== current) return;
    errorScreen(error.message, handle);
  } finally {
    clearTimeout(spinner);
  }
}

export function start() {
  window.addEventListener('hashchange', handle);
  return handle();
}
