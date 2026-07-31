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

/**
 * Ввод подхода.
 *
 * Порядок блоков — контекст сверху, ввод снизу: где мы → что за упражнение →
 * все его подходы → поля → действия. Таблица подходов стоит НАД степперами
 * намеренно, по двум причинам. Она уводит кнопки «−/+» из верхней трети экрана
 * ближе к большому пальцу — их за тренировку жмут десятки раз, а «Записать
 * подход» ровно один раз на подход. И она держит высоту: строки на все подходы
 * упражнения нарисованы сразу, поэтому запись подхода не двигает степперы
 * под пальцем.
 */
function drawEntry() {
  const { current } = state;
  const exercise = current.exercise;
  const previous = previousSet();

  const startWeight = previous?.weight ?? 20;
  const startReps = previous?.reps ?? exercise.reps;

  render(`
    <div class="overline flush">${position(current)}</div>

    <div class="exercise-name">${escape(exercise.name)}</div>
    ${record(exercise.record, previous)}

    ${setTable()}

    ${stepper('weight', 'вес, кг', weight(startWeight), 2.5, 'decimal')}
    <div class="delta" id="weight-delta"></div>

    ${stepper('reps', 'повторения', startReps, 1, 'numeric')}
    <div class="delta" id="reps-delta"></div>

    <button class="btn outlined mt-3" id="skip">${skipLabel()}</button>

    ${planFold()}

    <button class="btn quiet mt-4" id="finish">Закончить тренировку</button>
  `);

  bindSteppers();
  bindSetRows();

  on('#skip', 'click', skip);
  on('#finish', 'click', finish);

  mainButton('Записать подход', submitSet);
  redrawDeltas();
}

/**
 * Как называется одна единица работы. У круговых это круг, а не подход:
 * в плане `set_number` кругового упражнения и ЕСТЬ номер круга
 * (services/workout.py), поэтому строка «Подход 2» врала бы прямо под
 * заголовком «круг 2 из 3».
 */
function words() {
  return state.current.is_circuit
    ? { title: 'Круг', one: 'круг', few: 'круга', many: 'кругов' }
    : { title: 'Подход', one: 'подход', few: 'подхода', many: 'подходов' };
}

/**
 * Все подходы упражнения одной таблицей: сделанные, текущий и те, что впереди.
 *
 * Раньше здесь был список только записанных — до первого подхода пустой, из-за
 * чего экран начинался с дыры в треть высоты, а каждая запись двигала вёрстку.
 * И «прошлый раз» жил отдельной строкой наверху, где он по построению повторял
 * оба степпера: поля предзаполнены ровно этими числами (см. startWeight выше).
 * В таблице та же справка стоит там, где она не дублируется, — на подходах,
 * которых ещё не было.
 */
function setTable() {
  const { current } = state;
  const done = state.sets.filter((s) => s.exercise_id === current.exercise.id);
  const before = current.exercise.prev;
  const word = words().title;

  const rows = [];
  for (let i = 0; i < current.total_sets; i += 1) {
    const fact = done[i];
    const name = `<span class="grow">${word} ${i + 1}</span>`;

    // Записанное — кнопка: по ней же подход и правят.
    if (fact) {
      rows.push(`
        <button class="set-row ${fact.skipped ? 'skipped' : 'done'}"
                data-set="${fact.id}" data-weight="${fact.weight}" data-reps="${fact.reps}">
          <span class="mark">${fact.skipped ? '—' : '✓'}</span>
          ${name}
          <span class="v">${fact.skipped ? 'пропущен' : `${weight(fact.weight)} кг × ${fact.reps}`}</span>
        </button>
      `);
      continue;
    }

    const now = i + 1 === current.set_number;
    const was = before[i];

    rows.push(`
      <div class="set-row${now ? ' now' : ''}">
        <span class="mark">${now ? '●' : '·'}</span>
        ${name}
        ${now
          ? '<span class="pill on">сейчас</span>'
          : `<span class="v was">${was ? `было ${weight(was.weight)} × ${was.reps}` : ''}</span>`}
      </div>
    `);
  }

  return `
    <div class="sets">${rows.join('')}</div>
    ${done.length ? '<div class="hint mt-2">Нажмите на записанный подход, чтобы исправить</div>' : ''}
  `;
}

