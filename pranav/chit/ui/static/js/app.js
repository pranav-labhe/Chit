const $=s=>document.querySelector(s); let chatId=null, authenticated=false;
async function req(path,options={}){const r=await fetch(BASE+path,{credentials:'same-origin',...options});let data=null;const txt=await r.text();try{data=txt?JSON.parse(txt):null}catch{data=txt}if(r.status===401&&path!='/_ui/login'){lock();throw new Error('Console session expired. Enter the API key again.')}return {ok:r.ok,status:r.status,data}}
function pretty(x){return typeof x==='string'?x:JSON.stringify(x,null,2)}
function setLogin(auth){$('#loginOverlay').classList.toggle('hidden',auth);$('#logout').classList.toggle('hidden',!auth)}
function showError(el,e){el.textContent=e.message||String(e);el.classList.add('error')}
async function lock(){authenticated=false;setLogin(false);$('#apiKey').value='';chatId=null;$('#chatSession').textContent=''}
async function updateNeuralOrb() {
        const orb = $('#neuralOrb');
        if (!authenticated || !orb) return;
    try {
        const status = await req('/_ui/train/status');
        if (!status.ok) return;
        
        const state = status.data.state;
        orb.classList.remove('orb-idle', 'orb-thinking', 'orb-learning');
        
        if (state === 'idle') {
            orb.classList.add('orb-idle');
        } else if (state === 'running' || state === 'queued') {
            orb.classList.add('orb-learning');
        } else {
            orb.classList.add('orb-idle');
        }
    } catch (e) {
        console.error('Orb update failed', e);
    }
}

async function checkSession(){try{const r=await req('/_ui/session');authenticated=!!r.data?.authenticated;setLogin(authenticated);$('#connection').textContent=authenticated?'Key held for this browser session':'Sign in required';if(authenticated){await refreshHealth();await loadWorkspace()}}catch(e){$('#connection').textContent=e.message}}

async function refreshHealth(){try{const r=await callApi('GET','/health',{},null);$('#connection').textContent='API · '+(r.data?.status||r.status);await updateNeuralOrb()}catch(e){$('#connection').textContent='API unavailable'}}

// Refresh live indicators only while the browser has an authenticated session.
setInterval(()=>{if(authenticated){updateNeuralOrb();updateKnowledgePipeline()}}, 15000);

