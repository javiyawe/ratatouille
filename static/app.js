/* ══════════════════════════════════════════════════════════
   Ratatouille — Frontend App
   Vanilla JS · No dependencias externas
   ══════════════════════════════════════════════════════════ */

'use strict';

const API = '';  // mismo origen

// ─────────────────────── Estado global ───────────────────────────────
const state = {
  allRecipes: [],
  chatHistory: [],   // [{role, content}, ...]
  isLoading: false,
};

// ─────────────────────── Helpers ─────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`HTTP ${res.status}: ${err}`);
  }
  return res.json();
}

function $(id) { return document.getElementById(id); }

function getRecipeEmoji(recipe) {
  const tags = (recipe.etiquetas || []).join(' ').toLowerCase();
  const tipo = (recipe.tipo_cocina || '').toLowerCase();
  const tecnica = (recipe.tecnica_coccion || '').toLowerCase();
  const titulo = (recipe.titulo || '').toLowerCase();

  if (/pasta|lasaña|risotto|italiana/.test(tags + tipo + titulo)) return '🍝';
  if (/sushi|ramen|noodle|asiática|japonesa|china/.test(tags + tipo)) return '🍜';
  if (/taco|burrito|mexicana|enchilada/.test(tags + tipo)) return '🌮';
  if (/pizza/.test(tags + titulo)) return '🍕';
  if (/hamburguesa|burger|americana/.test(tags + tipo + titulo)) return '🍔';
  if (/sopa|caldo|crema/.test(tags + titulo)) return '🍲';
  if (/ensalada|vegana|vegetariana/.test(tags)) return '🥗';
  if (/pescado|marisco|salmon|atún|bacalao/.test(tags + titulo)) return '🐟';
  if (/pollo|chicken/.test(tags + titulo)) return '🍗';
  if (/cerdo|costilla|cochinillo/.test(tags + titulo)) return '🥩';
  if (/tarta|pastel|bizcocho|brownie|postre/.test(tags + titulo)) return '🍰';
  if (/pan|baguette|brioche/.test(tags + titulo)) return '🍞';
  if (/francesa|croissant/.test(tags + tipo)) return '🥐';
  if (/curry|india|especias/.test(tags + tipo)) return '🍛';
  if (/horneado|horno/.test(tecnica)) return '🫕';
  if (/española|paella/.test(tags + tipo + titulo)) return '🥘';
  return '🍳';
}

function difficultyClass(diff) {
  const d = (diff || '').toLowerCase();
  if (d === 'fácil' || d === 'facil') return 'easy';
  if (d === 'difícil' || d === 'dificil') return 'hard';
  return 'medium';
}

function formatTime(minutes) {
  if (!minutes) return null;
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}min` : `${h}h`;
}

function parseTags(tagsVal) {
  if (!tagsVal) return [];
  if (Array.isArray(tagsVal)) return tagsVal;
  try { return JSON.parse(tagsVal); } catch { return []; }
}

// ─────────────────────── Markdown Renderer ───────────────────────────
// Implementación propia sin dependencias externas

function renderMarkdown(text) {
  if (!text) return '';

  // Escapar HTML
  let h = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Bloques de código (antes que inline)
  h = h.replace(/```[\w]*\n([\s\S]*?)```/g, (_, code) =>
    `<pre><code>${code.trim()}</code></pre>`
  );

  // Línea horizontal
  h = h.replace(/^---+$/gm, '<hr>');

  // Headers
  h = h.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^# (.+)$/gm, '<h2>$1</h2>');

  // Bold + italic combinado
  h = h.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  // Bold
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  h = h.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Inline code
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Blockquote
  h = h.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

  // Listas: convertir líneas de lista consecutivas
  // Numeradas
  h = h.replace(/((?:^\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(l =>
      `<li>${l.replace(/^\d+\. /, '').trim()}</li>`
    ).join('');
    return `<ol>${items}</ol>`;
  });
  // Bullet
  h = h.replace(/((?:^[-•] .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(l =>
      `<li>${l.replace(/^[-•] /, '').trim()}</li>`
    ).join('');
    return `<ul>${items}</ul>`;
  });

  // Párrafos: separar por doble salto de línea
  const blocks = h.split(/\n{2,}/);
  h = blocks.map(block => {
    block = block.trim();
    if (!block) return '';
    // No envolver en <p> los bloques que ya son tags block-level
    if (/^<(h[1-6]|ul|ol|li|pre|blockquote|hr)/.test(block)) return block;
    // Saltos simples dentro de párrafo → <br>
    return `<p>${block.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');

  return h;
}

