/**
 * Расписание и тренировочный день.
 *
 * В боте расписание было календарём на инлайн-кнопках — свёрнутый на неделю,
 * развёрнутый на месяц. Но программа задаётся по дням недели, а не по датам:
 * календарь показывал числа, за которыми не стояло ничего, кроме дня недели.
 * Поэтому здесь честная неделя Пн→Вс с сегодняшним днём, поднятым наверх смыслом.
 */
import { api, cached } from './../api.js';
import { go } from './../router.js';
import { escape, on, onAction, plural, render, same } from './../ui.js';

export async function scheduleScreen() {
  // Мгновенная отрисовка из последнего ответа, свежий — следом. См. home.js.
  const known = cached('api/schedule');
  if (known) paintSchedule(known);

  const data = await api.schedule();
  if (!known || !same(known, data)) paintSchedule(data);
}

function paintSchedule(data) {
  if (!data.program) {
    render(`
      <h1>Расписание</h1>
      <div class="empty">
        <p>Нет активной программы.</p>
        <button class="btn secondary small" id="to-programs">К программам</button>
      </div>
    `);
    return on('#to-programs', 'click', () => go('/programs'));
  }

  render(`
    <h1>Расписание</h1>
    <p class="subtitle">${escape(data.program.name)}</p>

    ${data.days.map((day) => {
      const isToday = day.day_of_week === data.today;

      return `
        <button class="list-item" data-day="${day.id}">
          <span class="grow">
            <span class="title">${escape(day.day_of_week)}</span>
            ${isToday ? '<span class="pill on">сегодня</span>' : ''}
            <br>
            <span class="sub">
              ${day.exercises.length
                ? escape(day.exercises.map((e) => e.name).join(', '))
                : 'отдых'}
            </span>
          </span>
          <span class="chev">›</span>
        </button>
      `;
    }).join('')}
  `);

  onAction('[data-day]', (node) => go(`/day/${node.dataset.day}`));
}

export async function dayScreen({ id }) {
  const data = await api.day(Number(id));
  const exercises = data.exercises;
  const sets = exercises.reduce((sum, e) => sum + e.sets, 0);

  render(`
    <h1>${escape(data.day.day_of_week)}</h1>
    <p class="subtitle">
      ${exercises.length
        ? `${plural(exercises.length, 'упражнение', 'упражнения', 'упражнений')} ·
           ${plural(sets, 'подход', 'подхода', 'подходов')}`
        : 'День отдыха'}
    </p>

    ${exercises.length ? '' : `
      <div class="empty">
        <p>В этот день ничего не запланировано.</p>
      </div>
    `}

    ${exercises.map((exercise, index) => `
      <div class="ex-row">
        <button class="ex-main" data-edit="${exercise.id}">
          <span class="title">${escape(exercise.name)}</span>
          ${exercise.circle ? '<span class="pill">круговое</span>' : ''}
          <br>
          <span class="sub num">${exercise.sets} × ${exercise.reps}</span>
        </button>
        <button class="icon-btn" data-up="${exercise.id}"
                aria-label="Выше" ${index === 0 ? 'disabled' : ''}>↑</button>
        <button class="icon-btn" data-down="${exercise.id}"
                aria-label="Ниже" ${index === exercises.length - 1 ? 'disabled' : ''}>↓</button>
      </div>
    `).join('')}

    <button class="btn secondary mt-4" data-add>Добавить упражнение</button>

    ${exercises.length ? '<button class="btn mt-2" id="start">Начать тренировку</button>' : ''}
  `);

  on('#start', 'click', () => go(`/workout/${data.day.id}`));
  onAction('[data-add]', () => go(`/catalog/${data.day.id}`));
  onAction('[data-edit]', (node) => go(`/day/${data.day.id}/exercise/${node.dataset.edit}`));

  // Порядок упражнений — не косметика: подряд идущие круговые собираются в один
  // круговой блок, поэтому перестановка меняет саму структуру тренировки.
  onAction('[data-up]', async (node) => {
    await api.exercises.move(Number(node.dataset.up), true);
    await dayScreen({ id });
  });

  onAction('[data-down]', async (node) => {
    await api.exercises.move(Number(node.dataset.down), false);
    await dayScreen({ id });
  });
}
