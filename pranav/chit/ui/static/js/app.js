const $=s=>document.querySelector(s); let chatId=null, authenticated=false;
const controlHelp={
  helpChatPage: {
    what: 'Lets you have a back-and-forth conversation with Chit. Chit remembers earlier messages in the chat, checks your saved memories, and automatically picks the best skill (chat, knowledge, grammar, behavior, or reasoning) for each turn.',
    example: 'Type a question and press Send. You can also turn on "Think" for step-by-step problem solving, "Web" for live internet search, or choose a specific skill in "Conversation skill".',
    best: 'Keep one topic per conversation. Click "New conversation" when switching subjects so old messages do not confuse the next answer.',
    recommended: 'Leave Conversation skill on "Auto / Everyday Chat" so Chit automatically chooses the right skill for your message.',
    risk: 'Chatting uses Chit\'s current brain and memories, but does not permanently retrain the AI. Very long chats drop the oldest messages when the context window fills up.'
  },
  helpConversationsPage: {
    what: 'Shows your saved chat sessions so you can reopen an earlier conversation or delete ones you no longer need.',
    example: 'Click "Continue conversation" on any card to load its full message history back into the Chat screen.',
    best: 'Reopen a past conversation when you want to pick up where you left off with the same facts and summary.',
    recommended: 'Delete old test chats from time to time to keep your list tidy.',
    risk: 'Deleting a conversation permanently removes its messages, remembered session facts, and summary.'
  },
  helpGenPage: {
    what: 'Gets a single, one-time answer or continues raw text directly without saving a chat session or past conversation history.',
    example: 'Write a prompt, pick how Chit should respond ("Answer my request" or "Continue my text"), choose an Assistant skill, and click Generate.',
    best: 'Use "Answer my request" for one-off questions, grammar fixes, or reasoning tasks. Use "Continue my text" when you want Chit to finish an incomplete sentence or paragraph.',
    recommended: 'Keep Creativity (temperature) low (0.0 to 0.4) for steady, accurate answers, and start with "Detailed" response length.',
    risk: 'Generate does not keep a conversation history, so include all needed details in your prompt.'
  },
  helpBrainPage: {
    what: 'Lets you search, add, and delete facts in Chit\'s long-term memory, and shows how many saved lessons are waiting to be trained.',
    example: 'Save a fact like "I prefer short answers in simple English" so Chit can use it immediately in future chats.',
    best: 'Use Memories for personal preferences and facts you want Chit to recall right away without waiting for a training run.',
    recommended: 'Write one clear, true sentence per memory and mark key facts as "Important" or "Very important".',
    risk: 'Deleting a memory removes it immediately from recall. Do not store passwords or private secrets in memories.'
  },
  helpTeachPage: {
    what: 'Lets you save new lessons (facts, question-and-answer pairs, or step-by-step reasoning examples) for Chit to study in a future training run.',
    example: 'Choose "A question and its answer" or "A step-by-step reasoning example", fill in the fields, and click Save lesson.',
    best: 'Use Q&A lessons for direct factual questions, step-by-step reasoning examples for logic or math, and short passages for general reading.',
    recommended: 'Check "Also save this as a memory" if you want Chit to use the lesson in Chat right away before you run training in Studio.',
    risk: 'Saved lessons only change Chit\'s neural brain after you run "Learn saved lessons" in Studio and promote the new model.'
  },
  helpDataPage: {
    what: 'Checks whether the training text files for a learning plan exist and are ready, and lets you split a text file into training and review sets.',
    example: 'Pick a learning recipe and click "Inspect training material" to see file sizes, example counts, and any warnings.',
    best: 'Always click "Preview a file split" first so you can check how many examples go into training vs. review before writing files.',
    recommended: 'Inspect your chosen learning recipe here before starting any training job in Studio.',
    risk: 'Creating a split with "Replace existing training files" checked overwrites the current train and review files (a backup is kept automatically).'
  },
  helpStudioPage: {
    what: 'Lets you choose a learning plan, start training runs, test newly trained candidate models for safety and quality, and make a passing candidate your live AI.',
    example: 'Pick a learning plan on the left, review its settings, and click "Start learning with this plan". When it finishes, click "Test safety rules" and "Benchmark Bridge & Calibrate" before clicking "Make this the Live AI".',
    best: 'Always run the safety test and Bridge benchmark on a finished candidate before promoting it to be your live AI.',
    recommended: 'Leave "Force this candidate live" unchecked so every new AI version is checked against the 50 safety rules first.',
    risk: 'Training uses heavy processor (CPU/GPU) and memory resources and can take time. Promoting a new model immediately replaces the live AI for all chats.'
  },
  helpDiagPage: {
    what: 'Runs health checks on the server, active AI model, text reader (tokenizer), and training files to help explain unreadable or unexpected replies.',
    example: 'Choose a learning plan, click "Check Chit", and then click "Generate a sample response" to test how clearly the current model writes.',
    best: 'Run this check whenever replies look garbled, repetitive, or cut off.',
    recommended: 'Make sure the "Selected plan and active text reader" check shows a green match (both using byte-utf8).',
    risk: 'All checks on this page are read-only and safe; they never alter your model or saved data.'
  },
  helpApiPage: {
    what: 'An interactive guide to every Chit API action. Pick an operation to see plain-English field explanations, build a request safely, and read the server response.',
    example: 'Click "Server health" or "Chat message" in the operation list, edit the fields, and click "Send this request".',
    best: 'Use the guided form builder rather than editing raw JSON by hand, because the builder checks field rules for you.',
    recommended: 'Try read-only actions (labelled GET) first to explore how Chit responds.',
    risk: 'Actions sent from this screen run on the live server and can save data, delete items, or start training.'
  },
  activeAiHelpWrap:{what:'Shows the exact date and time of the AI checkpoint file currently powering your chats.',example:'Compare this timestamp with a finished job in Studio to confirm which trained model is currently live.',best:'Check this after promoting a new candidate model or rolling back to an older version.',recommended:'Verify this timestamp whenever you update the live AI.',risk:'Read-only indicator; clicking it does not change the model.'},
  apiKey:{what:'Lets this browser sign in to Chit. The key stays safely on the server for your current browser session.',example:'Paste the API key given to you by the server owner.',best:'Only enter the key on your trusted Chit page. Never share it in screenshots or messages.',recommended:'Use the API key configured for this server.',risk:'Anyone with this key can change saved data or start training runs.'},
  chatInput:{what:'Write your message or question for Chit here. Chit keeps track of the conversation and uses relevant saved memories.',example:'“What is Chit and how does its memory work?”',best:'Ask one clear question at a time and include any helpful details.',recommended:'Write a complete sentence; press Enter to send or Shift+Enter for a new line.',risk:'Chit is a compact AI and can make mistakes. Double-check important facts.'},
  chatTask:{what:'Chooses which trained skill Chit should use for your message, or lets Chit pick the best skill automatically.',example:'Leave on "Auto / Everyday Chat" for normal use, or choose "Grammar & Writing" when fixing a sentence.',best:'Use "Auto / Everyday Chat" most of the time—Chit\'s Router automatically switches to Knowledge, Behavior, Grammar, or Reasoning when your question needs it.',recommended:'Auto / Everyday Chat.',risk:'Choosing "Continue Raw Text" extends your text directly without chat formatting, thinking steps, or web search.'},
  sendChat:{what:'Sends your message to Chit and adds the reply to this conversation.',example:'Type a message and click Send message (or press Enter).',best:'Give Chit enough context to answer clearly.',recommended:'Start a new conversation when switching to a completely different topic.',risk:'Messages are saved in your current conversation session.'},
  newChat:{what:'Starts a fresh conversation with a clean slate so earlier messages do not influence the next reply.',example:'Click New conversation before switching from a math question to a writing task.',best:'Keep each conversation focused on one subject.',recommended:'Use whenever you change topics.',risk:'This does not delete your previous chat; you can still find it in Conversations.'},
  thinkToggle:{what:'Turns on step-by-step thinking (Task: reasoning). Chit works through the problem in a collapsible "Thought process" box before giving its final answer.',example:'Turn on for word problems, logic puzzles, or multi-step questions.',best:'Use when a question needs careful deduction. Leave off for simple greetings or quick facts.',recommended:'Turn on for math and logic; leave off for casual chat.',risk:'Takes a little longer because Chit writes out its thinking steps first.'},
  searchToggle:{what:'Lets Chit search the web for fresh facts before answering your message.',example:'Turn on when asking about recent events, live facts, or topics outside Chit\'s saved memories.',best:'Use when you need up-to-date information from the internet.',recommended:'Leave off for normal chat; turn on when you need live web facts.',risk:'Adds about 1–2 seconds for the internet search and requires server internet access.'},
  genPrompt:{what:'The question, instruction, or starting text you want Chit to respond to.',example:'“Explain why leaves change colour in autumn.”',best:'State clearly what you want Chit to write or solve.',recommended:'A short, clear request works best.',risk:'Very long prompts leave less space in the context window for Chit\'s answer.'},
  genMode:{what:'Chooses whether Chit answers your request like an assistant or continues writing directly from your text.',example:'Choose “Answer my request” for a question; choose “Continue my text” for an unfinished sentence.',best:'Use “Answer my request” for almost all questions and tasks.',recommended:'Answer my request.',risk:'“Continue my text” extends your words directly without assistant formatting, thinking steps, or web search.'},
  genTask:{what:'Selects which trained skill header (Task: chat, knowledge, behavior, grammar, reasoning, or prose) Chit uses in assistant mode.',example:'Choose "Grammar & Writing" to rewrite a sentence, or "Knowledge & Facts" for factual Q&A.',best:'Leave on "Auto / Everyday Chat" if you want Chit\'s Router to pick the best skill automatically.',recommended:'Auto / Everyday Chat.',risk:'Only used when "How should Chit respond?" is set to "Answer my request".'},
  genTokens:{what:'Sets the maximum length of Chit’s reply.',example:'Choose “Concise” for a quick answer or “Detailed” for a fuller explanation.',best:'Start with Detailed and increase only if the answer gets cut off.',recommended:'Detailed (160 bytes/tokens).',risk:'Very long settings take more time and can cause a small model to wander off topic.'},
  genTemp:{what:'Controls how steady or creative Chit’s wording is.',example:'0.0 gives the most reliable, repeatable answer; 0.4–0.7 allows more varied phrasing.',best:'Lower it toward 0.0 if answers look inconsistent or off-track.',recommended:'0.0 for factual accuracy; 0.4 for everyday writing.',risk:'High values (above 0.8) increase the chance of spelling errors or nonsense words.'},
  genTopK:{what:'Limits how many possible next characters or words Chit considers at each step.',example:'A smaller number keeps choices narrow; 50 is the standard balance.',best:'Leave at 50 unless you are experimenting with creative writing.',recommended:'50 (has no effect when Creativity is set to 0).',risk:'Very small values can make phrasing stiff or repetitive.'},
  genSearch:{what:'Searches the web for live facts before generating a one-time assistant answer.',example:'Check this box when asking a factual question about the real world.',best:'Use in "Answer my request" mode when you want web-grounded facts.',recommended:'Unchecked for general writing; checked for live factual questions.',risk:'Only works in "Answer my request" mode (automatically disabled in "Continue my text" mode).'},
  genThink:{what:'Turns on step-by-step Chain-of-Thought reasoning before generating the final answer.',example:'Check this box when asking a logic puzzle or multi-step question.',best:'Use in "Answer my request" mode for questions that benefit from working through steps.',recommended:'Checked for reasoning tasks; unchecked for simple questions.',risk:'Only works in "Answer my request" mode and uses extra tokens for the thinking steps.'},
  runGenerate:{what:'Sends your prompt to Chit and shows the one-time response below without saving a conversation.',example:'Fill in your prompt and click Generate.',best:'Use this to test prompts or get a quick standalone answer.',recommended:'Use the Chat screen instead if you want a multi-turn conversation.',risk:'Longer responses take slightly more time and processor work.'},
  refreshSessions:{what:'Reloads your list of saved conversations from the server.',example:'Click Refresh conversations after starting or deleting a chat.',best:'Use if a recent conversation is not showing up yet.',recommended:'Click whenever you want the latest list.',risk:'Safe and read-only; does not change any saved conversations.'},
  lessonKind:{what:'Chooses what kind of lesson you are teaching Chit: a short fact passage, a question-and-answer pair, or a step-by-step reasoning example.',example:'Pick "A question and its answer" for direct Q&A, or "A step-by-step reasoning example" to teach how to solve a problem.',best:'Match the lesson type to how you want Chit to use the knowledge later.',recommended:'A question and its answer for clear facts; step-by-step reasoning for logic.',risk:'Inaccurate lessons can teach Chit wrong answers when trained.'},
  lessonSource:{what:'An optional note reminding you where this lesson came from.',example:'“Project handbook” or “Team notes”.',best:'Add a short source note so you know why this lesson was saved.',recommended:'Optional; leave blank if not needed.',risk:'Do not put private or secret details in the source note.'},
  lessonText:{what:'The fact or short paragraph you want Chit to study in a future training run (taught under Task: prose / knowledge).',example:'“Chit uses a 256-entry UTF-8 byte tokenizer so every character is read cleanly.”',best:'Write clear, complete sentences and check your spelling.',recommended:'Keep each lesson focused on one clear idea.',risk:'Chit only learns this into its neural weights after you run training in Studio.'},
  lessonQuestion:{what:'The question Chit should learn to answer (taught under Task: knowledge).',example:'“What tokenizer does Chit use?”',best:'Phrase the question the way a real person would ask it.',recommended:'One clear, direct question.',risk:'Overly vague questions make it harder for Chit to learn a clean match.'},
  lessonAnswer:{what:'The clear, accurate answer Chit should give for the question above.',example:'“Chit uses a 256-entry UTF-8 byte-level tokenizer.”',best:'Give a direct, honest answer in simple sentences.',recommended:'Keep the answer concise and factual.',risk:'If the answer contains mistakes, Chit may repeat those mistakes after training.'},
  lessonInput:{what:'The problem or question that requires step-by-step thinking (taught under Task: reasoning).',example:'“If a notebook costs 15 rupees and a pen costs 5 rupees, how much do 2 notebooks and 1 pen cost?”',best:'Write a clear problem where working through steps leads to the answer.',recommended:'One self-contained problem per lesson.',risk:'Make sure the problem statement includes all information needed to solve it.'},
  lessonReasoning:{what:'The step-by-step thinking Chit should write out before giving the final answer.',example:'“Two notebooks cost 2 * 15 = 30 rupees. Adding one 5-rupee pen gives 30 + 5 = 35 rupees.”',best:'Show each logical step clearly in order.',recommended:'1 to 3 clear sentences showing the deduction steps.',risk:'Skipping steps or writing faulty logic can confuse the model during training.'},
  lessonReasoningAnswer:{what:'The final conclusion or answer reached at the end of the reasoning steps.',example:'“The total cost is 35 rupees.”',best:'State the final answer clearly so it matches the steps above.',recommended:'A short, direct final answer sentence.',risk:'Make sure the final answer agrees with the step-by-step thinking.'},
  rememberLesson:{what:'Also saves this lesson into Chit’s long-term memory right now so Chat can recall it immediately without waiting for training.',example:'Check this box when teaching a fact you want Chit to know in your very next chat message.',best:'Turn on for important facts you want available right away.',recommended:'Checked for facts you need today; unchecked for bulk training lessons.',risk:'Creates both a memory and a lesson; deleting one later does not automatically delete the other.'},
  saveLesson:{what:'Saves this lesson into Chit’s training queue so it can be included in future learning runs.',example:'Review your text or Q&A fields, then click Save lesson.',best:'Double-check spelling and accuracy before saving.',recommended:'Save clear, verified facts and examples.',risk:'Saving queues the lesson; run "Learn saved lessons" in Studio when you want to train the model on it.'},
  knowledgeFilter:{what:'Filters the saved lessons list to show lessons waiting for training, lessons already trained, or all lessons.',example:'Choose “Ready to learn” to see what is queued for the next training run.',best:'Review “Ready to learn” before starting a lesson training job in Studio.',recommended:'Ready to learn.',risk:'Only changes which lessons are displayed on screen.'},
  refreshKnowledge:{what:'Reloads the saved lessons list and updates the learning pipeline counts.',example:'Click Refresh lessons after adding or deleting lessons.',best:'Use if the lesson list looks out of date.',recommended:'Click to refresh the view.',risk:'Safe and read-only.'},
  memSearch:{what:'Type a word or phrase here to search through Chit’s saved long-term memories.',example:'Type “simple English” or “project” to find matching memories.',best:'Use one or two specific keywords from the fact you are looking for.',recommended:'Search with a key noun or topic word.',risk:'Searching only reads memories; it never changes them.'},
  doMemSearch:{what:'Runs the search and displays matching saved memories below.',example:'Type a keyword in Search memories and click Search.',best:'If no results appear, try a shorter keyword.',recommended:'Use whenever you want to review or clean up saved memories.',risk:'Safe and read-only.'},
  newMemory:{what:'Write a fact or preference that Chit should remember and use immediately in conversations.',example:'“I prefer concise answers in simple English.”',best:'Write one short, clear statement that will be useful in future chats.',recommended:'Save helpful personal preferences or key project facts.',risk:'Saved immediately in memory. Do not store passwords or sensitive personal secrets.'},
  memoryType:{what:'Labels whether this memory is a personal preference/experience or a general fact.',example:'Choose “Personal experience or preference” for how you like answers written; choose “A useful fact” for reference info.',best:'Pick whichever label best describes the note.',recommended:'Personal experience or preference for user details.',risk:'Used only to organize memories; both types can be recalled in chat.'},
  memoryImportance:{what:'Sets how strongly this memory should stand out when Chit looks for relevant context.',example:'Choose “Very important” for core rules or preferences you want recalled often.',best:'Use “Important” for most facts and “Very important” for top priorities.',recommended:'Important (0.5).',risk:'Higher importance makes a memory more likely to be recalled, but does not verify that the text is true.'},
  saveMemory:{what:'Saves the fact above into Chit’s long-term memory so Chat can recall it right away.',example:'Write a clear sentence and click Save memory.',best:'Check that the sentence is accurate before saving.',recommended:'One clear fact per memory card.',risk:'Stored immediately; you can delete it anytime from the memory search results.'},
  dataConfig:{what:'Chooses which learning recipe’s training and review files you want to inspect or split.',example:'Pick “Everyday assistant” or “Full Unified Curriculum (6L-256)” to check its dataset files.',best:'Select the same learning recipe you plan to run in Studio.',recommended:'Match your intended Studio learning plan.',risk:'Choosing a recipe here is read-only and does not start training.'},
  dataSource:{what:'The name of a raw text file inside the server’s data folder that you want to split into training and review files.',example:'“lessons.txt” or “corpus.txt”',best:'Type only the file name (no folder slashes or computer paths).',recommended:'Always click "Preview a file split" before creating files.',risk:'The file must already exist in the server’s data folder.'},
  overwriteSplit:{what:'Allows "Create train and review files" to replace existing training files for the selected recipe (the server saves a backup copy first).',example:'Leave unchecked while previewing; check only when you intentionally want to replace the files.',best:'Keep unchecked until you have reviewed the split preview.',recommended:'Unchecked by default.',risk:'Replaces the recipe’s train and eval files used by future training runs.'},
  inspectData:{what:'Checks whether the selected learning recipe’s training and review files exist, how many examples they have, and whether they are ready for training.',example:'Select a recipe and click Inspect training material.',best:'Run this check before starting a training job in Studio.',recommended:'Check every recipe before training.',risk:'Safe and read-only; does not change any files.'},
  previewSplit:{what:'Shows a safe preview of how the text file would be divided into training (90%) and review (10%) examples without changing any files on disk.',example:'Enter a file name and click Preview a file split.',best:'Always preview first to make sure the example counts look right.',recommended:'Preview before creating any split.',risk:'Safe and read-only; no files are modified.'},
  applySplit:{what:'Divides the named text file and writes the resulting training and review files to disk for the selected recipe.',example:'Use after "Preview a file split" shows the expected example counts.',best:'Confirm the selected learning recipe before clicking.',recommended:'Keep "Replace existing training files" unchecked unless you intend to overwrite.',risk:'Writes files in the server data folder that future training runs will study.'},
  refreshModel:{what:'Reloads the summary of Chit’s current server health, loaded brain size, and processor device.',example:'Click Refresh status after promoting or reloading a model.',best:'Use to confirm the active brain is loaded and ready.',recommended:'Click anytime to refresh.',risk:'Safe and read-only.'},
  diagnosticConfig:{what:'Selects which learning plan to compare against the currently active AI brain during health checks.',example:'Choose the learning plan that trained your current checkpoint.',best:'Compare the plan’s tokenizer and context window with the live model.',recommended:'Everyday assistant or Full Unified Curriculum (6L-256).',risk:'Safe and read-only; does not start training.'},
  runDiagnostics:{what:'Runs a full check of the server connection, active AI brain, text reader (tokenizer), training data files, and recent training jobs.',example:'Click Check Chit when answers look garbled or unexpected.',best:'Read the green/orange check cards and follow any suggested next steps.',recommended:'Run whenever troubleshooting model behavior.',risk:'Safe and read-only.'},
  diagnosticPrompt:{what:'A simple test question sent to the live AI to check whether it replies with a clean, readable English sentence.',example:'“Reply with one clear sentence: What is a library?”',best:'Keep the test prompt short and simple so it is easy to judge the reply.',recommended:'Use the provided default test sentence.',risk:'Runs one quick generation without saving a chat session.'},
  runDiagnosticPrompt:{what:'Sends the test prompt above to Chit and displays the sample answer so you can judge its clarity.',example:'Click Generate a sample response, then read the output box below.',best:'Run "Check Chit" first, then test a sample response.',recommended:'Use to verify the live AI writes clean English.',risk:'Uses a small amount of processor work to generate one reply.'},
  responseReadable:{what:'Notes that the sample answer looks clear and readable, and explains what to check if a specific chat question still gave trouble.',example:'Click Readable when the sample sentence makes sense.',best:'Use after reading the generated sample reply.',recommended:'Click when the test output is clean.',risk:'Only shows helpful guidance on screen; does not change model settings.'},
  responseGarbled:{what:'Shows step-by-step troubleshooting advice when the sample answer looks broken, repetitive, or off-topic.',example:'Click Garbled or off-topic if the sample reply is unreadable.',best:'Follow the suggested checks for tokenizer match and checkpoint health.',recommended:'Click when the test output looks broken.',risk:'Only shows helpful guidance on screen; does not retrain the model automatically.'},
  openTrainingLibrary:{what:'Takes you directly to the Training library screen so you can inspect training files and warnings.',example:'Click Review training material if diagnostics reported a data warning.',best:'Inspect the same learning plan you checked in Troubleshooting.',recommended:'Use when checking data readiness.',risk:'Safe navigation button.'},
  openStudio:{what:'Takes you directly to the Studio screen where you can review learning plans and training jobs.',example:'Click Open learning plans to view or start training runs.',best:'Review the plan details before starting a training run.',recommended:'Use when you are ready to manage models in Studio.',risk:'Safe navigation button.'},
  trainConfig:{what:'Selects the learning plan (model architecture, training steps, and Task-header dataset files) to view or train in Studio.',example:'Choose “Stage 1: English & Grammar Foundation (6L-256)” or “Full Unified Curriculum (6L-256)” to read its details.',best:'Read the explanation card below this selector before starting training.',recommended:'Everyday assistant or the 6L-256 staged curriculum plans.',risk:'Selecting a plan only displays its details; training does not start until you click Start learning.'},
  startTrain:{what:'Starts a background training job using the selected learning plan’s training files.',example:'Choose a learning plan, review its settings, and click Start learning with this plan.',best:'Make sure your machine has enough free CPU/RAM and no other job is running.',recommended:'Keep "Force this candidate live" unchecked so the new model is safety-tested before going live.',risk:'Training uses heavy CPU/memory resources and can take a long time on a developer laptop.'},
  lessonScope:{what:'Chooses whether "Learn saved lessons" trains on every lesson you have saved or only on new lessons not yet trained.',example:'Choose “All lessons (recommended)” to review everything together, or “Only lessons not yet learned” for a quick update.',best:'Use “All lessons” so Chit does not forget earlier lessons while studying new ones.',recommended:'All lessons (recommended).',risk:'Training only on pending lessons gives the model less review of older lessons.'},
  trainKnowledge:{what:'Starts a background training run that studies the lessons you saved in Teach Chit.',example:'Save your lessons in Teach Chit, then come to Studio and click Learn saved lessons.',best:'Review your pending lessons in Teach Chit first to make sure they are accurate.',recommended:'Include All lessons and test the resulting candidate before making it live.',risk:'Uses processor and memory resources to train a new candidate model.'},
  apiMethod:{what:'Selects the HTTP action type for the raw JSON editor: GET reads data, POST sends or starts something, PATCH updates a setting, and DELETE removes an item.',example:'GET /health reads server health; POST /chat sends a chat message.',best:'Let the operation buttons above fill this in automatically.',recommended:'Use the method set by the chosen operation.',risk:'POST, PATCH, and DELETE can change saved data or start training.'},
  apiGuideSearch:{what:'Filters the full Chit API Guide below so only sections matching your search word are shown.',example:'Type “confidence”, “task”, or “sessions” to jump to matching guide sections.',best:'Search with one short keyword or route name.',recommended:'Leave blank to browse the entire guide.',risk:'Only filters the guide text on screen.'},
  clearApiGuideSearch:{what:'Clears the search box above and shows all sections of the Chit API Guide again.',example:'Click Clear search when you want to read the full guide.',best:'Use after finishing a keyword search.',recommended:'Click to reset the guide view.',risk:'Only resets the guide filter on screen.'},
  runGuidedApi:{what:'Sends the API request built in the guided form above and explains the server’s response in plain English.',example:'Fill in the guided fields, check the "JSON Chit will receive" preview, and click Send this request.',best:'Review the JSON preview before sending.',recommended:'Use this guided button rather than the raw JSON editor whenever possible.',risk:'Runs the selected action on the live server.'},
  apiPath:{what:'The server endpoint path for the advanced raw JSON editor (such as /health or /chat).',example:'/chat or /sessions/0123456789abcdef0123456789abcdef',best:'Click an operation button at the top of the page to fill this path automatically.',recommended:'Keep the path from the selected operation.',risk:'Changing the path targets a different server action.'},
  apiQuery:{what:'Optional URL filter parameters (as a JSON object) for the advanced request editor.',example:'{"limit": 50, "offset": 0}',best:'Use the guided form above unless you are testing custom query parameters.',recommended:'Keep the example JSON object.',risk:'Invalid JSON or out-of-range numbers will cause the request to fail.'},
  apiBody:{what:'The raw JSON data sent with POST or PATCH requests in the advanced editor.',example:'{"message": "Hello, Chit.", "task": "chat", "temperature": 0}',best:'Prefer the guided form above, which builds valid JSON for you automatically.',recommended:'Use the example body filled in by the chosen operation.',risk:'Invalid JSON or unsupported fields will be rejected by the server.'},
  runApi:{what:'Sends the raw JSON request from the advanced editor to the Chit server.',example:'Review the Method, API path, Query, and Body fields, then click Send API request.',best:'Double-check your JSON syntax before clicking.',recommended:'Use "Send this request" in the guided builder for everyday use.',risk:'Executes directly on the live server and can modify data or start training.'},
  apiKeySubmit:{what:'Verifies your API key and unlocks the Chit Console for this browser session.',example:'Paste your server API key and click Continue.',best:'Sign in only on your trusted Chit server address.',recommended:'Enter the configured CHIT_API_KEY.',risk:'Never share your API key with untrusted parties.'},
  logout:{what:'Signs out and locks the Chit Console in this browser window.',example:'Click Lock console when you finish working or step away from your computer.',best:'Lock the console whenever using a shared computer.',recommended:'Click when done with your session.',risk:'You will need to enter the API key again to unlock the console.'},
  refreshFactsBtn:{what:'Checks what personal facts (like your name or preferences) Chit has automatically remembered during this chat session.',example:'Click Check for new facts after telling Chit something about yourself.',best:'Use to see the exact session facts Chit is keeping in mind for this conversation.',recommended:'Click anytime during an active chat.',risk:'Safe and read-only.'},
  clearFactsBtn:{what:'Tells Chit to forget all personal facts it extracted during this specific conversation.',example:'Click Forget these facts if Chit picked up a mistaken detail in this chat.',best:'Use when you want to clear session-specific facts without deleting the whole conversation.',recommended:'Click only when you want to wipe this session\'s extracted facts.',risk:'Permanently clears the remembered facts for this conversation session.'},
  forcePromote:{what:'Automatically makes the newly trained model your live AI as soon as training finishes, skipping the 50 safety tests and Bridge benchmark.',example:'Leave unchecked for normal use; check only if you intentionally want to skip safety testing.',best:'Keep unchecked so you can test and benchmark the candidate before making it live.',recommended:'Unchecked (safe default).',risk:'Replaces your live AI without checking whether the new model passes safety or quality gates.'},
  reloadModelBtn:{what:'Reloads the live AI checkpoint file (checkpoints/latest.pt) from disk into server memory.',example:'Click Restart Live AI after updating checkpoint files on disk.',best:'Use when you want the server to re-read the live checkpoint and calibration curve from disk.',recommended:'Click after manual checkpoint updates.',risk:'Briefly pauses active chat generation for a second while reloading weights.'},
  rollbackModelBtn:{what:'Restores the live AI back to an earlier archived checkpoint using its SHA-256 version ID.',example:'Paste a previous checkpoint SHA-256 ID into the box and click Undo Last Update (Rollback).',best:'Use if a newly promoted model gives worse answers than your previous version.',recommended:'Confirm the version ID before rolling back.',risk:'Immediately swaps the live AI back to the selected older checkpoint.'},
  rollbackHashInput:{what:'Enter the SHA-256 version ID of the archived checkpoint you want to restore as the live AI.',example:'Paste the checkpoint SHA-256 fingerprint from an earlier model.',best:'Copy the exact ID rather than typing it by hand.',recommended:'Use a known good checkpoint ID.',risk:'An unknown or mistyped ID will be rejected safely without changing the live AI.'}
};
function inferredHelp(element){
    if(element.classList.contains('job-ai-stamp'))return {what:'Shows the exact date and time when this job\'s checkpoint file was saved.',example:'If this matches the "Live AI Checkpoint" timestamp at the top of Studio, this job is currently powering your chats.',best:'Compare this timestamp with the Live AI Checkpoint to see which version is active.',recommended:'Check after promoting a candidate.',risk:'Safe and read-only.'};
    if(element.classList.contains('eval-btn'))return {what:'Tests this trained candidate model against Chit\'s 50 Golden Gate safety and honesty rules.',example:'Click "Test safety rules" after a training job finishes.',best:'Always run this safety test before promoting a new candidate model.',recommended:'Run before clicking "Make this the Live AI".',risk:'Runs in the background and takes a short time to score all 50 rules.'};
    if(element.classList.contains('bench-btn'))return {what:'Tests how well the Bridge guides this candidate model (checking calculator math accuracy, confidence honesty, word loops, and response speed) and calibrates its confidence scores.',example:'Click "Benchmark Bridge & Calibrate" on a finished training job.',best:'Run this alongside "Test safety rules" so the model gets a calibrated confidence curve before going live.',recommended:'Run before promoting a candidate.',risk:'Runs in the background and uses processor work for about a minute.'};
    if(element.classList.contains('promote-btn'))return {what:'Makes this tested candidate model your new live AI for all chats and generations, and activates its calibrated confidence curve.',example:'Click "Make this the Live AI" after the candidate passes its safety test.',best:'Promote only when Safety Test says Passed and Bridge metrics look healthy.',recommended:'Confirm you are ready to replace the current live AI.',risk:'Immediately swaps the live AI for all users; the previous version is archived for rollback.'};
    if(element.classList.contains('retrieval-btn'))return {what:'Asks Chit to answer your last message again using live web search because Chit had low confidence in its first answer.',example:'Click "🌐 Search Web" when Chit warns that its confidence is low.',best:'Use when your question asks about real-world or recent facts.',recommended:'Click to ground the answer with live web search.',risk:'Sends your last message again with web search enabled.'};
    const label=element.getAttribute('aria-label')||element.labels?.[0]?.textContent?.trim()||element.textContent?.trim()||element.getAttribute('placeholder')||element.id||'This control';
    const view=element.dataset?.view;
    const words=(element.textContent||'').trim().toLowerCase();
    if(element.closest?.('#loginForm'))return {what:'Checks your API key and signs in to the Chit Console.',example:'Enter your key and click Continue.',best:'Use the key configured by the server administrator.',recommended:'Sign in only on your trusted Chit page.',risk:'Your key unlocks full console access; keep it private.'};
    if(words==='stop learning session')return {what:'Stops this running or queued training job immediately.',example:'Click "Stop learning session" if you started a training job by mistake or need to free up your computer\'s CPU and memory.',best:'Use whenever a training run is taking too long on your machine.',recommended:'Confirm when prompted to cancel the job.',risk:'Stops the training run; your current live AI remains untouched and keeps working normally.'};
    if(words==='continue conversation')return {what:'Reopens this saved conversation in the Chat screen so you can keep talking with the same history and remembered facts.',example:'Click "Continue conversation" on the chat card you want to resume.',best:'Use when returning to an earlier topic.',recommended:'Check the conversation title and message count before opening.',risk:'New messages you send will be added to this saved conversation.'};
    if(words==='delete'||words==='remove lesson')return {what:'Permanently deletes this saved conversation, memory, or lesson.',example:'Click Delete or Remove lesson when you no longer want this item stored.',best:'Read the item carefully before confirming deletion.',recommended:'Keep the item if you might still need it.',risk:'Deletion is permanent and cannot be undone.'};
    if(words==='use in chat'||words==='use')return {what:'Copies this saved memory or lesson into the Chat message box so you can ask Chit about it right away.',example:'Click Use, then type your question below the inserted text and press Send.',best:'Review the text placed in the message box before sending.',recommended:'Use when you want to bring a saved fact directly into your current chat.',risk:'Only fills the chat input box; nothing is sent until you click Send message.'};
    if(words==='copy'||words==='copied'||words==='clipboard unavailable')return {what:'Copies Chit’s final answer to your clipboard (without copying the internal thought trace).',example:'Click Copy on any Chit reply, then paste it into your notes or document.',best:'Review the answer before sharing it elsewhere.',recommended:'Use whenever you want to save or share a reply.',risk:'Copied text may still contain AI mistakes; verify important facts.'};
    if(words==='try another answer')return {what:'Sends your last message to Chit again with a touch of variety (temperature 0.25) to try a fresh phrasing.',example:'Click "Try another answer" if the first reply felt stiff or missed your point.',best:'If the second try also misses, rephrase your question with more detail.',recommended:'Try once before rewording your question.',risk:'Sends another chat request and adds the new reply to this conversation.'};
    if(words.includes('advanced tools'))return {what:'Opens or closes the Advanced tools menu in the sidebar, which holds the Guided API Reference.',example:'Click "Advanced tools" to reveal the API reference button.',best:'Open when you want to inspect or test Chit API routes directly.',recommended:'Keep closed for everyday chatting; open for developer exploration.',risk:'Safe and read-only; only shows or hides the menu item.'};
    if(words.includes('advanced response settings'))return {what:'Opens optional controls for Creativity (temperature), Response variety (top-k), live Web search, and step-by-step Thinking.',example:'Click "Advanced response settings" to turn on Web search or Thinking for a one-time generation.',best:'Keep the default slider values for everyday tasks and open this panel when you need Web search or Thinking.',recommended:'Creativity 0.4, Response variety 50.',risk:'Setting Creativity very high can make answers less accurate.'};
    if(words.includes('technical evidence and limits'))return {what:'Opens a detailed table of technical facts reported by the server, such as exact byte counts, tokenizer name, and why the last generation stopped.',example:'Click "Technical evidence and limits" after running "Check Chit" to inspect low-level numbers.',best:'Use when troubleshooting context truncation or tokenizer mismatches.',recommended:'Open after running a diagnostic check.',risk:'Safe and read-only.'};
    if(words.includes('save a memory for chit'))return {what:'Opens the form where you can type a new fact or personal preference into Chit’s long-term memory.',example:'Click "Save a memory for Chit" to add a preference like "I work in Python".',best:'Save short, clear facts that will be useful across many conversations.',recommended:'One fact per memory.',risk:'Only opens or closes the form until you click Save memory.'};
    if(words.includes('edit the raw json request')||words.includes('raw json'))return {what:'Opens the raw HTTP JSON editor for developers who want to edit request bodies directly.',example:'Click to view or edit the raw Method, Path, Query, and JSON Body.',best:'Use the guided form builder above unless you need to test custom JSON.',recommended:'Guided form builder for everyday use.',risk:'Malformed JSON will be rejected by the server.'};
    if(words.includes('read the complete chit api guide')||words.includes('api guide'))return {what:'Opens the complete plain-English Chit API Guide right inside this page, with a live search box.',example:'Click to browse or search all API routes, task headers, and troubleshooting tips.',best:'Use the search box inside to quickly find any topic.',recommended:'Read when learning how the API works.',risk:'Safe and read-only.'};
    if(words.includes('example, recommended use and risk'))return {what:'Shows a quick summary of an example value, best practice, and what to watch out for on this API field.',example:'Click to expand the field tip below the input box.',best:'Read before changing an unfamiliar API field.',recommended:'Expand whenever you want a quick reminder.',risk:'Safe and read-only.'};
    if(words.includes('show the complete response json'))return {what:'Shows the exact raw JSON data returned by the server for this API request.',example:'Click after sending a guided API request to inspect the full JSON payload.',best:'Use when debugging or building an app that calls the Chit API.',recommended:'Read the plain-English summary above first, then open raw JSON if needed.',risk:'Safe and read-only.'};
    const navInfo={chat:{what:'Opens the Chat screen where you can talk back and forth with Chit using saved memories, web search, and automatic Task skill routing.',example:'Click Chat in the left sidebar to start or continue a conversation.',best:'Use one conversation per topic for the clearest answers.',recommended:'Start here for everyday use.',risk:'Always double-check important facts in AI replies.'},conversations:{what:'Opens your list of saved conversations so you can reopen an earlier chat or delete old ones.',example:'Click Conversations to find and resume a previous discussion.',best:'Reopen a conversation when continuing the same topic.',recommended:'Delete old test chats you no longer need.',risk:'Deleting a conversation permanently removes its messages.'},generate:{what:'Opens the Generate screen for one-time answers or raw text continuation without saving a chat session.',example:'Click Generate to ask a standalone question or continue a sentence prefix.',best:'Choose an Assistant skill (chat, knowledge, behavior, grammar, reasoning, or prose) to guide the answer.',recommended:'Use Chat for back-and-forth dialogue and Generate for one-off prompts.',risk:'Generate does not keep conversation history across runs.'},brain:{what:'Opens the Brain screen where you can search and save long-term memories and view the learning pipeline.',example:'Click Brain to add a personal preference or search existing memories.',best:'Use memories for facts you want Chit to recall immediately in chat.',recommended:'Keep memories short, true, and specific.',risk:'Deleting a memory removes it from future recall.'},teach:{what:'Opens the Teach Chit screen where you can save facts, Q&A pairs, or step-by-step reasoning lessons for future training.',example:'Click Teach Chit to add a new Q&A or reasoning lesson to the learning queue.',best:'Check "Also save this as a memory" if you want Chit to use the fact before the next training run.',recommended:'Write clear, verified lessons.',risk:'Lessons only update Chit\'s neural weights after training in Studio.'},studio:{what:'Opens Studio where you can inspect learning plans, run training jobs, test safety rules, benchmark the Bridge, and promote models.',example:'Click Studio to review the 6L-256 curriculum plans or check training job history.',best:'Always test safety rules and benchmark the Bridge before promoting a new candidate model.',recommended:'Inspect training files in Training library before starting a run.',risk:'Training uses heavy processor and memory resources.'},data:{what:'Opens the Training library screen to check dataset readiness, view live model status, or restart/rollback the live AI.',example:'Click Training library to verify that all training and review files exist.',best:'Preview any file split before writing changes to disk.',recommended:'Check dataset readiness before training.',risk:'Splitting files with overwrite enabled replaces existing training files.'},diagnostics:{what:'Opens Troubleshooting to run health checks on the server, active model, tokenizer, and training data.',example:'Click Troubleshooting if answers look garbled, repetitive, or cut short.',best:'Run "Check Chit" and test a sample sentence to pinpoint the issue.',recommended:'Check that the active model uses the expected byte-utf8 text reader.',risk:'Safe and read-only diagnostic checks.'},explorer:{what:'Opens the Guided API Reference where every Chit API endpoint is explained in simple English with a live request builder.',example:'Click API reference under Advanced tools to explore and test server endpoints.',best:'Use the guided form fields and JSON preview to build requests safely.',recommended:'Start with read-only GET operations like Server health.',risk:'Sending POST or DELETE requests changes live server data.'}};
    if(navInfo[view])return navInfo[view];
    const isButton=element.tagName==='BUTTON';const text=(element.textContent||'').trim().toLowerCase();
    const risk=/delete|remove|stop|cancel|create|start|save|send|train|split|replace|logout|lock/.test(text)?'This action can change saved data, start background work, or stop a job. Review your settings before clicking.':'This control only adjusts what is selected or shown on screen.';
    const value=element.value||element.getAttribute('placeholder')||element.querySelector('option:checked')?.textContent||'the suggested setting';
    return {what:isButton?`Performs the “${label}” action on this screen.`:`Sets ${label.toLowerCase()} for this action.`,example:isButton?`Click “${label}” when you are ready to run it.`:`For example, choose “${value}”.`,best:'Read the short description nearby and pick the option that matches your goal.',recommended:isButton?'Review the fields above before clicking.':`Start with ${value}.`,risk};
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
    if(element.dataset.helpDecorated||element.id==='closeContextHelp'||element.classList.contains('help-trigger')||element.classList.contains('page-help'))return;
    if(element.matches('input[type="hidden"]'))return;
    if(element.closest?.('.thought-container'))return;
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
    const names={
        chit_assistant_cpu:'Everyday assistant',
        chit_cpu_learning:'Compact learning',
        chit_english_foundation:'English foundations',
        chit_english_foundation_6l_256:'Stage 1: English & Grammar Foundation (6L-256)',
        chit_conversation_reasoning_6l_256:'Stage 2: Conversation & Reasoning (6L-256)',
        chit_knowledge_behavior_6l_256:'Stage 3: Knowledge & Behavior (6L-256)',
        chit_v2_6l_256:'Full Unified Curriculum (6L-256)',
        chit_1mb:'1 MB Extended Corpus',
        chit_1mb_eval_100kb:'1 MB Corpus (Fast 100 KB Review)',
        chit_english_mixed:'Mixed English practice',
        chit_strong:'Extended study',
        chit_tiny:'Small and quick',
        chit_train_txt:'Text-file practice',
        chit_bpe_experiment:'Tokenizer experiment',
        chit_byte_experiment:'Byte-token experiment',
        chit_rope_512_candidate:'Long-context candidate',
        chit_rope_512_rescue:'Long-context recovery'
    };
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
    const intro=document.createElement('p');intro.textContent=name==='chit_assistant_cpu'?'A balanced everyday assistant plan that studies all 7 Task skills together. Check its files and settings before you train.':name==='chit_v2_6l_256'?'The complete 6-layer unified curriculum across English prose, grammar, conversation, reasoning, knowledge, and honest behavior.':name.includes('conversation_reasoning')?'Stage 2 curriculum: builds multi-turn conversation and step-by-step reasoning skills on top of Stage 1 English foundations.':name.includes('knowledge_behavior')?'Stage 3 curriculum: teaches factual Q&A, memory grounding, and honest behavior when facts are missing or conflicting.':name.includes('foundation')||name.includes('mixed')?'An English-focused plan that builds strong grammar, sentence structure, and reading comprehension.':name.includes('experiment')?'An experimental plan for comparing how Chit reads text.':'A prepared learning plan with set model size, study schedule, and Task-header training material.';
    const facts=document.createElement('div');facts.className='config-facts';
    facts.append(configField('Training updates',`${training.max_steps??'Not set'} steps. Each step updates the model once; more steps take longer.`));
    facts.append(configField(byteTokenizer?'Context window (bytes)':'Context window (tokens)',`${model.block_size??'Not set'} ${byteTokenizer?'bytes':'tokens'} at a time. A longer window uses more memory and compute.`));
    facts.append(configField('Model size',`${model.n_layer??'Not set'} layers · ${model.n_head??'Not set'} attention heads · ${model.n_embd??'Not set'} internal width. Matches the 6L-256 byte architecture.`));
    facts.append(configField('Training device',cfg.device||'Chosen automatically by the server'));
    if(training.batch_size)facts.append(configField('Examples per update',`${training.batch_size}. Larger batches use more memory.`));
    if(training.learning_rate)facts.append(configField('Learning rate',`${training.learning_rate}. This controls the size of each learning update; a value that is too high can make training unstable.`));
    if(training.eval_interval)facts.append(configField('Progress checks',`The server checks learning quality every ${training.eval_interval} updates.`));
    const sources=Array.isArray(data.sources)?data.sources:[];
    if(sources.length){const weightTotal=sources.reduce((sum,source)=>sum+Math.max(0,Number(source.weight)||0),0);facts.append(configField('Weighted text collections',sources.map(source=>{const weight=Math.max(0,Number(source.weight)||0),share=weightTotal?Math.round(weight/weightTotal*100):0;return `${String(source.path||'Unnamed file').split(/[\\/]/).pop()} · about ${share}% of sampled text`}).join(' · ')));if(data.eval_file)facts.append(configField('Combined review text',String(data.eval_file).split(/[\\/]/).pop()))}
    else{if(data.train_file)facts.append(configField('Training text',String(data.train_file).split(/[\\/]/).pop()));if(data.eval_file)facts.append(configField('Review text',String(data.eval_file).split(/[\\/]/).pop()))}
    const tokenizerName=tokenizer.name||'byte-utf8 (default)';facts.append(configField('Text reader',tokenizerName==='byte-utf8'?'Reads UTF-8 one byte at a time (256 byte vocabulary). No words are ever unknown.':tokenizerName==='bpe-tokenizers-json-v1'?'Uses a saved vocabulary to read common pieces of text together.':'Uses '+tokenizerName));
    facts.append(configField('Smart study method','Starts 70% of study windows cleanly at a "Task:" header and focuses learning on Chit\'s answers (Chit: / Reasoning: / Answer:) instead of memorizing user questions.'));
    if(tokenizer.sha256)facts.append(configField('Tokenizer fingerprint',`${tokenizer.sha256.slice(0,16)}… · identifies the vocabulary this plan expects.`));
    if(tokenizer.vocab_size)facts.append(configField('Vocabulary size',`${tokenizer.vocab_size} text pieces`));
    if(cfg.seed!==undefined)facts.append(configField('Repeatable setup',`Seed ${cfg.seed} makes random choices easier to reproduce.`));
    if(active.ok){const actual=active.data.tokenizer?.name,expected=tokenizer.name||'byte-utf8';facts.append(configField('Currently active reader',actual?`${actual}${expected===actual?' · matches this plan':` · this plan expects ${expected}`}`:'Not reported · the UI cannot confirm a match'))}
    const note=document.createElement('p');note.className='notice';note.textContent='This is what the selected plan will ask the training system to use. Training creates a candidate model; Chit keeps serving the current model until training succeeds and the candidate is promoted. Check the Training library for missing or short files first.';
    panel.replaceChildren();const heading=document.createElement('h3');heading.textContent=learningPlanName(name);panel.append(heading,intro,facts,note);
}

