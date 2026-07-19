/**
 * Клиент API.
 *
 * initData уезжает в заголовке X-Init-Data на каждом запросе — сервер проверяет
 * подпись и по ней же понимает, кто пришёл. Никаких токенов и сессий заводить не надо:
 * Telegram уже подписал пользователя за нас.
 */
import { initData, timeZone } from './tg.js';

/**
 * Куда бить запросами.
 *
 * Снаружи приложение живёт на подпути (https://sk1bid.ru/gym/), а локально — в корне
 * (http://127.0.0.1:8099/). Абсолютный путь «/api/...» в первом случае ушёл бы мимо,
 * в корень домена, поэтому адреса строим относительно страницы. Хэш роутера
 * (#/day/5) на базу не влияет.
 */
const BASE = new URL('.', document.baseURI);

async function request(method, path, body) {
  const response = await fetch(new URL(path, BASE), {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Init-Data': initData,
      // Пояс пользователя — чтобы «сегодня» считалось по его месту, а не по серверу.
      'X-Timezone': timeZone,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    // detail приходит от FastAPI: и от наших HTTPException, и от валидации схем.
    const detail = typeof data.detail === 'string' ? data.detail : 'ошибка сервера';
    throw new Error(detail);
  }

  return data;
}

export const api = {
  bootstrap: () => request('GET', 'api/bootstrap'),
  schedule:  () => request('GET', 'api/schedule'),
  day:       (id) => request('GET', `api/day/${id}`),

  training: {
    start:     (trainingDayId) => request('POST', 'api/training/start', { training_day_id: trainingDayId }),
    state:     () => request('GET', 'api/training/state'),
    addSet:    (payload) => request('POST', 'api/training/set', payload),
    editSet:   (id, weight, reps) => request('PATCH', `api/training/set/${id}`, { weight, reps }),
    deleteSet: (id) => request('DELETE', `api/training/set/${id}`),
    finish:    (sessionId) => request('POST', 'api/training/finish', { session_id: sessionId }),
  },

  rest: {
    get:   () => request('GET', 'api/rest'),
    start: (seconds, nextUp) => request('POST', 'api/rest/start', { seconds, next_up: nextUp }),
    stop:  () => request('POST', 'api/rest/stop'),
  },

  programs: {
    list:       () => request('GET', 'api/programs'),
    create:     (name) => request('POST', 'api/programs', { name }),
    update:     (id, changes) => request('PATCH', `api/programs/${id}`, changes),
    activate:   (id) => request('POST', `api/programs/${id}/activate`),
    deactivate: (id) => request('POST', `api/programs/${id}/deactivate`),
    remove:     (id) => request('DELETE', `api/programs/${id}`),
    days:       (id) => request('GET', `api/programs/${id}/days`),
  },

  exercises: {
    add:    (dayId, payload) => request('POST', `api/days/${dayId}/exercises`, payload),
    update: (id, changes) => request('PATCH', `api/exercises/${id}`, changes),
    move:   (id, up) => request('POST', `api/exercises/${id}/move?up=${up}`),
    remove: (id) => request('DELETE', `api/exercises/${id}`),
  },

  catalog: {
    categories: () => request('GET', 'api/catalog'),
    category:   (id) => request('GET', `api/catalog/${id}`),
  },

  userExercises: {
    list:   () => request('GET', 'api/user-exercises'),
    create: (payload) => request('POST', 'api/user-exercises', payload),
    update: (id, payload) => request('PATCH', `api/user-exercises/${id}`, payload),
    remove: (id) => request('DELETE', `api/user-exercises/${id}`),
  },

  profile:       () => request('GET', 'api/profile'),
  updateProfile: (name, weight) => request('PATCH', 'api/profile', { name, weight }),

  history:       (offset = 0) => request('GET', `api/history?offset=${offset}`),
  historyDetail: (id) => request('GET', `api/history/${id}`),

  stats:            () => request('GET', 'api/stats'),
  exerciseProgress: (id) => request('GET', `api/stats/exercise/${id}`),
};
