document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const viewLibroBtn = document.getElementById('viewLibroBtn');
    const viewChatBtn = document.getElementById('viewChatBtn');
    const viewLibro = document.getElementById('viewLibro');
    const viewChat = document.getElementById('viewChat');
    
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

    let recipes = [];
    let currentSelectedId = null;
    let extractedRecipe = null;
    let currentChatId = localStorage.getItem('last_chat_id');

    // --- Boot ---
    setTimeout(async () => {
        await loadRecipes();
        await loadChatHistory();
        handleRouting(); // Manejar ruta inicial
    }, 200);

    viewLibroBtn.onclick = () => switchView('libro');
    viewChatBtn.onclick = () => switchView('chat');

    // --- Navigation & Routing ---

    function navigate(path, state = {}) {
        history.pushState(state, '', path);
        handleRouting();
    }

    async function handleRouting() {
        const path = window.location.pathname;
        
        if (path.startsWith('/chat')) {
            switchView('chat', false);
            const chatId = path.split('/')[2];
            if (chatId) {
                currentChatId = chatId;
                localStorage.setItem('last_chat_id', chatId);
                await switchChat(chatId, true, false);
            } else {
                // Si estamos en /chat sin ID, intentar cargar el último o crear uno
                if (currentChatId) {
                    navigate(`/chat/${currentChatId}`);
                }
            }
        } else {
            // Default: /libro
            switchView('libro', false);
            const recipeId = path.split('/recipe/')[1];
            if (recipeId) {
                currentSelectedId = recipeId;
                await viewRecipe(recipeId, false);
            }
        }
    }

    window.onpopstate = handleRouting;

    function switchView(view, updateUrl = true) {
        if (view === 'libro') {
            viewLibro.classList.add('active');
            viewChat.classList.remove('active');
            viewLibroBtn.classList.add('active');
            viewChatBtn.classList.remove('active');
            if (updateUrl) {
                const url = currentSelectedId ? `/libro/recipe/${currentSelectedId}` : '/libro';
                navigate(url);
            }
        } else {
            viewLibro.classList.remove('active');
            viewChat.classList.add('active');
            viewLibroBtn.classList.remove('active');
            viewChatBtn.classList.add('active');
            if (updateUrl) {
                const url = currentChatId ? `/chat/${currentChatId}` : '/chat';
                navigate(url);
            }
        }
    }

    // --- Recipe Logic ---

    async function loadRecipes() {
        recipeList.innerHTML = '<div style="padding:2rem; color:#999; text-align:center;">Abriendo el libro...</div>';
        try {
            const res = await fetch('/api/recipes?limit=500');
            const data = await res.json();
            recipes = data.recipes || [];
            sortAndRender();
            updateStats();
            // No recipe selected by default as requested
        } catch (e) {
            recipeList.innerHTML = '<div style="padding:2rem; color:#e74c3c;">Error al conectar con la cocina.</div>';
        }
    }

    function sortAndRender() {
        const val = sortSelect.value;
        if (val === 'alpha') recipes.sort((a,b) => a.titulo.localeCompare(b.titulo));
        else if (val === 'time') recipes.sort((a,b) => (a.tiempos?.total_minutos || 999) - (b.tiempos?.total_minutos || 999));
        else if (val === 'difficulty') {
            const m = {'Fácil':1, 'Media':2, 'Difícil':3};
            recipes.sort((a,b) => (m[a.dificultad]||2) - (m[b.dificultad]||2));
        } else if (val === 'favs') {
            const f = JSON.parse(localStorage.getItem('favs')||'[]');
            recipes.sort((a,b) => {
                const aFav = f.includes(a._id) ? 0 : 1;
                const bFav = f.includes(b._id) ? 0 : 1;
                return aFav - bFav;
            });
        }
        renderList();
    }

    function renderList() {
        const criteria = sortSelect.value;
        let html = '';
        let lastL = '';
        
        if (!recipes.length) {
            recipeList.innerHTML = '<p style="padding:2rem; color:#999; text-align:center;">No hay recetas guardadas.</p>';
            return;
        }

        recipes.forEach(r => {
            if (criteria === 'alpha') {
                const char = (r.titulo || '#')[0].toUpperCase();
                if (char !== lastL) {
                    html += `<div class="letter-divider">${char}</div>`;
                    lastL = char;
                }
            }
            html += `
                <div class="recipe-item ${currentSelectedId === r._id ? 'active' : ''}" onclick="viewRecipe('${r._id}')">
                    <div class="recipe-item-header">
                        <h3>${r.titulo}</h3>
                        ${isFav(r._id) ? '<span class="list-star">★</span>' : ''}
                    </div>
                    <div class="meta">${r.tipo_cocina || 'Francesa'} • ${r.dificultad || 'Media'}</div>
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

        recipeDetail.innerHTML = `
            <div class="detail-paper">
                <header class="detail-header">
                    <h1>${r.titulo}</h1>
                    <div class="header-actions">
                        <button class="edit-btn" onclick="openEditModal('${id}')">✏️ Editar</button>
                        <button class="delete-recipe-btn" onclick="deleteRecipe('${id}')">🗑️</button>
                        <button class="fav-star ${isFav(id)?'active':''}" onclick="toggleFav('${id}', this)">★</button>
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
                                <b>${i.cantidad} ${i.unidad}</b>
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
        // Scroll reset robusto
        recipeDetail.scrollTo(0, 0);
        setTimeout(() => recipeDetail.scrollTop = 0, 0);
    };

    // --- Chat Logic ---

    const chefStatus = document.getElementById('chefStatus');

    async function loadChatHistory() {
        try {
            const res = await fetch('/api/chats');
            const data = await res.json();
            renderChatHistory(data.chats);
            if (currentChatId) switchChat(currentChatId, false);
        } catch(e) { console.error('Error loading chats', e); }
    }

    function renderChatHistory(chats) {
        if (!chats.length) {
            chatHistoryList.innerHTML = '<p style="padding:1.5rem 1rem; color:#ccc; font-size:0.75rem; text-align:center; font-style:italic;">Sin conversaciones previas.</p>';
            return;
        }
        chatHistoryList.innerHTML = chats.map(c => `
            <div class="chat-history-item ${currentChatId === c.id ? 'active' : ''}" onclick="switchChat('${c.id}')">
                <div class="chat-item-row">
                    <span class="chat-item-title">${c.title}</span>
                    <button class="chat-delete-btn" onclick="event.stopPropagation(); deleteChat('${c.id}')">×</button>
                </div>
                <div class="chat-item-date">${new Date(c.updated_at * 1000).toLocaleDateString('es-ES', {day:'2-digit', month:'short'})}</div>
            </div>
        `).join('');
    }

    window.deleteChat = async (id) => {
        if (!confirm('¿Borrar esta conversación?')) return;
        try {
            await fetch(`/api/chats/${id}`, { method: 'DELETE' });
            if (currentChatId === id) {
                currentChatId = null;
                localStorage.removeItem('last_chat_id');
                renderWelcome();
            }
            loadChatHistory();
        } catch(e) { console.error(e); }
    };

    window.switchChat = async (id, shouldLoad = true, updateUrl = true) => {
        if (updateUrl) { navigate(`/chat/${id}`); return; }
        currentChatId = id;
        localStorage.setItem('last_chat_id', id);
        document.querySelectorAll('.chat-history-item').forEach(el =>
            el.classList.toggle('active', el.getAttribute('onclick')?.includes(id))
        );
        if (!shouldLoad) return;

        chatMessages.innerHTML = '<div style="padding:4rem; text-align:center; color:#bbb; font-family:var(--serif); font-style:italic;">Preparando la mesa...</div>';
        try {
            const res = await fetch(`/api/chats/${id}`);
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
                        bubble.innerHTML = marked.parse(m.content);
                    }
                });
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
            currentChatId = data.id;
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
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return { wrap, body, bubble };
    }

    function addUserMsg(content) {
        const { bubble } = createMsgWrap('user');
        bubble.textContent = content;
        return bubble;
    }

    function addAiMsg(content) {
        const { body, bubble } = createMsgWrap('ai');
        if (content) bubble.innerHTML = marked.parse(content);
        bubble._body = body; // Store body ref for adding sources later
        return bubble;
    }

    function addThinkingWrap() {
        const wrap = document.createElement('div');
        wrap.className = 'msg-wrap ai';
        wrap.innerHTML = `
            <div class="msg-avatar-icon">🐀</div>
            <div class="msg-body">
                <div class="msg-thinking">
                    <div class="thinking-dots">
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                    </div>
                    <span class="thinking-label">Pensando...</span>
                </div>
            </div>`;
        chatMessages.appendChild(wrap);
        chatMessages.scrollTop = chatMessages.scrollHeight;
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
        div.innerHTML = sources.map(s =>
            `<button class="source-pill" onclick="viewRecipe('${s.id}')">📖 ${s.titulo}</button>`
        ).join('');
        body.appendChild(div);
    }

    // ── handleChat — con buffer de streaming robusto ─────────────────────

    async function handleChat() {
        const text = chatInput.value.trim();
        if (!text) return;

        if (chatMessages.querySelector('.welcome-container')) chatMessages.innerHTML = '';

        addUserMsg(text);
        chatInput.value = '';
        autoResize(chatInput);

        if (!currentChatId) await createNewChat(false);

        sendChat.disabled = true;
        chefStatus.textContent = 'Ratatui está pensando...';

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
            let buffer = ''; // Acumula texto parcial hasta tener líneas completas

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Procesar solo líneas completas (separadas por \n)
                const lines = buffer.split('\n');
                buffer = lines.pop(); // La última (incompleta) vuelve al buffer

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed) continue;

                    if (trimmed.startsWith('CHAT_ID: ')) {
                        const newId = trimmed.slice(9);
                        if (newId && currentChatId !== newId) {
                            currentChatId = newId;
                            localStorage.setItem('last_chat_id', newId);
                            loadChatHistory();
                        }

                    } else if (trimmed.startsWith('THOUGHT: ')) {
                        const thought = trimmed.slice(9);
                        chefStatus.textContent = thought;
                        setThinkingLabel(thinkingWrap, thought);

                    } else if (trimmed.startsWith('SOURCES: ')) {
                        try { pendingSources = JSON.parse(trimmed.slice(9)); } catch(_) {}

                    } else if (trimmed === '[DONE]') {
                        // fin del stream

                    } else {
                        // Token de contenido — mostrar burbuja AI
                        if (firstContent) {
                            thinkingWrap.remove();
                            aiDiv = addAiMsg('');
                            firstContent = false;
                            chefStatus.textContent = 'Ratatui está escribiendo...';
                        }
                        full += line + '\n';
                        aiDiv.innerHTML = marked.parse(full) + '<span class="streaming-cursor"></span>';
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    }
                }
            }

            // Procesar cualquier resto en el buffer
            if (buffer.trim() &&
                !buffer.startsWith('THOUGHT:') &&
                !buffer.startsWith('SOURCES:') &&
                !buffer.startsWith('CHAT_ID:')) {
                if (firstContent) {
                    thinkingWrap.remove();
                    aiDiv = addAiMsg('');
                    firstContent = false;
                }
                full += buffer;
            }

            // Renderizado final limpio (sin cursor)
            if (aiDiv) {
                aiDiv.innerHTML = marked.parse(full);
                attachSources(aiDiv, pendingSources);
            } else {
                thinkingWrap.remove();
            }

            chefStatus.textContent = 'Listo para más magia...';
            loadChatHistory();

        } catch (e) {
            thinkingWrap.remove();
            const errBubble = addAiMsg('');
            errBubble.textContent = 'Ratatui se ha distraído. Comprueba que el servidor esté corriendo e inténtalo de nuevo.';
            errBubble.style.color = '#e74c3c';
            chefStatus.textContent = 'Algo salió mal...';
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

    // --- Search & Modals ---

    searchInput.addEventListener('input', debounce(async () => {
        const q = searchInput.value;
        if (!q) return loadRecipes();
        const res = await fetch('/api/search', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:q, n_results:100})});
        const data = await res.json();
        recipes = data.recipes;
        renderList();
    }, 400));

    sortSelect.onchange = sortAndRender;
    sendChat.onclick = handleChat;
    newChatBtn.onclick = createNewChat;
    chatInput.addEventListener('input', () => autoResize(chatInput));
    chatInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChat(); } });

    // Modo sin distracciones — oculta/muestra el sidebar del chat
    document.getElementById('kitchenModeBtn').addEventListener('click', () => {
        const sidebar = document.querySelector('.chat-sidebar');
        sidebar.style.display = sidebar.style.display === 'none' ? '' : 'none';
    });
    
    addRecipeBtn.onclick = () => addModal.style.display = 'flex';
    closeModal.onclick = () => addModal.style.display = 'none';

    extractBtn.onclick = async () => {
        const text = rawRecipeText.value;
        if (!text) return;
        
        extractBtn.disabled = true;
        extractBtn.textContent = 'Interpretando...';
        extractionPreview.innerHTML = '<div class="extract-item"><i>Ratatui está leyendo tu receta...</i></div>';
        
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
                
                // Mostrar progreso crudo con efecto "escáner"
                extractionPreview.innerHTML = `
                    <div class="extract-item scann-effect">
                        <b>Ratatui está analizando...</b><br>
                        <small style="font-family:monospace; opacity:0.5; font-size:0.7rem;">${fullJSON.slice(-80)}</small>
                    </div>
                `;
            }

            // Al terminar, intentamos extraer el JSON de forma robusta
            fullJSON = fullJSON.trim();
            const jsonMatch = fullJSON.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                fullJSON = jsonMatch[0];
            }
            
            extractedRecipe = JSON.parse(fullJSON);
            
            // Normalizar por si acaso
            if (!extractedRecipe.titulo || extractedRecipe.titulo === 'string') {
                throw new Error('La IA no pudo estructurar la receta correctamente.');
            }
            
            extractionPreview.innerHTML = `
                <div class="extract-item"><b>Título:</b> ${extractedRecipe.titulo}</div>
                <div class="extract-item"><b>Descripción:</b> ${extractedRecipe.descripcion}</div>
                <div class="extract-item"><b>Ingredientes detectados:</b> ${extractedRecipe.ingredientes?.length || 0}</div>
                <div class="extract-item"><b>Pasos detectados:</b> ${extractedRecipe.pasos?.length || 0}</div>
            `;
            saveRecipeBtn.style.display = 'block';
        } catch(e) { 
            extractionPreview.innerHTML = `
                <div class="extract-item" style="color:#e74c3c">
                    <b>Ratatui ha tenido un contratiempo:</b><br>
                    No he podido interpretar bien la receta. Por favor, asegúrate de que el texto sea claro o intenta copiarlo de nuevo.
                </div>`;
            console.error(e);
        } finally { 
            extractBtn.disabled = false; 
            extractBtn.textContent = 'Analizar Texto'; 
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
            recipes = recipes.filter(r => r._id !== id);
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

    window.openEditModal = (id) => {
        const r = recipes.find(x => x._id === id);
        if (!r) return;
        
        document.getElementById('editTitle').value = r.titulo;
        document.getElementById('editDesc').value = r.descripcion || '';
        document.getElementById('editDiff').value = r.dificultad || 'Media';
        document.getElementById('editTime').value = r.tiempos?.total_minutos || 0;
        document.getElementById('editPortions').value = r.porciones || 0;
        document.getElementById('editIngs').value = JSON.stringify(r.ingredientes, null, 2);
        document.getElementById('editSteps').value = (r.pasos || []).join('\n');
        
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
            ingredientes: JSON.parse(document.getElementById('editIngs').value),
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
                document.getElementById('editIngs').value = JSON.stringify(r.ingredientes, null, 2);
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
            ingredientes: JSON.parse(document.getElementById('editIngs').value),
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