// ─────────────────────── Tabs ─────────────────────────────────────────

function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      $(`tab-${tab}`).classList.add('active');
    });
  });
}

// ─────────────────────── Stats ────────────────────────────────────────

async function loadStats() {
  try {
    const data = await apiFetch('/api/stats');
    $('stats-text').textContent = `${data.total_recipes} recetas · Local`;
    $('stats-badge').querySelector('.stats-dot').classList.add('online');
  } catch {
    $('stats-text').textContent = 'Sin conexión al backend';
  }
}

// ─────────────────────── Recipe Cards ────────────────────────────────

function createRecipeCard(recipe) {
  const card = document.createElement('div');
  card.className = 'recipe-card';

  const tags = parseTags(recipe.etiquetas).slice(0, 4);
  const emoji = getRecipeEmoji(recipe);
  const tiempos = recipe.tiempos || {};
  const totalMin = tiempos.total_minutos || recipe.total_time_minutes;
  const timeStr = formatTime(totalMin);
  const diffClass = difficultyClass(recipe.dificultad);
  const relevance = recipe._relevance;
  const id = recipe._id;

  card.innerHTML = `
    <div class="card-hero">
      ${id ? `<button class="card-delete-btn" title="Eliminar receta" data-id="${id}">✕</button>` : ''}
      <span class="card-hero-emoji">${emoji}</span>
      ${relevance !== undefined ? `<span class="card-relevance">${Math.round(relevance * 100)}%</span>` : ''}
    </div>
    <div class="card-body">
      <div class="card-title">${recipe.titulo || 'Sin título'}</div>
      <div class="card-meta">
        ${timeStr ? `<span class="card-meta-item">⏱ ${timeStr}</span>` : ''}
        ${recipe.porciones ? `<span class="card-meta-item">👥 ${recipe.porciones}</span>` : ''}
        ${recipe.tipo_cocina ? `<span class="card-meta-item">🌍 ${recipe.tipo_cocina}</span>` : ''}
      </div>
      ${recipe.descripcion ? `<p class="card-desc">${recipe.descripcion}</p>` : ''}
      ${tags.length ? `<div class="card-tags">${tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>` : ''}
    </div>
    <div class="card-footer">
      <span class="difficulty-badge ${diffClass}">${recipe.dificultad || 'Media'}</span>
      <span style="color:var(--text-dim);font-size:0.75rem">${recipe.tecnica_coccion || ''}</span>
    </div>
  `;

  // Clic en la tarjeta → modal de visualización
  card.addEventListener('click', e => {
    if (e.target.closest('.card-delete-btn')) return;
    openModal(recipe);
  });

  // Botón eliminar
  const delBtn = card.querySelector('.card-delete-btn');
  if (delBtn) {
    delBtn.addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm(`¿Eliminar "${recipe.titulo || 'esta receta'}"?`)) return;
      try {
        await apiFetch(`/api/recipes/${id}`, { method: 'DELETE' });
        card.style.transition = 'opacity 0.3s, transform 0.3s';
        card.style.opacity = '0';
        card.style.transform = 'scale(0.92)';
        setTimeout(() => { card.remove(); loadStats(); }, 300);
      } catch (err) {
        alert(`Error al eliminar: ${err.message}`);
      }
    });
  }

  return card;
}