$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();const status=$('#loginStatus');status.textContent='Checking…';status.classList.remove('error');const key=$('#apiKey').value;try{const r=await req('/_ui/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key})});$('#apiKey').value='';if(!r.ok)throw new Error(r.data?.detail||'Could not sign in.');authenticated=true;setLogin(true);status.textContent='';$('#connection').textContent='Key held for this browser session';await refreshHealth();await loadWorkspace()}catch(err){status.textContent=err.message;status.classList.add('error')}});
$('#logout').addEventListener('click',async()=>{try{await req('/_ui/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}finally{authenticated=false;await lock();$('#connection').textContent='Signed out'}});
async function callApi(method,path,query,body){const r=await req('/_ui/proxy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,path,query,body})});return r}
async function updateKnowledgePipeline() {
    try {
        const stats = await req('/_ui/knowledge/stats');
        if (stats.ok) {
            const byStatus = stats.data.by_status || {};
            $('#count-pending').textContent = byStatus.pending || 0;
            $('#count-trained').textContent = byStatus.trained || 0;
            
            const trainStatus = await req('/_ui/train/status');
            if (trainStatus.ok && trainStatus.data.state !== 'idle') {
                $('#count-training').textContent = '1';
            $('#count-training').closest('.pipeline-stage').classList.add('stage-active');
            } else {
                $('#count-training').textContent = '0';
                $('#count-training').closest('.pipeline-stage').classList.remove('stage-active');
            }
        }
    } catch (e) {
        console.error('Could not update pipeline', e);
    }
}

async function renderRecipes() {
    const r = await req('/_ui/train/configs');
    const list = $('#recipeList');
    if (!r.ok) {
        list.innerHTML = '<div class="notice error">Failed to load recipes</div>';
        return;
    }
    list.replaceChildren();
    (r.data.configs || []).forEach(cfg => {
        const card = document.createElement('div');
        card.className = 'recipe-card';
        card.tabIndex = 0;
        card.setAttribute('role', 'button');
        card.setAttribute('aria-pressed', 'false');
        const title = document.createElement('h3');
        title.textContent = cfg;
        const description = document.createElement('p');
        description.textContent = 'Preset training configuration';
        card.append(title, description);
        const choose = () => {
            document.querySelectorAll('.recipe-card').forEach(c => {
                c.classList.remove('active');
                c.setAttribute('aria-pressed', 'false');
            });
            card.classList.add('active');
            card.setAttribute('aria-pressed', 'true');
            window.selectedRecipe = cfg;
        };
        card.addEventListener('click', choose);
        card.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                choose();
            }
        });
        list.appendChild(card);
    });
}

async function renderJobs() {
    const r = await req('/_ui/train/jobs');
    const list = $('#jobList');
    if (!r.ok) {
        list.innerHTML = '<div class="notice error">Failed to load jobs</div>';
        return;
    }
    list.replaceChildren();
    if (r.data.jobs.length === 0) {
        list.innerHTML = '<div class="status" style="text-align: center; padding: 20px;">No recent jobs.</div>';
        return;
    }
    r.data.jobs.forEach(job => {
        const card = document.createElement('div');
        card.className = 'job-card';
        const stateCls = 'state-' + job.state;
        const header = document.createElement('div');
        header.className = 'job-header';
        const id = document.createElement('div');
        id.style.fontWeight = 'bold';
        id.textContent = `${String(job.id || '').slice(0, 8)}…`;
        const state = document.createElement('div');
        state.className = `job-state ${stateCls}`;
        state.textContent = job.state || 'unknown';
        header.append(id, state);
        const progress = document.createElement('div');
        progress.className = 'progress-bar';
        const fill = document.createElement('div');
        fill.className = 'progress-fill';
        fill.style.width = `${Math.max(0, Math.min(100, Number(job.progress || 0) * 100))}%`;
        progress.append(fill);
        const meta = document.createElement('div');
        meta.className = 'job-meta';
        const step = document.createElement('span');
        step.textContent = `Step ${job.step ?? 0}/${job.max_steps ?? 0}`;
        const loss = document.createElement('span');
        loss.textContent = `Loss: ${Number.isFinite(job.latest?.eval_loss) ? job.latest.eval_loss.toFixed(4) : 'N/A'}`;
        meta.append(step, loss);
        card.append(header, progress, meta);
        list.appendChild(card);
    });
}

$('#startTrain').addEventListener('click', async () => {
    if (!window.selectedRecipe) {
        alert('Please select a recipe first');
        return;
    }
    const status = $('#trainStatus');
    status.textContent = 'Igniting forge...';
    try {
        const r = await req('/_ui/train', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ config: window.selectedRecipe, init: 'auto' })
        });
        if (!r.ok) throw new Error(r.data?.detail || 'Training failed to start');
        status.textContent = 'Evolution started!';
        await renderJobs();
    } catch (e) {
        status.textContent = e.message;
        status.classList.add('error');
    }
});

async function loadWorkspace(){
    await Promise.all([renderRecipes(), renderJobs(), updateKnowledgePipeline(), updateNeuralOrb()]);
}

document.querySelectorAll('.nav button[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.nav button[data-view]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-current',x===b?'page':'false')});document.querySelectorAll('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='view-'+b.dataset.view));if(b.dataset.view==='brain')updateKnowledgePipeline();if(b.dataset.view==='studio'){renderRecipes();renderJobs()} }));



function addBubble(role, text, memoryIds = []) {
    const b = document.createElement('div');
    b.className = 'bubble ' + role;
    
    b.textContent = text;

    if (role === 'chit') {
        const actions = document.createElement('div');
        actions.className = 'bubble-actions';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'action-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(text);
            copyBtn.textContent = 'Copied!';
            setTimeout(() => copyBtn.textContent = 'Copy', 2000);
        };

        actions.appendChild(copyBtn);
        b.appendChild(actions);
    }
    
    $('#chatlog').appendChild(b);
    $('#chatlog').scrollTop = $('#chatlog').scrollHeight;
}


async function updateSessionTitle(sid) {
    if (!sid) return;
    try {
        const r = await req(`/_ui/session/title?session_id=${sid}`);
        if (r.ok) {
            $('#chatSession').textContent = 'Conversation: ' + r.data.title;
        }
    } catch (e) {
        console.error('Could not fetch session title', e);
    }
}

$('#sendChat').addEventListener('click', async () => {
    const box = $('#chatInput'), message = box.value.trim();
    if (!message) return;
    
    addBubble('user', message);
    box.value = '';
    $('#sendChat').disabled = true;
    
    try {
        const r = await callApi('POST', '/chat', {}, {
            message, 
            session_id: chatId, 
            temperature: 0.4
        });
        
        if (!r.ok) throw new Error(r.data?.detail ? pretty(r.data.detail) : 'Request failed (' + r.status + ')');
        
        chatId = r.data.session_id;
        
        $('#chatSession').textContent = chatId ? `Session ${chatId}` : 'No saved session';
        addBubble('chit', r.data.text || '');
        
    } catch (e) {
        addBubble('system', e.message);
    } finally {
        $('#sendChat').disabled = false;
    }
});

