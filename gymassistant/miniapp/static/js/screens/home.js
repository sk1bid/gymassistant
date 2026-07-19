/**
 * Главный экран: что сегодня и куда идти дальше.
 *
 * В боте это было меню уровня 0 из трёх картинок с подписями. Здесь на первом экране
 * сразу видно тренировку сегодняшнего дня — то, зачем приложение и открывают.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import * as rest from './../rest.js';
import { escape, on, plural, render } from './../ui.js';

export async function homeScreen() {
  const data = await api.bootstrap();
  rest.sync(data.rest);

  render(`
    <h1>Привет, ${escape(data.user.name)}</h1>

    ${todayCard(data)}

    <div class="section-title">Ещё</div>
    ${link('/schedule', '🗓️', 'Расписание', 'Тренировки по дням недели')}
    ${link('/programs', '⚙️', 'Программы', programsSubtitle(data.programs))}
    ${link('/profile', '📈', 'Профиль', 'Прогресс, рекорды, история')}
  `);

  on('#start', 'click', () => go(startPath(data)));
  document.querySelectorAll('[data-go]').forEach((node) => {
    node.addEventListener('click', () => go(node.dataset.go));
  });
}

function startPath(data) {
  // Незавершённая тренировка продолжается с того же места, а не начинается заново.
  return data.active_session ? '/workout' : `/workout/${data.today.id}`;
}

function todayCard(data) {
  if (!data.has_program) {
    return `
      <div class="card">
        <h2>Программы ещё нет</h2>
        <p class="hint">Соберите программу — распределите упражнения по дням недели,
        и приложение будет вести вас подход за подходом.</p>
        <button class="btn" data-go="/programs" style="margin-top:12px">Создать программу</button>
      </div>
    `;
  }

  const today = data.today;

  if (!today || !today.exercises.length) {
    return `
      <div class="card">
        <h2>Сегодня отдых</h2>
        <p class="hint">На ${escape(data.today_name.toLowerCase())} упражнений не запланировано.</p>
        <button class="btn secondary" data-go="/schedule" style="margin-top:12px">Открыть расписание</button>
      </div>
    `;
  }

  const sets = today.exercises.reduce((sum, e) => sum + e.sets, 0);

  return `
    <div class="card">
      <div class="row">
        <h2>${escape(data.today_name)}</h2>
        <span class="pill">${plural(today.exercises.length, 'упражнение', 'упражнения', 'упражнений')}</span>
      </div>

      <div class="hint" style="margin-bottom:12px">
        ${plural(sets, 'подход', 'подхода', 'подходов')} по плану
      </div>

      ${today.exercises.map((e) => `
        <div class="plan-item">
          <span class="mark">${e.circle ? '↻' : '•'}</span>
          <span class="grow">${escape(e.name)}</span>
          <span class="hint">${e.sets}×${e.reps}</span>
        </div>
      `).join('')}

      <button class="btn" id="start" style="margin-top:16px">
        ${data.active_session ? 'Продолжить тренировку' : 'Начать тренировку'}
      </button>
    </div>
  `;
}

function programsSubtitle(programs) {
  const active = programs.find((p) => p.active);
  if (active) return `Активна: ${active.name}`;
  return programs.length ? 'Ни одна не активна' : 'Пока не создано';
}

function link(path, icon, title, subtitle) {
  return `
    <button class="list-item" data-go="${path}">
      <span class="icon">${icon}</span>
      <span class="grow">
        <span class="title">${title}</span><br>
        <span class="sub">${escape(subtitle)}</span>
      </span>
      <span class="chev">›</span>
    </button>
  `;
}
