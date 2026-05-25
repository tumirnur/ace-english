
let graphData = null;
let studentMastery = {};
let currentTopicKey = null;
let currentQuestion = null;
let askedQuestionIds = [];
let answered = false;
let sessionErrors = [];
let sessionGapShown = false;
let currentTeacherGroupId = null;

let currentStudent = JSON.parse(localStorage.getItem('ace_student') || 'null');

let loginMode = 'login'; // 'login' | 'register'

function setLoginMode(mode) {
  loginMode = mode;
  document.getElementById('btn-mode-login').classList.toggle('active', mode === 'login');
  document.getElementById('btn-mode-reg').classList.toggle('active', mode === 'register');
  const btn = document.getElementById('login-submit-btn');
  btn.textContent = mode === 'login' ? 'Войти →' : 'Создать аккаунт →';
  document.getElementById('login-hint').textContent = mode === 'login'
    ? 'Нет аккаунта? Нажми «Регистрация»'
    : 'Уже есть аккаунт? Нажми «Войти»';
  showLoginError('');
}

function showLoginError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.classList.toggle('visible', !!msg);
}

async function doLogin() {
  const name = document.getElementById('login-name').value.trim();
  const password = document.getElementById('login-password').value;
  if (!name) { document.getElementById('login-name').focus(); return; }
  if (!password) { document.getElementById('login-password').focus(); return; }

  const btn = document.getElementById('login-submit-btn');
  btn.disabled = true;
  btn.textContent = '…';
  showLoginError('');

  const endpoint = loginMode === 'login' ? '/api/auth/login' : '/api/auth/register';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      showLoginError(data.detail || 'Ошибка. Попробуй снова.');
      btn.disabled = false;
      btn.textContent = loginMode === 'login' ? 'Войти →' : 'Создать аккаунт →';
      return;
    }
    currentStudent = data;
    localStorage.setItem('ace_student', JSON.stringify(data));
    showUserChip(data);
    document.getElementById('login-overlay').classList.add('hidden');
    init();
  } catch {
    showLoginError('Нет соединения с сервером');
    btn.disabled = false;
    btn.textContent = loginMode === 'login' ? 'Войти →' : 'Создать аккаунт →';
  }
}

function doLogout() {
  localStorage.removeItem('ace_student');
  currentStudent = null;
  document.getElementById('nav-user').classList.add('hidden');
  document.getElementById('login-overlay').classList.remove('hidden');
  document.getElementById('login-name').value = '';
  document.getElementById('login-password').value = '';
  showLoginError('');
}

function showUserChip(student) {
  const nav = document.getElementById('nav-user');
  document.getElementById('nav-user-name').textContent = student.name;
  document.getElementById('nav-user-letter').textContent = student.name[0].toUpperCase();
  nav.classList.remove('hidden');
}

['login-name', 'login-password'].forEach(id => {
  document.getElementById(id).addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
});

