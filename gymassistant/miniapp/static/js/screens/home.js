/**
 * Главный экран: что сегодня и куда идти дальше.
 *
 * В боте это было меню уровня 0 из трёх картинок с подписями. Здесь на первом экране
 * сразу видно тренировку сегодняшнего дня — то, зачем приложение и открывают.
 *
 * Приветствия наверху нет намеренно: имя пользователь и так знает, а строка с ним
 * отодвигала вниз единственное, ради чего экран открыт. День недели — заголовок,
 * ближайшее упражнение — акцентный блок, остальное — список на разделителях.
 */
import { api, cached } from './../api.js';
import { go } from './../router.js';
import * as rest from './../rest.js';
import { escape, on, onAll, plural, render, same } from './../ui.js';

export async function homeScreen() {
  // Если экран уже открывали в этот заход, рисуем его немедленно из последнего
  // ответа и только потом идём на сервер: переход перестаёт упираться в запрос.
  const known = cached('api/bootstrap');
  if (known) paint(known);

  const data = await api.bootstrap();
  rest.sync(data.rest);

  // Перерисовываем, только если данные реально другие: лишний render() сбрасывает
  // обработчики и заставляет экран моргать там, где ничего не изменилось.
  if (!known || !same(known, data)) paint(data);
}

function paint(data) {
  render(todayBlock(data));

  on('#start', 'click', () => go(startPath(data)));
  onAll('[data-go]', 'click', (node) => go(node.dataset.go));
}

function startPath(data) {
  // Незавершённая тренировка продолжается с того же места, а не начинается заново.
  return data.active_session ? '/workout' : `/workout/${data.today.id}`;
}

function todayBlock(data) {
  if (!data.has_program) {
    return `
      <h1>Программы ещё нет</h1>
      <p class="subtitle">Соберите программу — распределите упражнения по дням недели,
      и приложение будет вести вас подход за подходом.</p>
      <button class="btn" data-go="/programs">Создать программу</button>
    `;
  }

  const today = data.today;

  if (!today || !today.exercises.length) {
    return `
      <div class="overline flush">сегодня</div>
      <h1>${escape(data.today_name)}</h1>
      <p class="subtitle">Упражнений не запланировано — день отдыха.</p>
      <button class="btn secondary" data-go="/schedule">Открыть расписание</button>
    `;
  }

  const exercises = today.exercises;
  const sets = exercises.reduce((sum, e) => sum + e.sets, 0);

  return `
    <div class="overline flush">сегодня</div>
    <h1>${escape(data.today_name)}</h1>
    <p class="subtitle">
      ${plural(exercises.length, 'упражнение', 'упражнения', 'упражнений')} ·
      ${plural(sets, 'подход', 'подхода', 'подходов')}
    </p>

    ${data.active_session ? resumeCard() : nextCard(exercises[0])}

    ${restList(data.active_session ? exercises : exercises.slice(1))}

    <button class="btn mt-4" id="start">
      ${data.active_session ? 'Продолжить тренировку' : 'Начать тренировку'}
    </button>
  `;
}

/** Ближайшее упражнение — единственное, что выделено цветом на экране. */
function nextCard(exercise) {
  return `
    <div class="card accent">
      <div class="overline flush">следующее</div>
      <div class="lead mt-1">${escape(exercise.name)}</div>
      <div class="hint">
        ${plural(exercise.sets, 'подход', 'подхода', 'подходов')} по ${exercise.reps}
      </div>
    </div>
  `;
}

function resumeCard() {
  return `
    <div class="card accent">
      <div class="overline flush">тренировка идёт</div>
      <div class="hint mt-1">Продолжится с того подхода, на котором остановились.</div>
    </div>
  `;
}

function restList(exercises) {
  if (!exercises.length) return '';

  return `
    <div class="rows">
      ${exercises.map((e) => `
        <div class="plan-item">
          <span class="mark">${e.circle ? '↻' : '·'}</span>
          <span class="grow">${escape(e.name)}</span>
          <span class="num">${e.sets}×${e.reps}</span>
        </div>
      `).join('')}
    </div>
  `;
}
