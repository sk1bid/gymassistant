/**
 * Профиль, история и прогресс.
 *
 * История в боте была списком с пагинацией по пять штук, а её кнопки ссылались на UUID
 * из модульного словаря (utils/temporary_storage.py): словарь не чистился, тёк, и после
 * рестарта пода все кнопки истории умирали. Здесь id тренировки просто лежит в адресе.
 *
 * Графики — то, чего в чате не было в принципе: рисовать линию прогресса символами
 * никто не стал, поэтому от всей истории пользователю доставался плоский список чисел.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import { haptic } from './../tg.js';
import { escape, formatDate, on, onAction, plural, render, sheet, volume, weight } from './../ui.js';

export async function profileScreen() {
  const data = await api.profile();

  render(`
    <h1>Профиль</h1>

    <div class="card">
      <div class="row">
        <div>
          <div style="font-size:20px;font-weight:700">${escape(data.user.name)}</div>
          <div class="hint">${weight(data.user.weight)} кг</div>
        </div>
        <button class="btn secondary small" id="edit">Изменить</button>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <span class="hint">Тренировок</span><span>${data.total.sessions}</span>
      </div>
      <div class="row">
        <span class="hint">Подходов</span><span>${data.total.sets}</span>
      </div>
      <div class="row">
        <span class="hint">Поднято всего</span><span>${volume(data.total.volume)}</span>
      </div>
    </div>

    <button class="list-item" data-go="/records">
      <span class="icon">🏆</span>
      <span class="grow"><span class="title">Рекорды</span><br>
        <span class="sub">Личные максимумы и прогресс</span></span>
      <span class="chev">›</span>
    </button>

    <button class="list-item" data-go="/history">
      <span class="icon">📊</span>
      <span class="grow"><span class="title">История тренировок</span><br>
        <span class="sub">${plural(data.total.sessions, 'тренировка', 'тренировки', 'тренировок')}</span></span>
      <span class="chev">›</span>
    </button>
  `);

  onAction('[data-go]', (node) => go(node.dataset.go));

  on('#edit', 'click', () => {
    const form = sheet(`
      <h2>Профиль</h2>
      <div class="field">
        <label>Имя</label>
        <input type="text" id="name" maxlength="20" value="${escape(data.user.name)}">
      </div>
      <div class="field">
        <label>Вес, кг</label>
        <input type="number" id="weight" inputmode="decimal" step="0.5" value="${weight(data.user.weight)}">
      </div>
      <button class="btn" id="save">Сохранить</button>
    `);

    form.node.querySelector('#save').onclick = async () => {
      const name = form.node.querySelector('#name').value.trim();
      const value = parseFloat(form.node.querySelector('#weight').value);
      if (!name || !(value > 0)) return;

      await api.updateProfile(name, value);
      form.close();
      haptic('success');
      profileScreen();
    };
  });
}

export async function historyScreen() {
  const { sessions } = await api.history();

  render(`
    <h1>История</h1>

    ${sessions.length ? '' : '<div class="empty">Тренировок пока не было</div>'}

    ${sessions.map((session) => `
      <button class="list-item" data-session="${session.id}">
        <span class="grow">
          <span class="title">${escape(formatDate(session.date))}</span><br>
          <span class="sub">
            ${plural(session.exercises, 'упражнение', 'упражнения', 'упражнений')} ·
            ${plural(session.sets, 'подход', 'подхода', 'подходов')} ·
            ${volume(session.volume)}
          </span>
        </span>
        <span class="chev">›</span>
      </button>
    `).join('')}
  `);

  onAction('[data-session]', (node) => go(`/history/${node.dataset.session}`));
}

export async function sessionScreen({ id }) {
  const data = await api.historyDetail(id);

  render(`
    <h1>${escape(formatDate(data.session.date))}</h1>
    <p class="hint" style="margin:-8px 0 16px 4px">
      ${plural(data.session.sets, 'подход', 'подхода', 'подходов')} · ${volume(data.session.volume)}
    </p>

    ${data.exercises.map((exercise) => `
      <div class="card">
        <div style="font-weight:600;margin-bottom:10px">${escape(exercise.name)}</div>
        ${exercise.sets.map((set, i) => `
          <div class="set-chip">
            <span class="n">Подход ${i + 1}</span>
            <span>${weight(set.weight)} кг × ${set.reps}</span>
          </div>
        `).join('')}
      </div>
    `).join('')}
  `);
}

export async function recordsScreen() {
  const { records } = await api.stats();

  render(`
    <h1>Рекорды</h1>

    ${records.length ? '' : `
      <div class="empty">
        <p>Рекордов пока нет.</p>
        <p class="hint">Проведите первую тренировку.</p>
      </div>
    `}

    ${records.map((record) => `
      <button class="list-item" data-exercise="${record.exercise_id}">
        <span class="grow">
          <span class="title">${escape(record.name)}</span><br>
          <span class="sub">лучший подход: ${volume(record.max_volume)} объёма</span>
        </span>
        <span style="font-weight:700">${weight(record.max_weight)} кг</span>
      </button>
    `).join('')}
  `);

  onAction('[data-exercise]', (node) => go(`/progress/${node.dataset.exercise}`));
}

export async function progressScreen({ id }) {
  const data = await api.exerciseProgress(Number(id));
  const points = data.points;

  render(`
    <h1>${escape(data.name)}</h1>
    <p class="hint" style="margin:-8px 0 16px 4px">
      ${plural(points.length, 'тренировка', 'тренировки', 'тренировок')} с этим упражнением
    </p>

    ${points.length < 2 ? `
      <div class="empty">
        <p>Для графика нужно хотя бы две тренировки.</p>
      </div>
    ` : `
      <div class="card">
        <div class="section-title" style="margin:0 0 8px">Рабочий вес, кг</div>
        ${lineChart(points.map((p) => p.max_weight))}
      </div>

      <div class="card">
        <div class="section-title" style="margin:0 0 8px">Объём за тренировку, кг</div>
        ${lineChart(points.map((p) => p.volume))}
      </div>
    `}

    <div class="section-title">По тренировкам</div>
    ${points.slice().reverse().map((point) => `
      <div class="card tight">
        <div class="row">
          <span class="hint">${escape(formatDate(point.date))}</span>
          <span><b>${weight(point.max_weight)} кг</b> · ${volume(point.volume)}</span>
        </div>
      </div>
    `).join('')}
  `);
}

/**
 * Линейный график на голом SVG.
 *
 * Библиотеку тянуть незачем: точек десятки, а внешние скрипты в Mini App — это ещё
 * и лишняя загрузка на телефоне в зале, где интернет обычно так себе.
 */
function lineChart(values) {
  const W = 320;
  const H = 160;
  const PAD = 24;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const x = (i) => PAD + (i * (W - PAD * 2)) / Math.max(1, values.length - 1);
  const y = (v) => H - PAD - ((v - min) / span) * (H - PAD * 2);

  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(values.length - 1).toFixed(1)},${H - PAD} L${x(0).toFixed(1)},${H - PAD} Z`;

  const dots = values
    .map((v, i) => `<circle class="dot" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3"></circle>`)
    .join('');

  return `
    <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"
         role="img" aria-label="График: от ${Math.round(min)} до ${Math.round(max)}">
      <line class="grid" x1="${PAD}" y1="${PAD}" x2="${W - PAD}" y2="${PAD}"></line>
      <line class="grid" x1="${PAD}" y1="${H - PAD}" x2="${W - PAD}" y2="${H - PAD}"></line>

      <path class="area" d="${area}"></path>
      <path class="line" d="${line}"></path>
      ${dots}

      <text class="label" x="2" y="${PAD + 4}">${Math.round(max)}</text>
      <text class="label" x="2" y="${H - PAD + 4}">${Math.round(min)}</text>
    </svg>
  `;
}
