const $=s=>document.querySelector(s); let chatId=null, authenticated=false;
const controlHelp={
apiKey:{what:'Lets this browser sign in to Chit. The key stays on the server for this browser session.',example:'Paste the API key given to you by the server owner.',best:'Only enter the key on the trusted Chit page. Do not share it in a message or screenshot.',recommended:'Use the key supplied for this server.',risk:'Anyone with this key may be able to change data or start training.'},
chatInput:{what:'Write a message for Chit. Chat keeps a conversation going and may use saved memories.',example:'“Help me plan a simple weekly meal list.”',best:'Ask one clear question at a time. Add important context that Chit would not know.',recommended:'Use a complete sentence; press Enter to send or Shift+Enter for a new line.',risk:'Chit can make mistakes. Check important information.'},
sendChat:{what:'Sends your message and adds Chit’s reply to this saved conversation.',example:'Send “What should I pack for a rainy day?”',best:'Give Chit enough detail to understand what you need.',recommended:'Start a new conversation when you switch to a different topic.',risk:'The conversation is saved under your account session.'},
newChat:{what:'Starts a separate conversation with a fresh context.',example:'Use it before asking about an unrelated topic.',best:'Keep one topic in each conversation for clearer context.',recommended:'Use when you do not want earlier messages to guide the next answer.',risk:'This does not delete your old conversation; use Conversations to remove it.'},
genPrompt:{what:'The request or starting text Chit will respond to.',example:'“Explain why leaves change colour in autumn.”',best:'Ask for one task and say what kind of answer you want.',recommended:'A short, clear request is a good starting point.',risk:'Very long prompts leave less room for the answer.'},
genMode:{what:'Chooses whether Chit answers as an assistant or continues your text exactly.',example:'Choose “Answer my request” for a question; choose “Continue my text” for an unfinished sentence.',best:'Use assistant mode for everyday requests.',recommended:'Answer my request.',risk:'Continue mode does not add the normal assistant instructions or memory context.'},
genTokens:{what:'Sets the maximum amount Chit may write.',example:'Choose “Concise” for a short answer or “More detail” for a longer one.',best:'Start with Detailed and increase it only when needed.',recommended:'Detailed.',risk:'A larger answer can take longer and may wander off topic.'},
genTemp:{what:'Controls how predictable or varied the wording is.',example:'0 gives steadier wording; a higher number allows more variety.',best:'Lower it when answers look inconsistent.',recommended:'0 for troubleshooting; 0.4 for ordinary writing.',risk:'Higher values can make mistakes and gibberish more likely.'},
genTopK:{what:'Limits how many next-word choices Chit considers.',example:'A smaller value narrows its choices.',best:'Leave this alone unless you are comparing response settings.',recommended:'50; at temperature 0 it has little or no effect.',risk:'Very small values can make answers repetitive.'},
runGenerate:{what:'Sends one request and shows the reply without saving a conversation.',example:'Write a prompt, then choose Generate.',best:'Use this for a one-time answer or to test a prompt.',recommended:'Use the normal Chat screen for a back-and-forth conversation.',risk:'A long response uses more time and compute.'},
refreshSessions:{what:'Reloads the saved conversation list.',example:'Use after starting a new chat.',best:'Refresh if a recent conversation is missing.',recommended:'No setting needed.',risk:'This only reads the list.'},
lessonKind:{what:'Chooses whether the lesson is a short passage or a question with its answer.',example:'Choose question and answer for a fact Chit should answer directly.',best:'Use a single clear fact or one question and its correct answer.',recommended:'A fact or short passage for general information.',risk:'Conflicting or incorrect lessons can teach Chit the wrong thing.'},
lessonSource:{what:'Records where this lesson came from.',example:'“Product handbook, page 4” or “My preference”.',best:'Add a source when you may need to check the fact later.',recommended:'Optional; leave blank if there is no useful source.',risk:'Do not include private source details you do not want stored.'},
lessonText:{what:'The passage Chit can study in a future training run.',example:'“The office is closed on public holidays.”',best:'Write short, complete sentences and check spelling.',recommended:'One topic per lesson.',risk:'Saving a lesson does not make Chit learn it until you train.'},
lessonQuestion:{what:'The question that should match this lesson.',example:'“When is the office closed?”',best:'Write the question the way a person might ask it.',recommended:'One direct question.',risk:'A vague question can make the lesson harder to use.'},
lessonAnswer:{what:'The correct answer to the question above.',example:'“The office is closed on public holidays.”',best:'Answer the question directly and include needed context.',recommended:'A short, accurate answer.',risk:'Chit may repeat errors in a lesson when trained on it.'},
rememberLesson:{what:'Also saves the lesson as a memory so Chat can use it right away.',example:'Turn this on for a preference you want Chit to recall before training.',best:'Use for personal facts or details needed in near-term conversations.',recommended:'Leave off for general lessons intended only for training.',risk:'The memory and lesson are separate saved copies; removing one does not remove the other.'},
saveLesson:{what:'Adds this lesson to Chit’s learning queue.',example:'Save a checked question and answer.',best:'Review the wording before saving.',recommended:'Save only reliable, useful information.',risk:'The model changes only after a training session; training can take time.'},
knowledgeFilter:{what:'Shows lessons waiting to be learned, already learned, or all lessons.',example:'Choose “Ready to learn” to review the next training queue.',best:'Check pending lessons before starting training.',recommended:'Ready to learn.',risk:'Changing this only changes the list view.'},
refreshKnowledge:{what:'Reloads saved lessons and their current status.',example:'Use after saving or training a lesson.',best:'Refresh when lesson counts look out of date.',recommended:'No setting needed.',risk:'This only reads saved lessons.'},
memSearch:{what:'Finds saved memories that match the words you enter.',example:'Search “vegetarian” to find food preferences.',best:'Use a meaningful word or phrase from the memory.',recommended:'Search with one or two specific words.',risk:'An empty search cannot find useful results.'},
doMemSearch:{what:'Searches Chit’s saved memories.',example:'Type “home city”, then press Search.',best:'Try a shorter word if there are no matches.',recommended:'Search only when you want to inspect or remove a memory.',risk:'This reads memories; it does not change them.'},
newMemory:{what:'A fact or preference Chit can use in chat right away.',example:'“I prefer answers in simple English.”',best:'Write one short, searchable sentence.',recommended:'Save information that will help in future conversations.',risk:'A memory does not train the model. Do not save passwords or secrets.'},
memoryType:{what:'A label to help you describe the saved memory.',example:'Use personal experience for a preference; use fact for general information.',best:'Pick the closest label; it does not change how Chit is trained.',recommended:'Personal experience or preference for personal details.',risk:'This label is for organizing; it is not a privacy control.'},
memoryImportance:{what:'Marks how useful this memory is for future recall.',example:'Choose Very important for a strong, lasting preference.',best:'Use a higher value only for information that matters often.',recommended:'Important for a useful everyday fact.',risk:'A high value does not make the fact more accurate.'},
saveMemory:{what:'Saves this information to Chit’s memory for use in chat.',example:'Save “I prefer metric measurements.”',best:'Check that the sentence is clear and contains no secret information.',recommended:'One useful fact per memory.',risk:'This is stored immediately; delete it later if it is no longer wanted.'},
dataConfig:{what:'Chooses which saved training plan to inspect.',example:'Choose Everyday assistant to see its training files and readiness.',best:'Use the same plan you intend to train.',recommended:'Everyday assistant when available.',risk:'Inspection is read-only; choosing a plan does not start training.'},
dataSource:{what:'Names a text file already present in the server’s training folder.',example:'“lessons.txt”',best:'Enter only the file name, not a computer path or web address.',recommended:'Preview the split before writing files.',risk:'The file must exist on the server and fit its size limit.'},
overwriteSplit:{what:'Allows a new split to replace the plan’s current training files.',example:'Leave this off unless you have reviewed the preview and want to replace existing files.',best:'Keep it off for the first attempt.',recommended:'Off.',risk:'The old files are replaced; the server keeps a backup.'},
inspectData:{what:'Checks which training files this plan will use and whether they are ready.',example:'Inspect the plan before training.',best:'Fix any missing-file or size warnings first.',recommended:'Run before every new training run.',risk:'This only reads file information.'},
previewSplit:{what:'Shows how a text file would be divided without writing anything.',example:'Preview a file split, then review the estimated training and review portions.',best:'Always preview before creating a split.',recommended:'Use the default paragraph split for conversation text.',risk:'Preview does not change files.'},
applySplit:{what:'Writes new training and review files from the selected text file.',example:'Use after a preview shows the right files and sizes.',best:'Keep a backup of your source file and confirm the selected plan.',recommended:'Do not replace existing files unless you mean to.',risk:'This changes training files. Replacing old files keeps a backup but affects future training.'},
refreshModel:{what:'Reloads the current server and model status.',example:'Use after a model finishes training.',best:'Check this before troubleshooting an answer.',recommended:'No setting needed.',risk:'This only reads status.'},
diagnosticConfig:{what:'Chooses which plan’s training files to check.',example:'Pick the same plan you use for training.',best:'Compare the plan’s text reader with the active model.',recommended:'Everyday assistant when available.',risk:'This check does not start training.'},
runDiagnostics:{what:'Checks the server, model, readiness, training files, and recent jobs.',example:'Run this after an unexpected or unreadable reply.',best:'Review any attention messages and follow their suggested next steps.',recommended:'Run after choosing the plan that produced the problem.',risk:'These checks are read-only; they cannot prove that a model will answer well.'},
diagnosticPrompt:{what:'The short request sent to the active model for a sample reply.',example:'“Reply with one clear sentence: What is a library?”',best:'Use a simple prompt so the sample is easy to judge.',recommended:'Keep the suggested example for a basic check.',risk:'The request uses compute, but does not create a saved conversation.'},
runDiagnosticPrompt:{what:'Generates one sample answer from the active model.',example:'Use it to see whether the model can produce a clear sentence.',best:'Run the checks first, then judge the sample yourself.',recommended:'Use a short, familiar prompt.',risk:'This uses compute and is not a full quality test.'},
responseReadable:{what:'Records that the sample looks readable to you.',example:'Choose this when the answer is understandable and on topic.',best:'Judge clarity and relevance, not whether you agree with every detail.',recommended:'Use only after reading the full sample.',risk:'This is your feedback; it does not change model settings.'},
responseGarbled:{what:'Shows next steps for unreadable or off-topic sample answers.',example:'Choose this if the answer is mostly broken text or ignores the prompt.',best:'Run the system checks and inspect the selected plan’s training files.',recommended:'Use when the sample is hard to understand.',risk:'This feedback does not automatically retrain or change the model.'},
openTrainingLibrary:{what:'Opens the training file inspection screen.',example:'Use it to read warnings about missing or small training files.',best:'Inspect the same plan selected in Troubleshooting.',recommended:'Review warnings before training.',risk:'The inspection itself does not change files.'},
openStudio:{what:'Opens learning plan selection and training history.',example:'Use after checking that training material is ready.',best:'Read the selected plan details before starting.',recommended:'Use a plan suited to your available training data and hardware.',risk:'Starting training uses compute and may take time.'},
trainConfig:{what:'Chooses the model size, context, study schedule, and text files used for a training run.',example:'Choose Everyday assistant to see its settings before training.',best:'Read the explanation below the selector and inspect its data first.',recommended:'Everyday assistant for normal assistant examples, when available.',risk:'Larger or longer plans use more time and memory. Training data quality affects results.'},
startTrain:{what:'Starts a training run from the selected plan’s regular training files.',example:'Choose a plan, inspect its files, then start learning.',best:'Start only when training data is ready and no other run is active.',recommended:'Build on the current brain unless you intentionally need a fresh start.',risk:'Uses compute and may take time. The live model is kept unless the candidate completes and is promoted.'},
lessonScope:{what:'Chooses whether to train on every saved lesson or only lessons not yet learned.',example:'Use pending lessons to focus on new material.',best:'Use all lessons when you want Chit to revisit the complete lesson set.',recommended:'All lessons.',risk:'Training only pending lessons may give less review of older material.'},
trainKnowledge:{what:'Starts a learning run using lessons saved under Teach Chit.',example:'Save a few checked lessons, then choose Learn saved lessons.',best:'Inspect lessons and training files first.',recommended:'All lessons for balanced review, or pending for only new lessons.',risk:'Uses compute. Lessons are marked learned only if the model is promoted.'},
apiMethod:{what:'Chooses whether the request reads information, creates or changes something, or deletes it.',example:'GET reads; POST performs an action; DELETE removes an item.',best:'Use the method shown on the selected API topic.',recommended:'Do not change it unless you know why.',risk:'POST and DELETE requests can change saved data or start work.'},
apiPath:{what:'The server action selected in the API reference.',example:'The route is filled in when you choose a topic above.',best:'Leave the selected route unchanged unless using a known ID.',recommended:'Use the example route supplied by the topic.',risk:'Changing the route can target a different action.'},
apiQuery:{what:'Optional search or filtering choices for an advanced request.',example:'The selected topic fills in a working example when one is needed.',best:'Use the guided screen if you do not know these settings.',recommended:'Keep the supplied example.',risk:'Incorrect values can make the request fail or show a different set of records.'},
apiBody:{what:'The advanced information sent with a request that creates or changes something.',example:'The selected topic fills in a sample when it needs one.',best:'Prefer the guided screen; it checks common values for you.',recommended:'Keep the supplied example unless you understand each field.',risk:'A request can start training or change saved information. Review it before sending.'},
runApi:{what:'Sends the request shown in the advanced editor.',example:'Use after selecting an API topic and reviewing its example.',best:'Read the topic guide and confirm the method, route, and body.',recommended:'Use a guided screen for routine tasks.',risk:'Some requests change or delete data, or start long-running training.'},
apiKeySubmit:{what:'Checks the key and opens the Chit console.',example:'Enter the key, then choose Continue.',best:'Use the key from the server owner.',recommended:'Sign in only on the trusted Chit address.',risk:'Never share your key.'},
refreshSessions:{what:'Reloads your saved conversation list.',example:'Choose after creating a conversation.',best:'Use if the list is out of date.',recommended:'No setting needed.',risk:'Read-only.'}
};
function inferredHelp(element){
    const label=element.getAttribute('aria-label')||element.labels?.[0]?.textContent?.trim()||element.textContent?.trim()||element.getAttribute('placeholder')||element.id||'This control';
    const view=element.dataset?.view;
    const words=(element.textContent||'').trim().toLowerCase();
    if(element.closest?.('#loginForm'))return {what:'Checks your key and signs in to Chit.',example:'Enter your key, then choose Continue.',best:'Use the key given by the server owner.',recommended:'Sign in only on the trusted Chit page.',risk:'Your key can allow changes to Chit. Never share it.'};
    if(words==='continue conversation')return {what:'Opens this saved chat so you can keep talking in the same context.',example:'Choose it on the conversation you want to reopen.',best:'Start a new chat for a new topic.',recommended:'Review the conversation title before opening.',risk:'New messages will be added to this saved conversation.'};
    if(words==='delete'||words==='remove lesson')return {what:'Removes the selected saved conversation or lesson.',example:'Choose only after confirming you no longer need it.',best:'Review the item before removing it.',recommended:'Keep it if you are unsure.',risk:'This removes saved information and may not be undoable.'};
    if(words==='use in chat'||words==='use')return {what:'Copies this fact into the Chat message box so you can ask Chit about it.',example:'Choose Use, then add a question about the fact.',best:'Check the inserted text before sending it.',recommended:'Use when you want to discuss this fact now.',risk:'The fact is added to your draft; it is not sent until you choose Send.'};
    if(words==='copy')return {what:'Copies Chit’s reply to your clipboard.',example:'Choose Copy, then paste the text where you need it.',best:'Review the answer before sharing it.',recommended:'Use when you want to reuse the reply.',risk:'Copied text may contain mistakes; check it before sharing.'};
    if(words==='try another answer')return {what:'Asks Chit to answer your latest message again.',example:'Choose after a reply missed your intent.',best:'Make your original prompt clearer if the next reply is also wrong.',recommended:'Try once after checking the prompt.',risk:'This sends another request and uses compute.'};
    const navInfo={chat:{what:'Opens the conversation screen where you can talk with Chit.',example:'Choose Chat to ask a question and continue the conversation.',best:'Use one conversation for one topic.',recommended:'Start here for normal use.',risk:'Replies can be wrong; check important facts.'},conversations:{what:'Opens your saved conversation list.',example:'Choose one to continue it or remove it.',best:'Use this when you need to return to an earlier topic.',recommended:'No setting needed.',risk:'Deleting a conversation removes its saved messages.'},generate:{what:'Opens the one-time answer screen.',example:'Ask for one answer without saving a conversation.',best:'Use Chat for a back-and-forth exchange.',recommended:'Use the default response settings.',risk:'Long answers take longer and may be less focused.'},brain:{what:'Opens saved memories and lesson progress.',example:'Search for a memory or review learning counts.',best:'Use memory for facts Chit should recall now.',recommended:'No setting needed.',risk:'Deleting a memory removes it from recall.'},teach:{what:'Opens the lesson form for information Chit may learn later.',example:'Save one checked fact or question and answer.',best:'Keep lessons accurate and focused.',recommended:'Use a short, clear lesson.',risk:'Lessons affect the model only after training.'},studio:{what:'Opens learning plans and training progress.',example:'Choose a plan, read its settings, then start learning.',best:'Inspect data before training.',recommended:'Use the everyday assistant plan when available.',risk:'Training uses compute and may take time.'},data:{what:'Opens the training file inspection screen.',example:'Check that the plan has enough training text.',best:'Preview a file split before writing it.',recommended:'No setting needed.',risk:'Creating a split changes files used by future training.'},diagnostics:{what:'Opens checks for the server, model, tokenizer, data, and recent training.',example:'Use after a reply looks unreadable or unexpected.',best:'Run checks, then try the simple sample prompt.',recommended:'Choose the same plan that produced the problem.',risk:'Checks cannot guarantee that a model will answer correctly.'},explorer:{what:'Opens the plain-language API reference and optional technical editor.',example:'Choose a topic to see what it does and what it needs.',best:'Use the guided screens for normal tasks.',recommended:'Only open the request editor if you understand the selected route.',risk:'Advanced requests can change data or start work.'}};
    if(navInfo[view])return navInfo[view];
    const isButton=element.tagName==='BUTTON';const text=(element.textContent||'').trim().toLowerCase();
    const risk=/delete|remove|stop|cancel|create|start|save|send|train|split|replace|logout|lock/.test(text)?'This action may change saved information, start work, or stop a job. Read the confirmation before continuing.':'This control does not change saved information by itself.';
    const value=element.value||element.getAttribute('placeholder')||element.querySelector('option:checked')?.textContent||'the suggested value';
    return {what:isButton?`Uses the “${label}” action.`:`Sets or provides ${label.toLowerCase()}.`,example:isButton?`Choose “${label}” when you want to do that action.`:`For example, use “${value}”.`,best:'Read the nearby explanation and use the simplest value that fits your goal.',recommended:isButton?'Choose this only when you are ready for the action.':`Start with ${value}.`,risk};
}
let helpReturnFocus=null;
function showContextHelp(element){
    const panel=$('#contextHelpPanel'),content=$('#contextHelpContent');if(!panel||!content)return;
    if(helpReturnFocus?.setAttribute)helpReturnFocus.setAttribute('aria-expanded','false');
    helpReturnFocus=document.activeElement;
    if(helpReturnFocus?.setAttribute)helpReturnFocus.setAttribute('aria-expanded','true');
    const info=controlHelp[element.id]||element._helpInfo||inferredHelp(element);
    const label=element._helpLabel||element.getAttribute('aria-label')||element.labels?.[0]?.textContent?.trim()||element.textContent?.trim()||element.id||'Help';
    $('#contextHelpTitle').textContent=label.replace(/ⓘ/g,'').trim();content.replaceChildren();
    [['What it does',info.what],['Example',info.example],['Best way to use it',info.best],['Recommended starting point',info.recommended],['Risks and things to know',info.risk]].forEach(([heading,value])=>{const section=document.createElement('section');const title=document.createElement('h3');title.textContent=heading;const text=document.createElement('p');text.textContent=value;section.append(title,text);content.appendChild(section)});
    panel.classList.remove('hidden');$('#closeContextHelp').focus();
}
function addHelpTrigger(element){
    if(element.dataset.helpDecorated||element.id==='closeContextHelp'||element.classList.contains('help-trigger'))return;
    if(element.matches('input[type="hidden"]'))return;
    const info=controlHelp[element.id]||element._helpInfo||inferredHelp(element);
    element._helpInfo=info;element._helpLabel=element.labels?.[0]?.textContent?.trim()||element.getAttribute('aria-label')||element.textContent?.trim()||element.placeholder||element.id||'Help';
    element.dataset.helpDecorated='true';
    element.title=info.what;
    if(element.classList.contains('endpoint'))return;
    if(element.matches('.nav button[data-view]')){
        const trigger=document.createElement('button');trigger.type='button';trigger.className='help-trigger';trigger.textContent='i';trigger.setAttribute('aria-label',`Help: ${element._helpLabel}`);trigger.setAttribute('aria-controls','contextHelpPanel');
        trigger.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();showContextHelp(element)});element.insertAdjacentElement('afterend',trigger);return;
    }
    if(element.matches('input,textarea,select')){
        const label=element.labels?.[0];
        if(label){const trigger=document.createElement('span');trigger.className='help-trigger';trigger.textContent='i';trigger.setAttribute('role','button');trigger.setAttribute('tabindex','0');trigger.setAttribute('aria-label',`Help: ${element._helpLabel}`);trigger.setAttribute('aria-controls','contextHelpPanel');const open=event=>{event.preventDefault();event.stopPropagation();showContextHelp(element)};trigger.addEventListener('click',open);trigger.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){open(event)}});label.appendChild(trigger)}
        else{const trigger=document.createElement('button');trigger.type='button';trigger.className='help-trigger';trigger.textContent='i';trigger.setAttribute('aria-label',`Help: ${element._helpLabel}`);trigger.setAttribute('aria-controls','contextHelpPanel');trigger.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();showContextHelp(element)});element.insertAdjacentElement('afterend',trigger)}
    }else if(element.tagName==='SUMMARY'){const trigger=document.createElement('span');trigger.className='help-trigger';trigger.textContent='i';trigger.setAttribute('role','button');trigger.setAttribute('tabindex','0');trigger.setAttribute('aria-label',`Help: ${element._helpLabel}`);trigger.setAttribute('aria-controls','contextHelpPanel');const open=event=>{event.preventDefault();event.stopPropagation();showContextHelp(element)};trigger.addEventListener('click',open);trigger.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){open(event)}});element.appendChild(trigger)}
    else{const trigger=document.createElement('button');trigger.type='button';trigger.className='help-trigger';trigger.textContent='i';trigger.setAttribute('aria-label',`Help: ${element._helpLabel}`);trigger.setAttribute('aria-controls','contextHelpPanel');trigger.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();showContextHelp(element)});element.insertAdjacentElement('afterend',trigger)}
}
function decorateHelp(root=document){root.querySelectorAll('button:not(.help-trigger),input,textarea,select,summary').forEach(addHelpTrigger)}
async function req(path,options={}){const r=await fetch(BASE+path,{credentials:'same-origin',...options});let data=null;const txt=await r.text();try{data=txt?JSON.parse(txt):null}catch{data=txt}if(r.status===401&&path!='/_ui/login'){lock();throw new Error('Console session expired. Enter the API key again.')}return {ok:r.ok,status:r.status,data}}
function pretty(x){return typeof x==='string'?x:JSON.stringify(x,null,2)}
function safeMarkdown(value){let html=String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');html=html.replace(/```([\s\S]*?)```/g,'<pre><code>$1</code></pre>').replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>').replace(/\n/g,'<br>');return html}
function friendlyError(data,status){let detail=data?.detail??data;let message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(x=>x.msg||String(x)).join('; '):detail?.message||'';if(status===409)return 'Chit is busy studying right now. Wait for the current learning session to finish, then try again.';if(status===403)return 'This feature is not enabled for this Chit server. Ask its administrator to enable learning tools.';if(status===404)return message.includes('source')?'That file is not in the server’s training library. Check its name and try again.':'We could not find that item. Refresh the page and try again.';if(status===422)return message||'Some information is missing or outside the allowed range. Review the highlighted fields.';if(status>=500)return 'The server could not complete that request. Please try again in a moment.';return message||`Something went wrong (status ${status}).`}
function setLogin(auth){$('#loginOverlay').classList.toggle('hidden',auth);$('#logout').classList.toggle('hidden',!auth)}
function showError(el,e){el.textContent=e.message||String(e);el.classList.add('error')}
async function lock(){authenticated=false;setLogin(false);$('#connection').textContent='Sign in required · session expired or UI server restarted';$('#apiKey').value='';chatId=null;$('#chatSession').textContent='';$('#chatlog').replaceChildren();$('#sessionList').textContent='Sign in to load conversations.';$('#knowledgeList').replaceChildren();$('#memoryGrid').textContent='Sign in to search saved memories.';$('#diagnosticResponse').textContent='The response will appear here.';lastResponseEvidence=null;renderDiagnosticEvidence()}
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