async function renderJobs() {
    const [rJobs, rCands, rModel] = await Promise.all([
        req('/_ui/train/jobs'),
        req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'GET',path:'/candidates'})}),
        req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'GET',path:'/model'})})
    ]);
    const liveStampEl = document.getElementById('studioLiveStamp');
    const liveTsRaw = (rModel.ok && rModel.data?.checkpoint_timestamp) ? rModel.data.checkpoint_timestamp : null;
    const liveStampFormatted = liveTsRaw ? new Date(liveTsRaw).toLocaleString() : null;
    if (liveStampEl) {
        liveStampEl.textContent = liveStampFormatted || 'None (Not initialized)';
    }
    const list = $('#jobList');
    if (!rJobs.ok) {
        list.textContent = 'Could not load learning history. ' + friendlyError(rJobs.data, rJobs.status);
        return;
    }
    list.replaceChildren();
    
    const cands = (rCands.ok && rCands.data?.candidates) ? Object.fromEntries(rCands.data.candidates.map(c => [c.job_id, c])) : {};

    if (rJobs.data.jobs.length === 0) {
        list.innerHTML = '<div class="status" style="text-align: center; padding: 20px;">No recent jobs.</div>';
        return;
    }
    
    rJobs.data.jobs.forEach(job => {
        const card = document.createElement('div');
        card.className = 'job-card';
        const stateCls = 'state-' + job.state;
        const header = document.createElement('div');
        header.className = 'job-header';
        const id = document.createElement('div');
        id.style.fontWeight = 'bold';
        id.textContent = `Job: ${String(job.id || '').slice(0, 8)}…`;
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
        step.textContent = job.state==='running'?`Learning progress - step ${job.step ?? 0} of ${job.max_steps ?? '?'}`:job.state==='succeeded'?'Chit finished this learning session':`Progress - step ${job.step ?? 0} of ${job.max_steps ?? '?'}`;
        const loss = document.createElement('span');
        loss.textContent = `Loss: ${Number.isFinite(job.latest?.eval_loss) ? job.latest.eval_loss.toFixed(4) : 'N/A'}`;
        const plan = document.createElement('span');
        plan.textContent = `Plan: ${job.metadata?.config_name || 'Unknown'}`;
        plan.style.marginLeft = '12px';
        meta.append(step, loss, plan);
        card.append(header, progress, meta);
        
        if(['queued','running'].includes(job.state)){
            const actions = document.createElement('div');
            actions.className = 'actions';
            actions.style.marginTop = '10px';
            const btn = document.createElement('button');
            btn.className = 'danger';
            btn.textContent = 'Stop learning session';
            btn.addEventListener('click', async () => {
                if(!confirm('Stop this learning session immediately?')) return;
                const cr = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:`/train/${job.id}/cancel`})});
                if(cr.ok) setTimeout(renderJobs, 500);
            });
            actions.appendChild(btn);
            card.appendChild(actions);
        } else if (job.state === 'succeeded') {
            const c = cands[job.id] || {};
            const rawTs = c.checkpoint_timestamp;
            const ts = rawTs ? new Date(rawTs).toLocaleString() : 'No checkpoint';
            const isLive = ts !== 'No checkpoint' && (
                job.promoted ||
                (liveTsRaw && rawTs && new Date(rawTs).getTime() === new Date(liveTsRaw).getTime()) ||
                (liveStampFormatted && ts === liveStampFormatted)
            );
            const liveBadge = isLive ? `<span style="color:var(--success); font-weight:bold; margin-left: 8px;">(Currently Live AI)</span>` : '';
            const evalHtml = c.evaluation ? 
                `<b>Safety Test:</b> <span style="color:${c.evaluation.behavioral_gate?.gate_pass ? 'var(--success)' : 'var(--danger)'}; font-weight:bold;">${c.evaluation.behavioral_gate?.gate_pass ? 'Passed' : 'Failed'}</span> (Checked ${c.evaluation.behavioral_gate?.case_ratings?.length || 0} rules)` : 
                `<i>Safety Test: Not tested yet</i>`;
                
            let bridgeHtml = '';
            if (c.bridge_benchmark) {
                if (c.bridge_benchmark.status === 'running') {
                    bridgeHtml = `
                        <div style="margin: 6px 0; font-size: 12px;">
                            <b>Bridge Quality & Calibration:</b> <span style="color:var(--accent); font-weight:bold;">Running bridge evaluation and calibration analysis in background…</span>
                        </div>`;
                } else if (c.bridge_benchmark.status === 'failed') {
                    bridgeHtml = `
                        <div style="margin: 6px 0; font-size: 12px;">
                            <b>Bridge Quality & Calibration:</b> <span style="color:var(--danger); font-weight:bold;">Analysis failed: ${safeMarkdown(c.bridge_benchmark.error || 'Unknown error')}</span>
                        </div>`;
                } else {
                    const b = c.bridge_benchmark;
                    const mathPct = Math.round((b.arithmetic_exact_match !== undefined ? b.arithmetic_exact_match : 0) * 100);
                    const eceVal = b.expected_calibration_error !== undefined ? b.expected_calibration_error.toFixed(3) : 'N/A';
                    const latVal = b.p95_latency_ms ? (b.p95_latency_ms / 1000).toFixed(1) + 's' : 'N/A';
                    const truncPct = Math.round((b.truncated_before_stop_rate !== undefined ? b.truncated_before_stop_rate : 0) * 100);
                    const loopPct = Math.round((b.loop_rate !== undefined ? b.loop_rate : 0) * 100);

                    bridgeHtml = `
                        <div style="margin: 6px 0; font-size: 12px; line-height: 1.6;">
                            <b>Bridge Quality & Calibration:</b>
                            <div style="margin-top: 4px; display: flex; flex-wrap: wrap; gap: 6px;">
                                <span class="metric-badge" style="background:#1e3a29; border:1px solid #28a745; color:#a3e9b9; padding:2px 8px; border-radius:4px; cursor:help;" 
                                      title="Math Exactness: Percentage of arithmetic questions answered 100% accurately using symbolic calculator tools without hallucinations.">
                                    🧮 Math Exactness: ${mathPct}%
                                </span>
                                <span class="metric-badge" style="background:#1a334d; border:1px solid #17a2b8; color:#a6d8f0; padding:2px 8px; border-radius:4px; cursor:help;" 
                                      title="Calibration Error (ECE): Measures how honest the model's confidence scores are. Lower is better (0.0 means perfect truthfulness).">
                                    🎯 Calibration Error (ECE): ${eceVal}
                                </span>
                                <span class="metric-badge" style="background:#3d2f1f; border:1px solid #ffc107; color:#ffe8a1; padding:2px 8px; border-radius:4px; cursor:help;" 
                                      title="P95 Latency: 95% of user queries finish faster than this duration. Lower is faster.">
                                    ⚡ Speed (P95): ${latVal}
                                </span>
                                <span class="metric-badge" style="background:#332630; border:1px solid #6c757d; color:#e0d0da; padding:2px 8px; border-radius:4px; cursor:help;" 
                                      title="Truncation Rate: Percentage of replies cut short by memory budget limits before finishing terminal punctuation.">
                                    ✂️ Incomplete: ${truncPct}%
                                </span>
                                <span class="metric-badge" style="background:#262a33; border:1px solid #6c757d; color:#d0d7e0; padding:2px 8px; border-radius:4px; cursor:help;" 
                                      title="Degenerate Loops: Frequency of repetitive looping words or token stuttering. 0% is ideal.">
                                    🔁 Word Loops: ${loopPct}%
                                </span>
                            </div>
                        </div>`;
                }
            } else {
                bridgeHtml = `<div style="font-size:12px; margin: 4px 0; color:var(--text-muted, #888);"><i>Bridge Quality & Calibration: Not analyzed yet</i></div>`;
            }

            const isBenchmarking = c.bridge_benchmark?.status === 'running';
            const candDiv = document.createElement('div');
            candDiv.style.marginTop = '10px';
            candDiv.style.paddingTop = '10px';
            candDiv.style.borderTop = '1px dashed var(--accent)';
            
            candDiv.innerHTML = `
                <div style="font-size:12px; margin-bottom:4px; display:inline-block;" class="job-ai-stamp" id="candStamp_${job.id}"><b>Job Checkpoint:</b> ${ts} ${liveBadge}</div><br>
                <div style="font-size:12px; margin: 4px 0;">${evalHtml}</div>
                ${bridgeHtml}
                <div style="font-size:11px; color:var(--text-muted, #aaa); margin: 6px 0; line-height: 1.4; padding: 6px 8px; background: rgba(255,255,255,0.03); border-radius: 4px; border-left: 2px solid var(--accent);">
                    💡 <b>What is the Bridge?</b> The Bridge coordinates communication between your chat/generate prompts and Chit's neural brain. Benchmarking measures how effectively it prevents word loops, enforces memory budgets, offloads arithmetic, and calibrates confidence for user-friendly, accurate output.
                </div>
                <div class="actions" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px;">
                    <button class="secondary eval-btn" data-id="${job.id}" title="Tests candidate against the 50 Golden Set behavioral safety rules.">Test safety rules</button>
                    <button class="secondary bench-btn" data-id="${job.id}" ${isBenchmarking ? 'disabled' : ''} 
                            title="The Bridge sits between your chat/generate requests and Chit's brain. Click to benchmark how well it guides the model and automatically prepare confidence calibration.">
                        ${isBenchmarking ? '📊 Analyzing bridge…' : '📊 Benchmark Bridge & Calibrate'}
                    </button>
                    <button class="primary promote-btn" data-id="${job.id}" ${c.evaluation?.behavioral_gate?.gate_pass ? '' : 'disabled'}
                            title="Promotes this candidate to be the live served model and activates its calibrated confidence curve.">
                        Make this the Live AI
                    </button>
                </div>
            `;
            
            card.appendChild(candDiv);
        }
        
        list.appendChild(card);
    });
    
    // Wire up candidate buttons
    document.querySelectorAll('.eval-btn').forEach(btn => btn.addEventListener('click', async (e) => {
        const id = e.target.dataset.id;
        e.target.textContent = 'Testing...';
        e.target.disabled = true;
        await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:`/candidates/${id}/evaluate`})});
        alert('Test started in the background. Refresh in a minute.');
    }));

    document.querySelectorAll('.bench-btn').forEach(btn => btn.addEventListener('click', async (e) => {
        const id = e.target.dataset.id;
        e.target.textContent = '📊 Analyzing bridge…';
        e.target.disabled = true;
        const res = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:`/candidates/${id}/benchmark`})});
        if (res.ok) {
            alert('Bridge benchmark started in the background. The Bridge is testing exact math, ECE confidence calibration, memory truncation, and speed. Refresh in a minute to see results.');
            setTimeout(renderJobs, 1000);
        } else {
            alert('Could not start benchmark: ' + (res.data?.detail || res.status));
            e.target.textContent = '📊 Benchmark Bridge & Calibrate';
            e.target.disabled = false;
        }
    }));
    
    document.querySelectorAll('.promote-btn').forEach(btn => btn.addEventListener('click', async (e) => {
        const id = e.target.dataset.id;
        if (!confirm('Promote this tested version to be your live AI?')) return;
        e.target.textContent = 'Making live...';
        e.target.disabled = true;
        try {
            const r = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:`/candidates/${id}/promote`})});
            if (r.ok) {
                alert('Success! The live AI has been hot-swapped.');
                await refreshHealth();
                await renderJobs();
            } else {
                alert('Promotion failed: ' + (r.data?.detail || r.status));
                e.target.textContent = 'Make this the Live AI';
                e.target.disabled = false;
            }
        } catch(err) {
            e.target.textContent = 'Make this the Live AI';
            e.target.disabled = false;
        }
    }));
    
    // Add dynamically injected buttons to tooltip system
    document.querySelectorAll('.eval-btn, .bench-btn, .promote-btn, .job-ai-stamp').forEach(addHelpTrigger);

    // Auto-poll while training jobs or candidate benchmarks are running
    const hasActiveTask = rJobs.data.jobs.some(j => ['queued', 'running'].includes(j.state)) ||
                          Object.values(cands).some(c => c.bridge_benchmark?.status === 'running');
    if (hasActiveTask) {
        if (!window._jobsPollTimer) {
            window._jobsPollTimer = setTimeout(() => {
                window._jobsPollTimer = null;
                renderJobs();
            }, 3000);
        }
    } else if (window._jobsPollTimer) {
        clearTimeout(window._jobsPollTimer);
        window._jobsPollTimer = null;
    }
}