function renderGrid(recipes) {
  const grid = $('recipes-grid');
  grid.innerHTML = '';

  if (!recipes.length) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🫙</div>
        <h3>Sin resultados</h3>
        <p>Prueba con otros términos o ajusta los filtros.</p>
      </div>`;
    return;
  }

  recipes.forEach(r => grid.appendChild(createRecipeCard(r)));
}

// ─────────────────────── Modal ────────────────────────────────────────

function openModal(recipe) {
  const overlay = $('modal-overlay');
  const body = $('modal-body');

  const tiempos = recipe.tiempos || {};
  const tags = parseTags(recipe.etiquetas);
  const emoji = getRecipeEmoji(recipe);
  const ingredientes = recipe.ingredientes || [];
  const pasos = recipe.pasos || [];
  const nutri = recipe.valor_nutricional || {};

  const statsHtml = [
    tiempos.preparacion_minutos ? `<div class="stat-pill"><span>🔪</span> Prep: ${formatTime(tiempos.preparacion_minutos)}</div>` : '',
    tiempos.coccion_minutos     ? `<div class="stat-pill"><span>🔥</span> Cocción: ${formatTime(tiempos.coccion_minutos)}</div>` : '',
    tiempos.total_minutos       ? `<div class="stat-pill"><span>⏱</span> Total: ${formatTime(tiempos.total_minutos)}</div>` : '',
    tiempos.reposo_minutos      ? `<div class="stat-pill"><span>💤</span> Reposo: ${formatTime(tiempos.reposo_minutos)}</div>` : '',
    recipe.porciones            ? `<div class="stat-pill"><span>👥</span> ${recipe.porciones} porciones</div>` : '',
    recipe.dificultad           ? `<div class="stat-pill"><span>📊</span> ${recipe.dificultad}</div>` : '',
    nutri.calorias_por_porcion  ? `<div class="stat-pill"><span>⚡</span> ${nutri.calorias_por_porcion} kcal/ración</div>` : '',
  ].filter(Boolean).join('');

  const ingredientesHtml = ingredientes.length ? `
    <p class="modal-section-title">Ingredientes</p>
    <ul class="ingredients-list">
      ${ingredientes.map(ing => {
        const qty = ing.cantidad ? `${ing.cantidad} ${ing.unidad || ''}`.trim() : (ing.unidad || '');
        return `
          <li class="ingredient-item">
            <span class="ingredient-qty">${qty}</span>
            <span class="ingredient-name">${ing.nombre}</span>
            ${ing.preparacion ? `<span class="ingredient-prep">${ing.preparacion}</span>` : ''}
          </li>`;
      }).join('')}
    </ul>` : '';

  const pasosHtml = pasos.length ? `
    <p class="modal-section-title">Preparación</p>
    <ol class="steps-list">
      ${pasos.map((paso, i) => `
        <li class="step-item">
          <span class="step-num">${i + 1}</span>
          <span class="step-text">${paso}</span>
        </li>`).join('')}
    </ol>` : '';

  const nutriHtml = nutri.calorias_por_porcion ? `
    <p class="modal-section-title">Valor Nutricional (por ración)</p>
    <div class="modal-stats">
      ${nutri.calorias_por_porcion ? `<div class="stat-pill"><span>⚡</span>${nutri.calorias_por_porcion} kcal</div>` : ''}
      ${nutri.proteinas_g          ? `<div class="stat-pill"><span>💪</span>${nutri.proteinas_g}g proteínas</div>` : ''}
      ${nutri.carbohidratos_g      ? `<div class="stat-pill"><span>🌾</span>${nutri.carbohidratos_g}g carbos</div>` : ''}
      ${nutri.grasas_g             ? `<div class="stat-pill"><span>🫒</span>${nutri.grasas_g}g grasas</div>` : ''}
    </div>` : '';

  const chemHtml = recipe.notas_quimicas ? `
    <p class="modal-section-title">Química del Plato</p>
    <div class="modal-chemistry">🔬 ${recipe.notas_quimicas}</div>` : '';

  const tagsHtml = tags.length ? `
    <p class="modal-section-title">Etiquetas</p>
    <div class="modal-tags-wrap">${tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>` : '';

  body.innerHTML = `
    <div class="modal-header-emoji">${emoji}</div>
    <h2 class="modal-title">${recipe.titulo || 'Sin título'}</h2>
    ${recipe.descripcion ? `<p class="modal-desc">${recipe.descripcion}</p>` : ''}
    <div class="modal-stats">${statsHtml}</div>
    ${ingredientesHtml}
    ${pasosHtml}
    ${chemHtml}
    ${nutriHtml}
    ${tagsHtml}
  `;

  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const overlay = $('modal-overlay');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

function initModal() {
  $('modal-close').addEventListener('click', closeModal);
  $('modal-overlay').addEventListener('click', e => {
    if (e.target === $('modal-overlay')) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });
}

// ─────────────────────── Búsqueda / Filtros ──────────────────────────

async function loadAllRecipes() {
  const grid = $('recipes-grid');
  grid.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Cargando recetas…</p></div>';
  try {
    const data = await apiFetch('/api/recipes?limit=100');
    state.allRecipes = data.recipes || [];
    $('search-label').classList.add('hidden');
    $('clear-search-btn').classList.add('hidden');
    renderGrid(state.allRecipes);
  } catch (err) {
    grid.innerHTML = `<div class="empty-state">
      <div class="empty-icon">⚠️</div>
      <h3>Error al conectar</h3>
      <p>${err.message}</p>
      <p class="hint">¿Está corriendo el servidor? <code>uvicorn main:app --reload</code></p>
    </div>`;
  }
}

async function searchRecipes() {
  const query = $('search-input').value.trim();
  if (!query) { loadAllRecipes(); return; }

  const maxTime   = $('filter-time').value ? parseInt($('filter-time').value) : null;
  const difficulty = $('filter-difficulty').value || null;

  const grid = $('recipes-grid');
  grid.innerHTML = '<div class="loading-state"><div class="spinner"></div><p>Buscando…</p></div>';

  const label = $('search-label');
  label.innerHTML = `Resultados semánticos para <strong>"${query}"</strong>`;
  label.classList.remove('hidden');
  $('clear-search-btn').classList.remove('hidden');

  try {
    const data = await apiFetch('/api/search', {
      method: 'POST',
      body: JSON.stringify({ query, n_results: 12, max_time: maxTime, difficulty }),
    });
    renderGrid(data.recipes || []);
  } catch (err) {
    grid.innerHTML = `<div class="empty-state">
      <div class="empty-icon">❌</div>
      <h3>Error en la búsqueda</h3>
      <p>${err.message}</p>
    </div>`;
  }
}

function initSearch() {
  $('search-btn').addEventListener('click', searchRecipes);
  $('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchRecipes();
  });
  $('load-all-btn').addEventListener('click', () => {
    $('search-input').value = '';
    loadAllRecipes();
  });
  $('clear-search-btn').addEventListener('click', () => {
    $('search-input').value = '';
    $('filter-time').value = '';
    $('filter-difficulty').value = '';
    loadAllRecipes();
  });
  $('filter-time').addEventListener('change', () => { if ($('search-input').value) searchRecipes(); });
  $('filter-difficulty').addEventListener('change', () => { if ($('search-input').value) searchRecipes(); });
}

// ─────────────────────── Chat ─────────────────────────────────────────

function appendMessage(role, content, opts = {}) {
  const container = $('chat-messages');
  const isAlchemy = opts.alchemy || false;

  const div = document.createElement('div');
  div.className = `msg msg-${role}`;

  const avatarEmoji = role === 'assistant' ? '👨‍🍳' : '🧑';
  const bubbleClass = isAlchemy ? 'msg-bubble alchemy-bubble' : 'msg-bubble';

  const htmlContent = role === 'assistant'
    ? renderMarkdown(content)
    : `<p>${content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</p>`;

  div.innerHTML = `
    <div class="msg-avatar">${avatarEmoji}</div>
    <div class="${bubbleClass}">${htmlContent}</div>
  `;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function showTyping() {
  const container = $('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg msg-assistant msg-typing';
  div.id = 'typing-indicator';
  div.innerHTML = `
    <div class="msg-avatar">👨‍🍳</div>
    <div class="msg-bubble">
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function removeTyping() {
  const t = $('typing-indicator');
  if (t) t.remove();
}

function updateModeIndicator(isAlchemy) {
  const pill = $('mode-pill');
  const dot  = pill.querySelector('.mode-dot');
  const label = $('mode-label');

  if (isAlchemy) {
    pill.classList.add('alchemy');
    dot.className = 'mode-dot alchemy';
    label.textContent = '⚗️ Modo Alquimia';
  } else {
    pill.classList.remove('alchemy');
    dot.className = 'mode-dot normal';
    label.textContent = 'Modo Normal';
  }
}

function showSources(sources) {
  const bar  = $('sources-bar');
  const list = $('sources-list');
  if (!sources || !sources.length) {
    bar.classList.add('hidden');
    return;
  }
  list.innerHTML = sources
    .filter(Boolean)
    .map(s => `<span class="source-chip">${s}</span>`)
    .join('');
  bar.classList.remove('hidden');
}

async function sendMessage() {
  if (state.isLoading) return;

  const input = $('chat-input');
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  input.style.height = 'auto';
  state.isLoading = true;
  $('send-btn').disabled = true;
  $('sources-bar').classList.add('hidden');
  $('hints-row').style.display = 'none';

  // Mostrar mensaje del usuario
  appendMessage('user', message);

  // Añadir a historial
  state.chatHistory.push({ role: 'user', content: message });

  // Indicador de typing
  showTyping();

  try {
    const data = await apiFetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        history: state.chatHistory.slice(-20),  // últimos 10 turnos
      }),
    });

    removeTyping();

    const response = data.response || 'Sin respuesta del modelo.';
    const isAlchemy = data.alchemy_mode || false;

    appendMessage('assistant', response, { alchemy: isAlchemy });
    state.chatHistory.push({ role: 'assistant', content: response });

    updateModeIndicator(isAlchemy);
    showSources(data.sources);

  } catch (err) {
    removeTyping();
    appendMessage('assistant',
      `**Error al contactar con el Chef IA.**\n\n${err.message}\n\n` +
      `Verifica que el servidor está corriendo: \`uvicorn main:app --reload\``,
      { alchemy: false }
    );
  } finally {
    state.isLoading = false;
    $('send-btn').disabled = false;
    input.focus();
  }
}