/* ---------------------------------------------------------- пропуск подхода
 *
 * Раньше выхода не было: план двигался только записанным подходом, поэтому не
 * сделав третий, человек либо записывал его, соврав про вес, либо бросал тренировку.
 * Вариантов два, потому что причины разные: «этот не смог, следующий попробую»
 * и «сегодня не идёт вовсе».
 */

/** Сколько подходов упражнения ещё не закрыто, считая текущий. */
function remaining() {
  return state.current.total_sets - state.current.set_number + 1;
}

/**
 * Многоточие — это обещание: нажатие потребует ещё одного выбора.
 *
 * Кнопка называлась «Пропустить подход», а открывала шторку, первый пункт которой
 * назывался так же. То есть подпись обещала действие, а давала меню, и самый
 * частый случай стоил двух тапов. Теперь выбор предлагается только когда он есть:
 * на последнем подходе упражнения «пропустить этот» и «закончить упражнение» —
 * одно и то же, и кнопка делает это сразу. Пропуск обратим тапом по строке
 * подхода («Всё-таки сделал»), поэтому подтверждения не просим.
 */
function skipLabel() {
  return remaining() > 1 ? 'Пропустить подход…' : 'Пропустить подход';
}

async function skip() {
  if (remaining() > 1) return skipSheet();
  await sendSkip(false);
}

async function sendSkip(whole, form) {
  try {
    state = await api.training.skip(state.session_id, state.current.exercise.id, whole);
  } catch (error) {
    form?.close();
    haptic('error');
    return alert(`Не удалось: ${error.message}`);
  }

  form?.close();
  haptic('warning');
  rest.sync(state.rest);
  draw();
}

function skipSheet() {
  const { one, few, many } = words();
  const form = sheet(`
    <h2>Пропустить</h2>
    <p class="hint">${escape(state.current.exercise.name)} — ${position(state.current)}</p>

    <button class="btn secondary mt-4" id="skip-one">Только этот ${one}</button>
    <button class="btn secondary mt-2" id="skip-all">
      Всё упражнение · ${plural(remaining(), one, few, many)}
    </button>

    <p class="hint mt-3">
      Пропущенное остаётся в тренировке, но не идёт ни в объём, ни в рекорды.
    </p>
  `);

  form.node.querySelector('#skip-one').onclick = () => sendSkip(false, form);
  form.node.querySelector('#skip-all').onclick = () => sendSkip(true, form);
}

/**
 * Где мы сейчас — одной строкой.
 *
 * У круговых раньше висело только «круг 1 из 3». Это половина ответа: круг говорит,
 * сколько раз пройти блок, но не сколько снарядов осталось внутри круга, — а стоя
 * между тремя станциями хочется знать именно это. Получалось, что в самом путаном
 * режиме информации меньше, чем в простом, где «подход 2 из 4» отвечает на всё.
 */
function position(current) {
  if (!current.is_circuit) {
    return `подход ${current.set_number} из ${current.total_sets}`;
  }

  const round = `круг ${current.round_number} из ${current.total_rounds}`;

  // Круговой блок из одного упражнения — вырожденный случай: «упражнение 1 из 1»
  // ничего не добавляет.
  return current.total_exercises > 1
    ? `${round} · упражнение ${current.exercise_number} из ${current.total_exercises}`
    : round;
}

/**
 * Рекорд — только если до него ещё есть куда тянуться.
 *
 * Когда прошлый раз и был рекордом, строка превращалась в третье повторение одного
 * и того же числа: «прошлый раз 30 × 7 · рекорд 30 кг» над полем, где набрано 30.
 * Ровно та же причина, по которой отсюда убрали строку с советом веса.
 */
function record(value, previous) {
  if (!value || value <= (previous?.weight ?? 0)) return '';
  return `<div class="meta">рекорд <b>${weight(value)} кг</b></div>`;
}