function switchTab(tab) {
  const tabs = ['course', 'student', 'teacher', 'oulad'];
  document.querySelectorAll('.tab-btn').forEach((b, i) =>
    b.classList.toggle('active', tabs[i] === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  if (tab === 'teacher') loadTeacher();
  if (tab === 'student') initStudentTab();
  if (tab === 'oulad') initOuladTab();
}

async function initCourse() {
  const res = await fetch('/api/graph');
  graphData = await res.json();
  drawGraph();
}

const NODE_EN = {
  subject_verb:         'Subject + Verb',
  present_simple:       'Present Simple',
  irregular_verbs:      'Irregular Verbs',
  present_continuous:   'Present Continuous',
  future_will:          'Future Simple',
  past_simple:          'Past Simple',
  future_going_to:      'be going to',
  present_perfect:      'Present Perfect',
  past_continuous:      'Past Continuous',
  past_perfect:         'Past Perfect',
  present_perfect_cont: 'Present Perfect Continuous',
};

const NODE_RU = {
  subject_verb:         'Подлежащее и сказуемое',
  present_simple:       'Настоящее простое',
  irregular_verbs:      'Неправильные глаголы',
  present_continuous:   'Настоящее длительное',
  future_will:          'Будущее (will)',
  past_simple:          'Прошедшее простое',
  future_going_to:      'Будущее (going to)',
  present_perfect:      'Настоящее совершённое',
  past_continuous:      'Прошедшее длительное',
  past_perfect:         'Прошедшее совершённое',
  present_perfect_cont: 'Совершённое длительное',
};

function drawGraph() {
  const edgeLayer  = document.getElementById('edges-layer');
  const chipsLayer = document.getElementById('chips-layer');
  const nodeLayer  = document.getElementById('nodes-layer');
  edgeLayer.innerHTML  = '';
  chipsLayer.innerHTML = '';
  nodeLayer.innerHTML  = '';

  const W = 64, H = 64, RX = 15;
  const LABEL_Y = H / 2 + 11;

  const nodeMap = {};
  graphData.nodes.forEach(n => nodeMap[n.key] = n);

  graphData.edges.forEach(e => {
    const from = nodeMap[e.from];
    const to   = nodeMap[e.to];
    if (!from || !to) return;
    const x1 = from.pos_x;
    const y1 = from.pos_y + H / 2 + 3;
    const x2 = to.pos_x;
    const y2 = to.pos_y - H / 2 - 6;
    const midY = (y1 + y2) / 2;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M ${x1},${y1} C ${x1},${midY} ${x2},${midY} ${x2},${y2}`);
    path.classList.add('edge-line');
    edgeLayer.appendChild(path);
  });

  graphData.nodes.forEach(n => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('transform', `translate(${n.pos_x},${n.pos_y})`);

    const cls = nodeClass(n.key, n.prerequisite_keys);
    const isLocked = cls === 'node-locked';

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', -W / 2);
    rect.setAttribute('y', -H / 2);
    rect.setAttribute('width', W);
    rect.setAttribute('height', H);
    rect.setAttribute('rx', RX);
    rect.setAttribute('ry', RX);
    rect.classList.add('node-rect', cls);
    if (!isLocked) {
      rect.style.cursor = 'pointer';
      rect.addEventListener('click', () => selectTopic(n.key));
    }

    const abbr = wrapText(NODE_EN[n.key] || n.key, 11);
    const abbrStartY = -(abbr.length - 1) * 7;
    abbr.forEach((word, i) => {
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.textContent = word;
      t.classList.add('node-icon');
      t.setAttribute('x', 0);
      t.setAttribute('y', abbrStartY + i * 14);
      if (isLocked) t.style.fill = 'rgba(255,255,255,.22)';
      if (cls === 'node-progress') t.style.fill = '#0c0c0c'; // black on lime
      if (!isLocked) t.style.cursor = 'pointer';
      g.appendChild(t);
    });

    const titleLines = wrapText(NODE_RU[n.key] || n.title, 14);
    const chipLineH = 13;
    const chipPadV = 6;
    const chipH = titleLines.length * chipLineH + chipPadV * 2;
    const maxLen = Math.max(...titleLines.map(l => l.length));
    const chipW = Math.max(maxLen * 6.2 + 18, 44);
    const chipY = LABEL_Y;

    const chip = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    chip.setAttribute('x', n.pos_x - chipW / 2);
    chip.setAttribute('y', n.pos_y + chipY);
    chip.setAttribute('width', chipW);
    chip.setAttribute('height', chipH);
    chip.setAttribute('rx', chipH / 2);
    chip.setAttribute('ry', chipH / 2);
    chip.classList.add(isLocked ? 'node-chip-locked' : 'node-chip');
    chipsLayer.appendChild(chip);

    titleLines.forEach((word, i) => {
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.textContent = word;
      t.classList.add('node-label');
      t.setAttribute('x', 0);
      t.setAttribute('y', chipY + chipPadV + chipLineH * i + chipLineH / 2);
      if (isLocked) t.classList.add('node-label-locked');
      if (!isLocked) t.style.cursor = 'pointer';
      g.appendChild(t);
    });

    if (!isLocked) g.addEventListener('click', () => selectTopic(n.key));

    g.insertBefore(rect, g.firstChild);
    nodeLayer.appendChild(g);
  });
}

function wrapText(text, maxLen) {
  const words = text.split(' ');
  const lines = [];
  let cur = '';
  for (const w of words) {
    if ((cur + ' ' + w).trim().length > maxLen && cur) { lines.push(cur); cur = w; }
    else cur = (cur + ' ' + w).trim();
  }
  if (cur) lines.push(cur);
  return lines;
}

function nodeClass(key, prereqKeys) {
  const acc = studentMastery[key];
  if (acc !== undefined) {
    if (acc >= 0.8) return 'node-mastered';
    if (acc > 0)   return 'node-progress';
  }
  const locked = prereqKeys.some(pk => (studentMastery[pk] ?? -1) < 0.5);
  return locked ? 'node-locked' : 'node-available';
}

function selectTopic(key) {
  currentTopicKey = key;
  askedQuestionIds = [];
  sessionErrors = [];
  sessionGapShown = false;

  const node = graphData.nodes.find(n => n.key === key);
  if (!node) return;
  const stars = '★'.repeat(node.difficulty) + '☆'.repeat(4 - node.difficulty);

  document.getElementById('question-panel').innerHTML = `
    <div class="topic-kicker">
      <span class="topic-kicker__name">${node.title}</span>
      <span class="topic-kicker__stars">${stars}</span>
    </div>
    ${node.theory ? `
      <div class="theory-box">
        <div class="theory-box__title">Теория</div>
        <div class="theory-box__body">${node.theory}</div>
      </div>` : ''}
    <button class="btn btn-orange" style="margin-top:1rem;width:100%"
            onclick="loadQuestion()">Начать тест по теме →</button>
  `;
}

async function loadQuestion() {
  if (!currentTopicKey) return;
  const lastId = askedQuestionIds[askedQuestionIds.length - 1] || 0;
  const res = await fetch(
    `/api/topic/${currentTopicKey}/question?exclude_ids=${askedQuestionIds.join(',')}&last_id=${lastId}`
  );
  if (!res.ok) { showEmptyHint('Нет вопросов для этой темы'); return; }
  currentQuestion = await res.json();
  if (!askedQuestionIds.includes(currentQuestion.id))
    askedQuestionIds.push(currentQuestion.id);
  else
    askedQuestionIds = [currentQuestion.id];
  renderQuestion(currentQuestion);
}

function renderQuestion(q) {
  answered = false;
  const diff = getTopicDifficulty(q.topic_key);
  const stars = '★'.repeat(diff) + '☆'.repeat(4 - diff);
  const panel = document.getElementById('question-panel');
  panel.innerHTML = `
    <div class="topic-kicker">
      <span class="topic-kicker__name">${q.topic_title}</span>
      <span class="topic-kicker__stars">${stars}</span>
    </div>
    <div class="question-text">${q.text.replace(/___/g, '<u>___</u>')}</div>
    <div id="hint-area"></div>
    <button class="btn btn-ghost btn-sm hint-btn" id="hint-btn" onclick="getHint()">
      Получить подсказку
    </button>
    <div class="options-list" id="options-list" style="margin-top:.75rem"></div>
    <div id="feedback-area"></div>
    <div id="gap-analysis-area"></div>
  `;
  const list = document.getElementById('options-list');
  q.options.forEach(o => {
    const btn = document.createElement('button');
    btn.className = 'quiz-option';
    btn.textContent = o;
    btn.addEventListener('click', () => pickOption(btn, o));
    list.appendChild(btn);
  });
}

async function getHint() {
  const btn = document.getElementById('hint-btn');
  if (!btn) return;
  btn.disabled = true;
  btn.textContent = 'Думаю…';
  document.getElementById('hint-area').innerHTML =
    '<div class="loader" style="margin:.5rem 0"></div>';
  try {
    const res = await fetch(
      `/api/topic/${currentTopicKey}/hint?question_id=${currentQuestion.id}`
    );
    const data = await res.json();
    document.getElementById('hint-area').innerHTML =
      `<div class="hint-box"><em>${data.hint || 'Подсказка недоступна'}</em></div>`;
  } catch {
    document.getElementById('hint-area').innerHTML =
      `<div class="hint-box">Подсказка временно недоступна</div>`;
  }
  btn.remove();
}

function getTopicDifficulty(key) {
  if (!graphData) return 1;
  return (graphData.nodes.find(n => n.key === key) || {}).difficulty || 1;
}

function esc(s) { return s.replace(/'/g, '&#39;').replace(/"/g, '&quot;'); }

function pickOption(btn, answer) {
  if (answered) return;
  answered = true;
  document.querySelectorAll('.quiz-option').forEach(b => { b.disabled = true; });
  btn.classList.add('selected');
  submitAnswer(answer, btn);
}

async function submitAnswer(answer, btn) {
  const res = await fetch('/api/answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      student_id: currentStudent?.id || 1,
      question_id: currentQuestion.id,
      student_answer: answer,
    }),
  });
  const data = await res.json();

  document.querySelectorAll('.quiz-option').forEach(b => {
    if (b.textContent.trim() === data.correct_answer.trim()) b.classList.add('correct');
  });
  if (!data.is_correct) btn.classList.add('wrong');

  const acc = studentMastery[currentTopicKey] || 0;
  studentMastery[currentTopicKey] = data.is_correct
    ? Math.min(acc + 0.15, 1)
    : Math.max(acc - 0.05, 0);
  drawGraph();

  const fb = document.getElementById('feedback-area');
  if (data.is_correct) {
    fb.innerHTML = `
      <div class="feedback-box feedback-box--ok">Правильно! Отличная работа.</div>
      <button class="btn btn-ghost" style="margin-top:.75rem;width:100%"
              onclick="loadQuestion()">Следующий вопрос →</button>
    `;
  } else {
    sessionErrors.push({
      topic: currentTopicKey,
      topic_title: currentQuestion.topic_title || currentTopicKey,
      error_category: data.error_category || '',
      question_text: currentQuestion.text || '',
      student_answer: answer,
      question_id: currentQuestion.id,
    });

    let redirectHtml = '';
    if (data.redirect_to_key) {
      const node = graphData.nodes.find(n => n.key === data.redirect_to_key);
      const title = node ? node.title : data.redirect_to_key;
      redirectHtml = `
        <div class="redirect-box">
          ${data.redirect_reason ? `<span>${data.redirect_reason}</span><br><br>` : ''}
          <button class="btn btn-orange btn-sm"
                  onclick="selectTopic('${data.redirect_to_key}')">
            Перейти к «${title}» →
          </button>
        </div>`;
    }
    fb.innerHTML = `
      <div class="feedback-box feedback-box--warn">
        Неверно. Правильный ответ: <strong>${data.correct_answer}</strong>
        ${data.diagnosis ? `<br><br>${data.diagnosis}` : ''}
      </div>
      ${redirectHtml}
      <button class="btn btn-ghost" style="margin-top:.75rem;width:100%"
              onclick="loadQuestion()">Попробовать ещё раз →</button>
    `;
    if (sessionErrors.length >= 2 && !sessionGapShown) analyzeSessionGaps();
  }
}

async function analyzeSessionGaps() {
  sessionGapShown = true;
  const area = document.getElementById('gap-analysis-area');
  if (!area) return;
  area.innerHTML = '<div class="loader" style="margin:.75rem 0"></div>';
  try {
    const res = await fetch(`/api/student/${currentStudent?.id || 1}/session-gaps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ errors: sessionErrors }),
    });
    const data = await res.json();
    area.innerHTML = data.summary ? `
      <div class="gap-analysis-box">
        <div class="gap-analysis-box__title">Обнаружена системная ошибка</div>
        <div>${data.summary}</div>
        ${data.recommendation ? `<div style="margin-top:.5rem;font-style:italic;color:var(--muted)">${data.recommendation}</div>` : ''}
      </div>` : '';
  } catch { area.innerHTML = ''; }
}