async function renderMemoryGallery(results = []) {
    const grid = $('#memoryGrid');
    grid.innerHTML = '';
    
    if (results.length === 0) {
        grid.innerHTML = '<div class="status" style="grid-column: 1/-1; text-align: center; padding: 40px;">No memories found matching your search.</div>';
        return;
    }
    
    results.forEach(mem => {
        const card = document.createElement('div');
        card.className = 'memory-card';
        
        const content = document.createElement('div');
        content.className = 'memory-content';
        content.textContent = mem.content || '';
        const tags = document.createElement('div');
        tags.className = 'memory-tags';
        (mem.tags || []).forEach(tag => {
            const badge = document.createElement('span');
            badge.className = 'memory-tag';
            badge.textContent = tag;
            tags.appendChild(badge);
        });
        const footer = document.createElement('div');
        footer.className = 'memory-footer';
        const importance = document.createElement('div');
        importance.className = 'memory-importance';
        importance.textContent = `Importance: ${mem.importance ?? 0.5}`;
        const actions = document.createElement('div');
        actions.className = 'memory-actions';
        const use = document.createElement('button');
        use.className = 'btn-sm btn-use';
        use.type = 'button';
        use.textContent = 'Use';
        use.addEventListener('click', () => useMemory(mem.content || ''));
        const remove = document.createElement('button');
        remove.className = 'btn-sm btn-del';
        remove.type = 'button';
        remove.textContent = 'Delete';
        remove.addEventListener('click', () => deleteMemory(mem.id));
        actions.append(use, remove);
        footer.append(importance, actions);
        card.append(content, tags, footer);
        grid.appendChild(card);
    });
}

async function useMemory(content) {
    $('#chatInput').value += `${$('#chatInput').value ? '\n' : ''}${content}`;
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    $('#view-chat').classList.remove('hidden');
    $('#chatInput').focus();
}

async function deleteMemory(id) {
    if (!confirm('Are you sure you want to delete this memory?')) return;
    try {
        const r = await callApi('DELETE', `/memory/${encodeURIComponent(id)}`, {}, null);
        if (r.ok) {
            alert('Memory deleted');
            $('#doMemSearch').click();
        } else {
            throw new Error(r.data?.detail || 'Delete failed');
        }
    } catch (e) {
        alert(e.message);
    }
}

$('#doMemSearch').addEventListener('click', async () => {
    const q = $('#memSearch').value.trim();
    const grid = $('#memoryGrid');
    grid.innerHTML = '<div class="status" style="grid-column: 1/-1; text-align: center; padding: 40px;">Searching...</div>';
    try {
        if (!q) throw new Error('Enter a word or phrase to search memories.');
        const r = await req(`/_ui/memories?q=${encodeURIComponent(q)}`);
        if (!r.ok) throw new Error(r.data?.detail || 'Search failed');
        renderMemoryGallery(r.data.results);
    } catch (e) {
        const message = document.createElement('div');
        message.className = 'notice error';
        message.style.gridColumn = '1 / -1';
        message.textContent = e.message;
        grid.replaceChildren(message);
    }
});


$('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#sendChat').click()}});
$('#newChat').addEventListener('click',()=>{chatId=null;$('#chatlog').replaceChildren();$('#chatSession').textContent='New conversation'});
$('#runGenerate').addEventListener('click',async()=>{const status=$('#genStatus');status.textContent='Generating…';status.classList.remove('error');try{let stop=JSON.parse($('#genStop').value||'[]');if(!Array.isArray(stop))throw new Error('Stop strings must be a JSON array.');const body={prompt:$('#genPrompt').value,mode:$('#genMode').value,tokens:Number($('#genTokens').value),temperature:Number($('#genTemp').value),top_k:Number($('#genTopK').value),stop};const r=await callApi('POST','/generate',{},body);$('#genResult').textContent=pretty(r.data);if(!r.ok)throw new Error('API returned '+r.status);status.textContent='Complete'}catch(e){status.textContent=e.message;status.classList.add('error')}});
const list=$('#endpointList');let selected=null;ROUTES.forEach((route,i)=>{const b=document.createElement('button');b.type='button';b.className='endpoint';const title=document.createElement('b');const method=document.createElement('i');method.className='method';method.textContent=route.method;title.append(method,document.createTextNode(route.name));const path=document.createElement('span');path.textContent=route.path;b.append(title,path);b.title=route.category;b.addEventListener('click',()=>selectRoute(i));list.appendChild(b)});
function selectRoute(i){selected=ROUTES[i];$('#apiMethod').value=selected.method;$('#apiPath').value=selected.path;$('#apiQuery').value=JSON.stringify(selected.query||{},null,2);$('#apiBody').value=selected.body===null?'':JSON.stringify(selected.body,null,2);$('#apiResult').textContent='Ready: '+selected.name+' · '+selected.category;$('#apiStatus').textContent=''}
$('#runApi').addEventListener('click',async()=>{const status=$('#apiStatus'),result=$('#apiResult'),method=$('#apiMethod').value,path=$('#apiPath').value.trim();status.textContent='Sending…';status.classList.remove('error');try{const query=JSON.parse($('#apiQuery').value||'{}');if(!query||Array.isArray(query)||typeof query!=='object')throw new Error('Query parameters must be a JSON object.');let body=null;const raw=$('#apiBody').value.trim();if(raw)body=JSON.parse(raw);if(method!=='GET'&&!confirm('This request may change data, start training, or cancel a job. Continue?')){status.textContent='Cancelled';return}const r=await callApi(method,path,query,body);result.textContent=pretty(r.data);status.textContent='HTTP '+r.status;if(!r.ok)status.classList.add('error')}catch(e){result.textContent=e.message;status.textContent='Could not send request';status.classList.add('error')}});
checkSession();