// Refresh only the status used by the visible screen; pause while the tab is hidden.
let pollingTimer=null;
function scheduleUiRefresh(delay=30000){
    clearTimeout(pollingTimer);
    pollingTimer=setTimeout(async()=>{
        if(authenticated&&!document.hidden){
            const activeView=document.querySelector('.view:not(.hidden)')?.id;
            if(activeView==='view-brain')await updateKnowledgePipeline();
            if(activeView==='view-studio'||activeView==='view-diagnostics')await updateNeuralOrb();
        }
        scheduleUiRefresh(30000);
    },delay);
}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)scheduleUiRefresh(0)});
scheduleUiRefresh();

$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();const status=$('#loginStatus');status.textContent='Checking…';status.classList.remove('error');const key=$('#apiKey').value;try{const r=await req('/_ui/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:key})});$('#apiKey').value='';if(!r.ok)throw new Error(r.data?.detail||'Could not sign in.');authenticated=true;setLogin(true);status.textContent='';$('#connection').textContent='Key held for this browser session';await refreshHealth();await loadWorkspace()}catch(err){status.textContent=err.message;status.classList.add('error')}});
$('#logout').addEventListener('click',async()=>{try{await req('/_ui/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}finally{authenticated=false;await lock();$('#connection').textContent='Signed out'}});
async function callApi(method,path,query,body){const r=await req('/_ui/proxy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,path,query,body})});if(!r.ok)r.friendly=friendlyError(r.data,r.status);return r}
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

function learningPlanName(name){
    const names={chit_assistant_cpu:'Everyday assistant',chit_cpu_learning:'Compact learning',chit_english_foundation:'English foundations',chit_english_mixed:'Mixed English practice',chit_strong:'Extended study',chit_tiny:'Small and quick',chit_train_txt:'Text-file practice',chit_bpe_experiment:'Tokenizer experiment',chit_byte_experiment:'Byte-token experiment',chit_rope_512_candidate:'Long-context candidate',chit_rope_512_rescue:'Long-context recovery'};
    return names[name]||name.replaceAll('_',' ').replace(/^chit /,'');
}

async function renderRecipes(){
    const select=$('#trainConfig');select.replaceChildren();
    const r=await req('/_ui/train/configs');
    if(!r.ok){select.innerHTML='<option value="">Learning plans unavailable</option>';$('#configHelp').textContent='Could not load learning plans. '+friendlyError(r.data,r.status);return}
    const configs=r.data.configs||[];
    if(!configs.length){select.innerHTML='<option value="">No learning plans are available</option>';return}
    configs.forEach(name=>{const option=document.createElement('option');option.value=name;option.textContent=learningPlanName(name);select.appendChild(option)});
    const preferred=configs.includes(window.selectedRecipe)?window.selectedRecipe:configs.includes('chit_assistant_cpu')?'chit_assistant_cpu':configs[0];
    select.value=preferred;window.selectedRecipe=preferred;
    select.onchange=()=>{window.selectedRecipe=select.value;const dataRecipe=$('#dataConfig');if(dataRecipe)dataRecipe.value=select.value;const diagnosticRecipe=$('#diagnosticConfig');if(diagnosticRecipe)diagnosticRecipe.value=select.value;showConfigDetails(select.value)};
    await showConfigDetails(preferred);
}

function configField(label,value){const row=document.createElement('div');row.className='config-fact';const term=document.createElement('b');term.textContent=label;const detail=document.createElement('span');detail.textContent=String(value);row.append(term,detail);return row}

async function showConfigDetails(name){
    const panel=$('#configHelp');panel.textContent='Loading this learning plan…';
    const [r,active]=await Promise.all([req(`/_ui/train/configs/${encodeURIComponent(name)}`),callApi('GET','/model',{},null)]);
    if(!r.ok){panel.textContent=friendlyError(r.data,r.status);return}
    const cfg=r.data.config||{},model=cfg.model||{},training=cfg.training||{},data=cfg.data||{},tokenizer=cfg.tokenizer||{};
    const byteTokenizer=(tokenizer.name||'byte-utf8')==='byte-utf8';
    const intro=document.createElement('p');intro.textContent=name==='chit_assistant_cpu'?'A general-purpose assistant plan. Check its example data and settings before you train.':name.includes('foundation')||name.includes('mixed')?'An English-focused plan that studies one or more text collections.':name.includes('experiment')?'An experimental plan for comparing how Chit reads text.':'A prepared plan with set model size, study schedule, and training material.';
    const facts=document.createElement('div');facts.className='config-facts';
    facts.append(configField('Training updates',`${training.max_steps??'Not set'} steps. Each step updates the model once; more steps take longer.`));
    facts.append(configField(byteTokenizer?'Context window (bytes)':'Context window (tokens)',`${model.block_size??'Not set'} ${byteTokenizer?'bytes':'tokens'} at a time. A longer window uses more memory and compute.`));
    facts.append(configField('Model size',`${model.n_layer??'Not set'} layers · ${model.n_head??'Not set'} attention heads · ${model.n_embd??'Not set'} internal width. Larger values need more memory.`));
    facts.append(configField('Training device',cfg.device||'Chosen automatically by the server'));
    if(training.batch_size)facts.append(configField('Examples per update',`${training.batch_size}. Larger batches use more memory.`));
    if(training.learning_rate)facts.append(configField('Learning rate',`${training.learning_rate}. This controls the size of each learning update; a value that is too high can make training unstable.`));
    if(training.eval_interval)facts.append(configField('Progress checks',`The server checks learning quality every ${training.eval_interval} updates.`));
    const sources=Array.isArray(data.sources)?data.sources:[];
    if(sources.length){const weightTotal=sources.reduce((sum,source)=>sum+Math.max(0,Number(source.weight)||0),0);facts.append(configField('Weighted text collections',sources.map(source=>{const weight=Math.max(0,Number(source.weight)||0),share=weightTotal?Math.round(weight/weightTotal*100):0;return `${String(source.path||'Unnamed file').split(/[\\/]/).pop()} · about ${share}% of sampled text`}).join(' · ')))}
    else{if(data.train_file)facts.append(configField('Training text',String(data.train_file).split(/[\\/]/).pop()));if(data.eval_file)facts.append(configField('Review text',String(data.eval_file).split(/[\\/]/).pop()))}
    const tokenizerName=tokenizer.name||'byte-utf8 (default)';facts.append(configField('Text reader',tokenizerName==='byte-utf8'?'Reads UTF-8 one byte at a time. The context value above is therefore bytes.':tokenizerName==='bpe-tokenizers-json-v1'?'Uses a saved vocabulary to read common pieces of text together.':'Uses '+tokenizerName));
    if(tokenizer.sha256)facts.append(configField('Tokenizer fingerprint',`${tokenizer.sha256.slice(0,16)}… · identifies the vocabulary this plan expects.`));
    if(tokenizer.vocab_size)facts.append(configField('Vocabulary size',`${tokenizer.vocab_size} text pieces`));
    if(cfg.seed!==undefined)facts.append(configField('Repeatable setup',`Seed ${cfg.seed} makes random choices easier to reproduce.`));
    if(active.ok){const actual=active.data.tokenizer?.name,expected=tokenizer.name||'byte-utf8';facts.append(configField('Currently active reader',actual?`${actual}${expected===actual?' · matches this plan':` · this plan expects ${expected}`}`:'Not reported · the UI cannot confirm a match'))}
    const note=document.createElement('p');note.className='notice';note.textContent='This is what the selected plan will ask the training system to use. Training creates a candidate model; Chit keeps serving the current model until training succeeds and the candidate is promoted. Check the Training library for missing or short files first.';
    panel.replaceChildren();const heading=document.createElement('h3');heading.textContent=learningPlanName(name);panel.append(heading,intro,facts,note);
}

async function renderJobs() {
    const r = await req('/_ui/train/jobs');
    const list = $('#jobList');
    if (!r.ok) {
        list.textContent = 'Could not load learning history. ' + friendlyError(r.data, r.status);
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
        const narratives={queued:'Getting ready to learn',running:'Studying the training material',succeeded:'Learning complete',failed:'Learning stopped with a problem',cancelled:'Learning session stopped'};
        state.textContent = narratives[job.state] || 'Status unavailable';
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
        step.textContent = job.state==='running'?`Learning progress · step ${job.step ?? 0} of ${job.max_steps ?? '—'}`:job.state==='succeeded'?'Chit finished this learning session':`Progress · step ${job.step ?? 0} of ${job.max_steps ?? '—'}`;
        const loss = document.createElement('span');
        loss.textContent = `Loss: ${Number.isFinite(job.latest?.eval_loss) ? job.latest.eval_loss.toFixed(4) : 'N/A'}`;
        meta.append(step, loss);
        card.append(header, progress, meta);
        if(['queued','running'].includes(job.state)){
            const cancel=document.createElement('button');cancel.type='button';cancel.className='danger';cancel.textContent='Stop this learning session';
            cancel.addEventListener('click',async()=>{if(!confirm('Ask Chit to stop this learning session? Work already completed remains saved.'))return;const result=await callApi('POST',`/train/${encodeURIComponent(job.id)}/cancel`,{},null);if(result.ok){cancel.textContent='Stop requested';renderJobs()}else alert(friendlyError(result.data,result.status))});
            card.appendChild(cancel);
        }
        list.appendChild(card);
    });
}

$('#startTrain').addEventListener('click', async () => {
    window.selectedRecipe=$('#trainConfig').value;
    if (!window.selectedRecipe) {
        alert('Choose a learning plan first.');
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
        if (!r.ok) throw new Error(friendlyError(r.data, r.status));
        status.textContent = 'Chit has started learning. You can follow progress below.';
        await renderJobs();
    } catch (e) {
        status.textContent = e.message;
        status.classList.add('error');
    }
});

async function loadWorkspace(){
    await Promise.all([renderRecipes(), renderJobs(), updateKnowledgePipeline(), updateNeuralOrb(), loadModelSummary(), loadConversations(), loadKnowledge()]);
    populateDataConfigs();
}

async function loadModelSummary(){
    const box=$('#modelStatus');
    if(!box)return;
    box.textContent='Checking Chit’s current state…';
    try{
        const [health,ready,model]=await Promise.all([callApi('GET','/health',{},null),callApi('GET','/ready',{},null),callApi('GET','/model',{},null)]);
        if(!health.ok){box.textContent=friendlyError(health.data,health.status);return}
        const status=document.createElement('p');
        status.className='notice';
        status.textContent=health.data.status==='ok'?(ready.ok&&ready.data.status==='ready'?'Chit is ready for conversations and learning.':'Chit is ready for conversations. Some learning services may be unavailable.'):health.data.status==='no_model'?'The server is online, but no trained brain is loaded yet. Choose a learning recipe in Studio to get started.':'Chit is currently unavailable.';
        box.replaceChildren(status);
        if(model.ok){
            const details=document.createElement('p');details.className='status';
            const config=model.data.model_config||{};
            details.textContent=`Current brain · ${config.n_layer??'—'} layers · ${model.data.parameters?.toLocaleString?.()??'—'} learned settings · ${model.data.device||'device not reported'}`;
            box.appendChild(details);
        }
    }catch(e){box.textContent=e.message}
}

async function loadConversations(){
    const box=$('#sessionList');if(!box)return;
    box.textContent='Loading conversations…';
    try{
        const r=await callApi('GET','/sessions',{},null);
        if(!r.ok)throw new Error(r.friendly);
        const rows=Array.isArray(r.data)?r.data:r.data.sessions||[];
        box.replaceChildren();
        if(!rows.length){box.textContent='No saved conversations yet. Start a chat and Chit will keep its context here.';return}
        rows.forEach(session=>{
            const card=document.createElement('article');card.className='memory-card';
            const title=document.createElement('h3');title.textContent=session.summary||session.title||'Conversation';
            const meta=document.createElement('p');meta.className='status';meta.textContent=`${session.message_count??session.messages?.length??0} messages · ${session.updated_at||session.created_at||''}`;
            const actions=document.createElement('div');actions.className='actions';
            const open=document.createElement('button');open.className='primary';open.textContent='Continue conversation';open.addEventListener('click',()=>openConversation(session.id));
            const remove=document.createElement('button');remove.className='danger';remove.textContent='Delete';remove.addEventListener('click',()=>deleteConversation(session.id));
            actions.append(open,remove);card.append(title,meta,actions);box.appendChild(card);
        });
    }catch(e){box.textContent=e.message}
}

async function openConversation(id){
    const r=await callApi('GET',`/sessions/${encodeURIComponent(id)}`,{limit:100},null);
    if(!r.ok){$('#sessionStatus').textContent=friendlyError(r.data,r.status);return}
    chatId=id;$('#chatlog').replaceChildren();
    (r.data.messages||[]).forEach(message=>addBubble(message.role==='assistant'?'chit':message.role==='user'?'user':'system',message.content||message.text||''));
    $('#chatSession').textContent=r.data.summary||`Session ${id}`;
    document.querySelector('[data-view="chat"]').click();
}

async function deleteConversation(id){
    if(!confirm('Delete this conversation and its saved messages?'))return;
    const r=await callApi('DELETE',`/sessions/${encodeURIComponent(id)}`,{},null);
    $('#sessionStatus').textContent=r.ok?'Conversation deleted.':friendlyError(r.data,r.status);
    if(r.ok){if(chatId===id){chatId=null;$('#chatlog').replaceChildren();$('#chatSession').textContent=''}loadConversations()}
}

function lessonPayload(){
    const kind=$('#lessonKind').value;
    const item={kind,source:$('#lessonSource').value.trim()||null,remember:$('#rememberLesson').checked};
    if(kind==='text')item.text=$('#lessonText').value.trim();
    else{item.question=$('#lessonQuestion').value.trim();item.answer=$('#lessonAnswer').value.trim()}
    return item;
}

async function saveLesson(){
    const item=lessonPayload();const status=$('#lessonStatus');status.textContent='Saving lesson…';
    if((item.kind==='text'&&!item.text)||(item.kind==='qa'&&(!item.question||!item.answer))){status.textContent='Fill in the lesson before saving it.';return}
    const r=await callApi('POST','/knowledge',{}, {items:[item]});
    status.textContent=r.ok?(r.data.duplicates?'That lesson is already saved.':'Lesson saved. Train Chit when you’re ready for it to learn this material.'):friendlyError(r.data,r.status);
    if(r.ok){$('#lessonText').value='';$('#lessonQuestion').value='';$('#lessonAnswer').value='';loadKnowledge();updateKnowledgePipeline()}
}

async function loadKnowledge(){
    const box=$('#knowledgeList');if(!box)return;
    box.textContent='Loading saved lessons…';
    const selected=$('#knowledgeFilter')?.value||'pending';
    const query={limit:100};if(selected!=='all')query.status=selected;
    const r=await callApi('GET','/knowledge',query,null);
    if(!r.ok){box.textContent=friendlyError(r.data,r.status);return}
    box.replaceChildren();
    if(!r.data.items?.length){box.textContent=selected==='pending'?'No lessons are waiting to be learned yet.':'No lessons in this view.';return}
    r.data.items.forEach(entry=>{
        const card=document.createElement('article');card.className='memory-card';
        const payload=entry.payload||{};const heading=document.createElement('h3');heading.textContent=entry.kind==='qa'?payload.question:entry.kind==='reasoning'?payload.input:(payload.text||'Lesson');
        const content=document.createElement('p');content.className='memory-content';content.textContent=entry.kind==='qa'?payload.answer:entry.kind==='reasoning'?payload.answer:payload.text;
        const meta=document.createElement('p');meta.className='status';meta.textContent=`${entry.status==='trained'?'Already learned':'Ready to learn'}${entry.source?` · ${entry.source}`:''}`;
        const actions=document.createElement('div');actions.className='actions';
        const use=document.createElement('button');use.className='secondary';use.textContent='Use in chat';use.addEventListener('click',()=>{useMemory(`${heading.textContent}\n${content.textContent}`);document.querySelector('[data-view="chat"]').click()});
        const del=document.createElement('button');del.className='danger';del.textContent='Remove lesson';del.addEventListener('click',async()=>{if(!confirm('Remove this lesson from future training?'))return;const result=await callApi('DELETE',`/knowledge/${encodeURIComponent(entry.id)}`,{},null);if(result.ok){loadKnowledge();updateKnowledgePipeline()}else alert(friendlyError(result.data,result.status))});
        actions.append(use,del);card.append(heading,content,meta,actions);box.appendChild(card);
    });
}

async function populateDataConfigs(){
    const select=$('#dataConfig'),diagnostic=$('#diagnosticConfig');if(!select)return;
    const r=await callApi('GET','/train/configs',{},null);if(!r.ok)return;
    for(const target of [select,diagnostic].filter(Boolean)){target.replaceChildren();(r.data.configs||[]).forEach(config=>{const option=document.createElement('option');option.value=config;option.textContent=learningPlanName(config);target.appendChild(option)})}
    if(window.selectedRecipe){select.value=window.selectedRecipe;if(diagnostic)diagnostic.value=window.selectedRecipe}
}

async function inspectTrainingData(splitPreview=false,writeSplit=false){
    const status=$('#dataStatus'),out=$('#dataResult'),config=$('#dataConfig').value;status.textContent=splitPreview?'Checking split preview…':'Inspecting training material…';
    let method='GET',path='/data',query={config},body=null;
    if(splitPreview||writeSplit){const source=$('#dataSource').value.trim();if(!source){status.textContent='Enter the name of a text file in the server’s training library.';return}method='POST';path='/data/split';query={};body={source,config,by:'paragraph',eval_fraction:.1,dry_run:!writeSplit,overwrite:$('#overwriteSplit').checked};if(writeSplit&&!confirm('Create new training and review files from this text? Existing files will be replaced only if you chose that option.'))return}
    const r=await callApi(method,path,query,body);if(!r.ok){status.textContent=friendlyError(r.data,r.status);return}
    status.textContent=writeSplit?'Training and review files created.':splitPreview?'Preview ready. No files were changed.':'Training material inspected.';out.textContent=pretty(r.data);
}

async function trainSavedKnowledge(){
    const status=$('#trainStatus');status.textContent='Preparing a lesson-based learning session…';
    const body={config:$('#trainConfig')?.value||window.selectedRecipe||'chit_cpu_learning',select:$('#lessonScope').value,init:'auto'};
    const r=await callApi('POST','/knowledge/train',{},body);
    status.textContent=r.ok?'Chit has started learning your saved lessons. Follow progress below.':friendlyError(r.data,r.status);
    if(r.ok)renderJobs();
}

$('#lessonKind').addEventListener('change',()=>{const qa=$('#lessonKind').value==='qa';$('#lessonTextField').classList.toggle('hidden',qa);$('#lessonQaFields').classList.toggle('hidden',!qa)});
$('#saveLesson').addEventListener('click',saveLesson);
$('#refreshKnowledge').addEventListener('click',loadKnowledge);
$('#knowledgeFilter').addEventListener('change',loadKnowledge);
$('#refreshSessions').addEventListener('click',loadConversations);
$('#inspectData').addEventListener('click',()=>inspectTrainingData(false));
$('#previewSplit').addEventListener('click',()=>inspectTrainingData(true));
$('#applySplit').addEventListener('click',()=>inspectTrainingData(false,true));
$('#refreshModel').addEventListener('click',loadModelSummary);
$('#trainKnowledge').addEventListener('click',trainSavedKnowledge);
$('#saveMemory').addEventListener('click',async()=>{const content=$('#newMemory').value.trim(),status=$('#memorySaveStatus');if(!content){status.textContent='Write the memory first.';return}status.textContent='Saving…';const r=await callApi('POST','/memory',{}, {content,memory_type:$('#memoryType').value,importance:Number($('#memoryImportance').value),tags:[]});status.textContent=r.ok?'Memory saved. Chit can use it in conversations now.':friendlyError(r.data,r.status);if(r.ok){$('#newMemory').value='';if($('#memSearch').value.trim())$('#doMemSearch').click()}});

function addDiagnosticCheck(container,title,state,explanation){const card=document.createElement('article');card.className=`diagnostic-check check-${state}`;const heading=document.createElement('h3');heading.textContent=title;const badge=document.createElement('span');badge.className='check-badge';badge.textContent=state==='good'?'Looks good':state==='issue'?'Needs attention':'Could not check';const copy=document.createElement('p');copy.textContent=explanation;card.append(heading,badge,copy);container.appendChild(card)}

let lastResponseEvidence=null;
function addEvidenceItem(container,label,value){const item=document.createElement('div');item.className='evidence-item';const name=document.createElement('b');name.textContent=label;const detail=document.createElement('span');detail.textContent=value;item.append(name,detail);container.appendChild(item)}
function renderDiagnosticEvidence(serverEvidence={}){
    const box=$('#diagnosticEvidence');if(!box)return;box.replaceChildren();
    Object.entries(serverEvidence).forEach(([label,value])=>addEvidenceItem(box,label,value));
    if(lastResponseEvidence){
        addEvidenceItem(box,'Last reply',`${lastResponseEvidence.mode} · ${lastResponseEvidence.promptBytes} UTF-8 bytes in the prompt`);
        addEvidenceItem(box,'Generation settings',`${lastResponseEvidence.tokens} max response tokens · temperature ${lastResponseEvidence.temperature} · top-k ${lastResponseEvidence.topK}`);
        addEvidenceItem(box,'Conversation context',lastResponseEvidence.continued?'Continued a saved conversation':'Started without earlier chat messages');
        addEvidenceItem(box,'Memory recall',lastResponseEvidence.memoryCount===null?'The reply did not report memory use':`${lastResponseEvidence.memoryCount} saved ${lastResponseEvidence.memoryCount===1?'memory':'memories'} reported`);
        const metadata=lastResponseEvidence.metadata||{};
        const truncation=metadata.truncated??metadata.context_truncated;
        addEvidenceItem(box,'Context limit',truncation===true?'The server reported that some context was cut off.':truncation===false?'The server reported no context cut off.':'The API did not report whether context was cut off.');
        if(metadata.stop_reason)addEvidenceItem(box,'Why generation stopped',String(metadata.stop_reason));
    }else addEvidenceItem(box,'Last reply','No reply has been generated in this page yet.');
}
function recordResponseEvidence({mode,prompt,tokens,temperature,topK,continued=false,response={}}){
    const metadata=response.metadata||{};
    lastResponseEvidence={mode,promptBytes:new TextEncoder().encode(prompt||'').length,tokens,temperature,topK,continued,memoryCount:Array.isArray(metadata.memory_ids)?metadata.memory_ids.length:null,metadata};
    renderDiagnosticEvidence();
}

async function runDiagnostics(){
    const status=$('#diagnosticStatus'),results=$('#diagnosticResults'),advice=$('#diagnosticAdvice'),configName=$('#diagnosticConfig').value,evidence={};
    status.textContent='Checking Chit…';results.textContent='Reading server and model status…';advice.classList.add('hidden');
    try{
        const [health,ready,model,data,jobs,preset]=await Promise.all([
            callApi('GET','/health',{},null),callApi('GET','/ready',{},null),callApi('GET','/model',{},null),
            callApi('GET','/data',{config:configName},null),callApi('GET','/train',{},null),
            req(`/_ui/train/configs/${encodeURIComponent(configName)}`)
        ]);
        results.replaceChildren();const recommendations=[];
        if(!health.ok){addDiagnosticCheck(results,'Server connection','issue',friendlyError(health.data,health.status));recommendations.push('Reconnect to the Chit server or ask its administrator to check the server logs.')}
        else if(health.data.status==='no_model'){addDiagnosticCheck(results,'Active brain','issue','The server is responding, but it has no trained model loaded.');recommendations.push('Open Studio, choose a suitable learning plan, and complete a training run.');}
        else addDiagnosticCheck(results,'Server and active brain','good','The server is responding and a model is loaded.');
        if(health.ok){evidence['Server state']=String(health.data.status||'not reported');if(health.data.training_job)evidence['Active training job']='A training job is running';const queue=health.data.inference||health.data.inference_queue;if(queue&&typeof queue==='object'){const queueLength=queue.queue_length??queue.queued??queue.pending;if(queueLength!==undefined)evidence['Inference queue']=`${queueLength} waiting request(s)`;if(queue.max_queue_size!==undefined)evidence['Queue limit']=`${queue.max_queue_size} waiting request(s)`}}
        if(!ready.ok&&!ready.data?.checks)addDiagnosticCheck(results,'Service readiness','unknown',friendlyError(ready.data,ready.status));
        else if(ready.data.status!=='ready'){const failing=Object.entries(ready.data.checks||{}).filter(([,value])=>!value).map(([key])=>key);addDiagnosticCheck(results,'Supporting services','issue',`Some services are not ready${failing.length?`: ${failing.join(', ')}`:''}.`);recommendations.push('Wait for startup to finish. If the same service stays unavailable, ask the administrator to inspect the server health details.');}
        else addDiagnosticCheck(results,'Supporting services','good','Model, memory, knowledge, and request handling report ready.');
        if(model.ok){const tokenizer=model.data.tokenizer?.name;const block=model.data.model_config?.block_size;const unit=tokenizer==='byte-utf8'?'bytes':tokenizer?'tokens':'units not reported';addDiagnosticCheck(results,'Active model settings',tokenizer?'good':'unknown',`Text reader: ${tokenizer||'not reported'}. Context window: ${block??'not reported'} ${unit}. A tokenizer or checkpoint mismatch can make generated text look corrupted.`);evidence['Active text reader']=tokenizer||'Not reported';evidence['Active context window']=`${block??'not reported'} ${unit}`;evidence['Active device']=String(model.data.device||'not reported');if(model.data.checkpoint)evidence['Active checkpoint']=String(model.data.checkpoint);if(model.data.parameters!==undefined)evidence['Model parameters']=Number(model.data.parameters).toLocaleString()}
        else{addDiagnosticCheck(results,'Active model settings','unknown',friendlyError(model.data,model.status));recommendations.push('Confirm that a compatible trained checkpoint and tokenizer are installed and selected by the server.')}
        if(data.ok){const warnings=data.data.warnings||[];if(data.data.ready_to_train===false||warnings.length){addDiagnosticCheck(results,'Training material','issue',warnings.length?warnings.join(' '):'The selected plan is not ready to train.');recommendations.push('Open Training library, inspect this plan’s files, and resolve missing or too-small data warnings before retraining.')}else addDiagnosticCheck(results,'Training material','good',`The selected plan’s files pass the server’s readiness checks${data.data.train?.items?` (${data.data.train.items} training items)` : ''}.`)}
        else addDiagnosticCheck(results,'Training material','unknown',friendlyError(data.data,data.status));
        if(jobs.ok){const allJobs=jobs.data.jobs||[],active=allJobs.find(job=>['queued','running'].includes(job.state)),failed=allJobs.find(job=>job.state==='failed'),latest=allJobs[0];if(active){addDiagnosticCheck(results,'Recent learning activity','unknown',`A learning session is ${active.state}. Wait until it finishes before judging the newly trained brain.`);if(active.step!==undefined)evidence['Current training progress']=`${active.step} of ${active.max_steps??'unknown'} steps`;}else if(failed){addDiagnosticCheck(results,'Recent learning activity','issue','The latest available learning session failed.');recommendations.push('Open Studio and review the failed session details before trying again.')}else addDiagnosticCheck(results,'Recent learning activity','good','No active or failed recent learning session was reported.');if(latest?.latest?.eval_loss!==undefined)evidence['Latest review loss']=String(latest.latest.eval_loss);if(latest?.promoted!==undefined)evidence['Latest candidate promotion']=latest.promoted?'The candidate became the live model':'The candidate was not promoted'}
        else addDiagnosticCheck(results,'Recent learning activity','unknown','Training history is unavailable on this server.');
        if(preset.ok&&model.ok){const expected=preset.data.config?.tokenizer?.name||'byte-utf8';const actual=model.data.tokenizer?.name;if(actual&&expected!==actual){addDiagnosticCheck(results,'Selected plan and active text reader','issue',`The selected plan expects “${expected}”, while the active brain reports “${actual}”.`);recommendations.push('Use a checkpoint trained with the same tokenizer as its training plan. A mismatch can produce unreadable output.')}else if(actual)addDiagnosticCheck(results,'Selected plan and active text reader','good',`Both report “${actual}”.`);else addDiagnosticCheck(results,'Selected plan and active text reader','unknown','The active model did not report its tokenizer, so the UI cannot confirm whether it matches this plan.');const planSize=preset.data.config?.model?.block_size;if(planSize!==undefined)evidence['Selected plan context']=`${planSize} ${expected==='byte-utf8'?'bytes':'tokens'}`}
        if(data.ok&&data.data.train?.items!==undefined)evidence['Training examples in selected plan']=String(data.data.train.items);
        renderDiagnosticEvidence(evidence);
        status.textContent='Check complete.';
        if(recommendations.length){advice.replaceChildren();const heading=document.createElement('h3');heading.textContent='Suggested next steps';advice.appendChild(heading);const list=document.createElement('ol');recommendations.forEach(item=>{const li=document.createElement('li');li.textContent=item;list.appendChild(li)});advice.appendChild(list);advice.classList.remove('hidden')}
    }catch(error){status.textContent='Could not complete all checks.';results.textContent=error.message;renderDiagnosticEvidence(evidence)}
}

$('#runDiagnostics').addEventListener('click',runDiagnostics);
$('#diagnosticConfig').addEventListener('change',()=>{const value=$('#diagnosticConfig').value;const dataRecipe=$('#dataConfig'),trainRecipe=$('#trainConfig');if(dataRecipe)dataRecipe.value=value;if(trainRecipe){trainRecipe.value=value;window.selectedRecipe=value;showConfigDetails(value)}});
$('#dataConfig').addEventListener('change',()=>{const value=$('#dataConfig').value;const diagnosticRecipe=$('#diagnosticConfig');if(diagnosticRecipe)diagnosticRecipe.value=value});
$('#runDiagnosticPrompt').addEventListener('click',async()=>{const prompt=$('#diagnosticPrompt').value.trim(),out=$('#diagnosticResponse');if(!prompt){out.textContent='Enter a short test prompt first.';return}out.textContent='Generating one sample…';const r=await callApi('POST','/generate',{}, {prompt,mode:'assistant',tokens:100,temperature:0,top_k:1,stop:[]});out.textContent=r.ok?(r.data?.text||'The model returned no text.'):friendlyError(r.data,r.status);if(r.ok)recordResponseEvidence({mode:'Generate sample',prompt,tokens:100,temperature:0,topK:1,response:r.data})});
$('#responseReadable').addEventListener('click',()=>{const box=$('#responseFeedback');box.textContent='This sample reads clearly. If your original chat still looks wrong, check whether its prompt is ambiguous, contains conflicting instructions, or depends on information Chit has not learned.';box.classList.remove('hidden')});
$('#responseGarbled').addEventListener('click',()=>{const box=$('#responseFeedback');box.textContent='The sample is difficult to read. Run “Check Chit” and review the active model, tokenizer, and training material. If those checks pass, the current model may still need better or more relevant training; a healthy server does not guarantee strong language quality.';box.classList.remove('hidden')});
$('#openTrainingLibrary').addEventListener('click',()=>document.querySelector('[data-view="data"]').click());
$('#openStudio').addEventListener('click',()=>document.querySelector('[data-view="studio"]').click());

function showView(name,updateUrl=true){
    const target=document.querySelector(`.nav button[data-view="${CSS.escape(name)}"]`);
    if(!target)return;
    target.setAttribute('aria-controls','view-'+name);
    document.querySelectorAll('.nav button[data-view]').forEach(button=>{const active=button===target;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current')});
    document.querySelectorAll('.view').forEach(view=>view.classList.toggle('hidden',view.id!=='view-'+name));
    if(updateUrl){history.replaceState(null,'',`#${encodeURIComponent(name)}`);}
    if(authenticated){
        if(name==='brain'){updateKnowledgePipeline();loadKnowledge()}
        if(name==='studio'){renderRecipes();renderJobs()}
        if(name==='conversations')loadConversations();
        if(name==='data')populateDataConfigs();
    }
    scheduleUiRefresh(30000);
}
document.querySelectorAll('.nav button[data-view]').forEach(button=>button.addEventListener('click',()=>showView(button.dataset.view)));
const requestedView=decodeURIComponent(location.hash.replace(/^#/,''));
if(requestedView)showView(requestedView,false);



function addBubble(role, text, memoryIds = []) {
    const b = document.createElement('div');
    b.className = 'bubble ' + role;
    
    if(role==='chit')b.innerHTML=safeMarkdown(text);else b.textContent=text;

    if (role === 'chit') {
        const actions = document.createElement('div');
        actions.className = 'bubble-actions';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'action-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = async () => {try{await navigator.clipboard.writeText(text);copyBtn.textContent='Copied';setTimeout(()=>copyBtn.textContent='Copy',1800)}catch{copyBtn.textContent='Clipboard unavailable'}};
        const regenerate=document.createElement('button');regenerate.type='button';regenerate.className='action-btn';regenerate.textContent='Try another answer';regenerate.onclick=()=>{const messages=document.querySelectorAll('.bubble.user');if(messages.length){$('#chatInput').value=messages[messages.length-1].textContent;$('#sendChat').click()}};
        actions.appendChild(copyBtn);
        actions.appendChild(regenerate);
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
    const wasContinuing = Boolean(chatId);
    
    addBubble('user', message);
    box.value = '';
    $('#sendChat').disabled = true;
    
    try {
        const r = await callApi('POST', '/chat', {}, {
            message, 
            session_id: chatId, 
            temperature: 0.4
        });
        
        if (!r.ok) throw new Error(friendlyError(r.data,r.status));
        
        chatId = r.data.session_id;
        recordResponseEvidence({mode:'Chat',prompt:message,tokens:'server default',temperature:0.4,topK:'server default',continued:wasContinuing,response:r.data});
        
        $('#chatSession').textContent = chatId ? `Session ${chatId}` : 'No saved session';
        const recalled=r.data?.metadata?.memory_ids;
        if(Array.isArray(recalled)&&recalled.length){
            const breadcrumb=document.createElement('div');breadcrumb.className='memory-breadcrumb';
            breadcrumb.textContent=`Chit used ${recalled.length} saved ${recalled.length===1?'memory':'memories'} to shape this reply.`;
            $('#chatlog').appendChild(breadcrumb);
        }
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
        if (!r.ok) throw new Error(friendlyError(r.data, r.status));
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
$('#runGenerate').addEventListener('click',async()=>{const status=$('#genStatus');status.textContent='Generating…';status.classList.remove('error');try{const body={prompt:$('#genPrompt').value.trim(),mode:$('#genMode').value,tokens:Number($('#genTokens').value),temperature:Number($('#genTemp').value),top_k:Number($('#genTopK').value),stop:[]};if(!body.prompt)throw new Error('Write a prompt first.');const r=await callApi('POST','/generate',{},body);if(!r.ok)throw new Error(friendlyError(r.data,r.status));$('#genResult').textContent=typeof r.data?.text==='string'?r.data.text:pretty(r.data);recordResponseEvidence({mode:body.mode,prompt:body.prompt,tokens:body.tokens,temperature:body.temperature,topK:body.top_k,response:r.data});status.textContent='Done'}catch(e){status.textContent=e.message;status.classList.add('error')}});
const routeGuides={
'Server health':['Check whether the server and model are responding.','Nothing to enter.','Read-only. Reports whether a model is loaded and whether a training job is active.'],
'Service readiness':['Check whether the model, memory, knowledge, and inference services are ready for use.','Nothing to enter.','Read-only. Useful when the server is online but some features may still be starting.'],
'Live model details':['See which model is currently active and its main characteristics.','Nothing to enter.','Read-only. Shows the live model settings, device, and checkpoint details.'],
'Generate a response':['Ask Chit for a single response without creating a continuing conversation.','Your prompt, response length, and optional generation settings.','Read-only for saved conversations. Assistant mode may use relevant memories; continue mode extends the text you provide.'],
'Continue raw text':['Continue a piece of text from exactly where it ends.','A text prefix and response length.','Does not create a saved conversation. Useful for open-ended writing or text completion.'],
'Chat message':['Send a message in a continuing conversation.','Your message, plus an optional conversation ID to continue a previous chat.','Creates or updates a saved conversation and may use relevant memories. The reply includes a session ID so the conversation can continue.'],
'Create session':['Create an empty conversation before sending its first message.','Nothing to enter.','Creates a separate conversation with its own context. Most users can simply start chatting; Chit creates the session automatically.'],
'List sessions':['See the conversations saved for this API key.','Optional page size and starting position.','Read-only. Each result identifies a conversation and may include its summary.'],
'Read session':['Open one saved conversation and its messages.','The conversation ID and how many messages to show.','Read-only. Use the ID from the conversation list.'],
'Delete session':['Permanently remove a saved conversation and its messages.','The conversation ID.','Changes saved data. The console asks you to confirm before sending this request.'],
'Save a memory':['Save a fact or preference that Chit can use in later conversations.','The memory text; optionally choose a type, importance, and tags.','Adds one memory immediately. It does not train the model.'],
'Search memories':['Find memories that match a word or phrase.','A search phrase and optional result limit.','Read-only. Chit’s chat can also use relevant memories automatically.'],
'Delete memory':['Remove a saved memory so it is no longer available for recall.','The memory ID from a search result.','Changes saved data. It does not undo information already learned through model training.'],
'List training presets':['See the available learning plans.','Nothing to enter.','Read-only. The console loads this list when it opens the Studio selector.'],
'Start training':['Start a learning session using one selected plan.','A plan name; advanced options can set the device, seed, or model overrides.','Changes model files and uses compute. The current live brain remains available while the candidate trains.'],
'List training jobs':['See current and previous learning sessions.','Nothing to enter.','Read-only. Use a job ID to see more detail or stop an active session.'],
'Read training job':['Check progress and outcome for one learning session.','The training job ID.','Read-only. The result includes progress and whether the trained candidate was promoted.'],
'Cancel training job':['Ask Chit to stop a learning session that is queued or running.','The training job ID.','Changes an active job. The currently served model is not replaced by cancelling.'],
'Teach knowledge':['Save one or more lessons for Chit to learn later.','A short passage, a question with its answer, or a worked reasoning example.','Adds lessons to the learning queue. Set “remember” when a lesson should also be usable in chat before training.'],
'List knowledge':['Browse lessons that are waiting to be learned or have already been trained.','Optional status, type, tag, and page settings.','Read-only.'],
'Knowledge statistics':['See how many saved lessons are waiting, training, or already learned.','Nothing to enter.','Read-only.'],
'Read knowledge entry':['Read the complete contents and status of one saved lesson.','The lesson ID from the lesson list.','Read-only.'],
'Delete knowledge entry':['Remove a lesson from future training.','The lesson ID.','Changes the learning queue. A model trained on that lesson keeps what it already learned until retrained.'],
'Train on knowledge':['Start a learning session using saved lessons.','A learning plan; optionally choose all lessons or only pending lessons.','Uses compute and creates a candidate model. Lessons are marked trained only if the resulting model is promoted.'],
'Inspect training data':['Check which files a learning plan will study and whether the data is ready.','A learning plan name.','Read-only. Review warnings before starting training.'],
'Split corpus file':['Divide a text file into training and review portions.','A file name in the server data folder, a plan, and a split style.','Preview first with dry-run. Writing changes the plan’s training files; existing files require explicit overwrite and are backed up.']
};
const list=$('#endpointList');let selected=null;ROUTES.forEach((route,i)=>{const b=document.createElement('button');b.type='button';b.className='endpoint';const title=document.createElement('b');const method=document.createElement('i');method.className='method';method.textContent=route.method;title.append(method,document.createTextNode(route.name));const path=document.createElement('span');path.textContent=route.path;b.append(title,path);b.title=route.category;b.setAttribute('aria-pressed','false');const baseInfo=routeGuides[route.name]||['Use this Chit capability.','See the example values in the optional technical editor below.','The result is returned by the server.'];b._helpInfo={what:baseInfo[0],example:route.body===null?`${route.method} ${route.path} needs no request body.`:`${route.method} ${route.path}; example values are ready in the advanced editor.`,best:baseInfo[2],recommended:route.method==='GET'?'Use the supplied example first.':'Use the guided screen if you are unsure what to change.',risk:route.method==='GET'?'This reads information and does not change saved data.':route.method==='DELETE'?'This removes saved information and cannot usually be undone.':`This may create or change information or start work. ${baseInfo[2]}`};b.addEventListener('click',()=>selectRoute(i,b));list.appendChild(b)});
function routeMatchesPath(routePath,path){const pattern='^'+routePath.split('/').map(part=>{const key=part.match(/^\{([^}]+)\}$/)?.[1];if(key==='session_id'||key==='job_id')return '[0-9a-f]{32}';if(key==='memory_id'||key==='entry_id')return '[A-Za-z0-9_-]+';return key?'[^/]+':part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('/')+'$';return new RegExp(pattern).test(path)}
$('#runApi').addEventListener('click',async()=>{const status=$('#apiStatus'),result=$('#apiResult'),method=$('#apiMethod').value,path=$('#apiPath').value.trim();status.textContent='Checking request…';status.classList.remove('error');try{const matchingRoute=ROUTES.find(route=>route.method===method&&routeMatchesPath(route.path,path));if(!matchingRoute)throw new Error('This method and path are not in the guided API list. Replace any placeholder such as {session_id} with the real ID, then try again.');const query=JSON.parse($('#apiQuery').value||'{}');if(!query||Array.isArray(query)||typeof query!=='object')throw new Error('Query parameters must be a JSON object.');let body=null;const raw=$('#apiBody').value.trim();if(raw)body=JSON.parse(raw);if(matchingRoute.confirm||method==='DELETE'){const action=matchingRoute.name||'This request';if(!confirm(`${action} may change or remove saved information, use compute, or stop a job. Continue?`)){status.textContent='Cancelled';return}}status.textContent='Sending…';const r=await callApi(method,path,query,body);result.textContent=pretty(r.data);status.textContent='HTTP '+r.status;if(!r.ok)status.classList.add('error')}catch(e){result.textContent=e.message;status.textContent='Could not send request';status.classList.add('error')}});
function closeContextHelp(){const panel=$('#contextHelpPanel');if(panel.classList.contains('hidden'))return;panel.classList.add('hidden');if(helpReturnFocus?.setAttribute)helpReturnFocus.setAttribute('aria-expanded','false');if(helpReturnFocus?.isConnected)helpReturnFocus.focus()}
$('#closeContextHelp').addEventListener('click',closeContextHelp);
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeContextHelp()});
decorateHelp();
new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1){if(node.matches?.('button,input,textarea,select,summary'))addHelpTrigger(node);decorateHelp(node)}}))).observe(document.body,{childList:true,subtree:true});
checkSession();