function showEmptyHint(msg) {
  document.getElementById('question-panel').innerHTML =
    `<div class="empty-hint"><div>${msg}</div></div>`;
}

async function initStudentTab() {
  if (!currentStudent) return;
  loadDbStudent(currentStudent.id);
}

async function loadDbStudent(studentId) {
  const headerEl = document.getElementById('student-header');
  if (headerEl) { headerEl.innerHTML = ''; headerEl.style.display = 'none'; }
  document.getElementById('student-stats').innerHTML =
    '<div class="loader" style="margin:1.5rem 0"></div>';
  document.getElementById('topic-bars').innerHTML = '';
  document.getElementById('advice-area').innerHTML = '<div class="loader"></div>';
  document.getElementById('rank-area').innerHTML = '';

  const d = await fetch(`/api/student/${studentId}/progress`)
    .then(r => r.json()).catch(() => null);
  if (!d) {
    document.getElementById('student-stats').innerHTML = '<p class="muted">Ошибка загрузки</p>';
    return;
  }

  const stu = d.student || {};
  const studentName = stu.name || currentStudent?.name || 'Студент';
  const streak = stu.streak_days ?? 0;
  const groupName = stu.group_name || '';

  const totalAnswers = d.topic_mastery?.reduce((s, t) => s + (t.total||0), 0) || 0;
  const correct = d.topic_mastery?.reduce((s, t) => s + (t.correct||0), 0) || 0;
  const acc = totalAnswers ? Math.round(correct / totalAnswers * 100) : 0;
  const accClass = acc >= 70 ? 'stat-box--teal' : acc >= 50 ? 'stat-box--amber' : 'stat-box--danger';

  if (headerEl) {
    headerEl.style.cssText = 'display:flex;align-items:center;gap:1rem;background:#0c0c0c;border-radius:1rem;padding:1.25rem 1.5rem;margin-bottom:1rem';
    headerEl.innerHTML = `
      <div style="width:44px;height:44px;border-radius:50%;background:#ff2d78;color:#d4f53c;font-size:1.2rem;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0">${studentName[0].toUpperCase()}</div>
      <div>
        <div style="font-size:1.2rem;font-weight:800;color:#fff;letter-spacing:-.03em">${studentName}</div>
        <div style="font-size:.8rem;color:rgba(255,255,255,.45);margin-top:.1rem">${groupName}${groupName && streak ? ' · ' : ''}${streak ? `Серия: ${streak} дн.` : 'Начни отвечать на вопросы!'}</div>
      </div>`;
  }

  document.getElementById('student-stats').innerHTML = `
    <div class="stat-box ${accClass}">
      <div class="stat-box__value">${acc}%</div>
      <div class="stat-box__label">Точность</div>
    </div>
    <div class="stat-box">
      <div class="stat-box__value">${totalAnswers}</div>
      <div class="stat-box__label">Ответов</div>
    </div>
    <div class="stat-box stat-box--teal">
      <div class="stat-box__value">${correct}</div>
      <div class="stat-box__label">Правильных</div>
    </div>
    <div class="stat-box">
      <div class="stat-box__value">${streak}</div>
      <div class="stat-box__label">Дней подряд</div>
    </div>`;

  const bars = document.getElementById('topic-bars');
  bars.innerHTML = (d.topic_mastery || []).map(t => {
    if (!t.total) return '';
    const pct = Math.round(t.accuracy * 100);
    const color = pct >= 70 ? '#d4f53c' : '#ff2d78';
    return `<div class="topic-bar-row">
      <div class="topic-bar-name">${t.title}</div>
      <div class="topic-bar-track"><div class="topic-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <div class="topic-bar-pct" style="color:${color}">${pct}%</div>
    </div>`;
  }).join('');

  document.getElementById('rank-area').innerHTML = `
    <div style="padding:1.25rem 1.15rem">
      <div class="rank-big">${d.rank ?? '—'} <span style="font-size:1rem;color:var(--muted)">/ ${d.group_size ?? '—'}</span></div>
      <div class="rank-sub">Место в группе ${groupName}</div>
      ${d.group_avg_accuracy != null ? `<div style="font-size:.82rem;color:var(--muted);margin-top:.3rem">Средняя точность группы: ${Math.round(d.group_avg_accuracy*100)}%</div>` : ''}
    </div>`;

  const weakTopics = (d.topic_mastery || [])
    .filter(t => t.total > 0 && t.accuracy < 0.6)
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 3);
  const strongTopics = (d.topic_mastery || [])
    .filter(t => t.accuracy >= 0.8 && t.total > 0).length;

  const ml = d.ml_prediction;
  const mlHtml = ml ? renderMlPrediction(ml) : '';

  document.getElementById('advice-area').innerHTML = `
    ${mlHtml}
    <div style="font-size:.92rem;line-height:1.7;padding:.25rem 0;margin-top:${ml ? '.75rem' : '0'}">
      ${acc >= 75
        ? `<div class="feedback-box feedback-box--ok" style="margin-bottom:.75rem">Отличная работа! ${strongTopics} тем освоено на 80%+</div>`
        : acc >= 50
        ? `<div class="feedback-box feedback-box--warn" style="margin-bottom:.75rem">Хороший прогресс — продолжай практиковаться</div>`
        : `<div class="feedback-box feedback-box--warn" style="margin-bottom:.75rem">Начни с простых тем в графе знаний</div>`}
      ${weakTopics.length ? `
        <p style="font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted-faint);margin:.5rem 0 .4rem">Требуют внимания</p>
        ${weakTopics.map(t => `
          <div class="focus-tag" style="display:inline-block;margin:.2rem .2rem .2rem 0">${t.title} — ${Math.round(t.accuracy*100)}%</div>
        `).join('')}` : ''}
    </div>`;
}

