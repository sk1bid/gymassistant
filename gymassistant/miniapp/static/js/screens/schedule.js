/**
 * Расписание и тренировочный день.
 *
 * В боте расписание было календарём на инлайн-кнопках — свёрнутый на неделю,
 * развёрнутый на месяц. Но программа задаётся по дням недели, а не по датам:
 * календарь показывал числа, за которыми не стояло ничего, кроме дня недели.
 * Поэтому здесь честная неделя Пн→Вс с сегодняшним днём, поднятым наверх смыслом.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import { escape, on, onAction, render } from './../ui.js';

export async function scheduleScreen() {
  const data = await api.schedule();

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
    <p class="hint" style="margin:-8px 0 16px 4px">${escape(data.program.name)}</p>

    ${data.days.map((day) => {
      const isToday = day.day_of_week === data.today;
      const count = day.exercises.length;

      return `
        <button class="list-item" data-day="${day.id}">
          <span class="grow">
            <span class="title">
              ${escape(day.day_of_week)}
              ${isToday ? '<span class="pill on" style="margin-left:6px">сегодня</span>' : ''}
            </span><br>
            <span class="sub">
              ${count
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

  render(`
    <h1>${escape(data.day.day_of_week)}</h1>

    ${exercises.length ? '' : `
      <div class="empty">
        <p>В этот день ничего не запланировано.</p>
      </div>
    `}

    ${exercises.map((exercise, index) => `
      <div class="card tight">
        <div class="row">
          <div class="grow">
            <div style="font-weight:600">
              ${escape(exercise.name)}
              ${exercise.circle ? '<span class="pill" style="margin-left:4px">круговое</span>' : ''}
            </div>
            <div class="hint">${exercise.sets} × ${exercise.reps}</div>
          </div>
          <button class="btn secondary small" data-edit="${exercise.id}">Настроить</button>
        </div>

        <div class="row" style="margin-top:10px;justify-content:flex-start;gap:8px">
          <button class="btn secondary small" data-up="${exercise.id}" ${index === 0 ? 'disabled' : ''}>↑</button>
          <button class="btn secondary small" data-down="${exercise.id}"
                  ${index === exercises.length - 1 ? 'disabled' : ''}>↓</button>
          <button class="btn danger small" data-remove="${exercise.id}">Убрать</button>
        </div>
      </div>
    `).join('')}

    <button class="btn secondary" data-add>Добавить упражнение</button>

    ${exercises.length ? `
      <button class="btn" id="start" style="margin-top:8px">Начать тренировку</button>
    ` : ''}
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

  onAction('[data-remove]', async (node) => {
    await api.exercises.remove(Number(node.dataset.remove));
    await dayScreen({ id });
  });
}
