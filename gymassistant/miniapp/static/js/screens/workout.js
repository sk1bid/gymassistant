/**
 * Экран тренировки — то, ради чего всё затевалось.
 *
 * В боте один подход стоил четырёх сообщений: бот спрашивал вес, пользователь отвечал
 * числом, бот спрашивал повторения, пользователь отвечал числом, бот присылал
 * подтверждение с кнопками «Изменить» / «Продолжить», и всё это ещё за собой подчищал.
 * Здесь это два степпера и одна кнопка: вес и повторения видно одновременно, рядом —
 * что было в прошлый раз, и промах правится тапом по уже записанному подходу.
 *
 * Состояние экрана не хранится: после каждого действия сервер отдаёт полное состояние
 * тренировки, и мы просто перерисовываем. Поэтому закрытое приложение, перезапуск пода
 * и второй телефон не ломают ничего.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import * as rest from './../rest.js';
import { alert, confirm, haptic, mainButton, mainButtonProgress } from './../tg.js';
import { clock, escape, on, onAction, onAll, plural, render, sheet, volume, weight } from './../ui.js';

let state = null;
let unsubscribe = null;

export async function workoutScreen(params) {
  const dayId = params?.dayId;

  state = dayId
    ? await api.training.start(Number(dayId))
    : await api.training.state();

  if (!state.session_id) {
    // Тренировки нет — на этом экране делать нечего.
    return go('/', { replace: true });
  }

  rest.sync(state.rest);
  draw();
}

/* ---------------------------------------------------------------- отрисовка */

function draw() {
  if (state.finished) return drawFinished();
  if (rest.isResting()) return drawRest();
  return drawEntry();
}

/** Ввод подхода. */
function drawEntry() {
  const { current, progress } = state;
  const exercise = current.exercise;
  const previous = previousSet();

  const startWeight = previous?.weight ?? current.exercise.ai?.next_weight ?? 20;
  const startReps = previous?.reps ?? exercise.reps;

  render(`
    <div class="card">
      <div class="row">
        <span class="hint">${escape(state.day?.day_of_week || '')}</span>
        ${current.is_circuit
          ? `<span class="pill">Круг ${current.round_number} из ${current.total_rounds}</span>`
          : ''}
      </div>

      <div class="exercise-name">${escape(exercise.name)}</div>
      <div class="hint">Подход ${current.set_number} из ${current.total_sets}</div>

      <div class="row" style="margin-top:14px">
        <span class="hint">Прошлый раз</span>
        <span>${previous ? `${weight(previous.weight)} кг × ${previous.reps}` : '—'}</span>
      </div>
      <div class="row">
        <span class="hint">Рекорд</span>
        <span>${exercise.record ? `${weight(exercise.record)} кг` : '—'}</span>
      </div>

      <div class="progress"><div style="width:${(progress.done / progress.total) * 100}%"></div></div>
    </div>

    ${exercise.ai ? aiCard(exercise.ai) : ''}

    <div class="card">
      <label>Вес</label>
      <div class="stepper">
        <button data-step="weight" data-delta="-2.5">−</button>
        <div class="value">
          <input id="weight" type="number" inputmode="decimal" step="2.5" value="${weight(startWeight)}">
          <div class="unit">кг</div>
        </div>
        <button data-step="weight" data-delta="2.5">+</button>
      </div>
      <div class="delta" id="weight-delta"></div>
    </div>

    <div class="card">
      <label>Повторения</label>
      <div class="stepper">
        <button data-step="reps" data-delta="-1">−</button>
        <div class="value">
          <input id="reps" type="number" inputmode="numeric" step="1" value="${startReps}">
          <div class="unit">раз</div>
        </div>
        <button data-step="reps" data-delta="1">+</button>
      </div>
      <div class="delta" id="reps-delta"></div>
    </div>

    ${recordedSets()}
    ${planList()}

    <button class="btn danger" id="finish">Закончить тренировку</button>
  `);

  bindSteppers();
  bindRecordedSets();

  on('#finish', 'click', finish);

  mainButton('Записать подход', submitSet);
  redrawDeltas();
}

function aiCard(ai) {
  const plates = ai.plates_each_side?.length
    ? `<div class="hint" style="margin-top:4px">Блины: ${ai.plates_each_side.join(' + ')} на сторону</div>`
    : '';

  return `
    <div class="card tight">
      <div class="row">
        <div>
          <span class="pill ai">ИИ</span>
          <span style="margin-left:8px">Рекомендую <b>${weight(ai.next_weight)} кг</b></span>
          ${plates}
        </div>
        <button class="btn secondary small" id="use-ai">Взять</button>
      </div>
    </div>
  `;
}