function useHint(btn) {
  const input = $('chat-input');
  input.value = btn.textContent.trim();
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';

  // Cambiar a la pestaña Chef IA si no está activa
  const chefTab = document.querySelector('[data-tab="chef"]');
  if (!chefTab.classList.contains('active')) {
    chefTab.click();
  }
  input.focus();
}

function initChat() {
  const input = $('chat-input');
  const sendBtn = $('send-btn');

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  });

  // Enviar con Enter (Shift+Enter = nueva línea)
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);
}

// ─────────────────────── Modal Añadir Receta ─────────────────────────

const addModal = {
  overlay:    null,
  textarea:   null,
  charCount:  null,
  extractedRecipe: null,  // JSON recibido del backend tras /extract

  states: ['input', 'loading', 'preview', 'saving', 'success'],

  show() {
    this.overlay.classList.add('open');
    this.overlay.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    this.goTo('input');
    this.textarea.focus();
  },

  hide() {
    this.overlay.classList.remove('open');
    this.overlay.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  },

  goTo(state) {
    this.states.forEach(s => {
      $(`add-state-${s}`).classList.toggle('hidden', s !== state);
    });
  },

  // Anima los pasos del processing secuencialmente
  animateSteps(ids, intervalMs = 1800) {
    ids.forEach((id, i) => {
      setTimeout(() => {
        ids.slice(0, i).forEach(prev => {
          const el = $(prev);
          if (el) { el.classList.remove('active'); el.classList.add('done'); }
        });
        const el = $(id);
        if (el) el.classList.add('active');
      }, i * intervalMs);
    });
  },

  buildPreview(recipe) {
    const tiempos = recipe.tiempos || {};
    const ings = recipe.ingredientes || [];
    const tags = (recipe.etiquetas || []).slice(0, 6);

    const pillsHtml = [
      tiempos.total_minutos    ? `<div class="stat-pill"><span>⏱</span> ${formatTime(tiempos.total_minutos)}</div>` : '',
      recipe.porciones         ? `<div class="stat-pill"><span>👥</span> ${recipe.porciones} porciones</div>` : '',
      recipe.dificultad        ? `<div class="stat-pill"><span>📊</span> ${recipe.dificultad}</div>` : '',
      recipe.tipo_cocina       ? `<div class="stat-pill"><span>🌍</span> ${recipe.tipo_cocina}</div>` : '',
      recipe.tecnica_coccion   ? `<div class="stat-pill"><span>🔥</span> ${recipe.tecnica_coccion}</div>` : '',
    ].filter(Boolean).join('');

    const ingsHtml = ings.slice(0, 12).map(ing => {
      const qty = [ing.cantidad, ing.unidad].filter(Boolean).join(' ');
      return `<li class="preview-ing-item">
        <span class="preview-ing-qty">${qty || '—'}</span>
        <span class="preview-ing-name">${ing.nombre}${ing.preparacion ? `, ${ing.preparacion}` : ''}</span>
      </li>`;
    }).join('');

    const moreIngs = ings.length > 12 ? `<p style="font-size:0.78rem;color:var(--text-muted);margin-top:6px">…y ${ings.length - 12} más</p>` : '';
    const tagsHtml = tags.length ? `<div class="modal-tags-wrap">${tags.map(t => `<span class="tag">${t}</span>`).join('')}</div>` : '';

    $('add-preview-body').innerHTML = `
      <div class="preview-recipe-title">${getRecipeEmoji(recipe)} ${recipe.titulo || 'Sin título'}</div>
      ${recipe.descripcion ? `<p class="preview-recipe-desc">${recipe.descripcion}</p>` : ''}
      <div class="preview-pills">${pillsHtml}</div>
      ${ings.length ? `<p class="preview-section">Ingredientes (${ings.length})</p>
        <ul class="preview-ing-list">${ingsHtml}</ul>${moreIngs}` : ''}
      ${recipe.notas_quimicas ? `<p class="preview-section">Química del plato</p>
        <div class="modal-chemistry">🔬 ${recipe.notas_quimicas}</div>` : ''}
      ${tagsHtml ? `<p class="preview-section">Etiquetas</p>${tagsHtml}` : ''}
    `;
  },
};

