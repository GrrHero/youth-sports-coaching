(() => {
  const STORAGE_KEY = 'goonies-stars-v1';

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];

  const state = {
    plan: null,
    weekIndex: 0,
    selectedDate: null,
    done: loadDone(),
  };

  function loadDone() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch {
      return {};
    }
  }

  function saveDone() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.done));
  }

  function todayISO() {
    const n = new Date();
    const y = n.getFullYear();
    const m = String(n.getMonth() + 1).padStart(2, '0');
    const d = String(n.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function formatShort(iso) {
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  function starTotal() {
    return Object.values(state.done).filter(Boolean).length;
  }

  function updateStarBank() {
    $('#star-count').textContent = String(starTotal());
  }

  function findWeekIndexForToday(plan) {
    const t = todayISO();
    for (let i = 0; i < plan.weeks.length; i++) {
      const days = plan.weeks[i].days || [];
      if (days.some((d) => d.date === t)) return i;
    }
    // default to latest week
    return Math.max(0, plan.weeks.length - 1);
  }

  function currentWeek() {
    return state.plan.weeks[state.weekIndex];
  }

  function selectedDay() {
    const w = currentWeek();
    return (w.days || []).find((d) => d.date === state.selectedDate) || w.days[0];
  }

  function renderCalendar() {
    const w = currentWeek();
    $('#week-label').textContent = `Week ${w.num}`;
    const note = $('#week-note');
    if (w.note) {
      note.hidden = false;
      note.textContent = w.note;
    } else {
      note.hidden = true;
      note.textContent = '';
    }

    $('#prev-week').disabled = state.weekIndex <= 0;
    $('#next-week').disabled = state.weekIndex >= state.plan.weeks.length - 1;

    const cal = $('#calendar');
    cal.innerHTML = '';
    const today = todayISO();

    for (const day of w.days) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'day-chip';
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', day.date === state.selectedDate ? 'true' : 'false');
      if (day.date === today) btn.classList.add('is-today');
      if (day.date === state.selectedDate) btn.classList.add('is-selected');
      if (day.kind === 'rest') btn.classList.add('is-rest');
      if (day.kind === 'play') btn.classList.add('is-play');

      const dow = document.createElement('span');
      dow.className = 'dow';
      dow.textContent = day.day;

      const dom = document.createElement('span');
      dom.className = 'dom';
      dom.textContent = day.date ? String(Number(day.date.slice(-2))) : '·';

      const demoj = document.createElement('span');
      demoj.className = 'demoj';
      demoj.textContent = day.emoji || '⭐';

      btn.append(dow, dom, demoj);
      btn.addEventListener('click', () => {
        state.selectedDate = day.date;
        render();
      });
      cal.appendChild(btn);
    }
  }

  function renderDay() {
    const day = selectedDay();
    const hero = $('#day-hero');
    const drillsEl = $('#drills');
    const videosBlock = $('#videos-block');
    const videosEl = $('#videos');

    if (!day) {
      hero.innerHTML = '';
      drillsEl.innerHTML = '<div class="empty-day">Pick a day!</div>';
      videosBlock.hidden = true;
      return;
    }

    const sessLabel =
      day.kind === 'session'
        ? `Session ${day.session}`
        : day.kind === 'play'
          ? 'Play Day'
          : day.kind === 'rest'
            ? 'Rest Day'
            : '';

    hero.innerHTML = `
      <div class="day-hero-emoji">${day.emoji || '⭐'}</div>
      <div class="day-hero-text">
        <h3>${escapeHtml(day.name || 'Practice')}</h3>
        <p class="day-hero-meta">${escapeHtml(sessLabel)}${day.sport ? ' · ' + escapeHtml(day.sport) : ''}${day.time ? ' · ' + escapeHtml(day.time) : ''}${day.date ? ' · ' + formatShort(day.date) : ''}</p>
      </div>
    `;

    drillsEl.innerHTML = '';
    const drills = day.drills || [];
    if (!drills.length) {
      drillsEl.innerHTML = '<div class="empty-day">No drills for this day yet.</div>';
    }

    const allVideos = [];
    const seenVid = new Set();

    for (const drill of drills) {
      const done = !!state.done[drill.id];
      const card = document.createElement('article');
      card.className = 'drill-card' + (done ? ' is-done' : '');
      card.dataset.id = drill.id;

      const steps = (drill.steps || [])
        .map((s) => `<li>${escapeHtml(s)}</li>`)
        .join('');

      card.innerHTML = `
        <div class="drill-top">
          <div class="drill-sport">${drill.emoji || '⭐'}</div>
          <div class="drill-titles">
            <h4 class="drill-name">${escapeHtml(drill.name)}</h4>
            <p class="drill-kind">${escapeHtml(drill.kind || '')}${drill.time ? ' · ' + escapeHtml(drill.time) : ''} · ${escapeHtml(drill.sport || '')}</p>
          </div>
          <div class="cue-badge" title="Cue word">${escapeHtml(drill.cue || 'Go!')}</div>
        </div>
        <div class="drill-body">
          <ol class="steps">${steps}</ol>
          <p class="fun-line"><span class="lbl">🎉 Make it fun</span>${escapeHtml(drill.fun || '')}</p>
          <p class="level-line"><span class="lbl">🚀 Level up</span>${escapeHtml(drill.level_up || '')}</p>
          <button type="button" class="did-it${done ? ' is-done' : ''}" data-drill="${escapeHtml(drill.id)}">
            ${done ? '⭐ You did it!' : '✨ I did it!'}
          </button>
        </div>
      `;
      drillsEl.appendChild(card);

      for (const v of drill.videos || []) {
        if (v.id && !seenVid.has(v.id)) {
          seenVid.add(v.id);
          allVideos.push(v);
        }
      }
    }

    $$('.did-it', drillsEl).forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.drill;
        state.done[id] = !state.done[id];
        saveDone();
        updateStarBank();
        renderDay();
      });
    });

    if (allVideos.length) {
      videosBlock.hidden = false;
      videosEl.innerHTML = allVideos
        .map(
          (v) => `
        <a class="video-card" href="${escapeAttr(v.url)}" target="_blank" rel="noopener">
          <img class="video-thumb" src="${escapeAttr(v.thumb)}" alt="" loading="lazy" width="320" height="180">
          <div class="video-info">
            <strong>${escapeHtml(v.title)}</strong>
            <span>▶ YouTube</span>
          </div>
        </a>`
        )
        .join('');
    } else {
      videosBlock.hidden = true;
      videosEl.innerHTML = '';
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, '&#39;');
  }

  function render() {
    renderCalendar();
    renderDay();
    updateStarBank();
  }

  async function init() {
    const res = await fetch('data/plan.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('Could not load plan.json');
    state.plan = await res.json();
    state.weekIndex = findWeekIndexForToday(state.plan);
    const w = currentWeek();
    const today = todayISO();
    const todayDay = (w.days || []).find((d) => d.date === today);
    state.selectedDate = todayDay ? todayDay.date : (w.days[0] && w.days[0].date);

    $('#prev-week').addEventListener('click', () => {
      if (state.weekIndex > 0) {
        state.weekIndex -= 1;
        const nw = currentWeek();
        state.selectedDate = nw.days[0].date;
        render();
      }
    });
    $('#next-week').addEventListener('click', () => {
      if (state.weekIndex < state.plan.weeks.length - 1) {
        state.weekIndex += 1;
        const nw = currentWeek();
        const t = todayISO();
        const hit = nw.days.find((d) => d.date === t);
        state.selectedDate = hit ? hit.date : nw.days[0].date;
        render();
      }
    });

    render();
  }

  init().catch((err) => {
    document.querySelector('main').innerHTML =
      '<p style="padding:2rem;text-align:center;font-weight:700">Could not load the practice plan. Try refreshing!</p>';
    console.error(err);
  });
})();
