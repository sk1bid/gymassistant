/**
 * Роутинг по хэшу: #/workout, #/day/12, #/program/3/settings.
 *
 * Хэш, а не History API, по двум причинам: приложение живёт на подпути (/gym/),
 * и в вебвью Telegram нет адресной строки — назад ходят системной кнопкой,
 * которую мы вешаем на history.back().
 */
import { backButton, mainButton } from './tg.js';
import { errorScreen, loading } from './ui.js';

const routes = [];

/** path — шаблон вида '/day/:id'. */
export function route(path, screen) {
  const names = [];
  const pattern = path.replace(/:(\w+)/g, (_, name) => {
    names.push(name);
    return '([^/]+)';
  });
  routes.push({ regex: new RegExp(`^${pattern}$`), names, screen });
}

export function go(path, { replace = false } = {}) {
  const target = `#${path}`;
  if (location.hash === target) return handle();
  if (replace) location.replace(target);
  else location.hash = target;
}

export function back() {
  history.back();
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

async function handle() {
  const path = location.hash.slice(1) || '/';
  const found = match(path);

  // Экраны сами решают, что показывать в главной кнопке и нужна ли «назад».
  // Сбрасываем обе, чтобы кнопка предыдущего экрана не осталась висеть на этом.
  mainButton(null, null);
  backButton(path === '/' ? null : back);

  if (!found) return go('/', { replace: true });

  // Пользователь мог уйти с экрана, пока грузились его данные, — тогда рисовать
  // уже нечего: за это время успел отработать более свежий переход.
  const token = ++current;
  loading();

  try {
    await found.screen(found.params);
  } catch (error) {
    if (token !== current) return;
    errorScreen(error.message, handle);
  }
}

export function start() {
  window.addEventListener('hashchange', handle);
  return handle();
}