/**
 * Степпер: «−шаг», число, «+шаг».
 *
 * Шаг написан НА кнопках, и это не украшение. Он решает сразу две вещи: на сколько
 * двигает кнопка, раньше выяснялось только тыком; и два одинаковых по кеглю степпера
 * стали различимы — «±2.5» и «±1» опознаются мгновенно, а подпись под числом
 * (11 пикселей, самый мелкий текст экрана) для этого не годилась.
 *
 * aria-label на всём: без них скринридер читает четыре кнопки как «минус, плюс,
 * минус, плюс», не сообщая, какая пара к какому полю относится.
 *
 * Подписи называют ПОЛЕ, а не единицу: было «КГ» и «ПОВТОРЕНИЙ» — единица
 * измерения против существительного в родительном падеже, две разные сущности
 * в симметричных местах. Теперь «ВЕС, КГ» и «ПОВТОРЕНИЯ».
 */
function stepper(field, caption, value, step, mode) {
  const label = (delta) => `${caption}: ${delta > 0 ? 'плюс' : 'минус'} ${step}`;
  const face = (delta) => `${delta > 0 ? '+' : '−'}${step}`;

  return `
    <div class="stepper mt-4">
      <button class="step" data-step="${field}" data-delta="${-step}"
              aria-label="${label(-step)}">${face(-step)}</button>
      <div class="value">
        <input id="${field}" type="number" inputmode="${mode}" step="${step}"
               value="${value}" aria-label="${caption}">
        <div class="unit">${caption}</div>
      </div>
      <button class="step" data-step="${field}" data-delta="${step}"
              aria-label="${label(step)}">${face(step)}</button>
    </div>
  `;
}

/**
 * План всей тренировки — свёрнутый ряд-раскрывашка.
 *
 * Здесь же теперь живёт счёт по тренировке. Раньше «осталось 12 подходов» стояло
 * наверху, в двух сантиметрах от «подход 1 из 3»: два счётчика одним словом, но
 * один про упражнение, другой про весь день, — читалось как противоречие. Теперь
 * уровни разведены: шапка экрана говорит только про текущее упражнение, про
 * тренировку целиком — эта строка и список под ней.
 *
 * Полосы прогресса не осталось вовсе. Ростом в три пикселя и залитая на ноль
 * в начале тренировки, она была неотличима от разделителя, а сам список с
 * галочками показывает то же самое честнее.
 */
function planFold() {
  const doneCount = state.progress.done;
  const left = state.progress.total - doneCount;

  return `
    <details class="fold">
      <summary>
        <span class="grow">План тренировки</span>
        <span class="sub">${left
          ? `ещё ${plural(left, 'подход', 'подхода', 'подходов')}`
          : 'всё сделано'}</span>
        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
      </summary>
    ${state.plan.map((step, i) => {
      const status = i < doneCount ? 'done' : (i === doneCount ? 'now' : '');
      const mark = i < doneCount ? '✓' : (step.is_circuit ? '↻' : '·');
      const suffix = step.is_circuit
        ? `круг ${step.round_number}/${step.total_rounds}`
        : `подход ${step.set_number}/${step.total_sets}`;

      return `
        <div class="plan-item ${status}">
          <span class="mark">${mark}</span>
          <span class="grow">${escape(step.name)}</span>
          <span class="num">${suffix}</span>
        </div>
      `;
    }).join('')}
    </details>
  `;
}