$('#startTrain').addEventListener('click', async () => {
    window.selectedRecipe=$('#trainConfig').value;
    if (!window.selectedRecipe) {
        alert('Choose a learning plan first.');
        return;
    }
    const forcePromote=$('#forcePromote').checked;
    if(forcePromote&&!confirm('Force promotion bypasses evaluation and reviewer gates and replaces the live model when training succeeds. Continue?'))return;
    const status = $('#trainStatus');
    status.textContent = 'Igniting forge...';
    try {
        const r = await req('/_ui/train', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ config: window.selectedRecipe, init: 'auto', promote: forcePromote, force_promote: forcePromote })
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
        const liveStampEl = document.getElementById('studioLiveStamp');
        if (liveStampEl) {
            if (model.ok && model.data?.checkpoint_timestamp) {
                liveStampEl.textContent = new Date(model.data.checkpoint_timestamp).toLocaleString();
            } else {
                liveStampEl.textContent = 'None (Not initialized)';
            }
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
    else if(kind==='reasoning'){
        item.input=$('#lessonInput')?.value.trim()||'';
        item.reasoning=$('#lessonReasoning')?.value.trim()||'';
        item.answer=$('#lessonReasoningAnswer')?.value.trim()||'';
    }else{item.question=$('#lessonQuestion').value.trim();item.answer=$('#lessonAnswer').value.trim()}
    return item;
}

async function saveLesson(){
    const item=lessonPayload();const status=$('#lessonStatus');status.textContent='Saving lesson…';
    if((item.kind==='text'&&!item.text)||(item.kind==='qa'&&(!item.question||!item.answer))||(item.kind==='reasoning'&&(!item.input||!item.reasoning||!item.answer))){status.textContent='Fill in all fields for the lesson before saving it.';return}
    const r=await callApi('POST','/knowledge',{}, {items:[item]});
    status.textContent=r.ok?(r.data.duplicates?'That lesson is already saved.':'Lesson saved. Train Chit when you’re ready for it to learn this material.'):friendlyError(r.data,r.status);
    if(r.ok){$('#lessonText').value='';$('#lessonQuestion').value='';$('#lessonAnswer').value='';if($('#lessonInput'))$('#lessonInput').value='';if($('#lessonReasoning'))$('#lessonReasoning').value='';if($('#lessonReasoningAnswer'))$('#lessonReasoningAnswer').value='';loadKnowledge();updateKnowledgePipeline()}
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
        const content=document.createElement('p');content.className='memory-content';content.textContent=entry.kind==='qa'?payload.answer:entry.kind==='reasoning'?`Steps: ${payload.reasoning||''}\nAnswer: ${payload.answer||''}`:payload.text;
        const kindLabel=entry.kind==='qa'?'Q&A (Task: knowledge)':entry.kind==='reasoning'?'Reasoning (Task: reasoning)':'Passage (Task: prose)';
        const meta=document.createElement('p');meta.className='status';meta.textContent=`${entry.status==='trained'?'Already learned':'Ready to learn'} · ${kindLabel}${entry.source?` · ${entry.source}`:''}`;
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
    const forcePromote=$('#forcePromote').checked;
    if(forcePromote&&!confirm('Force promotion bypasses evaluation and reviewer gates and replaces the live model when training succeeds. Continue?'))return;
    const body={config:$('#trainConfig')?.value||window.selectedRecipe||'chit_cpu_learning',select:$('#lessonScope').value,init:'auto',promote:forcePromote,force_promote:forcePromote};
    const r=await callApi('POST','/knowledge/train',{},body);
    status.textContent=r.ok?'Chit has started learning your saved lessons. Follow progress below.':friendlyError(r.data,r.status);
    if(r.ok)renderJobs();
}

$('#lessonKind').addEventListener('change',()=>{const kind=$('#lessonKind').value;$('#lessonTextField').classList.toggle('hidden',kind!=='text');$('#lessonQaFields').classList.toggle('hidden',kind!=='qa');$('#lessonReasoningFields')?.classList.toggle('hidden',kind!=='reasoning')});
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



function taskBadgeInfo(task, requestedTask) {
    const names = {
        chat: 'Chat',
        knowledge: 'Knowledge',
        behavior: 'Behavior',
        grammar: 'Grammar',
        reasoning: 'Reasoning',
        prose: 'Prose',
        continue: 'Continue'
    };
    const descriptions = {
        chat: 'Everyday conversation skill (Task: chat). Used for friendly dialogue, greetings, and general help.',
        knowledge: 'Knowledge & Facts skill (Task: knowledge). Used when answering from saved memories, live web search, or Chit project facts.',
        behavior: 'Honesty & Boundaries skill (Task: behavior). Used when facts are missing, conflicting, ambiguous, or restricted by safety rules.',
        grammar: 'Grammar & Writing skill (Task: grammar). Used for fixing sentences, verb tenses, and rewriting text.',
        reasoning: 'Step-by-Step Reasoning skill (Task: reasoning). Used for working through logic or math steps before answering.',
        prose: 'Prose & Reading skill (Task: prose). Used for reading comprehension and explaining words in context.',
        continue: 'Raw Text Continuation (Task: continue). Extends your text directly without chat formatting.'
    };
    const key = task || 'chat';
    const autoPicked = (!requestedTask || requestedTask === 'chat') && key !== 'chat';
    return {
        label: `Task: ${names[key] || key}${autoPicked ? ' (auto)' : ''}`,
        title: `${descriptions[key] || 'Task skill used for this reply.'}${autoPicked ? ' Chit\'s Router automatically chose this skill based on your message.' : ''}`
    };
}

function sourceBadgeInfo(source) {
    const map = {
        tool: { label: '🧮 Calculator / Tool', title: 'Answered with 100% exactness by Chit\'s built-in calculator or date tool rather than guessing.' },
        extractive: { label: '📌 Memory Fact', title: 'Answered directly from your saved memories or session facts so no details were made up.' },
        abstain: { label: '🛡️ Safety / Honesty Guard', title: 'Held back from guessing because required facts were missing or the request crossed a safety boundary.' },
        model: { label: '🧠 Neural Brain', title: 'Written by Chit\'s neural network and checked by the Bridge for clarity and loops.' }
    };
    return map[source] || null;
}

function addBubble(role, text, metadata = {}) {
    const b = document.createElement('div');
    b.className = 'bubble ' + role;
    
    // 0. If web grounded, prepend web search grounding badge with clickable domain badges
    if (role === 'chit' && metadata && metadata.web_grounded) {
        const webGroundedHeader = document.createElement('div');
        webGroundedHeader.className = 'web-grounded-header';
        webGroundedHeader.title = 'Chit searched the web for live facts and used the snippets below to ground this answer.';
        webGroundedHeader.innerHTML = `🌐 <strong>Grounded via Web Search</strong>`;
        
        const webSources = Array.isArray(metadata.web_sources) ? metadata.web_sources : [];
        if (webSources.length > 0) {
            const badgesWrap = document.createElement('span');
            badgesWrap.className = 'web-source-badges';
            badgesWrap.style.marginLeft = '8px';
            badgesWrap.style.display = 'inline-flex';
            badgesWrap.style.gap = '6px';
            badgesWrap.style.flexWrap = 'wrap';
            webSources.forEach(s => {
                const domain = s.domain || (s.url ? s.url.replace(/^https?:\/\//, '').split('/')[0].replace(/^www\./, '') : 'source');
                const badge = document.createElement('a');
                badge.className = 'web-source-pill';
                badge.href = s.url || '#';
                badge.target = '_blank';
                badge.rel = 'noopener noreferrer';
                badge.textContent = `[${domain}]`;
                badge.title = s.title ? `Web source — ${s.title}: ${s.snippet || ''}` : (s.snippet || s.url || 'Open web source in a new tab.');
                badge.style.fontSize = '11px';
                badge.style.padding = '1px 6px';
                badge.style.borderRadius = '3px';
                badge.style.background = 'rgba(255,255,255,0.08)';
                badge.style.color = 'var(--text-accent, #64B5F6)';
                badge.style.textDecoration = 'none';
                badge.style.border = '1px solid rgba(100,181,246,0.3)';
                badgesWrap.appendChild(badge);
            });
            webGroundedHeader.appendChild(badgesWrap);
        } else if (metadata.sources && metadata.sources.length) {
            const countSpan = document.createElement('span');
            countSpan.textContent = ` (${metadata.sources.length} sources)`;
            webGroundedHeader.appendChild(countSpan);
        }
        b.appendChild(webGroundedHeader);
    }

    // 1. If thoughts exist, prepend collapsible thought container at the top of the bubble
    if (role === 'chit' && metadata && metadata.thoughts) {
        const thoughtDetails = document.createElement('details');
        thoughtDetails.className = 'thought-container';
        
        const tokenLabel = metadata.thought_tokens ? `${metadata.thought_tokens} tokens` : 'trace';
        thoughtDetails.innerHTML = `
            <summary title="Click to view or hide the step-by-step thinking Chit wrote before giving its final answer.">💭 Thought process (${tokenLabel})</summary>
            <div class="thought-body">${safeMarkdown(metadata.thoughts)}</div>
        `;
        b.appendChild(thoughtDetails);
    }
    // 2. Main response body
    const content = document.createElement('div');
    content.className = 'bubble-content';
    if (role === 'chit') {
        content.innerHTML = safeMarkdown(text);
    } else {
        content.textContent = text;
    }
    b.appendChild(content);

    // 3. Uncertainty / Incompleteness Warning Notice
    if (role === 'chit' && (metadata.is_uncertain || metadata.is_incomplete)) {
        const notice = document.createElement('div');
        notice.className = 'retrieval-notice';
        const reasonText = metadata.is_incomplete 
            ? '⚡ Generation was cut short by the response length limit before finishing the sentence.' 
            : `⚠️ Chit has low confidence in this answer (${Math.round((metadata.confidence || 0) * 100)}%). Double-check important details or click Search Web.`;
        notice.title = metadata.is_incomplete
            ? 'The reply hit the maximum token limit before reaching a period. Try asking a more specific question.'
            : 'Chit\'s confidence score is below 40%, meaning the model was unsure of its wording.';
        notice.innerHTML = `<span>${reasonText}</span>`;
        b.appendChild(notice);
    }

    // 4. Action buttons (Copy only copies the final answer, NOT the thoughts)
    if (role === 'chit') {
        const actions = document.createElement('div');
        actions.className = 'bubble-actions';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'action-btn';
        copyBtn.textContent = 'Copy';
        copyBtn.onclick = async () => {try{await navigator.clipboard.writeText(text);copyBtn.textContent='Copied';setTimeout(()=>copyBtn.textContent='Copy',1800)}catch{copyBtn.textContent='Clipboard unavailable'}};
        const regenerate=document.createElement('button');regenerate.type='button';regenerate.className='action-btn';regenerate.textContent='Try another answer';regenerate.onclick=async ()=>{
            const messages=document.querySelectorAll('.bubble.user');
            if(messages.length){
                $('#chatInput').value=messages[messages.length-1].textContent;
                window._nextChatTemperature = 0.25;
                $('#sendChat').click();
            }
        };
        actions.appendChild(copyBtn);
        actions.appendChild(regenerate);

        const effTask = metadata.effective_task || metadata.plan?.effective_task || metadata.task;
        if (effTask) {
            const tInfo = taskBadgeInfo(effTask, metadata.requested_task);
            const tBadge = document.createElement('span');
            tBadge.className = 'task-badge';
            tBadge.textContent = tInfo.label;
            tBadge.title = tInfo.title;
            actions.appendChild(tBadge);
        }

        const sInfo = sourceBadgeInfo(metadata.source);
        if (sInfo) {
            const sBadge = document.createElement('span');
            sBadge.className = 'source-badge';
            sBadge.textContent = sInfo.label;
            sBadge.title = sInfo.title;
            actions.appendChild(sBadge);
        }

        if (typeof metadata.confidence === 'number') {
            const pct = Math.round(metadata.confidence * 100);
            const confBadge = document.createElement('span');
            confBadge.className = 'conf-badge ' + (metadata.is_uncertain ? 'conf-low' : 'conf-high');
            confBadge.textContent = `${pct}% conf`;
            confBadge.title = metadata.is_uncertain
                ? `Low confidence (${pct}%): Chit was unsure when writing this reply. Please verify facts or try Search Web.`
                : `Confidence score (${pct}%): How steady and certain Chit was when choosing the words in this reply${metadata.is_calibrated ? ' (calibrated for accuracy)' : ''}.`;
            actions.appendChild(confBadge);
        }

        if (metadata.needs_retrieval || metadata.is_uncertain) {
            const webBtn = document.createElement('button');
            webBtn.type = 'button';
            webBtn.className = 'action-btn retrieval-btn';
            webBtn.innerHTML = '🌐 Search Web';
            webBtn.title = 'Ask Chit to answer your last message again using live internet search.';
            webBtn.onclick = () => {
                const messages = document.querySelectorAll('.bubble.user');
                if (messages.length) {
                    $('#chatInput').value = messages[messages.length - 1].textContent;
                    window._nextChatSearch = true;
                    $('#sendChat').click();
                }
            };
            actions.appendChild(webBtn);
        }

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

$('#chatTask')?.addEventListener('change', () => {
    const taskVal = $('#chatTask').value;
    const isCont = taskVal === 'continue';
    const thinkEl = $('#thinkToggle'), searchEl = $('#searchToggle');
    if (thinkEl) {
        thinkEl.disabled = isCont;
        if (isCont) thinkEl.checked = false;
        else if (taskVal === 'reasoning') thinkEl.checked = true;
        if (thinkEl.parentElement) {
            thinkEl.parentElement.style.opacity = isCont ? '0.45' : '1';
            thinkEl.parentElement.title = isCont
                ? 'Step-by-step thinking is disabled in Continue Raw Text mode.'
                : 'Ask Chit to work through the problem step by step before giving its final answer.';
        }
    }
    if (searchEl) {
        searchEl.disabled = isCont;
        if (isCont) searchEl.checked = false;
        if (searchEl.parentElement) {
            searchEl.parentElement.style.opacity = isCont ? '0.45' : '1';
            searchEl.parentElement.title = isCont
                ? 'Web search is disabled in Continue Raw Text mode.'
                : 'Let Chit search the web for fresh facts before answering your message.';
        }
    }
});

$('#sendChat').addEventListener('click', async () => {
    const box = $('#chatInput'), message = box.value.trim();
    if (!message) return;
    const wasContinuing = Boolean(chatId);
    
    addBubble('user', message);
    box.value = '';
    $('#sendChat').disabled = true;
    
    try {
        const tempOverride = window._nextChatTemperature;
        window._nextChatTemperature = undefined;
        const searchOverride = window._nextChatSearch || false;
        window._nextChatSearch = undefined;
        const selectedTask = $('#chatTask')?.value || 'chat';
        const isContinueTask = selectedTask === 'continue';
        const searchChecked = !isContinueTask && ($('#searchToggle')?.checked || false);
        const think = !isContinueTask && ($('#thinkToggle')?.checked || selectedTask === 'reasoning');
        const payload = { message, session_id: chatId, task: selectedTask, think };
        if (typeof tempOverride === 'number') payload.temperature = tempOverride;
        if (!isContinueTask && (searchOverride || searchChecked)) payload.search = true;

        const r = await callApi('POST', '/chat', {}, payload);
        
        if (!r.ok) throw new Error(friendlyError(r.data,r.status));
        
        chatId = r.data.session_id || chatId;
        const rawRecalled = r.data?.metadata?.memory_ids;
        const genuineMemories = Array.isArray(rawRecalled) ? rawRecalled.filter(id => id && id !== 'web-search') : [];
        const hasMemory = genuineMemories.length > 0;
        const recordedTemp = tempOverride !== undefined 
            ? tempOverride 
            : (hasMemory ? 0 : 'adaptive');
        const recordedTopK = tempOverride !== undefined 
            ? 3 
            : (hasMemory ? 1 : 'adaptive');
        recordResponseEvidence({
            mode: `Chat (${selectedTask})`,
            prompt: message,
            tokens: 'server default',
            temperature: recordedTemp,
            topK: recordedTopK,
            continued: wasContinuing,
            response: r.data
        });
        
        $('#chatSession').textContent = chatId ? `Session ${chatId}` : 'No saved session';
        if (!wasContinuing && chatId) {
            updateSessionTitle(chatId).catch(console.error);
        }
        if (typeof loadChatFacts === 'function') {
            loadChatFacts().catch(console.error);
        }
        if(hasMemory){
            const breadcrumb=document.createElement('div');breadcrumb.className='memory-breadcrumb';
            breadcrumb.textContent=`Chit used ${genuineMemories.length} saved ${genuineMemories.length===1?'memory':'memories'} to shape this reply.`;
            $('#chatlog').appendChild(breadcrumb);
        }
        addBubble('chit', r.data.text || '', Object.assign({ requested_task: selectedTask }, r.data?.metadata || {}, r.data || {}));
        
    } catch (e) {
        addBubble('system', e.message);
    } finally {
        $('#sendChat').disabled = false;
    }
});


async function loadChatFacts() {
    if (!chatId) {
        document.getElementById('chatThoughtsCard').style.display = 'none';
        return;
    }
    document.getElementById('chatThoughtsCard').style.display = 'block';
    try {
        const r = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'GET',path:`/sessions/${chatId}/facts`})});
        if (r.ok && r.data && r.data.facts) {
            const facts = r.data.facts;
            document.getElementById('chatFactsList').innerHTML = Object.entries(facts).length === 0 ? '<p class="status">No facts extracted yet.</p>' : '';
            for (const [k, v] of Object.entries(facts)) {
                const div = document.createElement('div');
                div.className = 'memory-item';
                div.innerHTML = `<b>` + esc(k) + `</b>: ` + esc(v);
                document.getElementById('chatFactsList').appendChild(div);
            }
        }
    } catch (e) {
        document.getElementById('factsStatus').textContent = 'Could not load facts.';
    }
}
document.getElementById('refreshFactsBtn')?.addEventListener('click', loadChatFacts);
document.getElementById('clearFactsBtn')?.addEventListener('click', async () => {
    if (!chatId || !confirm('Clear all facts for this session?')) return;
    try {
        const r = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'DELETE',path:`/sessions/${chatId}/facts`})});
        if (r.ok) {
            document.getElementById('factsStatus').textContent = 'Facts cleared.';
            setTimeout(() => document.getElementById('factsStatus').textContent = '', 2000);
            await loadChatFacts();
        }
    } catch (e) {
        document.getElementById('factsStatus').textContent = 'Failed to clear facts.';
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
$('#genMode')?.addEventListener('change',()=>{
    const isCont=$('#genMode').value==='continue';
    const s=$('#genSearch'),t=$('#genThink'),taskSel=$('#genTask');
    if(s){s.disabled=isCont;if(isCont)s.checked=false;s.parentElement.style.opacity=isCont?'0.45':'1';s.parentElement.title=isCont?'Web search is only available when "How should Chit respond?" is set to "Answer my request".':'Searches the web for live facts before answering your request.';}
    if(t){t.disabled=isCont;if(isCont)t.checked=false;t.parentElement.style.opacity=isCont?'0.45':'1';t.parentElement.title=isCont?'Step-by-step thinking is only available when "How should Chit respond?" is set to "Answer my request".':'Turns on step-by-step thinking before giving the final answer.';}
    if(taskSel){taskSel.disabled=isCont;taskSel.style.opacity=isCont?'0.45':'1';taskSel.title=isCont?'Assistant skill selection is disabled in "Continue my text" mode because raw continuation uses Task: continue automatically.':controlHelp.genTask.what;}
});
$('#genTask')?.addEventListener('change',()=>{
    if($('#genTask').value==='reasoning' && $('#genThink') && !$('#genThink').disabled){
        $('#genThink').checked=true;
    }
});
$('#runGenerate').addEventListener('click',async()=>{
    const status=$('#genStatus');status.textContent='Generating…';status.classList.remove('error');
    try{
        const modeVal=$('#genMode').value;
        const selectedTask=modeVal==='continue'?'continue':($('#genTask')?.value||'chat');
        const body={
            prompt:$('#genPrompt').value.trim(),
            mode:modeVal,
            task:selectedTask,
            tokens:Number($('#genTokens').value),
            temperature:Number($('#genTemp').value),
            top_k:Number($('#genTopK').value),
            stop:[],
            search:modeVal!=='continue' && ($('#genSearch')?.checked || false),
            think:modeVal!=='continue' && ($('#genThink')?.checked || selectedTask==='reasoning'),
        };
        if(!body.prompt)throw new Error('Write a prompt first.');
        const r=await callApi('POST','/generate',{},body);
        if(!r.ok)throw new Error(friendlyError(r.data,r.status));
        $('#genResult').textContent=typeof r.data?.text==='string'?r.data.text:pretty(r.data);
        
        const metaBox=$('#genMeta');
        if(metaBox){
            metaBox.replaceChildren();
            const meta=Object.assign({}, r.data?.metadata||{}, r.data||{});
            if(meta.web_grounded){
                const pill=document.createElement('div');
                pill.className='web-grounded-header';
                pill.title='Chit searched the web for live facts and used the retrieved snippets to ground this answer.';
                const count=meta.sources?.length?` (${meta.sources.length} sources)`:'';
                pill.innerHTML=`🌐 <strong>Grounded via Web Search</strong>${count}`;
                metaBox.appendChild(pill);
            }
            const effTask=meta.effective_task || meta.plan?.effective_task || selectedTask;
            if(effTask){
                const tInfo=taskBadgeInfo(effTask, selectedTask);
                const tBadge=document.createElement('span');
                tBadge.className='task-badge';
                tBadge.textContent=tInfo.label;
                tBadge.title=tInfo.title;
                metaBox.appendChild(tBadge);
            }
            const sInfo=sourceBadgeInfo(meta.source);
            if(sInfo){
                const sBadge=document.createElement('span');
                sBadge.className='source-badge';
                sBadge.textContent=sInfo.label;
                sBadge.title=sInfo.title;
                metaBox.appendChild(sBadge);
            }
            if(typeof meta.confidence==='number'){
                const pct=Math.round(meta.confidence*100);
                const badge=document.createElement('span');
                badge.className='conf-badge '+(meta.is_uncertain?'conf-low':'conf-high');
                badge.textContent=`${pct}% conf`;
                badge.title=meta.is_uncertain
                    ? `Low confidence (${pct}%): Chit was unsure when writing this reply. Double-check important facts.`
                    : `Confidence score (${pct}%): How steady and certain Chit was when choosing the words in this reply${meta.is_calibrated?' (calibrated for accuracy)':''}.`;
                metaBox.appendChild(badge);
            }
            if(meta.thoughts){
                const thoughtDetails=document.createElement('details');
                thoughtDetails.className='thought-container';
                thoughtDetails.style.width='100%';
                const tokenLabel=meta.thought_tokens?`${meta.thought_tokens} tokens`:'trace';
                thoughtDetails.innerHTML=`<summary title="Click to view or hide the step-by-step thinking Chit wrote before giving its final answer.">💭 Thought process (${tokenLabel})</summary><div class="thought-body">${safeMarkdown(meta.thoughts)}</div>`;
                metaBox.appendChild(thoughtDetails);
            }
            if(meta.is_uncertain || meta.is_incomplete){
                const notice=document.createElement('div');
                notice.className='retrieval-notice';
                const reason=meta.is_incomplete?'⚡ Generation was cut short by the response length limit before finishing the sentence.':`⚠️ Low model confidence (${Math.round((meta.confidence||0)*100)}%). Double-check important details.`;
                notice.title=meta.is_incomplete?'Increase "Response length" if you want a longer answer.':'Chit\'s confidence score is below 40%, meaning the model was unsure of its wording.';
                notice.innerHTML=`<span>${reason}</span>`;
                metaBox.appendChild(notice);
            }
        }

        recordResponseEvidence({mode:`${body.mode} (${selectedTask})`,prompt:body.prompt,tokens:body.tokens,temperature:body.temperature,topK:body.top_k,response:r.data});
        status.textContent='Done';
    }catch(e){status.textContent=e.message;status.classList.add('error')}
});
const routeGuides={
'Server health':['Check whether the server and AI brain are online and responding.','Nothing to enter.','Read-only. Reports whether a model is loaded and whether a training job is running.'],
'Service readiness':['Check whether the model, memory store, knowledge store, and request queue are ready for use.','Nothing to enter.','Read-only. Useful when the server is online and you want to verify every internal service is ready.'],
'Live model details':['See which AI checkpoint is currently active, its layer count, context window, and text reader (tokenizer).','Nothing to enter.','Read-only. Shows the live model architecture, device, and checkpoint timestamp.'],
'System metrics':['Check the server’s live processor (CPU), memory (RAM), and disk usage percentages.','Nothing to enter.','Read-only. Useful before starting a heavy training or benchmark run.'],
'Generate a response':['Ask Chit for a single one-time answer without creating or saving a conversation.','Your prompt, chosen task skill, response length, and optional Web search or Thinking toggles.','Read-only for saved conversations. Assistant mode can use relevant memories and pick the best Task skill.'],
'Continue raw text':['Continue a piece of text directly from where your words end (Task: continue).','A text prefix and maximum response length.','Does not create a saved conversation. Useful for completing an unfinished sentence or paragraph.'],
'Chat message':['Send a message in a continuing conversation with automatic Task skill selection and memory recall.','Your message, optional task skill, and an optional conversation ID to continue an earlier chat.','Creates or updates a saved conversation, recalls relevant memories, and returns Chit’s reply and session ID.'],
'Create session':['Create a new empty conversation session before sending its first message.','Nothing to enter.','Creates a separate conversation ID. In everyday use, simply sending a Chat message creates a session automatically.'],
'List sessions':['See the saved conversations stored on the server.','Optional page limit and starting offset.','Read-only. Lists each conversation ID, message count, and summary.'],
'Read session':['Open one saved conversation and read its message history.','The 32-character conversation ID and how many messages to return.','Read-only. Copy the session ID from List sessions.'],
'Read facts':['See the personal facts (like your name or preferences) that Chit has automatically remembered during a conversation.','The 32-character conversation ID.','Read-only. Shows the key-value facts extracted from that chat session.'],
'Configure facts':['Turn automatic fact extraction on or off for a specific conversation session.','The 32-character conversation ID and enabled (true or false).','Updates the session setting. When enabled, Chit remembers personal details shared in that chat.'],
'Refresh facts':['Ask Chit to re-scan the conversation messages and update the remembered session facts right now.','The 32-character conversation ID.','Updates the extracted facts for that conversation based on its message history.'],
'Clear facts':['Tell Chit to permanently forget all personal facts extracted during a specific conversation.','The 32-character conversation ID.','Deletes the remembered facts for that session while keeping the chat messages intact.'],
'Read summary':['Read the short running summary that Chit keeps for a long conversation.','The 32-character conversation ID.','Read-only. Shows the progressive summary used when older messages scroll out of the context window.'],
'Configure summary':['Turn automatic conversation summarizing on or off for a specific session.','The 32-character conversation ID and enabled (true or false).','Updates the session setting. Summaries help Chit remember earlier context in long chats.'],
'Refresh summary':['Ask Chit to rebuild the running summary for a conversation right now.','The 32-character conversation ID.','Recomputes and saves the conversation summary from recent turns.'],
'Clear summary':['Delete the saved running summary for a specific conversation.','The 32-character conversation ID.','Removes the summary text for that session without deleting the messages.'],
'Delete session':['Permanently delete a saved conversation, its messages, remembered facts, and summary.','The 32-character conversation ID.','Permanently removes the conversation. The console asks you to confirm before sending.'],
'Save a memory':['Save a fact or personal preference into Chit’s long-term memory so future chats can recall it immediately.','The memory text, type (experience or fact), importance (0 to 1), and optional tags.','Stores the memory right away without needing to retrain the neural model.'],
'Search memories':['Find saved long-term memories that match a word or phrase.','A search keyword or phrase and maximum result count.','Read-only. Shows matching memories and their importance scores.'],
'Delete memory':['Permanently remove a saved memory so Chit no longer recalls it in future chats.','The memory ID from a search result.','Deletes that memory card immediately from the memory database.'],
'List training presets':['See all available learning plans (such as Everyday assistant and the 6L-256 staged curriculum configs).','Nothing to enter.','Read-only. Returns the list of learning plan names available in Studio.'],
'Train BPE tokenizer':['Train a byte-level BPE tokenizer asset from a learning plan’s corpus files and save it for training and live inference.','A learning plan name (config), target vocabulary size (default: 2000), and overwrite flag.','Creates the tokenizer asset beside the active checkpoint and at the config’s model_file path before training starts.'],
'Start training':['Start a background training run using a chosen learning plan.','A learning plan name, starting point (scratch, current, or auto), and force_promote flag.','Uses processor and memory resources to train a new candidate model while the current live AI keeps working.'],
'List training jobs':['See active and past training runs and their progress.','Nothing to enter.','Read-only. Returns job IDs, step counts, loss scores, and status.'],
'Read training job':['Check the detailed step progress, review loss, and status of one training job.','The 32-character training job ID.','Read-only. Shows whether the job is running, succeeded, failed, or promoted.'],
'Cancel training job':['Stop a training job that is currently queued or running.','The 32-character training job ID.','Cancels the background training run safely without affecting your current live AI.'],
'List candidates':['See all trained candidate checkpoints and their safety test and Bridge benchmark results.','Nothing to enter.','Read-only. Used by Studio to display finished candidate models.'],
'Evaluate candidate':['Run the 50 Golden Gate behavioral safety and honesty tests on a finished candidate model.','The 32-character training job ID of the candidate.','Runs safety grading in the background. A candidate must pass this gate before normal promotion.'],
'Benchmark candidate bridge':['Test how well the Bridge guides a candidate model (math exactness, confidence calibration, word loops, and speed) and fit its confidence curve.','The 32-character training job ID of the candidate.','Runs the Bridge benchmark and generates a calibrated confidence curve in the background.'],
'Promote candidate':['Make a tested candidate model your new live AI for all chats and generations.','The 32-character training job ID of a passing candidate.','Hot-swaps the live AI to the new checkpoint and archives the previous checkpoint for rollback.'],
'Rollback champion':['Restore the live AI back to a previously archived checkpoint using its SHA-256 fingerprint.','The SHA-256 fingerprint (to_sha256) of the archived checkpoint.','Immediately switches the live AI back to the specified earlier version.'],
'Reload champion':['Reload the live AI checkpoint and calibration curve from disk into server memory.','Nothing to enter.','Refreshes the in-memory model weights from checkpoints/latest.pt.'],
'Teach knowledge':['Save one or more lessons (facts, Q&A pairs, or step-by-step reasoning examples) into the training queue.','A list of lesson items (kind: text, qa, or reasoning).','Queues the lessons for future training. Set remember: true to also save them as immediate memories.'],
'List knowledge':['Browse saved lessons waiting to be trained or already included in a trained model.','Optional status filter (pending or trained), limit, and offset.','Read-only. Returns saved lesson items and their training status.'],
'Knowledge statistics':['See the count of lessons waiting to be learned vs. already learned.','Nothing to enter.','Read-only. Powers the Learning Pipeline counter on the Brain screen.'],
'Read knowledge entry':['Read the full text, question/answer, or reasoning steps of one saved lesson.','The lesson entry ID from List knowledge.','Read-only. Shows all fields and timestamps for that lesson.'],
'Delete knowledge entry':['Remove a saved lesson from the training queue so future training runs do not study it.','The lesson entry ID.','Deletes the lesson from the queue. Does not undo weights already trained into a model.'],
'Train on knowledge':['Start a background training run that studies your saved lessons from Teach Chit.','A learning plan name, how many times to repeat lessons, and whether to study all or pending lessons.','Trains a candidate model on your saved lessons. Lessons are marked trained once the candidate is promoted.'],
'Inspect training data':['Check whether a learning plan’s training and review text files exist and pass readiness checks.','A learning plan name (config).','Read-only. Reports file sizes, example counts, and any data warnings.'],
'Split corpus file':['Divide a raw text file in the server’s data folder into training and review (eval) files.','The source file name, learning plan, split style (paragraph or line), review fraction, and dry_run flag.','Keep dry_run: true to preview first. Setting dry_run: false writes the new train and review files.']
};
function guideInline(text){let value=String(text).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');value=value.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*]+)\*/g,'<em>$1</em>').replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|#[^\s)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');return value}
function guideSlug(text){return text.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')}
function renderApiGuide(markdown){
    const lines=markdown.replaceAll('\r','').split('\n'),out=[];let i=0,sectionOpen=false;
    const closeSection=()=>{if(sectionOpen){out.push('</section>');sectionOpen=false}};
    while(i<lines.length){const line=lines[i];if(!line.trim()){i++;continue}
        if(line.startsWith('```')){const code=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);i++;out.push(`<pre><code>${code.join('\n').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}</code></pre>`);continue}
        if(/^## /.test(line)){closeSection();const title=line.slice(3).replace(/\s+#.*$/,'');out.push(`<section class="guide-section" data-guide-section><h2 id="${guideSlug(title)}">${guideInline(title)}</h2>`);sectionOpen=true;i++;continue}
        const heading=line.match(/^(#{1,6})\s+(.+)$/);if(heading){const level=heading[1].length,title=heading[2].replace(/\s+#.*$/,'');out.push(`<h${level} id="${guideSlug(title)}">${guideInline(title)}</h${level}>`);i++;continue}
        if(i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){const cells=s=>s.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim());const headers=cells(line);out.push('<div class="guide-table-wrap"><table><thead><tr>'+headers.map(x=>`<th>${guideInline(x)}</th>`).join('')+'</tr></thead><tbody>');i+=2;while(i<lines.length&&lines[i].includes('|')){out.push('<tr>'+cells(lines[i]).map(x=>`<td>${guideInline(x)}</td>`).join('')+'</tr>');i++}out.push('</tbody></table></div>');continue}
        if(/^\s*[-*]\s+/.test(line)||/^\s*\d+\.\s+/.test(line)){const ordered=/^\s*\d+\./.test(line),tag=ordered?'ol':'ul',items=[];while(i<lines.length&&(/^\s*[-*]\s+/.test(lines[i])||/^\s*\d+\.\s+/.test(lines[i]))){items.push(`<li>${guideInline(lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/,''))}</li>`);i++}out.push(`<${tag}>${items.join('')}</${tag}>`);continue}
        const para=[line.trim()];i++;while(i<lines.length&&lines[i].trim()&&!/^(#{1,6}\s|```|\s*[-*]\s+|\s*\d+\.\s+)/.test(lines[i])&&!(i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])))para.push(lines[i++].trim());out.push(`<p>${guideInline(para.join(' '))}</p>`)
    }closeSection();return out.join('\n')
}
async function loadFullApiGuide(){const target=$('#fullApiGuide'),status=$('#apiGuideStatus');try{const response=await req('/_ui/api-guide');if(!response.ok)throw new Error(typeof response.data==='string'?response.data:'Guide could not be loaded.');target.innerHTML=renderApiGuide(response.data);status.textContent='Full ChitAPIGuide.md loaded. Search filters its numbered sections.';filterApiGuide()}catch(error){status.textContent='Could not load the full guide.';target.textContent=error.message}}
function filterApiGuide(){const query=$('#apiGuideSearch').value.trim().toLowerCase();let shown=0;$('#fullApiGuide').querySelectorAll('[data-guide-section]').forEach(section=>{const match=!query||section.textContent.toLowerCase().includes(query);section.hidden=!match;if(match)shown++});$('#apiGuideStatus').textContent=query?`${shown} guide section${shown===1?'':'s'} match “${query}”.`:'Full ChitAPIGuide.md loaded. Search filters its numbered sections.'}
$('#apiGuideSearch').addEventListener('input',filterApiGuide);$('#clearApiGuideSearch').addEventListener('click',()=>{$('#apiGuideSearch').value='';filterApiGuide();$('#apiGuideSearch').focus()});
const apiFieldHelp={
prompt:['The question, instruction, or starting text you want Chit to respond to.','“Explain how saved memory helps Chit.”','State clearly what you want Chit to answer or continue.','Very long prompts leave less room in the 256-byte context window for the answer.'],
message:['The next message you want to send in this conversation.','“How does Chit’s byte tokenizer work?”','Write one clear question or statement; include session_id to continue an earlier chat.','Messages are saved in the conversation session.'],
mode:['Chooses whether Chit answers as a helpful assistant or continues your raw text directly.','assistant answers a request; continue extends the given text prefix.','Use assistant for questions and tasks; use continue for finishing an incomplete sentence.','Continue mode does not use assistant instructions, thinking steps, or web search.'],
task:['Chooses which trained Task skill header Chit uses for this request.','chat, knowledge, behavior, grammar, reasoning, prose, or continue.','Leave on chat to let Chit’s Router pick the best skill automatically, or pick a specific skill to force that mode.','Choosing continue extends raw text without saving a chat session.'],
tokens:['Maximum number of new bytes/tokens Chit may write in its reply.','100 for a short answer; up to 500 for a longer one.','Start with 80–160 and increase only if the answer gets cut off.','Longer limits take more time and can allow a small model to drift off topic.'],
temperature:['Controls how steady or creative Chit’s wording is.','0 gives the steadiest, most repeatable answer; 0.4–0.7 allows more variety.','Use 0 for factual questions and math; use 0.4 for general writing.','Higher values increase the chance of spelling errors or made-up facts.'],
top_k:['Limits how many top next-character choices Chit considers at each step.','50 is the standard setting.','Keep at 50 unless you are experimenting with sampling variety.','Has no effect when temperature is 0.'],
stop:['Optional list of text strings that tell Chit to stop writing immediately if they appear.','["\\nUser:"]','Leave empty to use Chit’s built-in stop rules.','Any matching stop string cuts off the reply as soon as it is generated.'],
session_id:['The 32-character ID of the conversation session to open, update, or delete.','Copy the 32-character hex ID from List sessions or a previous Chat reply.','Leave empty when starting a brand-new conversation in Chat.','An unknown ID returns 404 Not Found.'],
job_id:['The 32-character ID of the training or candidate job to inspect, cancel, test, or promote.','Copy the 32-character hex ID from List training jobs or List candidates.','Use the exact job ID returned when training started.','An unknown ID returns 404 Not Found.'],
memory_id:['The unique ID of the saved long-term memory you want to delete.','Copy the ID from a Search memories result.','Verify the memory text before deleting its ID.','Deleting a memory permanently removes it from recall.'],
entry_id:['The unique ID of the saved knowledge lesson you want to read or delete.','Copy the ID from List knowledge.','Check the lesson contents before deleting.','Deleting removes the lesson from future training runs.'],
enabled:['Turns this conversation feature (automatic fact extraction or running summary) on or off.','true turns it on; false turns it off.','Keep true so Chit remembers your details and summarizes long chats automatically.','Turning it off stops Chit from updating facts or summaries in that session.'],
to_sha256:['The SHA-256 fingerprint of the archived model checkpoint you want to restore as the live AI.','Paste the 64-character SHA-256 hash of a previous champion checkpoint.','Copy the exact hash from Studio or server logs before rolling back.','Immediately replaces the live AI with the specified older checkpoint.'],
config:['The name of the learning plan (training recipe) to inspect or run.','chit_assistant_cpu or chit_v2_6l_256.','Inspect the plan’s files in Training library before starting a training job.','Starting training uses heavy CPU/memory resources.'],
vocab_size:['Target BPE vocabulary size for the subword tokenizer (must be at least 256).','2000 for standard subword vocabularies; up to 50000.','Keep at 2000 or match your config’s model.vocab_size.','Must be at least 256 for UTF-8 byte coverage and must match model.vocab_size during training.'],
force_promote:['Makes the newly trained model go live immediately when training finishes, skipping safety and Bridge checks.','false (recommended) keeps the normal safety-tested workflow; true forces immediate promotion.','Keep false so you can run safety tests and Bridge calibration first.','True replaces the live AI without verifying safety rules.'],
promote:['Requests that a finished training job automatically become the live AI model.','false by default; setting true also requires force_promote: true.','Keep false and promote from Studio after testing the candidate.','Replaces the live model as soon as training completes.'],
init:['Chooses whether training starts from a fresh blank brain or builds on top of the current live model.','auto continues from the current model when compatible; current requires continuing; scratch starts fresh.','Use auto or current for continual learning; use scratch only when training a brand-new stage from zero.','Scratch ignores all previously learned weights.'],
repeat:['How many times each saved lesson is repeated in the training mix during a knowledge training run.','3 is the standard starting value.','Keep between 1 and 5 so lessons are learned without memorizing word-for-word.','Very high repeat counts can cause overfitting on a small set of lessons.'],
select:['Chooses which saved lessons to include in a knowledge training run.','all studies every saved lesson; pending studies only new lessons not yet trained.','Use all for balanced review so older lessons are not forgotten.','Studying only pending lessons gives less review of earlier material.'],
content:['The clear fact or personal preference to store in Chit’s long-term memory.','“I prefer concise answers in simple English.”','Write one short, true statement per memory.','Saved immediately in memory.db; never store passwords or secrets.'],
memory_type:['Categorizes the memory as a personal preference/experience or a general fact.','experience or fact.','Pick experience for user preferences and fact for reference knowledge.','Used for organization; both types can be recalled in chat.'],
importance:['How strongly this memory should be prioritized when Chit searches for relevant context (0.0 to 1.0).','0.5 for everyday facts; 0.8 for very important rules or preferences.','Use 0.5 for most memories and 0.8 for top priorities.','Higher importance increases recall priority but does not verify accuracy.'],
tags:['Optional short keyword labels to help organize and find this memory or lesson later.','["preferences", "writing"]','Add 1 to 3 short topic words if helpful.','Tags are stored in plain text alongside the item.'],
q:['The search word or phrase used to find matching saved memories.','“simple English” or “office”','Enter one or two specific keywords from the memory you want to find.','Very broad searches may return loosely related memories.'],
limit:['Maximum number of records to return in one page of results.','50 is the standard page size.','Keep the default unless you need a larger list.','Very large limits take slightly longer to load.'],
offset:['Number of earlier records to skip when paging through a long list.','0 starts at the very beginning of the list.','Start with 0, then add the limit value to view the next page.','If items are added or deleted while paging, positions can shift slightly.'],
status:['Filters saved lessons by whether they are waiting to be trained or already learned.','pending shows lessons waiting for training; trained shows lessons already included in a promoted model.','Use pending to check what will be studied next.','Only filters the returned list; does not change lesson data.'],
kind:['Selects the lesson format: a passage of text, a question-and-answer pair, or a step-by-step reasoning example.','text, qa, or reasoning.','Choose qa for factual questions, reasoning for step-by-step logic, and text for general reading passages.','Each kind is formatted with its matching Task header (Task: prose, Task: knowledge, or Task: reasoning).'],
text:['The passage or fact statement for a text lesson.','“Chit uses a 256-entry UTF-8 byte tokenizer.”','Write clear, complete sentences.','Included in future training runs when saved.'],
input:['The problem or question for a step-by-step reasoning lesson (Task: reasoning).','“If 3 pens cost 15 rupees, how much does 1 pen cost?”','State the problem clearly with all needed numbers or facts.','Used as the Input: field in Task: reasoning training examples.'],
reasoning:['The step-by-step thinking that leads from the problem to the final answer in a reasoning lesson.','“Dividing 15 rupees by 3 pens gives 15 / 3 = 5 rupees per pen.”','Write each logical step in order so Chit learns how to work through the problem.','Used as the Reasoning: scratchpad in Task: reasoning training examples.'],
remember:['When true, also saves this lesson into long-term memory immediately so Chat can recall it before training.','true saves to both knowledge and memory; false saves only to the training queue.','Set true when you want Chit to use the fact right away in Chat.','Creates a separate memory entry in memory.db.'],
source:['For data split: the file name in the server data folder (e.g. corpus.txt). For lessons: an optional note on where the fact came from.','“corpus.txt” (when splitting files) or “Project handbook” (when saving a lesson).','When splitting data, enter only the file name inside data/.','Splitting with overwrite enabled can replace existing train/eval files.'],
by:['How a text file is divided into individual training examples during a split.','paragraph keeps multi-line Task/User/Chit blocks together; line splits line-by-line.','Always use paragraph for Chit Task-formatted files so multi-line examples stay intact.','Splitting by line on a multi-line file will break Task headers apart from their answers.'],
eval_fraction:['The share of examples held back for the review (eval) file when splitting a dataset (for example, 0.1 = 10%).','0.1 holds back 10% of examples for review and puts 90% in training.','Keep around 0.05 to 0.10 so review loss accurately measures model progress.','Too little review data makes it hard to tell if training improved the model.'],
seed:['Fixed random number seed so a dataset split or training run happens the exact same way every time.','42 or 1337.','Keep the default seed for reproducible splits and training runs.','Changing the seed changes which examples land in the review set.'],
overwrite:['Allows a dataset split to replace existing train and review files (the server automatically saves a .bak backup).','false prevents overwriting existing files; true replaces them after backing up.','Preview with dry_run: true first, then enable overwrite only when ready.','Replaces the training files used by future runs of that learning plan.'],
dry_run:['Previews how a dataset split will divide the file without writing or changing any files on disk.','true previews counts only; false writes the train and review files.','Always run with true first to check the example counts.','Setting false writes files to the server data folder.'],
items:['The list of lesson objects to save into Chit’s knowledge queue.','[{"kind": "qa", "question": "What is Chit?", "answer": "Chit is the neural brain of Atmini."}]','Review each question, reasoning step, and answer for accuracy before sending.','Saved lessons will be studied in future knowledge training runs.'],
question:['The question for a question-and-answer lesson (Task: knowledge).','“What is Chit?”','Write the question the way a user would naturally ask it.','Paired with the answer field during training.'],
answer:['The clear, accurate answer for a Q&A or reasoning lesson.','“Chit is the neural brain of Atmini.”','Keep the answer direct, truthful, and easy to read.','Chit’s training loss focuses directly on learning to write this answer.'],
think:['Turns on Chain-of-Thought step-by-step reasoning (Task: reasoning) before Chit writes its final answer.','true turns on step-by-step thinking; false answers directly.','Turn on for logic puzzles, math word problems, or multi-step questions.','Generates extra thinking tokens before the final answer.'],
search:['Searches the web for live facts before answering and grounds Chit’s reply in the retrieved snippets.','true enables live web search; false uses only local memories and the neural brain.','Turn on for recent events or facts not stored in Chit’s memory.','Requires server internet access and adds about 1–2 seconds for search.']
};
const responseFieldHelp={
text:'The final answer or text continuation written by Chit.',
raw_text:'The raw output from the neural network before Bridge cleanup or formatting.',
session_id:'The 32-character conversation ID. Use this ID to continue the same chat session.',
id:'The unique ID assigned to this conversation, memory, lesson, or training job.',
state:'Current job status: queued (waiting), running (studying), succeeded (finished), failed, or cancelled.',
progress:'How far along the training job is, from 0.0 (just started) to 1.0 (100% finished).',
step:'The current training update step completed so far.',
max_steps:'The total number of training update steps scheduled by the learning plan.',
promoted:'True if this candidate checkpoint was promoted to become the live AI model.',
status:'Overall health or readiness label (such as ok, ready, no_model, or degraded).',
model_loaded:'True when a trained AI checkpoint is loaded in memory and ready to answer.',
training_job:'The ID of the currently running training job, or null if the trainer is idle.',
checks:'Individual readiness results for the model, memory store, knowledge store, and inference queue.',
inference:'Live status of the request queue showing how many chat/generate requests are active or waiting.',
detail:'Plain-English explanation from the server when a request was rejected or encountered an error.',
warnings:'Important data or configuration notices you should review before starting a training run.',
ready_to_train:'True when all required training and review files for this learning plan exist and pass checks.',
train:'Details about the training dataset files, byte sizes, and example counts.',
eval:'Details about the held-out review (evaluation) dataset file and its size.',
metadata:'Detailed diagnostic facts recorded during generation, routing, and verification.',
memory_ids:'List of saved long-term memory IDs that Chit recalled and used to ground this reply.',
source:'Which part of Chit produced the final answer: model (neural brain), tool (calculator/date), extractive (saved memory/fact), or abstain (honesty/safety guard).',
effective_task:'The trained Task skill header (chat, knowledge, behavior, grammar, reasoning, prose, or continue) that Chit’s Router selected for this turn.',
plan:'The Router’s execution plan showing the chosen Task skill, token budgets, and sampling settings.',
tokens_prompt:'How many bytes/tokens were used by the assembled prompt (including memories and recent chat history).',
tokens_reserved:'How many bytes/tokens were reserved in the context window for Chit’s reply.',
tokens_history_dropped:'How many older conversation messages were left out so the prompt would fit inside the context window.',
parameters:'Total number of learnable neural network weights in the active AI model.',
device:'The processor running the AI model (such as cpu or cuda GPU).',
checkpoint:'File path of the currently active model checkpoint on the server.',
checkpoint_timestamp:'Exact date and time when the checkpoint file was saved on disk.',
tokenizer:'Details of the text reader used by the model (such as byte-utf8 with 256 byte values).',
model_config:'Architecture settings of the loaded neural network (layers, attention heads, width, and block_size).',
items:'The list of records returned by this request.',
results:'The list of matching memory records returned by your search.',
sessions:'The list of saved conversation sessions.',
jobs:'The list of active and completed training jobs.',
candidates:'The list of trained candidate checkpoints with their safety evaluation and Bridge benchmark scores.',
total:'Total number of matching records stored on the server.',
created_at:'Date and time when this record was created.',
updated_at:'Date and time when this record was last updated.',
trained_at:'Date and time when this lesson was included in a promoted model.',
facts:'Personal facts (key-value pairs) that Chit automatically remembered during this conversation.',
facts_enabled:'True when Chit is set to automatically remember personal facts shared in this conversation.',
summary:'The short running summary of earlier messages in this conversation.',
summary_enabled:'True when Chit is set to automatically maintain a running summary for this conversation.',
cpu:'Current processor (CPU) usage percentage on the server.',
mem:'Current system memory (RAM) usage percentage on the server.',
disk:'Current storage disk usage percentage on the server.',
evaluation:'Results of the 50 Golden Gate behavioral safety and honesty tests for this candidate.',
behavioral_gate:'Detailed pass/fail score and rule ratings from the 50 Golden Gate safety evaluation.',
bridge_benchmark:'Results from benchmarking how well the Bridge guides this candidate (math exactness, calibration error, speed, and loop rate).',
msg:'Plain-English description of why a field value was rejected.',
loc:'Which field in the request had a validation problem.',
type:'Short validation error code reported by the server.',
input:'The input value or problem statement associated with this record.',
ctx:'Additional context explaining the validation rule.',
confidence:'Confidence score from 0.0 to 1.0 showing how steady and certain Chit was when choosing the words in its reply.',
is_calibrated:'True when the confidence score was adjusted using a verified calibration curve from Bridge benchmarking.',
needs_retrieval:'True when Chit detected low confidence or missing facts and recommends running a live Web search.',
web_grounded:'True when Chit searched the web and grounded this answer using live internet snippets.',
sources:'List of web search snippets retrieved to ground the answer.',
web_sources:'Clickable web source domains, titles, and snippets used to ground this answer.',
vocab_size:'The total number of subword tokens in the trained tokenizer vocabulary.',
path:'The file path where the trained tokenizer JSON asset was written.',
latest_sidecar_path:'The companion tokenizer file path placed beside the latest model checkpoint.',
checkpoint_asset_sha256:'The cryptographic SHA-256 hash of the trained tokenizer asset.',
files_used:'The list of training-only text corpus files used to build the tokenizer vocabulary.',
is_uncertain:'True when Chit’s confidence score fell below the 40% certainty threshold.',
is_incomplete:'True when the reply was cut off by the maximum token limit before finishing a complete sentence.',
thoughts:'The step-by-step Chain-of-Thought reasoning Chit wrote before producing its final answer.',
thought_tokens:'How many bytes/tokens were used by the step-by-step thinking trace.'
};
const apiFieldChoices={mode:['assistant','continue'],task:['chat','knowledge','behavior','grammar','reasoning','prose','continue'],init:['scratch','current','auto'],memory_type:['experience','fact'],status:['pending','trained'],kind:['text','qa','reasoning'],by:['line','paragraph'],select:['all','pending']};
const apiNumericRules={vocab_size:{min:256,max:50000,step:1},tokens:{min:1,max:500,step:1},temperature:{min:0,max:2,step:.1},top_k:{min:1,max:256,step:1},importance:{min:0,max:1,step:.1},limit:{min:1,max:500,step:1},offset:{min:0,max:100000,step:1},repeat:{min:1,max:100,step:1},eval_fraction:{min:.000001,max:.499999,step:.01},seed:{min:0,max:4294967295,step:1}};
let guidedState=null;
function cloneJson(value){return value===undefined?null:JSON.parse(JSON.stringify(value))}
function humanFieldName(key){return key.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function fieldInfo(key,value){return apiFieldHelp[key]||[`This is the “${humanFieldName(key)}” value sent to Chit.`,`Example: ${typeof value==='object'?JSON.stringify(value):String(value??'')}.`,'Use the example as a starting point and change only what you need.','The server may reject a value that does not match its rules.']}
function setAtPath(root,path,value){let node=root;for(let i=0;i<path.length-1;i++){const key=path[i],next=path[i+1];if(node[key]===null||typeof node[key]!=='object')node[key]=typeof next==='number'?[]:{};node=node[key]}node[path[path.length-1]]=value}
function getAtPath(root,path){return path.reduce((node,key)=>node?.[key],root)}
function scalarFor(value,raw){if(typeof value==='number'){if(!String(raw).trim())throw new Error('A number is required.');const n=Number(raw);if(!Number.isFinite(n))throw new Error('Enter a valid number.');return n}if(typeof value==='boolean')return raw==='true';return raw}
function renderRequestField(parent,key,path,value,scope){const info=fieldInfo(key,value),wrap=document.createElement('div');wrap.className='api-field';const label=document.createElement('label');label.textContent=humanFieldName(key);wrap.appendChild(label);const help=document.createElement('p');help.className='api-field-help';help.textContent=info[0];wrap.appendChild(help);let control;if(Array.isArray(value)||value===null){control=document.createElement('textarea');control.rows=4;control.value=JSON.stringify(value,null,2);control.dataset.jsonValue='true'}else if(typeof value==='boolean'){control=document.createElement('select');[['true','Yes / true'],['false','No / false']].forEach(([v,t])=>{const option=document.createElement('option');option.value=v;option.textContent=t;control.appendChild(option)});control.value=String(value)}else if(key==='config'){control=document.createElement('select');control.dataset.dynamicChoices='configs';const option=document.createElement('option');option.value=value??'';option.textContent=value?`${value} · example`:'Loading available plans…';control.appendChild(option);req('/_ui/train/configs').then(result=>{if(!result.ok)return;const configs=result.data?.configs||result.data?.items||[];if(!Array.isArray(configs))return;control.replaceChildren();configs.forEach(config=>{const item=document.createElement('option');item.value=typeof config==='string'?config:config.name;item.textContent=item.value;control.appendChild(item)});if(value&&configs.some(config=>(typeof config==='string'?config:config.name)===value))control.value=value;updateRequestPreview()}).catch(()=>{option.textContent=value?`${value} · example`:'Could not load plans; use the full guide.'})}else if(apiFieldChoices[key]){control=document.createElement('select');apiFieldChoices[key].forEach(choice=>{const option=document.createElement('option');option.value=choice;option.textContent=choice;control.appendChild(option)});control.value=value??apiFieldChoices[key][0]}else if(typeof value==='string'&&['prompt','message','content','question','answer'].includes(key)){control=document.createElement('textarea');control.rows=3;control.value=value}else{control=document.createElement('input');control.type=typeof value==='number'?'number':'text';control.value=value??'';if(typeof value==='number'){const rule=apiNumericRules[key]||{step:'any'};control.min=rule.min??'';control.max=rule.max??'';control.step=key==='eval_fraction'?'any':rule.step??'any'}}control.dataset.scope=scope;control.dataset.keypath=JSON.stringify(path);control._helpInfo={what:info[0],example:info[1],best:info[2],recommended:typeof value==='number'?`Keep the example value (${value}) unless you have a reason to change it.`:'Use the supplied example as a safe starting point.',risk:info[3]};control.addEventListener('input',updateRequestPreview);control.addEventListener('change',updateRequestPreview);label.appendChild(control);const detail=document.createElement('details');detail.className='api-field-details';const summary=document.createElement('summary');summary.textContent='Example, recommended use and risk';const detailText=document.createElement('p');detailText.textContent=`Example: ${info[1]} Best way: ${info[2]} Risk: ${info[3]}`;detail.append(summary,detailText);wrap.appendChild(detail);parent.appendChild(wrap)}
function renderObjectFields(parent,obj,scope,prefix=[]){if(!obj||typeof obj!=='object')return;Object.entries(obj).forEach(([key,value])=>{const path=[...prefix,key];if(value&&typeof value==='object'&&!Array.isArray(value)){const group=document.createElement('fieldset');group.className='api-nested-fields';const legend=document.createElement('legend');legend.textContent=humanFieldName(key);group.appendChild(legend);renderObjectFields(group,value,scope,path);parent.appendChild(group)}else if(Array.isArray(value)&&value.length&&value.every(item=>item&&typeof item==='object'&&!Array.isArray(item))){const group=document.createElement('fieldset');group.className='api-nested-fields';const legend=document.createElement('legend');legend.textContent=humanFieldName(key);group.appendChild(legend);const note=document.createElement('p');note.className='api-field-help';note.textContent='This is a list of structured items. Edit the example fields, add more items, or remove the last item.';group.appendChild(note);const itemList=document.createElement('div');group.appendChild(itemList);const redrawItems=()=>{itemList.replaceChildren();const current=getAtPath(guidedState[scope],path)||[];current.forEach((item,index)=>{const itemGroup=document.createElement('fieldset');itemGroup.className='api-item-fields';const itemLegend=document.createElement('legend');itemLegend.textContent=`Item ${index+1}`;itemGroup.appendChild(itemLegend);renderObjectFields(itemGroup,item,scope,[...path,index]);itemList.appendChild(itemGroup)});removeButton.disabled=current.length<=1};const actions=document.createElement('div');actions.className='actions';const addButton=document.createElement('button');addButton.type='button';addButton.className='secondary';addButton.textContent='Add another item';addButton._helpInfo={what:'Adds another copy of the example item to this list.',example:'Add a second question and answer when saving more than one lesson.',best:'Use one complete, checked item for each fact or question.',recommended:'Add only the items you actually want included.',risk:'Every added lesson may later be used in training.'};const removeButton=document.createElement('button');removeButton.type='button';removeButton.className='secondary';removeButton.textContent='Remove last item';removeButton._helpInfo={what:'Removes the last item from this request list.',example:'Choose if you added an item by mistake.',best:'Review its contents before removing.',recommended:'Keep at least one item when the API requires a list.',risk:'The removed item will not be sent.'};addButton.addEventListener('click',()=>{const current=getAtPath(guidedState[scope],path)||[];current.push(cloneJson(current[0]));redrawItems();updateRequestPreview()});removeButton.addEventListener('click',()=>{const current=getAtPath(guidedState[scope],path)||[];if(current.length>1)current.pop();redrawItems();updateRequestPreview()});actions.append(addButton,removeButton);group.appendChild(actions);redrawItems();parent.appendChild(group)}else renderRequestField(parent,key,path,value,scope)})}
function updateRequestPreview(){if(!guidedState)return;let path=guidedState.route.path;document.querySelectorAll('#apiBuilder [data-scope="path"]').forEach(control=>{const key=control.dataset.keypath;path=path.replace(`{${key}}`,encodeURIComponent(control.value.trim()))});const query=cloneJson(guidedState.query),body=cloneJson(guidedState.body);let invalid=null;document.querySelectorAll('#apiBuilder [data-scope="query"],#apiBuilder [data-scope="body"]').forEach(control=>{control.setCustomValidity('');try{const target=control.dataset.scope==='query'?query:body;const fieldPath=JSON.parse(control.dataset.keypath);const initial=getAtPath(target,fieldPath);let value;if(control.dataset.jsonValue==='true'){value=JSON.parse(control.value)}else if(typeof initial==='number'||typeof initial==='boolean')value=scalarFor(initial,control.value);else value=control.value;if(!control.checkValidity())throw new Error(control.validationMessage||'Check the allowed value range.');setAtPath(target,fieldPath,value);control.classList.remove('invalid-json')}catch(error){control.setCustomValidity(error.message);control.classList.add('invalid-json');invalid=error}});guidedState.path=path;guidedState.query=query;guidedState.body=body;const payload={method:guidedState.route.method,path,query};if(guidedState.route.method!=='GET')payload.body=body;$('#requestJsonPreview').textContent=JSON.stringify(payload,null,2);const missingId=Object.values(guidedState.pathValues||{}).some(v=>!v.trim());const invalidId=Object.entries(guidedState.pathValues||{}).some(([key,value])=>value.trim()&&((key==='session_id'||key==='job_id')?!/^[0-9a-f]{32}$/.test(value.trim()):! /^[A-Za-z0-9_-]+$/.test(value.trim())));$('#runGuidedApi').disabled=Boolean(invalid)||missingId||invalidId;$('#guidedApiStatus').textContent=invalid?`Fix the highlighted field: ${invalid.message}`:missingId?'Enter the required item ID to complete the route.':invalidId?'Check the ID format. Conversation and job IDs use 32 lowercase letters or numbers.':'Review the request preview, then send when ready.';return !invalid&&!missingId&&!invalidId}
function describeResponseValue(key,value){if(responseFieldHelp[key])return responseFieldHelp[key];if(Array.isArray(value))return `${value.length} ${value.length===1?'item':'items'} returned in this list.`;if(value&&typeof value==='object')return 'More detailed information is grouped inside this object.';return `The server returned the ${humanFieldName(key).toLowerCase()} value.`}
function addResponseEntry(parent,key,value,depth=0){const row=document.createElement(depth===0?'section':'details');row.className='response-entry';const title=depth===0?document.createElement('h4'):document.createElement('summary');title.textContent=depth>0?`${humanFieldName(key)}: ${Array.isArray(value)?`${value.length} items`:value&&typeof value==='object'?'details':String(value)}`:humanFieldName(key);row.appendChild(title);const meaning=document.createElement('p');meaning.textContent=describeResponseValue(key,value);row.appendChild(meaning);if(value&&typeof value==='object'){const entries=Array.isArray(value)?value.slice(0,20).map((item,index)=>[`Item ${index+1}`,item]):Object.entries(value);entries.forEach(([childKey,childValue])=>{if(depth<4)addResponseEntry(row,String(childKey),childValue,depth+1)});if(Array.isArray(value)&&value.length>20){const note=document.createElement('p');note.textContent=`Showing the first 20 of ${value.length} items. See the complete JSON below.`;row.appendChild(note)}}else{const sample=document.createElement('pre');sample.textContent=String(value);row.appendChild(sample)}parent.appendChild(row)}
function explainApiResponse(data,status){const article=$('#apiResponseExplainer');article.replaceChildren();article.classList.remove('hidden');const heading=document.createElement('h3');heading.textContent=status>=200&&status<300?'Chit’s response':'What went wrong';article.appendChild(heading);const summary=document.createElement('p');summary.className=status>=200&&status<300?'response-good':'response-bad';summary.textContent=status>=200&&status<300?`Request completed (HTTP ${status}). Here is what the response means:`:`Request failed${status?` (HTTP ${status})`:''}. ${status?friendlyError(data,status):'Check the message below, then correct the request and try again.'}`;article.appendChild(summary);const payload=data&&typeof data==='object'&&!Array.isArray(data)?data:{result:data};Object.entries(payload||{}).forEach(([key,value])=>addResponseEntry(article,key,value));const raw=document.createElement('details'),sum=document.createElement('summary'),pre=document.createElement('pre');sum.textContent='Show the complete response JSON';pre.textContent=JSON.stringify(data,null,2);raw.append(sum,pre);article.appendChild(raw);$('#apiResult').textContent=JSON.stringify(data,null,2)}
function selectRoute(index,button){const route=ROUTES[index];if(!route)return;selected=route;$('#endpointList').querySelectorAll('.endpoint').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));const info=routeGuides[route.name]||['Use this capability to work with Chit.','Review the route and example values.','The server returns the result.'];const target=$('#apiGuide');target.replaceChildren();const title=document.createElement('h3');title.textContent=`${route.name} · ${route.method} ${route.path}`;target.appendChild(title);[['What it does',info[0]],['When to use it',info[2]],['What happens',route.method==='GET'?'This reads information and does not change saved records.':route.method==='DELETE'?'This removes saved information. Review the target carefully.':'This may save information, use compute, or start training. Review each value before sending.']].forEach(([heading,copy])=>{const section=document.createElement('section'),h=document.createElement('h4'),p=document.createElement('p');h.textContent=heading;p.textContent=copy;section.append(h,p);target.appendChild(section)});guidedState={route,path:route.path,pathValues:{},query:cloneJson(route.query||{}),body:cloneJson(route.body)};const builder=$('#apiBuilder');builder.replaceChildren();builder.classList.remove('hidden');const heading=document.createElement('h3');heading.textContent='Build your request';builder.appendChild(heading);const pathParams=[...route.path.matchAll(/\{([^}]+)\}/g)];if(pathParams.length){const group=document.createElement('section');group.className='api-field-group';const h=document.createElement('h4');h.textContent='Fill in the item ID';group.appendChild(h);pathParams.forEach(match=>{const key=match[1],field=document.createElement('div');field.className='api-field';const label=document.createElement('label');label.textContent=humanFieldName(key);const note=document.createElement('p');note.className='api-field-help';note.textContent=`Paste the ${humanFieldName(key).toLowerCase()} from the list or response where you found this item.`;const input=document.createElement('input');input.type='text';input.placeholder=`Paste ${key} here`;input.dataset.scope='path';input.dataset.keypath=key;input._helpInfo={what:note.textContent,example:`Copy the ${key} shown by the related list or create request.`,best:'Copy the complete ID; do not type a shortened version.',recommended:'Use the exact ID returned by Chit.',risk:'An incorrect ID will not select the item you expect.'};input.addEventListener('input',()=>{guidedState.pathValues[key]=input.value;updateRequestPreview()});label.appendChild(input);field.append(label,note);group.appendChild(field);guidedState.pathValues[key]=''});builder.appendChild(group)}if(Object.keys(route.query||{}).length){const group=document.createElement('section');group.className='api-field-group';const h=document.createElement('h4');h.textContent='Search and filter options';group.appendChild(h);renderObjectFields(group,guidedState.query,'query');builder.appendChild(group)}if(route.method!=='GET'&&route.body!==null){const group=document.createElement('section');group.className='api-field-group';const h=document.createElement('h4');h.textContent='Information to send';group.appendChild(h);renderObjectFields(group,guidedState.body,'body');builder.appendChild(group)}else if(route.method!=='GET'){const note=document.createElement('p');note.textContent='This action does not need a request body.';builder.appendChild(note)}const preview=document.createElement('section');preview.className='request-preview';const previewTitle=document.createElement('h4');previewTitle.textContent='JSON Chit will receive';const previewNote=document.createElement('p');previewNote.textContent='JSON is a structured message: curly braces group named fields, square brackets hold a list, quoted values are text, and numbers or true/false are sent as data. This preview changes as you edit the fields above.';const previewText=document.createElement('pre');previewText.id='requestJsonPreview';const previewActions=document.createElement('div');previewActions.className='actions';const copyButton=document.createElement('button');copyButton.type='button';copyButton.className='secondary';copyButton.textContent='Copy request JSON';copyButton._helpInfo={what:'Copies the JSON preview to your clipboard so you can save or reuse it.',example:'Choose after checking the request preview.',best:'Review the values before sharing the JSON.',recommended:'Copy only when you need the request outside this screen.',risk:'Copied JSON may contain private text or identifiers.'};const copyStatus=document.createElement('span');copyStatus.className='status';copyButton.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(previewText.textContent);copyStatus.textContent='JSON copied.'}catch{copyStatus.textContent='Clipboard is unavailable. Select and copy the preview text.'}});previewActions.append(copyButton,copyStatus);preview.append(previewTitle,previewNote,previewText,previewActions);builder.appendChild(preview);$('#apiMethod').value=route.method;$('#apiPath').value=route.path;$('#apiQuery').value=JSON.stringify(route.query||{},null,2);$('#apiBody').value=route.body===null?'':JSON.stringify(route.body,null,2);$('#runGuidedApi').disabled=false;$('#apiResponseExplainer').classList.add('hidden');$('#guidedApiStatus').textContent='Review each field and the JSON preview.';updateRequestPreview()}
const list=$('#endpointList');let selected=null;ROUTES.forEach((route,i)=>{const b=document.createElement('button');b.type='button';b.className='endpoint';const title=document.createElement('b');const method=document.createElement('i');method.className='method';method.textContent=route.method;title.append(method,document.createTextNode(route.name));const path=document.createElement('span');path.textContent=route.path;b.append(title,path);b.title=route.category;b.setAttribute('aria-pressed','false');const baseInfo=routeGuides[route.name]||['Use this Chit capability.','See the example values in the optional technical editor below.','The result is returned by the server.'];b._helpInfo={what:baseInfo[0],example:route.body===null?`${route.method} ${route.path} needs no request body.`:`${route.method} ${route.path}; example values are ready in the advanced editor.`,best:baseInfo[2],recommended:route.method==='GET'?'Use the supplied example first.':'Use the guided screen if you are unsure what to change.',risk:route.method==='GET'?'This reads information and does not change saved data.':route.method==='DELETE'?'This removes saved information and cannot usually be undone.':`This may create or change information or start work. ${baseInfo[2]}`};b.addEventListener('click',()=>selectRoute(i,b));list.appendChild(b)});
loadFullApiGuide();
function routeMatchesPath(routePath,path){const pattern='^'+routePath.split('/').map(part=>{const key=part.match(/^\{([^}]+)\}$/)?.[1];if(key==='session_id'||key==='job_id')return '[0-9a-f]{32}';if(key==='memory_id'||key==='entry_id')return '[A-Za-z0-9_-]+';return key?'[^/]+':part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('/')+'$';return new RegExp(pattern).test(path)}
async function sendApi(route,path,query,body,statusElement){if(route.confirm||route.method==='DELETE'){const consequence=route.method==='DELETE'?'This removes saved information.':'This can use compute or change saved information.';if(!confirm(`${route.name}: ${consequence} Continue?`)){statusElement.textContent='Request cancelled.';return}}statusElement.textContent='Sending request…';statusElement.classList.remove('error');try{const response=await callApi(route.method,path,query,route.method==='GET'?undefined:body);explainApiResponse(response.data,response.status);statusElement.textContent=response.ok?`Done (HTTP ${response.status}). Read the explanation below.`:`Request failed (HTTP ${response.status}). Read the explanation below.`;if(!response.ok)statusElement.classList.add('error')}catch(error){statusElement.textContent=error.message||'Could not send the request.';statusElement.classList.add('error');explainApiResponse({detail:error.message||String(error)},0)}}
$('#runGuidedApi').addEventListener('click',()=>{if(!guidedState||!updateRequestPreview())return;sendApi(guidedState.route,guidedState.path,guidedState.query,guidedState.body,$('#guidedApiStatus'))});
$('#runApi').addEventListener('click',async()=>{const status=$('#apiStatus'),method=$('#apiMethod').value,path=$('#apiPath').value.trim();status.textContent='Checking request…';status.classList.remove('error');try{const matchingRoute=ROUTES.find(route=>route.method===method&&routeMatchesPath(route.path,path));if(!matchingRoute)throw new Error('This method and path are not in the guided API list. Replace any placeholder with the real ID, then try again.');const query=JSON.parse($('#apiQuery').value||'{}');if(!query||Array.isArray(query)||typeof query!=='object')throw new Error('Query parameters must be a JSON object.');const raw=$('#apiBody').value.trim();const body=raw?JSON.parse(raw):null;await sendApi(matchingRoute,path,query,body,status)}catch(error){status.textContent=error.message;status.classList.add('error');explainApiResponse({detail:error.message},0)}});
function closeContextHelp(){const panel=$('#contextHelpPanel');if(panel.classList.contains('hidden'))return;panel.classList.add('hidden');if(helpReturnFocus?.setAttribute)helpReturnFocus.setAttribute('aria-expanded','false');if(helpReturnFocus?.isConnected)helpReturnFocus.focus()}
$('#closeContextHelp').addEventListener('click',closeContextHelp);
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeContextHelp()});
decorateHelp();
new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{if(node.nodeType===1){if(node.matches?.('button,input,textarea,select,summary'))addHelpTrigger(node);decorateHelp(node)}}))).observe(document.body,{childList:true,subtree:true});
checkSession();



