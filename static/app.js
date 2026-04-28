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
    const sourceNodes = document.getElementById('sourceNodes');
    
    const addRecipeBtn = document.getElementById('addRecipeBtn');
    const addModal = document.getElementById('addModal');
    const closeModal = document.querySelector('.close-modal');
    const extractBtn = document.getElementById('extractBtn');
    const saveRecipeBtn = document.getElementById('saveRecipeBtn');
    const rawRecipeText = document.getElementById('rawRecipeText');
    const extractionPreview = document.getElementById('extractionPreview');

    let recipes = [];
    let chatHistory = [];
    let currentSelectedId = null;
    let extractedRecipe = null;

    // --- Boot ---
    setTimeout(loadRecipes, 200);

    // --- View Navigation ---
    viewLibroBtn.onclick = () => switchView('libro');
    viewChatBtn.onclick = () => switchView('chat');

    function switchView(view) {
        if (view === 'libro') {
            viewLibro.classList.add('active');
            viewChat.classList.remove('active');
            viewLibroBtn.classList.add('active');
            viewChatBtn.classList.remove('active');
        } else {
            viewLibro.classList.remove('active');
            viewChat.classList.add('active');
            viewLibroBtn.classList.remove('active');
            viewChatBtn.classList.add('active');
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
            if (recipes.length && !currentSelectedId) viewRecipe(recipes[0]._id);
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
                    <h3>${r.titulo}</h3>
                    <div class="meta">${r.tipo_cocina || 'Francesa'} • ${r.dificultad || 'Media'}</div>
                </div>
            `;
        });
        recipeList.innerHTML = html;
    }

    window.viewRecipe = (id) => {
        const r = recipes.find(x => x._id === id);
        if (!r) return;
        currentSelectedId = id;
        renderList();

        recipeDetail.innerHTML = `
            <div class="detail-paper">
                <header class="detail-header">
                    <h1>${r.titulo}</h1>
                    <button class="fav-star ${isFav(id)?'active':''}" onclick="toggleFav('${id}', this)">★</button>
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
        recipeDetail.scrollTop = 0;
    };

    // --- Chat Logic ---

    async function handleChat() {
        const text = chatInput.value.trim();
        if (!text) return;

        addMsg('user', text);
        chatInput.value = '';
        
        // Ratatouille está pensando...
        const aiDiv = addMsg('ai', '...');
        aiDiv.classList.add('typing');
        let full = '';

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, history: chatHistory })
            });

            if (!res.ok) throw new Error('Error en la comunicación');

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let first = true;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                
                for (let line of lines) {
                    if (line.startsWith('SOURCES: ')) {
                        try {
                            const s = JSON.parse(line.replace('SOURCES: ',''));
                            sourceNodes.innerHTML = s.map(n => `<div class="node-chip">${n}</div>`).join('');
                        } catch(e) {}
                    } else if (line.trim() === '[DONE]') {
                    } else if (line) {
                        if (line.startsWith('{')) {
                            try {
                                const j = JSON.parse(line);
                                line = j.response || line;
                            } catch(e) {}
                        }

                        if (first) { 
                            aiDiv.textContent = ''; 
                            aiDiv.classList.remove('typing');
                            first = false; 
                        }
                        full += line;
                        aiDiv.innerHTML = marked.parse(full); // USAR MARKED
                        chatMessages.scrollTop = chatMessages.scrollHeight;
                    }
                }
            }
            chatHistory.push({role:'user', content:text}, {role:'assistant', content:full});
        } catch (e) { 
            aiDiv.textContent = 'Ratatouille se ha distraído... parece que algo huele raro en la cocina. Intenta de nuevo.'; 
            aiDiv.classList.remove('typing');
        }
    }

    function addMsg(role, content) {
        const d = document.createElement('div');
        d.className = `msg ${role}`;
        d.textContent = content;
        chatMessages.appendChild(d);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return d;
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
    chatInput.onkeypress = (e) => { if(e.key==='Enter') handleChat(); };
    
    addRecipeBtn.onclick = () => addModal.style.display = 'flex';
    closeModal.onclick = () => addModal.style.display = 'none';

    extractBtn.onclick = async () => {
        const text = rawRecipeText.value;
        if (!text) return;
        
        extractBtn.disabled = true;
        extractBtn.textContent = 'Interpretando...';
        extractionPreview.innerHTML = '<div class="extract-item"><i>Ratatouille está leyendo tu receta...</i></div>';
        
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
                        <b>Ratatouille está analizando...</b><br>
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
                    <b>Ratatouille ha tenido un contratiempo:</b><br>
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

    window.toggleFav = (id, el) => {
        let f = JSON.parse(localStorage.getItem('favs')||'[]');
        if (f.includes(id)) f = f.filter(x => x!==id);
        else f.push(id);
        localStorage.setItem('favs', JSON.stringify(f));
        el.classList.toggle('active');
    };

    function isFav(id) { return JSON.parse(localStorage.getItem('favs')||'[]').includes(id); }
    function debounce(fn, t) { let id; return (...a) => { clearTimeout(id); id = setTimeout(()=>fn(...a), t); }; }
});