/** Отдых: кольцо обратного отсчёта. Цифры идут от сервера. */
function drawRest() {
  const next = state.current;
  const R = 76;
  const C = 2 * Math.PI * R;

  render(`
    <div class="overline flush center">отдых</div>

    <div class="ring">
      <svg width="168" height="168">
        <circle class="bg" cx="84" cy="84" r="${R}"></circle>
        <circle class="fg" id="arc" cx="84" cy="84" r="${R}"
                stroke-dasharray="${C}" stroke-dashoffset="0"></circle>
      </svg>
      <div class="clock" id="clock">${clock(rest.secondsLeft())}</div>
    </div>

    ${next ? `
      <div class="card accent center">
        <div class="overline flush">дальше</div>
        <div class="lead mt-1">${escape(next.exercise.name)}</div>
        <div class="hint">подход ${next.set_number} из ${next.total_sets}</div>
      </div>
    ` : ''}

    <button class="btn mt-4" id="skip">Закончить отдых</button>
    <button class="btn outlined mt-2" id="add-minute">+1 минута</button>

    <p class="hint center mt-4">
      Можно закрыть приложение — бот напомнит в чате, когда отдых кончится.
    </p>
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

  // Итог — это одно число, поэтому оно и набрано как заголовок, а не спрятано в строку.
  render(`
    <div class="overline flush center">тренировка отработана</div>
    <div class="card accent center mt-3">
      <div class="display">${volume(totalVolume)}</div>
      <div class="hint mt-1">поднято за сегодня</div>
    </div>
    <p class="hint center">${plural(done.length, 'подход', 'подхода', 'подходов')}</p>
    <button class="btn mt-4" id="finish">Завершить</button>
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
}

/**
 * Подсказка «+2.5 кг к прошлому разу» — то, ради чего вообще смотрят на прошлый раз.
 *
 * Показывается только при расхождении. Раньше при равенстве под обоими степперами
 * писалось «как в прошлый раз» — две строки текста ровно про то, что ничего
 * не изменилось.
 *
 * Слот есть у обоих полей, даже когда пуст. Раньше он был только под весом, и
 * отступ над «ПОВТОРЕНИЯ» выходил вдвое больше, чем над «ВЕС»: кегли степперам
 * уравняли как паре, а вертикальный ритм эту работу отменял — на экране они
 * читались двумя независимыми блоками.
 */
function redrawDeltas() {
  const previous = previousSet();
  if (!previous) return;

  delta('weight-delta', (parseFloat(document.getElementById('weight').value) || 0) - previous.weight,
    (n) => `${weight(n)} кг`);

  delta('reps-delta', (parseInt(document.getElementById('reps').value, 10) || 0) - previous.reps,
    (n) => plural(n, 'повторение', 'повторения', 'повторений'));
}

function delta(id, diff, format) {
  const node = document.getElementById(id);
  if (!node) return;

  const rounded = Math.round(diff * 10) / 10;
  node.className = `delta ${rounded > 0 ? 'up' : rounded < 0 ? 'down' : ''}`;
  node.textContent = rounded === 0
    ? ''
    : `${rounded > 0 ? '+' : '−'}${format(Math.abs(rounded))} к прошлому разу`;
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

function bindSetRows() {
  // Только записанные: у строк, которых ещё не было, править нечего.
  onAction('.set-row.done, .set-row.skipped', async (node) => {
    const id = Number(node.dataset.set);
    const wasSkipped = node.classList.contains('skipped');

    // У пропущенного в базе нули — подставлять их в форму бессмысленно.
    // Берём то же, с чего начинается обычный ввод: прошлый раз или план.
    const previous = previousSet();
    const currentWeight = wasSkipped ? (previous?.weight ?? 20) : Number(node.dataset.weight);
    const currentReps = wasSkipped
      ? (previous?.reps ?? state.current?.exercise?.reps ?? 10)
      : Number(node.dataset.reps);

    const form = sheet(`
      <h2>${wasSkipped ? 'Всё-таки сделал' : 'Исправить подход'}</h2>
      ${wasSkipped ? '<p class="hint">Подход перестанет считаться пропущенным.</p>' : ''}
      <div class="field">
        <label>Вес, кг</label>
        <input type="number" id="edit-weight" inputmode="decimal" step="2.5" value="${weight(currentWeight)}">
      </div>
      <div class="field">
        <label>Повторения</label>
        <input type="number" id="edit-reps" inputmode="numeric" value="${currentReps}">
      </div>
      <button class="btn" id="save">Сохранить</button>
      <button class="btn danger mt-2" id="remove">Удалить подход</button>
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
    <div class="overline flush center">готово</div>
    <div class="card accent center mt-3">
      <div class="display">${volume(summary.volume)}</div>
      <div class="hint mt-1">общий объём</div>
    </div>
    <p class="hint center">
      ${plural(summary.sets, 'подход', 'подхода', 'подходов')} ·
      ${plural(summary.exercises, 'упражнение', 'упражнения', 'упражнений')}
    </p>
    <button class="btn mt-4" id="home">На главную</button>
  `);

  on('#home', 'click', () => go('/'));
}
