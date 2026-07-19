/**
 * Программы тренировок и их настройки.
 *
 * Настройки отдыха — главное, что здесь появилось. В боте эти поля лежали в БД
 * (rest_between_set, circular_rounds, circular_rest_*), читались во время тренировки,
 * но интерфейса к ним не существовало: все тренировались с дефолтными пятью минутами
 * между подходами и не имели способа это изменить. А rest_between_exercise и вовсе
 * клали в FSM и ни разу не читали — отдыха между упражнениями просто не было.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import { confirm, haptic } from './../tg.js';
import { clock, escape, on, onAction, plural, render, sheet } from './../ui.js';

export async function programsScreen() {
  const { programs } = await api.programs.list();

  render(`
    <h1>Программы</h1>

    ${programs.length ? '' : `
      <div class="empty">
        <p>Программ пока нет.</p>
        <p class="hint">Программа — это упражнения, разложенные по дням недели.</p>
      </div>
    `}

    ${programs.map((program) => `
      <button class="list-item" data-open="${program.id}">
        <span class="icon">${program.active ? '🟢' : '⚪️'}</span>
        <span class="grow">
          <span class="title">${escape(program.name)}</span><br>
          <span class="sub">
            ${program.active ? 'активна · ' : ''}${plural(program.filled_days, 'день', 'дня', 'дней')} заполнено
          </span>
        </span>
        <span class="chev">›</span>
      </button>
    `).join('')}

    <button class="btn secondary" id="create" style="margin-top:8px">Создать программу</button>
  `);

  onAction('[data-open]', (node) => go(`/program/${node.dataset.open}`));

  on('#create', 'click', () => {
    const form = sheet(`
      <h2>Новая программа</h2>
      <div class="field">
        <label>Название</label>
        <input type="text" id="name" maxlength="50" placeholder="Например: Силовая, 3 дня">
      </div>
      <p class="hint" style="margin-bottom:16px">
        Создадутся все семь дней недели — заполните те, в которые тренируетесь.
        Программа сразу станет активной.
      </p>
      <button class="btn" id="save">Создать</button>
    `);

    form.node.querySelector('#save').onclick = async () => {
      const name = form.node.querySelector('#name').value.trim();
      if (!name) return;

      const { program } = await api.programs.create(name);
      form.close();
      haptic('success');
      go(`/program/${program.id}`);
    };
  });
}

/** Одна программа: дни, активация, настройки, удаление. */
export async function programScreen({ id }) {
  const data = await api.programs.days(Number(id));
  const program = data.program;

  render(`
    <h1>${escape(program.name)}</h1>
    <p class="hint" style="margin:-8px 0 16px 4px">
      ${program.active ? '🟢 активная программа' : 'не активна'}
    </p>

    ${data.days.map((day) => `
      <button class="list-item" data-day="${day.id}">
        <span class="grow">
          <span class="title">${escape(day.day_of_week)}</span><br>
          <span class="sub">
            ${day.exercises.length
              ? escape(day.exercises.map((e) => e.name).join(', '))
              : 'отдых'}
          </span>
        </span>
        <span class="chev">›</span>
      </button>
    `).join('')}

    <div class="section-title">Программа</div>

    <button class="btn secondary" id="settings">Настройки отдыха и кругов</button>

    ${program.active
      ? '<button class="btn ghost" id="deactivate" style="margin-top:8px">Сделать неактивной</button>'
      : '<button class="btn" id="activate" style="margin-top:8px">Сделать активной</button>'}

    <button class="btn danger" id="remove" style="margin-top:8px">Удалить программу</button>
  `);

  onAction('[data-day]', (node) => go(`/day/${node.dataset.day}`));

  on('#settings', 'click', () => openSettings(program, () => programScreen({ id })));

  on('#activate', 'click', async () => {
    await api.programs.activate(program.id);
    haptic('success');
    programScreen({ id });
  });

  on('#deactivate', 'click', async () => {
    await api.programs.deactivate(program.id);
    haptic('warning');
    programScreen({ id });
  });

  on('#remove', 'click', async () => {
    if (!await confirm(`Удалить «${program.name}»? Дни и упражнения удалятся вместе с ней.`)) return;

    await api.programs.remove(program.id);
    haptic('warning');
    go('/programs');
  });
}

function openSettings(program, reload) {
  const settings = program.settings;

  const form = sheet(`
    <h2>Настройки</h2>

    <div class="section-title" style="margin-top:0">Обычные упражнения</div>
    ${seconds('rest_between_set', 'Отдых между подходами', settings.rest_between_set)}
    ${seconds('rest_between_exercise', 'Отдых между упражнениями', settings.rest_between_exercise)}

    <div class="section-title">Круговые</div>
    <div class="field">
      <label>Кругов в блоке</label>
      <input type="number" id="circular_rounds" inputmode="numeric"
             min="1" max="20" value="${settings.circular_rounds}">
    </div>
    ${seconds('circular_rest_between_exercise', 'Отдых между упражнениями в круге',
              settings.circular_rest_between_exercise)}
    ${seconds('circular_rest_between_rounds', 'Отдых между кругами',
              settings.circular_rest_between_rounds)}

    <div class="section-title">Уведомления</div>
    <div class="card" style="background:var(--bg)">
      <label class="switch" style="margin:0">
        <span class="grow">
          <span style="font-weight:600">Тихие напоминания</span><br>
          <span class="hint">Минутные пинги без звука, звонко — за 30 секунд до конца и в конце</span>
        </span>
        <input type="checkbox" id="quiet_rest_pings" ${settings.quiet_rest_pings ? 'checked' : ''}>
        <span class="track"></span>
      </label>
    </div>

    <button class="btn" id="save" style="margin-top:16px">Сохранить</button>
  `);

  form.node.querySelector('#save').onclick = async () => {
    const value = (id) => Number(form.node.querySelector(`#${id}`).value);

    await api.programs.update(program.id, {
      rest_between_set: value('rest_between_set'),
      rest_between_exercise: value('rest_between_exercise'),
      circular_rounds: value('circular_rounds'),
      circular_rest_between_exercise: value('circular_rest_between_exercise'),
      circular_rest_between_rounds: value('circular_rest_between_rounds'),
      quiet_rest_pings: form.node.querySelector('#quiet_rest_pings').checked,
    });

    form.close();
    haptic('success');
    reload();
  };

  // Отдых задаётся в секундах, но думают о нём в минутах — показываем и то и другое.
  form.node.querySelectorAll('[data-seconds]').forEach((input) => {
    const hint = form.node.querySelector(`#${input.id}-hint`);
    const update = () => { hint.textContent = clock(Number(input.value) || 0); };
    input.addEventListener('input', update);
    update();
  });
}

function seconds(id, label, value) {
  return `
    <div class="field">
      <label>${label}</label>
      <div class="row">
        <input type="number" id="${id}" data-seconds inputmode="numeric"
               min="0" max="3600" step="15" value="${value}">
        <span class="hint" id="${id}-hint" style="flex:0 0 52px;text-align:right"></span>
      </div>
    </div>
  `;
}