function renderMlPrediction(ml) {
  if (!ml) return '';
  const predColor = { Distinction: '#d4f53c', Pass: '#00b464', Fail: '#ff2d78' };
  const predLabel = { Distinction: 'Отлично', Pass: 'Зачёт', Fail: 'Риск провала' };
  const clusterColor = { 'Отличники': '#d4f53c', 'Активные': '#00b464', 'Пассивные': '#aaa', 'Группа риска': '#ff2d78', 'Результативные': '#d4f53c' };
  const pred = ml.prediction || '—';
  const pCol = predColor[pred] || '#aaa';
  const pLbl = predLabel[pred] || pred;
  const cluster = ml.cluster_label || '—';
  const cCol = clusterColor[cluster] || '#aaa';
  const prob = Math.round((ml.pass_probability || 0) * 100);
  return `
    <div style="background:#0c0c0c;border-radius:.85rem;padding:.9rem 1rem;margin-bottom:.1rem">
      <div style="font-size:.68rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.35);margin-bottom:.6rem">
        ML-анализ (OULAD Random Forest)
      </div>
      <div style="display:flex;gap:1.25rem;flex-wrap:wrap;align-items:center">
        <div>
          <div style="font-size:.7rem;color:rgba(255,255,255,.4);margin-bottom:.2rem">Прогноз</div>
          <span style="font-size:.9rem;font-weight:800;color:${pCol}">${pLbl}</span>
        </div>
        <div>
          <div style="font-size:.7rem;color:rgba(255,255,255,.4);margin-bottom:.2rem">Кластер</div>
          <span style="display:inline-flex;align-items:center;gap:.3rem;font-size:.82rem;font-weight:700;color:#fff">
            <span style="width:7px;height:7px;border-radius:50%;background:${cCol};display:inline-block"></span>${cluster}
          </span>
        </div>
        <div style="flex:1;min-width:80px">
          <div style="font-size:.7rem;color:rgba(255,255,255,.4);margin-bottom:.35rem">Вероятность успеха</div>
          <div style="display:flex;align-items:center;gap:.5rem">
            <div style="flex:1;height:5px;background:rgba(255,255,255,.1);border-radius:999px;overflow:hidden">
              <div style="height:100%;width:${prob}%;background:linear-gradient(90deg,#ff2d78,#d4f53c);border-radius:999px"></div>
            </div>
            <span style="font-size:.78rem;font-weight:700;color:#fff;white-space:nowrap">${prob}%</span>
          </div>
        </div>
      </div>
    </div>`;
}