/** Уже записанные подходы — тап правит, долгий тап удаляет. */
function recordedSets() {
  const done = state.sets.filter((s) => s.exercise_id === state.current.exercise.id);
  if (!done.length) return '';

  return `
    <div class="section-title">Записано</div>
    <div class="card">
      ${done.map((s, i) => `
        <div class="set-chip" data-set="${s.id}" data-weight="${s.weight}" data-reps="${s.reps}">
          <span class="n">Подход ${i + 1}</span>
          <span>${weight(s.weight)} кг × ${s.reps}</span>
        </div>
      `).join('')}
      <div class="hint" style="margin-top:8px">Нажмите на подход, чтобы исправить</div>
    </div>
  `;
}

function planList() {
  const doneCount = state.progress.done;

  return `
    <div class="section-title">План</div>
    <div class="card">
      ${state.plan.map((step, i) => {
        const status = i < doneCount ? 'done' : (i === doneCount ? 'now' : '');
        const mark = i < doneCount ? '✓' : (step.is_circuit ? '↻' : '•');
        const suffix = step.is_circuit
          ? `круг ${step.round_number}/${step.total_rounds}`
          : `подход ${step.set_number}/${step.total_sets}`;

        return `
          <div class="plan-item ${status}">
            <span class="mark">${mark}</span>
            <span class="grow">${escape(step.name)}</span>
            <span class="hint">${suffix}</span>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

/** Отдых: кольцо обратного отсчёта. Цифры идут от сервера. */
function drawRest() {
  const next = state.current;
  const R = 76;
  const C = 2 * Math.PI * R;

  render(`
    <div class="card" style="text-align:center">
      <div class="ring">
        <svg width="168" height="168">
          <circle class="bg" cx="84" cy="84" r="${R}"></circle>
          <circle class="fg" id="arc" cx="84" cy="84" r="${R}"
                  stroke-dasharray="${C}" stroke-dashoffset="0"></circle>
        </svg>
        <div class="clock" id="clock">${clock(rest.secondsLeft())}</div>
      </div>

      <div class="hint" style="margin-bottom:16px">
        ${next ? `Дальше: <b>${escape(next.exercise.name)}</b>, подход ${next.set_number}` : ''}
      </div>

      <button class="btn" id="skip">Закончить отдых</button>
      <button class="btn ghost" id="add-minute" style="margin-top:8px">+1 минута</button>
    </div>

    <div class="hint" style="text-align:center;padding:0 16px">
      Можно закрыть приложение — бот напомнит в чате, когда отдых кончится.
    </div>
  `);

  mainButton(null, null);

  const arc = document.getElementById('arc');
  const clockNode = document.getElementById('clock');

  // Кольцо и цифры перерисовываются на каждый тик из rest.js — там же и источник времени.
  unsubscribe?.();
  unsubscribe = rest.onTick((left, total) => {
    if (!document.body.contains(clockNode)) return;

    clockNode.textContent = clock(left);
    arc.style.strokeDashoffset = total ? C * (1 - left / total) : 0;

    if (left <= 0) draw();   // отдых кончился — обратно к вводу подхода
  });

  on('#skip', 'click', async () => {
    await rest.stop();
    draw();
  });

  on('#add-minute', 'click', async () => {
    haptic('light');
    const { rest: updated } = await api.rest.start(
      rest.secondsLeft() + 60,
      next ? `${next.exercise.name} — подход ${next.set_number}` : null,
    );
    rest.sync(updated);
    drawRest();
  });
}

function drawFinished() {
  const done = state.sets;
  const totalVolume = done.reduce((sum, s) => sum + s.weight * s.reps, 0);

  render(`
    <div class="card" style="text-align:center">
      <div style="font-size:52px">💪</div>
      <h2>Тренировка отработана</h2>
      <div class="hint">${plural(done.length, 'подход', 'подхода', 'подходов')} · ${volume(totalVolume)}</div>
    </div>
    <button class="btn" id="finish">Завершить</button>
  `);

  mainButton('Завершить', finish);
  on('#finish', 'click', finish);
}

/* ---------------------------------------------------------------- действия */

function previousSet() {
  const { current } = state;
  const previous = current.exercise.prev;
  if (!previous.length) return null;

  // Сопоставляем подход с подходом: третий сегодня — с третьим в прошлый раз.
  // Если в прошлый раз подходов было меньше, показываем последний.
  return previous[current.set_number - 1] || previous[previous.length - 1];
}

function bindSteppers() {
  onAll('[data-step]', 'click', (node) => {
    const input = document.getElementById(node.dataset.step);
    const delta = parseFloat(node.dataset.delta);
    const value = (parseFloat(input.value) || 0) + delta;

    input.value = Math.max(0, Math.round(value * 100) / 100);
    haptic('light');
    redrawDeltas();
  });

  on('#weight', 'input', redrawDeltas);
  on('#reps', 'input', redrawDeltas);

  on('#use-ai', 'click', () => {
    document.getElementById('weight').value = weight(state.current.exercise.ai.next_weight);
    haptic('medium');
    redrawDeltas();
  });
}

/** Подсказка «+2.5 кг к прошлому разу» — то, ради чего вообще смотрят на прошлый раз. */
function redrawDeltas() {
  const previous = previousSet();
  const weightNode = document.getElementById('weight-delta');
  const repsNode = document.getElementById('reps-delta');
  if (!weightNode || !previous) return;

  const show = (node, diff, unit) => {
    node.className = `delta ${diff > 0 ? 'up' : diff < 0 ? 'down' : ''}`;
    node.textContent = diff === 0
      ? 'как в прошлый раз'
      : `${diff > 0 ? '+' : ''}${Math.round(diff * 10) / 10} ${unit}`;
  };

  show(weightNode, (parseFloat(document.getElementById('weight').value) || 0) - previous.weight, 'кг');
  show(repsNode, (parseInt(document.getElementById('reps').value, 10) || 0) - previous.reps, 'повт.');
}

async function submitSet() {
  const weightValue = parseFloat(document.getElementById('weight').value);
  const repsValue = parseInt(document.getElementById('reps').value, 10);

  if (!(weightValue >= 0) || !(repsValue >= 1)) {
    return alert('Проверьте вес и повторения');
  }

  mainButtonProgress(true);
  try {
    state = await api.training.addSet({
      session_id: state.session_id,
      exercise_id: state.current.exercise.id,
      weight: weightValue,
      reps: repsValue,
    });

    haptic('success');
    rest.sync(state.rest);   // сервер уже поставил отдых — просто отображаем
    draw();
  } catch (error) {
    haptic('error');
    alert(`Не записалось: ${error.message}`);
  } finally {
    mainButtonProgress(false);
  }
}

function bindRecordedSets() {
  onAction('.set-chip', async (node) => {
    const id = Number(node.dataset.set);
    const currentWeight = Number(node.dataset.weight);
    const currentReps = Number(node.dataset.reps);

    const form = sheet(`
      <h2>Исправить подход</h2>
      <div class="field">
        <label>Вес, кг</label>
        <input type="number" id="edit-weight" inputmode="decimal" step="2.5" value="${weight(currentWeight)}">
      </div>
      <div class="field">
        <label>Повторения</label>
        <input type="number" id="edit-reps" inputmode="numeric" value="${currentReps}">
      </div>
      <button class="btn" id="save">Сохранить</button>
      <button class="btn danger" id="remove" style="margin-top:8px">Удалить подход</button>
    `);

    form.node.querySelector('#save').onclick = async () => {
      const newWeight = parseFloat(form.node.querySelector('#edit-weight').value);
      const newReps = parseInt(form.node.querySelector('#edit-reps').value, 10);

      state = await api.training.editSet(id, newWeight, newReps);
      form.close();
      haptic('success');
      draw();
    };

    form.node.querySelector('#remove').onclick = async () => {
      state = await api.training.deleteSet(id);
      form.close();
      haptic('warning');
      draw();
    };
  });
}

async function finish() {
  const partial = !state.finished;
  const question = partial
    ? 'Тренировка не доделана. Всё равно завершить?'
    : 'Завершить тренировку?';

  if (!await confirm(question)) return;

  const summary = await api.training.finish(state.session_id);
  await rest.stop({ silent: true });

  haptic('success');
  mainButton(null, null);

  render(`
    <div class="card" style="text-align:center">
      <div style="font-size:52px">🏁</div>
      <h2>Готово</h2>
      <div class="hint">
        ${plural(summary.sets, 'подход', 'подхода', 'подходов')} ·
        ${plural(summary.exercises, 'упражнение', 'упражнения', 'упражнений')} ·
        ${volume(summary.volume)}
      </div>
    </div>
    <button class="btn" id="home">На главную</button>
  `);

  on('#home', 'click', () => go('/'));
}