function initAddRecipe() {
  addModal.overlay   = $('add-modal-overlay');
  addModal.textarea  = $('add-recipe-text');
  addModal.charCount = $('char-count');

  // Abrir modal
  $('add-recipe-btn').addEventListener('click', () => addModal.show());

  // Cerrar
  $('add-modal-close').addEventListener('click', () => addModal.hide());
  addModal.overlay.addEventListener('click', e => {
    if (e.target === addModal.overlay) addModal.hide();
  });

  // Contador de caracteres
  addModal.textarea.addEventListener('input', () => {
    const n = addModal.textarea.value.length;
    addModal.charCount.textContent = `${n.toLocaleString()} caracteres`;
  });

  // PASO 1 → Procesar (extract)
  $('add-process-btn').addEventListener('click', async () => {
    const text = addModal.textarea.value.trim();
    if (!text) {
      addModal.textarea.focus();
      addModal.textarea.style.borderColor = 'var(--danger)';
      setTimeout(() => { addModal.textarea.style.borderColor = ''; }, 1500);
      return;
    }

    addModal.goTo('loading');
    addModal.animateSteps(['proc-step-0', 'proc-step-1', 'proc-step-2'], 2000);

    try {
      const data = await apiFetch('/api/recipes/extract', {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      addModal.extractedRecipe = data.recipe;
      addModal.buildPreview(data.recipe);
      addModal.goTo('preview');
    } catch (err) {
      addModal.goTo('input');
      alert(`Error al procesar: ${err.message}`);
    }
  });

  // Volver a editar texto
  $('add-back-btn').addEventListener('click', () => addModal.goTo('input'));

  // PASO 2 → Guardar (save)
  $('add-save-btn').addEventListener('click', async () => {
    if (!addModal.extractedRecipe) return;
    addModal.goTo('saving');

    // Animar el paso de ChromaDB tras 1.8s
    setTimeout(() => {
      const s = $('proc-step-saving');
      if (s) s.classList.add('active');
    }, 1800);

    try {
      const data = await apiFetch('/api/recipes/save', {
        method: 'POST',
        body: JSON.stringify({ recipe: addModal.extractedRecipe }),
      });

      $('add-success-name').textContent = data.recipe?.titulo || 'Receta guardada';
      addModal.goTo('success');
      loadStats();

      // Añadir la tarjeta al grid si está visible "todas"
      const label = $('search-label');
      if (label.classList.contains('hidden')) {
        // Estamos en vista "todas" — recargamos el grid
        loadAllRecipes();
      }
    } catch (err) {
      addModal.goTo('preview');
      alert(`Error al guardar: ${err.message}`);
    }
  });

  // Añadir otra
  $('add-another-btn').addEventListener('click', () => {
    addModal.textarea.value = '';
    addModal.charCount.textContent = '0 caracteres';
    addModal.extractedRecipe = null;
    addModal.goTo('input');
    addModal.textarea.focus();
  });

  // Ver recetario (cierra modal)
  $('add-done-btn').addEventListener('click', () => {
    addModal.hide();
    addModal.textarea.value = '';
    addModal.charCount.textContent = '0 caracteres';
    addModal.extractedRecipe = null;
  });
}

// ─────────────────────── Init ─────────────────────────────────────────

function init() {
  initTabs();
  initModal();
  initSearch();
  initChat();
  initAddRecipe();
  loadStats();
  loadAllRecipes();
}

document.addEventListener('DOMContentLoaded', init);