async function loadTeacher() {
  const groups = await fetch('/api/teacher/groups').then(r => r.json());
  document.getElementById('groups-row').innerHTML = groups.map(g => {
    const pct = Math.round(g.avg_accuracy * 100);
    const riskClass = g.students_at_risk > 0 ? 'risk-badge--red' : 'risk-badge--green';
    const riskText  = g.students_at_risk > 0 ? `${g.students_at_risk} в зоне риска` : 'Всё в норме';
    return `
      <div class="group-card" id="gcard-${g.id}" onclick="loadGroupDetail(${g.id})">
        <div class="group-card__name">${g.name}</div>
        <div class="group-stat"><span>Студентов</span><span class="val">${g.student_count}</span></div>
        <div class="group-stat"><span>Средняя точность</span><span class="val" style="color:#ff2d78">${pct}%</span></div>
        <div class="group-stat"><span>Слабейшая тема</span><span class="val" style="max-width:130px;text-align:right;font-size:.75rem">${g.weakest_topic}</span></div>
        <span class="risk-badge ${riskClass}">${riskText}</span>
      </div>`;
  }).join('');
}

async function loadGroupDetail(groupId) {
  currentTeacherGroupId = groupId;
  document.querySelectorAll('.group-card').forEach(c => c.classList.remove('selected'));
  const card = document.getElementById('gcard-' + groupId);
  if (card) card.classList.add('selected');

  const data = await fetch(`/api/teacher/group/${groupId}`).then(r => r.json());
  document.getElementById('detail-heading').textContent = `Детали: ${data.group.name}`;
  document.getElementById('group-detail').classList.add('visible');

  document.getElementById('teacher-student-detail').style.display = 'none';

  const aiArea = document.getElementById('group-ai-advice');
  aiArea.style.display = 'none';
  aiArea.innerHTML = '';

  document.getElementById('topic-heatmap').innerHTML = data.topic_stats.map(t => {
    if (t.accuracy === null) return `
      <div class="heat-row">
        <div class="heat-name">${t.title}</div>
        <div class="heat-cell heat-cell--none">нет данных</div>
      </div>`;
    const pct = Math.round(t.accuracy * 100);
    const textColor = t.accuracy >= 0.8 ? '#3a5200' : '#fff';
    return `
      <div class="heat-row">
        <div class="heat-name">${t.title}</div>
        <div class="heat-cell" style="background:${heatColor(t.accuracy)};color:${textColor}">${pct}%</div>
      </div>`;
  }).join('');

  document.getElementById('students-tbody').innerHTML = data.students.map(s => {
    const pct = Math.round(s.accuracy * 100);
    const weak = s.weak_topics.length
      ? s.weak_topics.map(t => `<span class="focus-tag">${t}</span>`).join(' ')
      : '<span style="color:var(--muted)">—</span>';
    const riskBadge = s.at_risk
      ? '<span class="risk-badge risk-badge--red" style="font-size:.65rem;margin-left:.4rem">риск</span>'
      : '';
    return `
      <tr class="${s.at_risk ? 'at-risk ' : ''}clickable" onclick="showTeacherStudentDetail(${s.id})">
        <td><strong>${s.name}</strong>${riskBadge}</td>
        <td style="white-space:nowrap">
          <span style="font-weight:700;color:#ff2d78">${pct}%</span>
          <div style="width:50px;height:4px;background:rgba(12,12,12,.07);border-radius:2px;margin-top:4px;overflow:hidden;display:inline-block;margin-left:6px;vertical-align:middle">
            <div style="width:${pct}%;height:100%;background:#ff2d78;border-radius:2px"></div>
          </div>
        </td>
        <td style="white-space:nowrap">${s.streak_days} дн.</td>
        <td style="font-size:.8rem">${weak}</td>
      </tr>`;
  }).join('');

  document.getElementById('group-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadGroupAiAdvice() {
  if (!currentTeacherGroupId) return;
  const btn = document.getElementById('ai-advice-btn');
  const area = document.getElementById('group-ai-advice');
  btn.disabled = true;
  btn.textContent = 'Анализирую…';
  area.style.display = 'block';
  area.innerHTML = '<div class="loader"></div>';

  try {
    const data = await fetch(`/api/teacher/group/${currentTeacherGroupId}/ai-advice`).then(r => r.json());
    const interventionsHtml = (data.interventions || []).map(iv => `
      <div class="intervention-row">
        <span class="intervention-priority intervention-priority--${iv.priority}">
          ${iv.priority}
        </span>
        <div class="intervention-body">
          <div class="intervention-action">${iv.action}</div>
          <div class="intervention-meta">${iv.target ? `Для: ${iv.target}` : ''}${iv.rationale ? ' · ' + iv.rationale : ''}</div>
        </div>
      </div>`).join('');
    area.innerHTML = `
      <div class="advice-text"><strong>План вмешательства</strong></div>
      ${data.overall_strategy ? `<div class="advice-text" style="margin-bottom:.75rem">${data.overall_strategy}</div>` : ''}
      ${interventionsHtml}
      ${data.time_estimate ? `<div class="advice-forecast" style="margin-top:.75rem">Срок: ${data.time_estimate}</div>` : ''}
    `;
  } catch {
    area.innerHTML = '<p class="muted">Не удалось получить рекомендации</p>';
  }
  btn.disabled = false;
  btn.textContent = 'План вмешательства';
}

async function showTeacherStudentDetail(studentId) {
  const panel = document.getElementById('teacher-student-detail');
  panel.style.display = 'block';

  const headerEl = document.getElementById('tsd-header');
  headerEl.innerHTML = '';
  headerEl.style.display = 'none';
  document.getElementById('tsd-stats').innerHTML =
    '<div class="loader" style="margin:1.5rem 0"></div>';
  document.getElementById('tsd-bars').innerHTML = '';
  document.getElementById('tsd-advice').innerHTML = '<div class="loader"></div>';
  document.getElementById('tsd-rank').innerHTML = '';

  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const d = await fetch(`/api/student/${studentId}/progress`)
    .then(r => r.json()).catch(() => null);
  if (!d) {
    document.getElementById('tsd-stats').innerHTML = '<p class="muted">Ошибка загрузки</p>';
    return;
  }

  const stu = d.student || {};
  const studentName = stu.name || 'Студент';
  const streak = stu.streak_days ?? 0;
  const groupName = stu.group_name || '';

  document.getElementById('tsd-name').textContent = studentName;

  const totalAnswers = d.topic_mastery?.reduce((s, t) => s + (t.total||0), 0) || 0;
  const correct = d.topic_mastery?.reduce((s, t) => s + (t.correct||0), 0) || 0;
  const acc = totalAnswers ? Math.round(correct / totalAnswers * 100) : 0;
  const accClass = acc >= 70 ? 'stat-box--teal' : acc >= 50 ? 'stat-box--amber' : 'stat-box--danger';

  headerEl.style.cssText = 'display:flex;align-items:center;gap:1rem;background:#0c0c0c;border-radius:1rem;padding:1.25rem 1.5rem;margin-bottom:1rem';
  headerEl.innerHTML = `
    <div style="width:44px;height:44px;border-radius:50%;background:#ff2d78;color:#d4f53c;font-size:1.2rem;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0">${studentName[0].toUpperCase()}</div>
    <div>
      <div style="font-size:1.2rem;font-weight:800;color:#fff;letter-spacing:-.03em">${studentName}</div>
      <div style="font-size:.8rem;color:rgba(255,255,255,.45);margin-top:.1rem">${groupName}${groupName && streak ? ' · ' : ''}${streak ? `Серия: ${streak} дн.` : 'Нет активности'}</div>
    </div>`;

  document.getElementById('tsd-stats').innerHTML = `
    <div class="stat-box ${accClass}">
      <div class="stat-box__value">${acc}%</div>
      <div class="stat-box__label">Точность</div>
    </div>
    <div class="stat-box">
      <div class="stat-box__value">${totalAnswers}</div>
      <div class="stat-box__label">Ответов</div>
    </div>
    <div class="stat-box stat-box--teal">
      <div class="stat-box__value">${correct}</div>
      <div class="stat-box__label">Правильных</div>
    </div>
    <div class="stat-box">
      <div class="stat-box__value">${streak}</div>
      <div class="stat-box__label">Дней подряд</div>
    </div>`;

  document.getElementById('tsd-bars').innerHTML = (d.topic_mastery || []).map(t => {
    if (!t.total) return '';
    const pct = Math.round(t.accuracy * 100);
    const color = pct >= 70 ? '#d4f53c' : '#ff2d78';
    return `<div class="topic-bar-row">
      <div class="topic-bar-name">${t.title}</div>
      <div class="topic-bar-track"><div class="topic-bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <div class="topic-bar-pct" style="color:${color}">${pct}%</div>
    </div>`;
  }).join('');

  document.getElementById('tsd-rank').innerHTML = `
    <div style="padding:1.25rem 1.15rem">
      <div class="rank-big">${d.rank ?? '—'} <span style="font-size:1rem;color:var(--muted)">/ ${d.group_size ?? '—'}</span></div>
      <div class="rank-sub">Место в группе ${groupName}</div>
      ${d.group_avg_accuracy != null ? `<div style="font-size:.82rem;color:var(--muted);margin-top:.3rem">Средняя точность группы: ${Math.round(d.group_avg_accuracy*100)}%</div>` : ''}
    </div>`;

  const weakTopics = (d.topic_mastery || [])
    .filter(t => t.total > 0 && t.accuracy < 0.6)
    .sort((a, b) => a.accuracy - b.accuracy)
    .slice(0, 3);
  const strongTopics = (d.topic_mastery || []).filter(t => t.accuracy >= 0.8 && t.total > 0).length;

  const mlTsd = d.ml_prediction;
  const mlTsdHtml = mlTsd ? renderMlPrediction(mlTsd) : '';

  document.getElementById('tsd-advice').innerHTML = `
    ${mlTsdHtml}
    <div style="font-size:.92rem;line-height:1.7;padding:.25rem 0;margin-top:${mlTsd ? '.75rem' : '0'}">
      ${acc >= 75
        ? `<div class="feedback-box feedback-box--ok" style="margin-bottom:.75rem">Отличная работа! ${strongTopics} тем освоено на 80%+</div>`
        : acc >= 50
        ? `<div class="feedback-box feedback-box--warn" style="margin-bottom:.75rem">Хороший прогресс — требуется закрепление</div>`
        : `<div class="feedback-box feedback-box--warn" style="margin-bottom:.75rem">Требуется дополнительная работа</div>`}
      ${weakTopics.length ? `
        <p style="font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted-faint);margin:.5rem 0 .4rem">Требуют внимания</p>
        ${weakTopics.map(t => `
          <div class="focus-tag" style="display:inline-block;margin:.2rem .2rem .2rem 0">${t.title} — ${Math.round(t.accuracy*100)}%</div>
        `).join('')}` : '<p style="color:var(--muted);font-size:.85rem">Нет данных об ошибках</p>'}
    </div>`;
}

function closeTeacherStudentDetail() {
  const panel = document.getElementById('teacher-student-detail');
  panel.style.display = 'none';
  document.getElementById('group-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function heatColor(acc) {
  if (acc >= 0.8)  return '#d4f53c';
  if (acc >= 0.65) return '#d4f53c';
  if (acc >= 0.5)  return '#ff2d78';
  if (acc >= 0.35) return 'rgba(255,45,120,.55)';
  return '#0c0c0c';
}

async function init() {
  await initCourse();

  if (currentStudent) {
    const prog = await fetch(`/api/student/${currentStudent.id}/progress`)
      .then(r => r.json()).catch(() => null);
    if (prog?.topic_mastery) {
      prog.topic_mastery.forEach(t => {
        if (t.total > 0) studentMastery[t.key] = t.accuracy;
      });
      drawGraph();
    }
  }
  await initStudentTab();
}

if (currentStudent) {
  showUserChip(currentStudent);
  document.getElementById('login-overlay').classList.add('hidden');
  init();
}

(function () {
  const dot  = document.querySelector('.cur-dot');
  const ring = document.querySelector('.cur-ring');
  if (!dot || !ring) return;

  let mx = 0, my = 0;
  let rx = 0, ry = 0;

  document.addEventListener('mousemove', e => {
    mx = e.clientX;
    my = e.clientY;
    dot.style.transform = `translate(${mx - 5}px, ${my - 5}px)`;
  });

  (function loop() {
    rx += (mx - rx) * 0.11;
    ry += (my - ry) * 0.11;
    ring.style.transform = `translate(${rx - 19}px, ${ry - 19}px)`;
    requestAnimationFrame(loop);
  })();

  document.addEventListener('mousedown', () => {
    dot.style.transform  += ' scale(0.7)';
    ring.style.transform += ' scale(1.4)';
    ring.style.opacity   = '.9';
  });
  document.addEventListener('mouseup', () => {
    ring.style.opacity = '.55';
  });
})();

let _ouladLoaded = false;

async function initOuladTab() {
  if (_ouladLoaded) return;
  _ouladLoaded = true;
  await Promise.all([loadOuladStats(), loadOuladSample()]);
}

async function loadOuladStats() {
  const [status, cohort] = await Promise.all([
    fetch('/api/oulad/status').then(r => r.json()).catch(() => null),
    fetch('/api/oulad/cohort').then(r => r.json()).catch(() => null),
  ]);

  const statsRow = document.getElementById('oulad-stats-row');
  if (status) {
    statsRow.innerHTML = `
      <div class="stat-box"><div class="stat-box__val">${(status.students_loaded || 0).toLocaleString('ru')}</div><div class="stat-box__lbl">студентов в датасете</div></div>
      <div class="stat-box"><div class="stat-box__val">22</div><div class="stat-box__lbl">курса Open University</div></div>
      <div class="stat-box"><div class="stat-box__val">${cohort ? Math.round(cohort.avg_score) + '%' : '—'}</div><div class="stat-box__lbl">средний балл</div></div>
      <div class="stat-box"><div class="stat-box__val">${cohort ? Math.round(cohort.avg_clicks).toLocaleString('ru') : '—'}</div><div class="stat-box__lbl">кликов в среднем</div></div>
    `;
  }

  if (cohort && cohort.result_distribution) {
    const dist = cohort.result_distribution;
    const labels = { Distinction: 'Отлично', Pass: 'Зачтено', Withdrawn: 'Отчислен', Fail: 'Провал' };
    const colors = { Distinction: '#d4f53c', Pass: '#00b464', Withdrawn: '#aaa', Fail: '#ff2d78' };
    const order = ['Distinction', 'Pass', 'Withdrawn', 'Fail'];
    document.getElementById('oulad-dist').innerHTML = order.map(k => {
      const pct = Math.round((dist[k] || 0) * 100);
      return `<div class="oulad-dist-bar">
        <span class="oulad-dist-bar__label">${labels[k] || k}</span>
        <div class="oulad-dist-bar__track">
          <div class="oulad-dist-bar__fill" style="width:${pct}%;background:${colors[k]}"></div>
        </div>
        <span class="oulad-dist-bar__pct">${pct}%</span>
      </div>`;
    }).join('');
  }

  const clusters = [
    { name: 'Группа риска',  color: '#ff2d78', desc: 'Низкая активность, высокий риск провала. RF предсказывает Fail с вероятностью >70%.' },
    { name: 'Пассивные',     color: '#aaa',    desc: 'Умеренная активность, нерегулярные заходы. Чаще финишируют с зачётом.' },
    { name: 'Активные',      color: '#00b464', desc: 'Регулярные сессии, высокий click rate. Хорошо коррелируют с Pass.' },
    { name: 'Отличники',     color: '#d4f53c', desc: 'Максимальная вовлечённость, высокие баллы. RF предсказывает Distinction.' },
  ];
  document.getElementById('oulad-clusters').innerHTML = clusters.map(c => `
    <div class="oulad-cluster-row">
      <div class="oulad-cluster-dot" style="background:${c.color}"></div>
      <div>
        <div class="oulad-cluster-name">${c.name}</div>
        <div class="oulad-cluster-desc">${c.desc}</div>
      </div>
    </div>
  `).join('');
}

async function loadOuladSample() {
  _ouladLoaded = true; // в случае вызова кнопкой без initOuladTab
  const tbody = document.getElementById('oulad-tbody');
  tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--muted)">Загрузка...</td></tr>';

  const data = await fetch('/api/oulad/sample-students').then(r => r.json()).catch(() => null);
  if (!data || !data.length) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--muted)">Данные OULAD недоступны</td></tr>';
    return;
  }

  const resultClass = r => {
    if (!r) return '';
    const k = r.toLowerCase();
    if (k === 'distinction') return 'distinction';
    if (k === 'pass') return 'pass';
    if (k === 'fail') return 'fail';
    return 'withdrawn';
  };

  tbody.innerHTML = data.map(s => {
    const actualCls  = resultClass(s.final_result);
    const predictCls = resultClass(s.predicted_class);
    const match = (s.final_result || '').toLowerCase() === (s.predicted_class || '').toLowerCase();
    const prob = Math.round((s.success_probability || 0) * 100);
    const clusterColor = { 'Отличники': '#d4f53c', 'Активные': '#00b464', 'Пассивные': '#aaa', 'Группа риска': '#ff2d78' };
    const col = clusterColor[s.learning_style] || '#aaa';
    return `<tr>
      <td style="font-family:monospace;color:var(--muted)">${s.id_student}</td>
      <td><strong>${s.code_module}</strong></td>
      <td>${(s.code_presentation || '').replace('J','Ян').replace('B','Фев')}</td>
      <td>${s.gender === 'M' ? 'М' : 'Ж'}</td>
      <td>${s.age_band || '—'}</td>
      <td>${s.weight_score != null ? s.weight_score.toFixed(1) : '—'}</td>
      <td>${(s.total_clicks || 0).toLocaleString('ru')}</td>
      <td><span class="oulad-badge oulad-badge--${actualCls}">${s.final_result || '—'}</span></td>
      <td><span class="oulad-badge oulad-badge--${predictCls} oulad-badge--${match ? 'match' : 'mismatch'}" title="${match ? 'Совпало ✓' : 'Расхождение'}">${s.predicted_class || '—'} ${match ? '✓' : '≠'}</span></td>
      <td>
        <div style="display:flex;align-items:center;gap:.4rem">
          <div style="flex:1;height:6px;background:rgba(0,0,0,.07);border-radius:999px;overflow:hidden;min-width:40px">
            <div class="oulad-prob-bar" style="width:${prob}%"></div>
          </div>
          <span style="font-size:.72rem;color:var(--muted);white-space:nowrap">${prob}%</span>
        </div>
      </td>
      <td><span style="display:inline-flex;align-items:center;gap:.3rem;font-size:.75rem;font-weight:600">
        <span style="width:7px;height:7px;border-radius:50%;background:${col};flex-shrink:0;display:inline-block"></span>
        ${s.learning_style || '—'}
      </span></td>
    </tr>`;
  }).join('');
}
