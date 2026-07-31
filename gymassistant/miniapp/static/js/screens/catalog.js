/**
 * Каталог упражнений и настройка упражнения в дне.
 *
 * В боте это были уровни 5–7 меню: категории → упражнения в категории → добавление,
 * и отдельная ветка настроек, где из всех параметров упражнения можно было менять
 * ровно один — количество подходов. Повторения не менялись никогда: обработчик
 * вызывался только с tp="sets", и base_reps у всех навсегда оставался равен 10.
 */
import { api } from './../api.js';
import { go } from './../router.js';
import { confirm, haptic } from './../tg.js';
import { escape, on, onAction, render, sheet } from './../ui.js';

/** Категории — выбираем, что добавить в день. */
export async function catalogScreen({ dayId }) {
  const { categories } = await api.catalog.categories();

  render(`
    <h1>Добавить упражнение</h1>

    ${categories.map((category) => `
      <button class="list-item" data-category="${category.id}">
        <span class="grow">
          <span class="title">${escape(category.name)}</span><br>
          <span class="sub">${category.count} в каталоге</span>
        </span>
        <span class="chev">›</span>
      </button>
    `).join('')}

    <div class="section-title">Своё</div>
    <button class="list-item" id="mine">
      <span class="grow"><span class="title">Мои упражнения</span><br>
        <span class="sub">Создать или изменить</span></span>
      <span class="chev">›</span>
    </button>
  `);

  onAction('[data-category]', (node) => go(`/catalog/${dayId}/${node.dataset.category}`));
  on('#mine', 'click', () => go('/my-exercises'));
}

/** Упражнения категории — тап добавляет в день. */
export async function categoryScreen({ dayId, categoryId }) {
  const { exercises } = await api.catalog.category(Number(categoryId));

  render(`
    <h1>Выберите упражнение</h1>

    ${exercises.length ? '' : '<div class="empty">В этой группе пока пусто</div>'}

    ${exercises.map((exercise) => `
      <button class="list-item" data-add="${exercise.id}" data-kind="${exercise.kind}">
        <span class="grow">
          <span class="title">
            ${escape(exercise.name)}
            ${exercise.kind === 'user' ? '<span class="pill">своё</span>' : ''}
          </span><br>
          <span class="sub">${escape(exercise.description || '')}</span>
        </span>
        <span class="chev">+</span>
      </button>
    `).join('')}
  `);

  onAction('[data-add]', async (node) => {
    const id = Number(node.dataset.add);
    const kind = node.dataset.kind;

    // Круговое или обычное — спрашиваем сразу: от этого зависит, попадёт ли упражнение
    // в круговой блок вместе с соседями.
    const form = sheet(`
      <h2>Как выполнять?</h2>
      <button class="btn" id="normal">Обычное упражнение</button>
      <p class="hint mt-2">Все подходы подряд, с отдыхом между ними.</p>
      <button class="btn secondary mt-4" id="circle">Круговое</button>
      <p class="hint mt-2">Войдёт в круг вместе с соседними круговыми:
      по одному подходу каждого, затем следующий круг.</p>
    `);

    const add = async (circle) => {
      const payload = kind === 'admin'
        ? { admin_exercise_id: id, circle_training: circle }
        : { user_exercise_id: id, circle_training: circle };

      await api.exercises.add(Number(dayId), payload);
      form.close();
      haptic('success');
      go(`/day/${dayId}`);
    };

    form.node.querySelector('#normal').onclick = () => add(false);
    form.node.querySelector('#circle').onclick = () => add(true);
  });
}

