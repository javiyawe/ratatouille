document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const layoutLibroBtn = document.getElementById('layoutLibroBtn');
    const layoutSplitBtn = document.getElementById('layoutSplitBtn');
    const layoutChatBtn  = document.getElementById('layoutChatBtn');
    const viewLibro = document.getElementById('viewLibro');
    const viewChat  = document.getElementById('viewChat');
    const appViewport = document.querySelector('.app-viewport');
    
    const recipeList = document.getElementById('recipeList');
    const recipeDetail = document.getElementById('recipeDetail');
    const searchInput = document.getElementById('searchInput');
    const sortSelect = document.getElementById('sortSelect');
    
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendChat = document.getElementById('sendChat');
    const chatHistoryList = document.getElementById('chatHistoryList');
    const newChatBtn = document.getElementById('newChatBtn');
    
    const addRecipeBtn = document.getElementById('addRecipeBtn');
    const addModal = document.getElementById('addModal');
    const closeModal = document.querySelector('.close-modal');
    const extractBtn = document.getElementById('extractBtn');
    const saveRecipeBtn = document.getElementById('saveRecipeBtn');
    const rawRecipeText = document.getElementById('rawRecipeText');
    const extractionPreview = document.getElementById('extractionPreview');
    const previewPanel = document.getElementById('previewPanel');
    const previewContent = document.getElementById('previewContent');
    const closePreviewBtn = document.getElementById('closePreviewBtn');

    let recipes = [];
    let currentSelectedId = null;
    let extractedRecipe = null;
    let currentChatId = localStorage.getItem('last_chat_id');

    let isSearchMode    = false;
    let autoScroll      = true;          // sigue el scroll automáticamente
    let displayedChatId = null;          // ID del chat actualmente en el DOM
    let currentLayout   = localStorage.getItem('layout') || 'libro';

    // Muestra cantidad + unidad sin duplicar si la unidad ya va en la cantidad
    function fmtQty(ing) {
        const q = (ing.cantidad || '').trim();
        const u = (ing.unidad   || '').trim();
        if (!u || q.toLowerCase().includes(u.toLowerCase())) return q;
        return `${q} ${u}`;
    }

    // --- Boot ---
    // Aplicar layout guardado inmediatamente (antes de cargar datos)
    setLayout(currentLayout, false);

    setTimeout(async () => {
        await loadRecipes();
        await loadChatHistory();
        handleRouting();
    }, 200);

    layoutLibroBtn.onclick = () => setLayout('libro');
    layoutSplitBtn.onclick = () => setLayout('split');
    layoutChatBtn.onclick  = () => setLayout('chat');

    // --- Navigation & Routing ---

    function navigate(path, state = {}) {
        if (window.location.pathname === path) return;
        history.pushState(state, '', path);
        handleRouting();
    }

    function redirect(path) {
        history.replaceState({}, '', path);
    }

    /** Cambia el modo de layout y actualiza el viewport + botones del nav */
    function setLayout(mode, updateUrl = true) {
        currentLayout = mode;
        localStorage.setItem('layout', mode);

        appViewport.className = `app-viewport mode-${mode}`;
        layoutLibroBtn.classList.toggle('active', mode === 'libro');
        layoutSplitBtn.classList.toggle('active', mode === 'split');
        layoutChatBtn.classList.toggle('active',  mode === 'chat');

        if (mode !== 'chat') previewPanel.classList.remove('active');

        if (!updateUrl) return;

        if (mode === 'libro') {
            navigate(currentSelectedId ? `/libro/recipe/${currentSelectedId}` : '/libro');
        } else if (mode === 'chat') {
            navigate(currentChatId ? `/chat/${currentChatId}` : '/chat');
        }
        // split: mantener URL actual, ambos paneles activos
    }

    async function handleRouting() {
        const path = window.location.pathname;

        if (path.startsWith('/chat')) {
            // Solo cambiar layout si estamos en modo libro puro
            if (currentLayout === 'libro') setLayout('chat', false);

            const chatId = path.split('/')[2];
            if (chatId) {
                currentChatId = chatId;
                localStorage.setItem('last_chat_id', chatId);
                await switchChat(chatId, true, false);
            } else {
                if (currentChatId) {
                    redirect(`/chat/${currentChatId}`);
                    await switchChat(currentChatId, true, false);
                } else {
                    chatMessages.innerHTML = '';
                    renderWelcome();
                }
            }
        } else {
            // Solo cambiar layout si estamos en modo chat puro
            if (currentLayout === 'chat') setLayout('libro', false);

            if (!path.startsWith('/libro')) redirect('/libro');

            const recipeId = path.split('/recipe/')[1];
            if (recipeId) {
                currentSelectedId = recipeId;
                await viewRecipe(recipeId, false);
            }
        }
    }

    window.onpopstate = () => handleRouting();

    // --- Recipe Logic ---

    let allRecipes = [];  // copia maestra sin filtrar

    async function loadRecipes() {
        recipeList.innerHTML = '<div style="padding:2rem; color:#999; text-align:center;">Abriendo el libro...</div>';
        try {
            const res = await fetch('/api/recipes?limit=500');
            const data = await res.json();
            allRecipes = data.recipes || [];
            recipes = [...allRecipes];
            isSearchMode = false;
            sortAndRender();
            updateStats();
        } catch (e) {
            recipeList.innerHTML = '<div style="padding:2rem; color:#e74c3c;">Error al conectar con la cocina.</div>';
        }
    }

    function sortAndRender() {
        const val = sortSelect.value;
        if (val === 'relevance') {
            // En modo búsqueda: mantener orden por relevancia; en modo normal: alfabético
            if (!isSearchMode) recipes.sort((a,b) => a.titulo.localeCompare(b.titulo));
        } else if (val === 'alpha') {
            recipes.sort((a,b) => a.titulo.localeCompare(b.titulo));
        } else if (val === 'time') {
            recipes.sort((a,b) => (a.tiempos?.total_minutos || 999) - (b.tiempos?.total_minutos || 999));
        } else if (val === 'difficulty') {
            const m = {'Fácil':1, 'Media':2, 'Difícil':3};
            recipes.sort((a,b) => (m[a.dificultad]||2) - (m[b.dificultad]||2));
        } else if (val === 'favs') {
            const f = JSON.parse(localStorage.getItem('favs')||'[]');
            recipes.sort((a,b) => (f.includes(a._id)?0:1) - (f.includes(b._id)?0:1));
        }
        renderList();
    }

    function renderList() {
        const criteria = sortSelect.value;
        let html = '';
        let lastL = '';

        if (!recipes.length) {
            const msg = isSearchMode
                ? 'Sin resultados para esta búsqueda.'
                : 'No hay recetas guardadas.';
            recipeList.innerHTML = `<p style="padding:2rem; color:#999; text-align:center;">${msg}</p>`;
            return;
        }

        if (isSearchMode) {
            html += `<div class="search-results-header">${recipes.length} resultado${recipes.length!==1?'s':''}</div>`;
        }

        recipes.forEach(r => {
            if (!isSearchMode && criteria === 'alpha') {
                const char = (r.titulo || '#')[0].toUpperCase();
                if (char !== lastL) {
                    html += `<div class="letter-divider">${char}</div>`;
                    lastL = char;
                }
            }

            const tags = (r.etiquetas || []).slice(0,2).map(t =>
                `<span class="recipe-tag">${t}</span>`).join('');
            const timeInfo = r.tiempos?.total_minutos
                ? `<span class="meta-time">⏱ ${r.tiempos.total_minutos} min</span>` : '';

            html += `
                <div class="recipe-item ${currentSelectedId === r._id ? 'active' : ''}" onclick="viewRecipe('${r._id}')">
                    <div class="recipe-item-header">
                        <h3>${r.titulo}</h3>
                        ${isFav(r._id) ? '<span class="list-star">★</span>' : ''}
                    </div>
                    <div class="meta">${r.tipo_cocina || 'Francesa'} • ${r.dificultad || 'Media'} ${timeInfo}</div>
                    ${tags ? `<div class="recipe-tags-row">${tags}</div>` : ''}
                </div>
            `;
        });
        recipeList.innerHTML = html;
    }

    window.viewRecipe = async (id, updateUrl = true) => {
        if (updateUrl) {
            navigate(`/libro/recipe/${id}`);
            return;
        }
        const r = recipes.find(x => x._id === id);
        if (!r) return;
        currentSelectedId = id;
        renderList();

        recipeDetail.scrollTop = 0;   // resetear antes de pintar para que no herede scroll previo
        recipeDetail.innerHTML = `
            <div class="detail-paper">
                <header class="detail-header">
                    <h1>${r.titulo}</h1>
                    <div class="header-actions">
                        <button class="recipe-action-btn" onclick="openEditModal('${id}')" title="Editar receta">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        </button>
                        <button class="recipe-action-btn danger" onclick="deleteRecipe('${id}')" title="Eliminar receta">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                        </button>
                        <button class="recipe-action-btn fav-btn ${isFav(id)?'active':''}" onclick="toggleFav('${id}', this)" title="Favorito">★</button>
                    </div>
                </header>
                
                <div class="detail-grid">
                    <div class="info-card"><label>Tiempo</label><strong>${r.tiempos?.total_minutos || '?'} min</strong></div>
                    <div class="info-card"><label>Porciones</label><strong>${r.porciones || '?'}</strong></div>
                    <div class="info-card"><label>Nivel</label><strong>${r.dificultad || 'Media'}</strong></div>
                </div>

                <div class="detail-section">
                    <h3>Ingredientes</h3>
                    <div class="ing-grid">
                        ${r.ingredientes.map(i => `
                            <div class="ing-row">
                                <span>${i.nombre}</span>
                                <b>${fmtQty(i)}</b>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="detail-section">
                    <h3>Preparación</h3>
                    ${r.pasos.map((s,i) => `
                        <div class="step-row">
                            <div class="step-n">${i+1}</div>
                            <div class="step-t">${s}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    };

    window.previewRecipe = async (id) => {
        const cleanId = id.replace(/[\[\]]/g, '').trim();

        // En modo dividido: abrir la receta en el panel del libro (integración clave)
        if (currentLayout === 'split') {
            await viewRecipe(cleanId, false);
            return;
        }

        let r = recipes.find(x => x._id === cleanId);
        if (!r) {
            try {
                const res = await fetch(`/api/recipes?limit=500`);
                const data = await res.json();
                recipes = data.recipes || [];
                r = recipes.find(x => x._id === cleanId);
            } catch(e) { console.error("Error fetching recipes for preview", e); }
        }
        
        if (!r) {
            console.warn("Recipe not found for ID:", cleanId);
            return;
        }

        previewContent.innerHTML = `
            <h1>${r.titulo}</h1>
            <p style="font-style: italic; color: #666; margin-bottom: 1.5rem; line-height: 1.5;">
                ${r.descripcion || 'Una delicadeza culinaria sin descripción, preparada con amor.'}
            </p>

            <div class="preview-meta">
                <div class="preview-badge">
                    <span>Tiempo</span>
                    ${r.tiempos?.total_minutos || '?'} min
                </div>
                <div class="preview-badge">
                    <span>Porciones</span>
                    ${r.porciones || '?'} pers.
                </div>
                <div class="preview-badge">
                    <span>Nivel</span>
                    ${r.dificultad || 'Media'}
                </div>
            </div>

            <div class="preview-section">
                <h3>Ingredientes</h3>
                <ul class="preview-ing-list">
                    ${r.ingredientes.map(i => `
                        <li class="preview-ing-item">
                            <span>${i.nombre}</span>
                            <b>${fmtQty(i)}</b>
                        </li>
                    `).join('')}
                </ul>
            </div>

            <div class="preview-section">
                <h3>Instrucciones detalladas</h3>
                ${r.pasos.map((s, i) => `
                    <div class="preview-step-item">
                        <div class="preview-step-n">${i + 1}</div>
                        <div class="preview-step-t">${s}</div>
                    </div>
                `).join('')}
            </div>

            <button class="btn-primary" style="width:100%; margin-top:1rem; padding: 1rem;" onclick="viewRecipe('${cleanId}')">
                Ver en el libro completo
            </button>
        `;
        previewPanel.classList.add('active');
        
        // Scroll al inicio del preview
        previewContent.scrollTo({ top: 0, behavior: 'smooth' });
    };

    closePreviewBtn.onclick = () => previewPanel.classList.remove('active');

    // --- Chat Logic ---

    const chefStatus = document.getElementById('chefStatus');

    async function loadChatHistory() {
        try {
            const res = await fetch('/api/chats');
            const data = await res.json();
            renderChatHistory(data.chats);
        } catch(e) { console.error('Error loading chats', e); }
    }

    function esc(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function renderChatHistory(chats) {
        if (!chats.length) {
            chatHistoryList.innerHTML = '<p style="padding:1.5rem 1rem; color:#ccc; font-size:0.75rem; text-align:center; font-style:italic;">Sin conversaciones previas.</p>';
            return;
        }
        chatHistoryList.innerHTML = chats.map(c => `
            <div class="chat-history-item ${currentChatId === c.id ? 'active' : ''}"
                 data-chat-id="${c.id}"
                 onclick="switchChat('${c.id}')">
                <div class="chat-item-row">
                    <span class="chat-item-title">${esc(c.title)}</span>
                    <div class="chat-item-btns">
                        <button class="chat-rename-btn" title="Renombrar"
                                onclick="event.stopPropagation(); startRenameChat('${c.id}')">✎</button>
                        <button class="chat-delete-btn"
                                onclick="event.stopPropagation(); deleteChat('${c.id}')">×</button>
                    </div>
                </div>
                <div class="chat-item-date">${new Date(c.updated_at * 1000).toLocaleDateString('es-ES', {day:'2-digit', month:'short'})}</div>
            </div>
        `).join('');
    }

    window.startRenameChat = (id) => {
        const item = chatHistoryList.querySelector(`[data-chat-id="${id}"]`);
        if (!item) return;
        const titleSpan = item.querySelector('.chat-item-title');
        if (!titleSpan || titleSpan.classList.contains('editing')) return;

        const currentTitle = titleSpan.textContent.trim();
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'chat-rename-input';
        input.value = currentTitle;
        input.maxLength = 120;
        titleSpan.classList.add('editing');
        titleSpan.replaceWith(input);
        input.focus();
        input.select();

        let done = false;
        const save = async () => {
            if (done) return;
            done = true;
            const newTitle = input.value.trim() || currentTitle;
            try {
                await fetch(`/api/chats/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle }),
                });
            } catch(e) { console.error(e); }
            loadChatHistory();
        };
        const cancel = () => { if (done) return; done = true; loadChatHistory(); };

        input.addEventListener('keydown', e => {
            if (e.key === 'Enter')  { e.preventDefault(); save(); }
            if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        });
        input.addEventListener('blur', save);
    };

    window.deleteChat = async (id) => {
        if (!confirm('¿Borrar esta conversación?')) return;
        try {
            await fetch(`/api/chats/${id}`, { method: 'DELETE' });
            if (currentChatId === id) {
                currentChatId   = null;
                displayedChatId = null;
                localStorage.removeItem('last_chat_id');
                renderWelcome();
            }
            loadChatHistory();
        } catch(e) { console.error(e); }
    };

    // polling activo para respuestas pendientes: chatId → intervalId
    const _pendingPolls = {};

    function _stopPoll(chatId) {
        if (_pendingPolls[chatId]) {
            clearInterval(_pendingPolls[chatId]);
            delete _pendingPolls[chatId];
        }
    }

    function _startPoll(chatId, thinkingEl) {
        _stopPoll(chatId);
        let attempts = 0;
        _pendingPolls[chatId] = setInterval(async () => {
            attempts++;
            if (attempts > 90) { _stopPoll(chatId); thinkingEl?.remove(); return; } // 3 min max
            try {
                const res  = await fetch(`/api/chats/${chatId}`);
                const data = await res.json();
                const last = data.history?.[data.history.length - 1];
                if (last?.role === 'assistant') {
                    _stopPoll(chatId);
                    thinkingEl?.remove();
                    const bubble = addAiMsg('');
                    bubble.innerHTML = marked.parse(parseReferences(last.content, last.sources || []));
                    if (last.sources?.length) attachSources(bubble, last.sources);
                    scrollBottom(true);
                    loadChatHistory();
                    chefStatus.textContent = 'Listo para más magia';
                }
            } catch(_) { _stopPoll(chatId); thinkingEl?.remove(); }
        }, 2000);
    }

    window.switchChat = async (id, shouldLoad = true, updateUrl = true) => {
        if (updateUrl) { navigate(`/chat/${id}`); return; }
        currentChatId = id;
        localStorage.setItem('last_chat_id', id);
        document.querySelectorAll('.chat-history-item').forEach(el =>
            el.classList.toggle('active', el.getAttribute('onclick')?.includes(id))
        );
        if (!shouldLoad) return;

        // Si este chat ya está renderizado en el DOM (el usuario vuelve desde el libro),
        // no re-fetchamos: los mensajes pendientes siguen ahí.
        if (id === displayedChatId && chatMessages.children.length > 0
                && !chatMessages.querySelector('.welcome-container')) {
            return;
        }

        // Parar cualquier poll anterior de otro chat
        Object.keys(_pendingPolls).forEach(cid => { if (cid !== id) _stopPoll(cid); });

        displayedChatId = id;
        chatMessages.innerHTML = '<div style="padding:4rem; text-align:center; color:#bbb; font-family:var(--serif); font-style:italic;">Preparando la mesa...</div>';
        try {
            const res  = await fetch(`/api/chats/${id}`);
            const data = await res.json();
            chatMessages.innerHTML = '';
            if (!data.history?.length) {
                renderWelcome();
            } else {
                data.history.forEach(m => {
                    if (m.role === 'user') {
                        addUserMsg(m.content);
                    } else if (m.role === 'assistant') {
                        const bubble = addAiMsg('');
                        bubble.innerHTML = marked.parse(parseReferences(m.content, m.sources || []));
                        if (m.sources?.length) attachSources(bubble, m.sources);
                    }
                });

                // Si el último mensaje es del usuario, el chef aún está procesando
                const last = data.history[data.history.length - 1];
                if (last?.role === 'user') {
                    const thinkingEl = addThinkingWrap();
                    setThinkingLabel(thinkingEl, 'Preparando respuesta…');
                    chefStatus.textContent = 'Ratatui está cocinando';
                    _startPoll(id, thinkingEl);
                }
            }
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } catch(e) {
            chatMessages.innerHTML = '<div style="color:#e74c3c; padding:2rem; text-align:center;">Error al cargar la conversación.</div>';
        }
    };

    function renderWelcome() {
        chatMessages.innerHTML = `
            <div class="welcome-container">
                <div class="welcome-logo">🐀</div>
                <h1>¡Bonjour!</h1>
                <p>¿Qué alquimia culinaria realizaremos hoy?</p>
                <div class="quick-prompts">
                    <button onclick="setChatInput('¿Qué puedo cocinar con pollo y limón?')">🍋 Pollo al limón</button>
                    <button onclick="setChatInput('Sugiéreme una cena romántica para dos')">🕯️ Cena romántica</button>
                    <button onclick="setChatInput('¿Cómo puedo mejorar mi risotto?')">🍚 Técnica de Risotto</button>
                    <button onclick="setChatInput('¿Qué recetas tengo en el libro?')">📖 Mi recetario</button>
                </div>
            </div>
        `;
    }

    window.setChatInput = (val) => {
        chatInput.value = val;
        autoResize(chatInput);
        chatInput.focus();
    };

    window.handleAction = (action) => {
        const prompts = {
            pair:     '¿Con qué vino o bebida me recomiendas maridar este plato?',
            shopping: 'Genera una lista de la compra organizada para esta receta.',
            scale:    'Ajusta las cantidades de la receta para 6 personas.',
            alquimia: 'Propón una variante creativa o fusión de este plato.'
        };
        if (prompts[action]) {
            chatInput.value = prompts[action];
            autoResize(chatInput);
            handleChat();
        }
    };

    window.createNewChat = async (withWelcome = true) => {
        try {
            const res = await fetch('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: 'Nueva conversación' })
            });
            const data = await res.json();
            currentChatId   = data.id;
            displayedChatId = data.id;
            localStorage.setItem('last_chat_id', currentChatId);
            if (withWelcome) {
                navigate(`/chat/${currentChatId}`);
                loadChatHistory();
                chatMessages.innerHTML = '';
                renderWelcome();
            }
            return data.id;
        } catch(e) { console.error(e); }
    };

    // ── Scroll ───────────────────────────────────────────────────────────

    // Detecta si el usuario sube manualmente → desactiva auto-scroll
    chatMessages.addEventListener('scroll', () => {
        const dist = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight;
        autoScroll = dist < 80;
    }, { passive: true });

    function scrollBottom(force = false) {
        if (!autoScroll && !force) return;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ── Funciones de construcción de mensajes ───────────────────────────

    function createMsgWrap(role) {
        const wrap = document.createElement('div');
        wrap.className = `msg-wrap ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar-icon';
        avatar.textContent = role === 'ai' ? '🐀' : 'Tú';

        const body = document.createElement('div');
        body.className = 'msg-body';

        const bubble = document.createElement('div');
        bubble.className = `msg-bubble ${role}`;

        body.appendChild(bubble);
        wrap.appendChild(avatar);
        wrap.appendChild(body);
        chatMessages.appendChild(wrap);
        scrollBottom();
        return { wrap, body, bubble };
    }

    function addUserMsg(content) {
        autoScroll = true;          // al enviar, siempre seguimos
        const { bubble } = createMsgWrap('user');
        bubble.textContent = content;
        scrollBottom(true);
        return bubble;
    }

    function addAiMsg(content, sources = []) {
        autoScroll = true;          // nueva respuesta → retomamos seguimiento
        const { body, bubble } = createMsgWrap('ai');
        if (content) bubble.innerHTML = marked.parse(parseReferences(content, sources));
        bubble._body = body;
        return bubble;
    }

    function addThinkingWrap() {
        const wrap = document.createElement('div');
        wrap.className = 'msg-wrap ai';
        wrap.innerHTML = `
            <div class="msg-avatar-icon">🐀</div>
            <div class="msg-body">
                <div class="msg-thinking">
                    <div class="thinking-content">
                        <span class="thinking-dots"><span></span><span></span><span></span></span>
                        <span class="thinking-label">Pensando</span>
                    </div>
                </div>
            </div>`;
        chatMessages.appendChild(wrap);
        scrollBottom();
        return wrap;
    }

    function setThinkingLabel(wrap, text) {
        const label = wrap.querySelector('.thinking-label');
        if (label) label.textContent = text;
    }

    function attachSources(bubble, sources) {
        if (!sources?.length) return;
        const body = bubble._body || bubble.parentElement;
        const div = document.createElement('div');
        div.className = 'msg-sources';
        div.innerHTML = sources.map(s => {
            const label = s.num != null ? `[${s.num}] ${s.titulo}` : s.titulo;
            return `<button class="source-pill" onclick="previewRecipe('${s.id}')">📖 ${label}</button>`;
        }).join('');
        body.appendChild(div);
    }

    /**
     * Convierte referencias del LLM en spans clicables.
     * Soporta dos formatos:
     *   [1], [2]  — nuevo formato numerado (sources array requerido)
     *   [ID: uuid] — formato legacy para mensajes antiguos
     */
    function parseReferences(text, sources = []) {
        // Mapa num → source
        const numMap = {};
        (sources || []).forEach(s => { if (s.num != null) numMap[s.num] = s; });

        // Formato nuevo: [1], [2] …
        if (Object.keys(numMap).length) {
            text = text.replace(/\[(\d+)\]/g, (match, n) => {
                const s = numMap[parseInt(n)];
                if (!s) return match;
                return `<sup class="recipe-ref recipe-ref-num" data-recipe-id="${s.id}" title="${s.titulo}">[${n}]</sup>`;
            });
        }

        // Formato legacy: Nombre [ID: uuid]
        text = text.replace(/([^#*\[\n\r]+)?\s*\[[iI][dD]:\s*([0-9a-fA-F-]{8,36})\]/g,
            (_m, name, id) => {
                const cleanId     = id.trim();
                const displayName = (name || '').trim() || 'Ver Receta';
                return `<span class="recipe-ref" data-recipe-id="${cleanId}" title="${displayName}"><span class="ref-icon">📖</span> ${displayName}</span>`;
            }
        );

        return text;
    }

    // Delegación de eventos para las referencias del chat
    chatMessages.addEventListener('click', (e) => {
        const ref = e.target.closest('.recipe-ref');
        if (ref) {
            const id = ref.getAttribute('data-recipe-id');
            if (id) window.previewRecipe(id);
        }
    });

    // ── handleChat — SSE JSON protocol ──────────────────────────────────

    async function handleChat() {
        const text = chatInput.value.trim();
        if (!text) return;

        if (chatMessages.querySelector('.welcome-container')) chatMessages.innerHTML = '';

        // Si había un poll activo para este chat, pararlo (el SSE lo sustituye)
        if (currentChatId) _stopPoll(currentChatId);

        addUserMsg(text);
        chatInput.value = '';
        autoResize(chatInput);

        if (!currentChatId) await createNewChat(false);
        displayedChatId = currentChatId;   // este chat está vivo en el DOM

        sendChat.disabled = true;
        chefStatus.textContent = 'Ratatui está pensando';

        const thinkingWrap = addThinkingWrap();
        let full = '';
        let pendingSources = [];
        let aiDiv = null;
        let firstContent = true;

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, chat_id: currentChatId })
            });

            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Los eventos SSE están delimitados por \n\n
                const parts = buffer.split('\n\n');
                buffer = parts.pop(); // El último (incompleto) vuelve al buffer

                for (const part of parts) {
                    for (const line of part.split('\n')) {
                        if (!line.startsWith('data: ')) continue;
                        let event;
                        try { event = JSON.parse(line.slice(6)); } catch(_) { continue; }

                        switch (event.type) {
                            case 'chat_id': {
                                const newId = event.value;
                                if (newId && currentChatId !== newId) {
                                    currentChatId = newId;
                                    localStorage.setItem('last_chat_id', newId);
                                    loadChatHistory();
                                }
                                break;
                            }
                            case 'thought': {
                                chefStatus.textContent = event.value;
                                setThinkingLabel(thinkingWrap, event.value);
                                break;
                            }
                            case 'sources': {
                                pendingSources = event.value;
                                break;
                            }
                            case 'token': {
                                if (firstContent) {
                                    thinkingWrap.remove();
                                    aiDiv = addAiMsg('');
                                    firstContent = false;
                                    chefStatus.textContent = 'Ratatui está escribiendo';
                                }
                                full += event.value;
                                aiDiv.innerHTML = marked.parse(parseReferences(full, pendingSources))
                                               + '<span class="streaming-cursor"></span>';
                                scrollBottom();   // solo sigue si autoScroll está activo
                                break;
                            }
                            case 'done': {
                                if (aiDiv) {
                                    aiDiv.innerHTML = marked.parse(parseReferences(full, pendingSources));
                                    attachSources(aiDiv, pendingSources);
                                }
                                chefStatus.textContent = 'Listo para más magia';
                                break;
                            }
                            case 'title': {
                                loadChatHistory();
                                break;
                            }
                        }
                    }
                }
            }

            // Asegurar renderizado final si el stream terminó sin evento 'done'
            if (aiDiv && aiDiv.innerHTML.includes('streaming-cursor')) {
                aiDiv.innerHTML = marked.parse(parseReferences(full, pendingSources));
                attachSources(aiDiv, pendingSources);
            } else if (firstContent) {
                thinkingWrap.remove();
            }

            chefStatus.textContent = 'Listo para más magia';

        } catch (e) {
            thinkingWrap.remove();
            const errBubble = addAiMsg('');
            errBubble.textContent = 'Ratatui se ha distraído. Comprueba que el servidor esté corriendo e inténtalo de nuevo.';
            errBubble.style.color = '#e74c3c';
            chefStatus.textContent = 'Algo salió mal';
            console.error(e);
        } finally {
            sendChat.disabled = false;
        }
    }

    // Auto-resize del textarea
    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }

    // --- Search & Filter Chips ---

    async function runSearch() {
        const q = searchInput.value.trim();

        if (!q) {
            isSearchMode = false;
            recipes = [...allRecipes];
            sortAndRender();
            return;
        }

        isSearchMode = true;
        recipeList.innerHTML = '<div class="search-loading">Buscando…</div>';

        try {
            const res = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: q, n_results: 100 })
            });
            const data = await res.json();
            recipes = data.recipes || [];
            if (sortSelect.value === 'alpha' || sortSelect.value === 'relevance') {
                sortSelect.value = 'relevance';
            }
            sortAndRender();
        } catch (e) {
            recipeList.innerHTML = '<div style="padding:2rem;color:#e74c3c;">Error en la búsqueda.</div>';
        }
    }

    searchInput.addEventListener('input', debounce(runSearch, 350));
    sortSelect.onchange = sortAndRender;
    sendChat.onclick = handleChat;
    newChatBtn.onclick = createNewChat;
    chatInput.addEventListener('input', () => autoResize(chatInput));
    chatInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChat(); } });

    // Modo sin distracciones — en chat puro oculta sidebar; en split activa modo chat
    document.getElementById('kitchenModeBtn').addEventListener('click', () => {
        if (currentLayout === 'split') {
            setLayout('chat');
        } else {
            const sidebar = document.querySelector('.chat-sidebar');
            if (sidebar) sidebar.style.display = sidebar.style.display === 'none' ? '' : 'none';
        }
    });
    
    addRecipeBtn.onclick = () => addModal.style.display = 'flex';
    document.getElementById('addIngBtn').onclick = () => window.addIngRow();
    closeModal.onclick = () => addModal.style.display = 'none';

    extractBtn.onclick = async () => {
        const text = rawRecipeText.value;
        if (!text) return;
        
        extractBtn.disabled = true;
        extractBtn.textContent = 'Interpretando';
        
        extractionPreview.classList.remove('empty');
        extractionPreview.innerHTML = `
            <div class="extracting-loader"></div>
            <div style="padding: 1rem; color: #999; font-style: italic; text-align: center;">
                Ratatui está leyendo tu receta y estructurando los sabores
            </div>
        `;
        
        let fullJSON = '';
        try {
            const res = await fetch('/api/recipes/extract', { 
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({text})
            });

            if (!res.ok) throw new Error('Servidor no responde');

            const reader = res.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                fullJSON += chunk;
                
                // Efecto visual de "escritura" en la previsualización
                const lastBit = fullJSON.slice(-50).replace(/["{}[\]]/g, '');
                if (lastBit.length > 5) {
                    extractionPreview.innerHTML = `
                        <div class="extracting-loader"></div>
                        <div style="opacity: 0.6; font-size: 0.85rem;">
                            <b>Analizando componentes...</b><br>
                            <span style="font-family: monospace;">> ${lastBit}</span>
                        </div>
                    `;
                }
            }

            // Al terminar, intentamos extraer el JSON de forma robusta
            fullJSON = fullJSON.trim();
            const jsonMatch = fullJSON.match(/\{[\s\S]*\}/);
            if (jsonMatch) fullJSON = jsonMatch[0];
            
            extractedRecipe = JSON.parse(fullJSON);
            
            if (!extractedRecipe.titulo || extractedRecipe.titulo === 'string') {
                throw new Error('La IA no pudo estructurar la receta correctamente.');
            }
            
            // Renderizado final de PREVIEW ESTÉTICO
            extractionPreview.innerHTML = `
                <div class="live-preview-content">
                    <h2>${extractedRecipe.titulo}</h2>
                    <p class="desc">${extractedRecipe.descripcion || ''}</p>
                    
                    <div class="preview-meta" style="margin-bottom: 1.5rem;">
                        <div class="preview-badge"><span>Nivel</span>${extractedRecipe.dificultad || 'Media'}</div>
                        <div class="preview-badge"><span>Tiempo</span>${extractedRecipe.tiempos?.total_minutos || '?'} min</div>
                    </div>

                    <h4>Ingredientes</h4>
                    <ul class="preview-ing-list">
                        ${(extractedRecipe.ingredientes || []).map(i => `
                            <li class="preview-ing-item">
                                <span>${i.nombre}</span>
                                <b>${fmtQty(i)}</b>
                            </li>
                        `).join('')}
                    </ul>

                    <h4>Preparación</h4>
                    <div class="preview-steps">
                        ${(extractedRecipe.pasos || []).map((s, i) => `
                            <div class="preview-step-item">
                                <div class="preview-step-n">${i+1}</div>
                                <div class="preview-step-t" style="font-size: 0.85rem;">${s}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            saveRecipeBtn.style.display = 'block';
        } catch(e) { 
            extractionPreview.classList.add('empty');
            extractionPreview.innerHTML = `
                <div class="empty-preview-state" style="color:#e74c3c">
                    <b>Ouch! Contretemps...</b><br>
                    No he podido interpretar bien la receta. Prueba a simplificar el texto.
                </div>`;
            console.error(e);
        } finally { 
            extractBtn.disabled = false; 
            extractBtn.textContent = '✨ Analizar y Estructurar'; 
        }
    };

    saveRecipeBtn.onclick = async () => {
        saveRecipeBtn.disabled = true;
        saveRecipeBtn.textContent = 'Guardando...';
        try {
            await fetch('/api/recipes/save', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({recipe:extractedRecipe})});
            addModal.style.display = 'none';
            loadRecipes();
            // Limpiar modal
            rawRecipeText.value = '';
            extractionPreview.innerHTML = '';
            saveRecipeBtn.style.display = 'none';
        } catch(e) { alert('Error al guardar.'); }
        finally { saveRecipeBtn.disabled = false; saveRecipeBtn.textContent = 'Guardar en el Libro'; }
    };

    window.deleteRecipe = async (id) => {
        if (!confirm('¿Eliminar esta receta del libro?')) return;
        try {
            const res = await fetch(`/api/recipes/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error();
            recipes    = recipes.filter(r => r._id !== id);
            allRecipes = allRecipes.filter(r => r._id !== id);
            currentSelectedId = null;
            recipeDetail.innerHTML = '<div class="empty-state"><div class="empty-icon">🍲</div><p>Elige una receta del libro para comenzar la magia.</p></div>';
            renderList();
            updateStats();
        } catch (e) {
            alert('Error al eliminar la receta.');
        }
    };

    window.toggleFav = (id, el) => {
        let f = JSON.parse(localStorage.getItem('favs')||'[]');
        if (f.includes(id)) f = f.filter(x => x!==id);
        else f.push(id);
        localStorage.setItem('favs', JSON.stringify(f));
        el.classList.toggle('active');
        renderList(); // Update the sidebar stars immediately
    };

    function isFav(id) { return JSON.parse(localStorage.getItem('favs')||'[]').includes(id); }
    function debounce(fn, t) { let id; return (...a) => { clearTimeout(id); id = setTimeout(()=>fn(...a), t); }; }

    async function updateStats() {
        try {
            const res = await fetch('/api/stats');
            const data = await res.json();
            document.getElementById('recipeCount').textContent = `${data.total_recipes} recetas`;
        } catch(e) {}
    }

    function renderIngList(ingredients) {
        const list = document.getElementById('ingList');
        list.innerHTML = '';
        (ingredients || []).forEach(ing => addIngRow(ing));
    }

    window.addIngRow = function(ing = {}) {
        const list = document.getElementById('ingList');
        const row = document.createElement('div');
        row.className = 'ing-row-edit';
        row.innerHTML = `
            <input class="ing-input ing-nombre" value="${ing.nombre || ''}" placeholder="Ingrediente">
            <input class="ing-input ing-cant"   value="${ing.cantidad || ''}" placeholder="Cant.">
            <input class="ing-input ing-unit"   value="${ing.unidad || ''}"  placeholder="Ud.">
            <button type="button" class="ing-del-btn" onclick="this.closest('.ing-row-edit').remove()">×</button>
        `;
        list.appendChild(row);
        row.querySelector('.ing-nombre').focus();
    };

    function collectIngredients() {
        return Array.from(document.querySelectorAll('#ingList .ing-row-edit')).map(row => ({
            nombre:   row.querySelector('.ing-nombre').value.trim(),
            cantidad: row.querySelector('.ing-cant').value.trim(),
            unidad:   row.querySelector('.ing-unit').value.trim(),
        })).filter(i => i.nombre);
    }

    window.openEditModal = (id) => {
        const r = recipes.find(x => x._id === id);
        if (!r) return;
        
        document.getElementById('editTitle').value    = r.titulo;
        document.getElementById('editDesc').value     = r.descripcion || '';
        document.getElementById('editDiff').value     = r.dificultad || 'Media';
        document.getElementById('editTime').value     = r.tiempos?.total_minutos || 0;
        document.getElementById('editPortions').value = r.porciones || 0;
        document.getElementById('editCuisine').value  = r.tipo_cocina || '';
        renderIngList(r.ingredientes || []);
        document.getElementById('editSteps').value    = (r.pasos || []).join('\n');

        document.getElementById('editModal').style.display = 'flex';
        document.getElementById('magicInstructions').value = '';
        
        document.getElementById('saveEditBtn').onclick = () => saveEdit(id);
        document.getElementById('magicBtn').onclick = () => applyMagic(id);
    };

    async function applyMagic(_id) {
        const instr = document.getElementById('magicInstructions').value.trim();
        if (!instr) return;

        const magicBtn = document.getElementById('magicBtn');
        magicBtn.disabled = true;
        magicBtn.innerHTML = '<span class="loading-spin">⌛</span> Procesando...';

        const currentRecipe = {
            titulo: document.getElementById('editTitle').value,
            descripcion: document.getElementById('editDesc').value,
            dificultad: document.getElementById('editDiff').value,
            tiempos: { total_minutos: parseInt(document.getElementById('editTime').value) || 0 },
            porciones: parseInt(document.getElementById('editPortions').value) || 0,
            tipo_cocina: document.getElementById('editCuisine').value,
            ingredientes: collectIngredients(),
            pasos: document.getElementById('editSteps').value.split('\n').filter(s => s.trim())
        };

        try {
            const res = await fetch('/api/recipes/refine', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recipe: currentRecipe, instructions: instr })
            });
            const data = await res.json();
            if (data.recipe) {
                const r = data.recipe;
                document.getElementById('editTitle').value = r.titulo;
                document.getElementById('editDesc').value = r.descripcion;
                document.getElementById('editDiff').value = r.dificultad;
                document.getElementById('editTime').value = r.tiempos?.total_minutos || 0;
                document.getElementById('editPortions').value = r.porciones || 0;
                renderIngList(r.ingredientes || []);
                if (r.tipo_cocina) document.getElementById('editCuisine').value = r.tipo_cocina;
                document.getElementById('editSteps').value = (r.pasos || []).join('\n');
                document.getElementById('magicInstructions').value = '';
            }
        } catch(e) {
            alert('Ratatui se ha liado con la magia. Intenta de nuevo.');
        } finally {
            magicBtn.disabled = false;
            magicBtn.textContent = 'Aplicar Magia';
        }
    }

    async function saveEdit(id) {
        const saveBtn = document.getElementById('saveEditBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Guardando...';
        
        const updatedRecipe = {
            titulo: document.getElementById('editTitle').value,
            descripcion: document.getElementById('editDesc').value,
            dificultad: document.getElementById('editDiff').value,
            tiempos: { total_minutos: parseInt(document.getElementById('editTime').value) || 0 },
            porciones: parseInt(document.getElementById('editPortions').value) || 0,
            tipo_cocina: document.getElementById('editCuisine').value,
            ingredientes: collectIngredients(),
            pasos: document.getElementById('editSteps').value.split('\n').filter(s => s.trim())
        };

        try {
            const res = await fetch(`/api/recipes/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ recipe: updatedRecipe })
            });
            if (res.ok) {
                document.getElementById('editModal').style.display = 'none';
                await loadRecipes();
                await viewRecipe(id, false); // Refrescar vista
            } else {
                alert('Error al guardar cambios');
            }
        } catch(e) {
            console.error(e);
            alert('Error en la conexión');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Guardar Cambios';
        }
    }

    document.getElementById('cancelEdit').onclick = () => {
        document.getElementById('editModal').style.display = 'none';
    };
});
