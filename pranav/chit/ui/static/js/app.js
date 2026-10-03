const BASE=__BASE_PATH__, ROUTES=__ROUTES__;
const $=s=>document.querySelector(s), esc=s=>String(s??''); let chatId=null;
async function req(path,options={}){const r=await fetch(BASE+path,{credentials:'same-origin',...options});let data=null;const txt=await r.text();try{data=txt?JSON.parse(txt):null}catch{data=txt}if(r.status===401&&path!='/_ui/login'){lock();throw new Error('Console session expired. Enter the API key again.')}return {ok:r.ok,status:r.status,data}}
function pretty(x){return typeof x==='string'?x:JSON.stringify(x,null,2)}
function setLogin(auth){$('#loginOverlay').classList.toggle('hidden',auth);$('#logout').classList.toggle('hidden',!auth)}
function showError(el,e){el.textContent=e.message||String(e);el.classList.add('error')}
async function lock(){setLogin(false);$('#apiKey').value='';chatId=null;$('#chatSession').textContent=''}
async function updateNeuralOrb() {
    const orb = $('#neuralOrb');
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

async function checkSession(){try{const r=await req('/_ui/session');setLogin(!!r.data?.authenticated);$('#connection').textContent=r.data?.authenticated?'Key held for this browser session':'Sign in required';if(r.data?.authenticated)await refreshHealth()}catch(e){$('#connection').textContent=e.message}}

async function refreshHealth(){try{const r=await callApi('GET','/health',{},null);$('#connection').textContent='API · '+(r.data?.status||r.status);await updateNeuralOrb()}catch(e){$('#connection').textContent='API unavailable'}}

// Update orb every 5 seconds to keep track of training jobs
setInterval(updateNeuralOrb, 5000);

$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();const status=$('#loginStatus');status.textContent='Checking…';status.classList.remove('error');const key=$('#apiKey').value;try{const r=await req('/_ui/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key})});$('#apiKey').value='';if(!r.ok)throw new Error(r.data?.detail||'Could not sign in.');setLogin(true);$('#connection').textContent='Key held for this browser session';await refreshHealth()}catch(err){status.textContent=err.message;status.classList.add('error')}});
$('#logout').addEventListener('click',async()=>{try{await req('/_ui/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}finally{await lock();$('#connection').textContent='Signed out'}});
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
                document.querySelector('.pipeline-stage:nth-child(4)').classList.add('stage-active');
            } else {
                $('#count-training').textContent = '0';
                document.querySelector('.pipeline-stage:nth-child(4)').classList.remove('stage-active');
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
    list.innerHTML = '';
    r.data.configs.forEach(cfg => {
        const card = document.createElement('div');
        card.className = 'recipe-card';
        card.innerHTML = `<h3>${cfg}</h3><p>Preset training configuration</p>`;
        card.onclick = () => {
            document.querySelectorAll('.recipe-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            window.selectedRecipe = cfg;
        };
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
    list.innerHTML = '';
    if (r.data.jobs.length === 0) {
        list.innerHTML = '<div class="status" style="text-align: center; padding: 20px;">No recent jobs.</div>';
        return;
    }
    r.data.jobs.forEach(job => {
        const card = document.createElement('div');
        card.className = 'job-card';
        const stateCls = 'state-' + job.state;
        card.innerHTML = `
            <div class="job-header">
                <div style="font-weight:bold">${job.id.slice(0,8)}...</div>
                <div class="job-state ${stateCls}">${job.state}</div>
            </div>
            <div class="progress-bar"><div class="progress-fill" style="width:${job.progress*100}%"></div></div>
            <div class="job-meta">
                <span>Step ${job.step}/${job.max_steps}</span>
                <span>Loss: ${job.latest?.eval_loss?.toFixed(4) || 'N/A'}</span>
            </div>
        `;
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

async function runFairFight() {
    const prompt = $('#fightPrompt').value.trim();
    if (!prompt) return;
    
    $('#result-a').textContent = 'Thinking...';
    $('#result-b').textContent = 'Thinking...';
    
    try {
        // In a real scenario, we would use different model endpoints.
        // For the demo, we simulate Model A and B.
        const resA = await callApi('POST', '/generate', {}, { prompt, tokens: 100 });
        const resB = await callApi('POST', '/generate', {}, { prompt, tokens: 100, temperature: 0.9 }); // Make B more creative
        
        $('#result-a').textContent = resA.data.text;
        $('#result-b').textContent = resB.data.text;
    } catch (e) {
        $('#result-a').textContent = 'Error: ' + e.message;
        $('#result-b').textContent = 'Error: ' + e.message;
    }
}

async function promoteModel(checkpoint) {
    try {
        const r = await req('/_ui/model/promote', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ checkpoint })
        });
        if (r.ok) alert('Model promoted successfully!');
        else throw new Error(r.data?.detail || 'Promotion failed');
    } catch (e) {
        alert(e.message);
    }
}

$('#runFight').addEventListener('click', runFairFight);
$('#promote-a').addEventListener('click', () => promoteModel('latest.pt'));
$('#promote-b').addEventListener('click', () => promoteModel('candidate.pt'));

document.querySelectorAll('.nav button[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.nav button[data-view]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(v=>v.classList.toggle('hidden',v.id!=='view-'+b.dataset.view));if(b.dataset.view==='brain')updateKnowledgePipeline();if(b.dataset.view==='studio'){renderRecipes();renderJobs()} }));



function addBubble(role, text, memoryIds = []) {
    const b = document.createElement('div');
    b.className = 'bubble ' + role;
    
    if (role === 'chit' && text) {
        b.innerHTML = marked.parse(text);
    } else {
        b.textContent = text;
    }

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

        const regenBtn = document.createElement('button');
        regenBtn.className = 'action-btn';
        regenBtn.textContent = 'Regenerate';
        regenBtn.onclick = () => {
            // To regenerate, we essentially send the last user message again
            const messages = document.querySelectorAll('.bubble.user');
            if (messages.length > 0) {
                const lastUserMsg = messages[messages.length - 1].textContent;
                $('#chatInput').value = lastUserMsg;
                $('#sendChat').click();
            }
        };

        actions.appendChild(copyBtn);
        actions.appendChild(regenBtn);
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
        
        // Handle memory breadcrumbs first
        if (r.data?.metadata?.memory_ids) {
            await addMemoryBreadcrumb(r.data.metadata.memory_ids);
        }
        
        chatId = r.data.session_id;
        
        // Smart Title Update
        await updateSessionTitle(chatId);
        
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
        
        const tagsHtml = (mem.tags || []).map(t => `<span class="memory-tag">${t}</span>`).join('');
        
        card.innerHTML = `
            <div class="memory-content">${mem.content}</div>
            <div class="memory-tags">${tagsHtml}</div>
            <div class="memory-footer">
                <div class="memory-importance">Importance: ${mem.importance || '0.5'}</div>
                <div class="memory-actions">
                    <button class="btn-sm btn-use" onclick="useMemory('${mem.id}', \`${esc(mem.content)}\`)">Use</button>
                    <button class="btn-sm btn-del" onclick="deleteMemory('${mem.id}')">Del</button>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

async function useMemory(id, content) {
    $('#chatInput').value += ` ${content}`;
    document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
    $('#view-chat').classList.remove('hidden');
    $('#chatInput').focus();
}

async function deleteMemory(id) {
    if (!confirm('Are you sure you want to delete this memory?')) return;
    try {
        const r = await callApi('DELETE', `/memory/${id}`, {}, null);
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
        const r = await req(`/_ui/memories?q=${encodeURIComponent(q)}`);
        if (!r.ok) throw new Error(r.data?.detail || 'Search failed');
        renderMemoryGallery(r.data.results);
    } catch (e) {
        grid.innerHTML = `<div class="notice error" style="grid-column: 1/-1; text-align: center; padding: 20px;">${e.message}</div>`;
    }
});


$('#chatInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#sendChat').click()}});
$('#newChat').addEventListener('click',()=>{chatId=null;$('#chatlog').replaceChildren();$('#chatSession').textContent='New conversation'});
$('#runGenerate').addEventListener('click',async()=>{const status=$('#genStatus');status.textContent='Generating…';status.classList.remove('error');try{let stop=JSON.parse($('#genStop').value||'[]');if(!Array.isArray(stop))throw new Error('Stop strings must be a JSON array.');const body={prompt:$('#genPrompt').value,mode:$('#genMode').value,tokens:Number($('#genTokens').value),temperature:Number($('#genTemp').value),top_k:Number($('#genTopK').value),stop};const r=await callApi('POST','/generate',{},body);$('#genResult').textContent=pretty(r.data);if(!r.ok)throw new Error('API returned '+r.status);status.textContent='Complete'}catch(e){status.textContent=e.message;status.classList.add('error')}});
const list=$('#endpointList');let selected=null;ROUTES.forEach((route,i)=>{const b=document.createElement('button');b.className='endpoint';b.innerHTML='<b><i class="method">'+route.method+'</i>'+route.name+'</b><span>'+route.path+'</span>';b.title=route.category;b.addEventListener('click',()=>selectRoute(i));list.appendChild(b)});
function selectRoute(i){selected=ROUTES[i];$('#apiMethod').value=selected.method;$('#apiPath').value=selected.path;$('#apiQuery').value=JSON.stringify(selected.query||{},null,2);$('#apiBody').value=selected.body===null?'':JSON.stringify(selected.body,null,2);$('#apiResult').textContent='Ready: '+selected.name+' · '+selected.category;$('#apiStatus').textContent=''}
$('#runApi').addEventListener('click',async()=>{const status=$('#apiStatus'),result=$('#apiResult'),method=$('#apiMethod').value,path=$('#apiPath').value.trim();status.textContent='Sending…';status.classList.remove('error');try{const query=JSON.parse($('#apiQuery').value||'{}');if(!query||Array.isArray(query)||typeof query!=='object')throw new Error('Query parameters must be a JSON object.');let body=null;const raw=$('#apiBody').value.trim();if(raw)body=JSON.parse(raw);if(selected?.confirm&&!confirm('This operation may change Chit data, start work, or stop a job. Continue?')){status.textContent='Cancelled';return}const r=await callApi(method,path,query,body);result.textContent=pretty(r.data);status.textContent='HTTP '+r.status;if(!r.ok)status.classList.add('error')}catch(e){result.textContent=e.message;status.textContent='Could not send request';status.classList.add('error')}});
checkSession();