/** Настройки упражнения в дне: подходы, повторения, круговое. */
export async function exerciseScreen({ dayId, id }) {
  const data = await api.day(Number(dayId));
  const exercise = data.exercises.find((e) => e.id === Number(id));

  if (!exercise) return go(`/day/${dayId}`, { replace: true });

  render(`
    <h1>${escape(exercise.name)}</h1>
    <p class="subtitle">${escape(exercise.description || '')}</p>

    <!-- Подписи только в <label>: у степпера есть и своя, .unit, но здесь она
         повторила бы слово в слово то, что уже написано над полем. -->
    <label for="sets">Подходов</label>
    <div class="stepper compact">
        <button data-field="sets" data-delta="-1" aria-label="Подходов: минус 1">−</button>
        <div class="value">
          <input id="sets" type="number" inputmode="numeric" value="${exercise.sets}" min="1" max="20">
        </div>
        <button data-field="sets" data-delta="1" aria-label="Подходов: плюс 1">+</button>
    </div>

    <label class="mt-4" for="reps">Повторений в подходе</label>
    <div class="stepper compact">
        <button data-field="reps" data-delta="-1" aria-label="Повторений: минус 1">−</button>
        <div class="value">
          <input id="reps" type="number" inputmode="numeric" value="${exercise.reps}" min="1" max="100">
        </div>
        <button data-field="reps" data-delta="1" aria-label="Повторений: плюс 1">+</button>
    </div>

    <div class="switch-card mt-4">
      <label class="switch">
        <span class="grow">
          <span class="lead">Круговое</span><br>
          <span class="hint">В круге с соседними круговыми упражнениями</span>
        </span>
        <input type="checkbox" id="circle" ${exercise.circle ? 'checked' : ''}>
        <span class="track"></span>
      </label>
    </div>

    <button class="btn mt-4" id="save">Сохранить</button>
    <button class="btn danger mt-2" id="remove">Убрать из дня</button>
  `);

  onAction('[data-field]', (node) => {
    const input = document.getElementById(node.dataset.field);
    const value = (parseInt(input.value, 10) || 0) + parseInt(node.dataset.delta, 10);
    input.value = Math.max(1, value);
  });

  on('#save', 'click', async () => {
    await api.exercises.update(exercise.id, {
      sets: parseInt(document.getElementById('sets').value, 10),
      reps: parseInt(document.getElementById('reps').value, 10),
      circle_training: document.getElementById('circle').checked,
    });
    haptic('success');
    go(`/day/${dayId}`);
  });

  on('#remove', 'click', async () => {
    if (!await confirm('Убрать упражнение из этого дня?')) return;
    await api.exercises.remove(exercise.id);
    haptic('warning');
    go(`/day/${dayId}`);
  });
}

/** Личные упражнения: создать, изменить, удалить. */
export async function myExercisesScreen() {
  const [{ exercises }, { categories }] = await Promise.all([
    api.userExercises.list(),
    api.catalog.categories(),
  ]);

  const categoryName = (id) => categories.find((c) => c.id === id)?.name || '';

  render(`
    <h1>Мои упражнения</h1>

    ${exercises.length ? '' : `
      <div class="empty">
        <p>Своих упражнений пока нет.</p>
        <p class="hint">Добавьте то, чего нет в каталоге.</p>
      </div>
    `}

    ${exercises.map((exercise) => `
      <button class="list-item" data-edit="${exercise.id}">
        <span class="grow">
          <span class="title">${escape(exercise.name)}</span><br>
          <span class="sub">${escape(categoryName(exercise.category_id))}</span>
        </span>
        <span class="chev">›</span>
      </button>
    `).join('')}

    <button class="btn secondary mt-4" id="create">Создать упражнение</button>
  `);

  on('#create', 'click', () => editUserExercise(null, categories));
  onAction('[data-edit]', (node) => {
    const exercise = exercises.find((e) => e.id === Number(node.dataset.edit));
    editUserExercise(exercise, categories);
  });
}

function editUserExercise(exercise, categories) {
  const form = sheet(`
    <h2>${exercise ? 'Изменить' : 'Новое упражнение'}</h2>

    <div class="field">
      <label>Название</label>
      <input type="text" id="name" maxlength="150" value="${escape(exercise?.name || '')}">
    </div>

    <div class="field">
      <label>Описание</label>
      <textarea id="description" maxlength="1000">${escape(exercise?.description || '')}</textarea>
    </div>

    <div class="field">
      <label>Группа мышц</label>
      <select id="category">
        ${categories.map((c) => `
          <option value="${c.id}" ${exercise?.category_id === c.id ? 'selected' : ''}>
            ${escape(c.name)}
          </option>
        `).join('')}
      </select>
    </div>

    <button class="btn" id="save">Сохранить</button>
    ${exercise ? '<button class="btn danger mt-2" id="remove">Удалить</button>' : ''}
  `);

  form.node.querySelector('#save').onclick = async () => {
    const payload = {
      name: form.node.querySelector('#name').value.trim(),
      description: form.node.querySelector('#description').value.trim(),
      category_id: Number(form.node.querySelector('#category').value),
    };

    if (!payload.name) return;

    if (exercise) await api.userExercises.update(exercise.id, payload);
    else await api.userExercises.create(payload);

    form.close();
    haptic('success');
    myExercisesScreen();
  };

  const removeButton = form.node.querySelector('#remove');
  if (removeButton) {
    removeButton.onclick = async () => {
      // Упражнение может стоять в днях программы — там оно удалится каскадом
      // вместе со всей историей подходов по нему. Предупреждаем честно.
      if (!await confirm('Удалить упражнение? Оно исчезнет из всех программ вместе с историей.')) return;

      await api.userExercises.remove(exercise.id);
      form.close();
      haptic('warning');
      myExercisesScreen();
    };
  }
}