document.getElementById('reloadModelBtn')?.addEventListener('click', async () => {
    if (!confirm('Reload the live AI from disk? This will briefly pause generation.')) return;
    try {
        const r = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:'/admin/reload'})});
        if (r.ok) {
            alert('AI Restarted.');
            await refreshHealth();
        } else {
            alert('Restart failed.');
        }
    } catch(e) { console.error(e); }
});

document.getElementById('rollbackModelBtn')?.addEventListener('click', async () => {
    const hash = document.getElementById('rollbackHashInput').value.trim();
    if (!hash) { alert('Enter an old version ID to restore.'); return; }
    if (!confirm('Restore the AI to version ' + hash + '?')) return;
    try {
        const r = await req('/_ui/proxy', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method:'POST',path:'/admin/rollback',query:{to_sha256:hash}})});
        if (r.ok) {
            alert('Restored successfully.');
            document.getElementById('rollbackHashInput').value = '';
            await refreshHealth();
        } else {
            alert('Restore failed.');
        }
    } catch(e) { console.error(e); }
});

addHelpTrigger(document.getElementById('activeAiHelpWrap'));

const pageGuideTitles = {
    helpChatPage: 'Chat Page Guide',
    helpConversationsPage: 'Conversations Page Guide',
    helpGenPage: 'Generate Page Guide',
    helpBrainPage: 'Brain / Memories Page Guide',
    helpTeachPage: 'Teach Chit Page Guide',
    helpStudioPage: 'Studio Page Guide',
    helpDataPage: 'Training Library Page Guide',
    helpDiagPage: 'Diagnostics & Health Page Guide',
    helpApiPage: 'Guided API Reference Page Guide'
};

document.querySelectorAll('.page-help').forEach(btn => {
    btn.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        btn._helpLabel = pageGuideTitles[btn.id] || 'Page Guide';
        btn._helpInfo = controlHelp[btn.id];
        showContextHelp(btn);
    });
});


async function pollMetrics() {
    if (!authenticated) {
        setTimeout(pollMetrics, 2000);
        return;
    }
    try {
        const r = await req('/_ui/proxy', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({method: 'GET', path: '/sys_metrics'})});
        if (r.ok && r.data) {
            const updateStat = (id, val) => {
                const el = document.getElementById(id);
                if (!el || typeof val !== 'number') return;
                el.textContent = val.toFixed(1) + '%';
                el.style.color = val < 60 ? 'var(--success)' : (val < 85 ? '#ff8c00' : 'var(--danger)');
            };
            updateStat('sysCpu', r.data.cpu);
            updateStat('sysMem', r.data.mem);
            updateStat('sysDisk', r.data.disk);
        }
    } catch(e) {}
    setTimeout(pollMetrics, 2000);
}
setTimeout(pollMetrics, 2000);
