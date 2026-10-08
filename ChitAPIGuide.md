# Chit API Guide — in Simple English

This guide explains every part of the Chit API in plain words. You do not need to be a programmer.
If you are one, the shorter technical reference is in `API.md`.

**Version:** 0.2.0  **Address of the server:** `https://api.chitt.online`

---

## Contents

1. [Read this first: the basics](#1-read-this-first-the-basics)
2. [How to send a request (three easy ways)](#2-how-to-send-a-request-three-easy-ways)
3. [What Chit is, and what it is not](#3-what-chit-is-and-what-it-is-not)
4. [The four big ideas: model, memory, knowledge, data](#4-the-four-big-ideas)
5. [Quick start: five steps from nothing to an answer](#5-quick-start-five-steps)
6. [Every endpoint, one by one](#6-every-endpoint-one-by-one)
   - [6.1 Check the server](#61-check-the-server)
   - [6.2 Write text](#62-write-text)
   - [6.3 Conversations (sessions)](#63-conversations-sessions)
   - [6.4 Memory](#64-memory)
   - [6.5 Training](#65-training)
   - [6.6 Knowledge](#66-knowledge)
   - [6.7 Training text files](#67-training-text-files)
7. [When something goes wrong](#7-when-something-goes-wrong)
8. [Step-by-step recipes](#8-step-by-step-recipes)
9. [Tips for better answers](#9-tips-for-better-answers)
10. [Glossary: hard words made easy](#10-glossary)
11. [One-page cheat sheet](#11-one-page-cheat-sheet)

---

## 1. Read this first: the basics

### What is an API?
An API is a way for one program to talk to another program over the internet.
Think of a restaurant. You (or your app) are the customer. The Chit server is the kitchen.
The API is the **menu and the waiter**: it lists what you can ask for, carries your order to the kitchen,
and brings back the answer.

### Words you will see again and again

| Word | What it means |
| --- | --- |
| **Endpoint** | One thing you can ask for. Each endpoint is a web address such as `/generate`. |
| **Request** | The message you send to the server. |
| **Response** | The message the server sends back. |
| **Method** | The kind of request. `GET` means "give me information". `POST` means "do something with what I send". `DELETE` means "remove this". |
| **JSON** | A simple way to write information as labeled pieces. See the example below. |
| **API key** | A secret password. The server only answers people who show it. |
| **Header** | A small note attached to a request. The API key goes in a header called `X-API-Key`. |
| **Status code** | A number in the response that says if it worked. See the table below. |
| **ID** | A long random code that names one thing, such as one conversation. Example: `eefa8d7646ca4a99bf1ef6b514cf75c5`. |

### What JSON looks like
JSON is just labels and values inside curly brackets. Text goes in quotation marks. Numbers do not.
`true` and `false` are yes and no. `null` means "nothing".

```json
{
  "prompt": "Atmini is",
  "tokens": 60,
  "temperature": 0,
  "stop": ["\n"]
}
```

Here `"prompt"` is a label and `"Atmini is"` is its value. `"stop"` has a list: the square brackets `[ ]` hold
several values.

**Tip:** every opening bracket `{` or `[` needs a closing one, every label and text needs quotation marks
(`"`, the straight kind, not curly), and items are separated by commas, with no comma after the last one.
Most beginner mistakes are a missing quote or comma.

### Status codes: did it work?

| Number | Meaning in plain words |
| --- | --- |
| **200** | Worked. The answer is in the response. |
| **201** | Worked, and something new was created. |
| **202** | Accepted. The work started and is still running (used for training). |
| **204** | Worked. There is nothing to show (used after a delete). |
| **401** | The API key is missing or wrong. |
| **403** | The training features are switched off on this server. |
| **404** | Not found. The thing you named (a conversation, a job…) does not exist. |
| **409** | A conflict. For example, a training job is already running. |
| **422** | Something in your request is not allowed (a wrong value, too long, a missing field). |
| **500** | A problem inside the server. |
| **503** | The server is up but there is no trained model yet. Train one first. |

### Which endpoints need the key?

| Group | Endpoints | Rule |
| --- | --- | --- |
| Open to everyone | `/health` | No key needed. |
| Need the key | `/model`, `/generate`, `/chat`, `/sessions`, `/memory` | If the server has a key set (the deployed one does), send it. |
| Need the key, and training must be on | `/train`, `/knowledge`, `/data` | Same, and the server must be configured with a key. Without a key these answer **403**. |

**Keep your key private.** Anyone who has it can train or change your model. Never put it in a public
place such as a public GitHub repository, a screenshot or a chat message.

---

## 2. How to send a request (three easy ways)

Every example in this guide shows four things: the **method** (GET, POST, DELETE), the **address**, and
for POST requests, the **body** (the JSON you send). Here is how to actually send one.

In the examples I write `YOUR_KEY` for your API key. Replace it with your real key.

### Way 1 — The browser console (easiest, nothing to install)
1. Open `https://api.chitt.online/console` (deployed) or `http://127.0.0.1:8001/` (local).
2. Enter your API key once. The console keeps it server-side for this browser session.
3. Use Chat or Generate for model requests, or choose an operation under **All API routes**.
4. Replace the sample values as needed. The console asks before deleting, cancelling work, training, or writing split files.

The interactive FastAPI reference remains at `https://api.chitt.online/docs`. In Swagger, click an endpoint,
choose **Try it out**, enter your key in the `x-api-key` box, and click **Execute**.

### Way 2 — curl (Mac, Linux, or "Git Bash" on Windows)
```bash
curl -X POST https://api.chitt.online/generate \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Atmini is", "tokens": 60, "temperature": 0, "stop": ["\n"]}'
```
For a GET request there is no `-d`:
```bash
curl -H "X-API-Key: YOUR_KEY" https://api.chitt.online/health
```

### Way 3 — Windows PowerShell
Do **not** type `curl` in PowerShell: it is a different tool there. Use `Invoke-RestMethod`:
```powershell
$h = @{ "X-API-Key" = "YOUR_KEY" }

# a POST request with a body
Invoke-RestMethod -Method Post -Uri https://api.chitt.online/generate -Headers $h `
  -ContentType "application/json" `
  -Body '{"prompt": "Atmini is", "tokens": 60, "temperature": 0, "stop": ["\n"]}'

# a GET request
Invoke-RestMethod -Uri https://api.chitt.online/health
```

### If your own computer runs the server
Use `http://127.0.0.1:8000` instead of `https://api.chitt.online`.

---

## 3. What Chit is, and what it is not

Please read this part. It saves a lot of frustration.

**चित् (Chit) is Atmini's neural brain, trained from scratch.** The current assistant preset has about
0.9 million adjustable parameters and a 512-byte context. It uses learned weights, relevant memory,
and conversation history to respond; training data and available compute determine what it can learn.

**What Chit is being trained to do:** respond to requests using examples in its training format, including
answers, explanations, translations, summaries, new writing, and guided problem solving. Its reliability
depends on the examples it has learned and the context available for each conversation.

**Current limits:**
- It has no external lookup service; answers rely on training examples and context supplied in the request.
- It may fail to combine familiar facts reliably or follow complex instructions, especially when important context is missing.
- It can produce confident errors, so check important answers.

**How to improve results:** add varied request-and-response examples to the reviewed corpus, then train and
check held-out requests. Matching the request language and task to the examples helps. Section 9 has tips.

---

## 4. The four big ideas

Four things sound alike but are different. Understanding them makes everything else easy.

| Idea | Simple explanation | Changes the model? | Where it lives |
| --- | --- | --- | --- |
| **The model** (its "weights") | The model's brain: a big list of numbers. It is what actually writes the text. | — | A file on the server |
| **Training data** (`train.txt`, `eval.txt`) | The text the model studies. `train.txt` is the textbook. `eval.txt` is the **exam** the model has not studied from. | Only after training | Two text files |
| **Memory** | A notebook of facts. Assistant-mode `/generate` and `/chat` can include matching notes in the prompt. | **No** | A small file |
| **Knowledge** | A pile of lessons waiting to be studied. You add lessons now; they only change the model after you run training. | Only after training | A small database |

### Which one should I use?

| I want to… | Use | Why |
| --- | --- | --- |
| Ask Chit to answer or create something | `POST /generate` or `/chat` | `/chat` also uses memory and session history. |
| Continue raw text | `POST /generate` with `mode: "continue"` | No assistant request wrapper. |
| Give Chit a fact **right now** | `POST /memory` | Works immediately, no waiting. |
| Teach Chit something for good | `POST /knowledge`, then `POST /knowledge/train` | Studied into the model. |
| Replace everything Chit studies | Change `train.txt`, then `POST /train` | Full retraining. |
| Keep a conversation going | `POST /chat` with a `session_id` | Remembers recent messages. |

---

## 5. Quick start: five steps

This takes several minutes or longer on CPU. The example uses `chit_assistant_cpu`, the assistant-style preset.

### Step 1 — Is the server alive?
`GET /health` (no key needed)

You should see `"status": "ok"`. If you see `"status": "no_model"`, there is no trained model yet: that is
fine, you will make one in step 3.

### Step 2 — Are the training files ready?
`GET /data?config=chit_assistant_cpu`

Look for `"ready_to_train": true`. If it says `false`, read the `warnings` list. It tells you what to fix.

### Step 3 — Start training
`POST /train` with this body:
```json
{"config": "chit_assistant_cpu", "init": "scratch"}
```
The answer has an `"id"`. **Copy it.** This is your training job. It starts running in the background.

### Step 4 — Wait until it is done
`GET /train/PASTE_THE_ID_HERE`

Repeat every few seconds. Watch two fields: `"state"` and `"progress"` (0 to 1). When `"state"` is
`"succeeded"` means training finished. By default the result remains a candidate and `"promoted"` is
`false`; use the reviewed promotion workflow to serve it. To explicitly bypass those review gates, send
`"force_promote": true` with `POST /train`. On a small test computer a full run took about two minutes;
your server may be faster or slower.

### Step 5 — Ask the model
`POST /generate` with this body:
```json
{"prompt": "Explain how memory helps an assistant.", "tokens": 100, "temperature": 0}
```
You get back:
```json
{"text": "..."}
```
Done. You trained a model and asked it a question.

---

## 6. Every endpoint, one by one

Each endpoint below has the same parts:
**What it does → When to use it → What you send → What you get back → Example → Common problems.**

In the "What you send" tables, **Required** means you must include it. If a field is optional and you leave it
out, the **Default** is used.

---

## 6.1 Check the server

### `GET /health`
**What it does.** Tells you if the server is running and whether a trained model is loaded.
**Key needed:** no.
**When to use it.** First thing, any time. Also after the server restarts.

**What you send.** Nothing.

**What you get back**
```json
{
  "status": "ok",
  "version": "0.2.0",
  "model_loaded": true,
  "error": null,
  "training_job": null
}
```

| Field | What it means |
| --- | --- |
| `status` | `ok` = ready to answer. `no_model` = server is on but nothing is trained yet. |
| `version` | The version of the API software. |
| `model_loaded` | `true` if a trained model is ready. |
| `error` | If there is no model, the reason is written here in words. Otherwise `null` (nothing). |
| `training_job` | The ID of a training job that is running right now, or `null` if none. |

**Common problems.** If this does not answer at all, the server is down or the address is wrong.

---

### `GET /model`
**What it does.** Describes the model that is currently live: its size and how it was trained.
**Key needed:** yes.
**When to use it.** To check which model is running, or to see how well training went.

**What you send.** Nothing.

**What you get back**
```json
{
  "model_config": {"vocab_size": 256, "block_size": 128, "n_layer": 2, "n_head": 2, "n_embd": 64, "dropout": 0.0},
  "parameters": 124672,
  "device": "cpu",
  "checkpoint": {
    "format": 2,
    "chit_version": "0.2.0",
    "step": 3000,
    "total_steps": 3000,
    "init_from": null,
    "best_eval_loss": 1.6965870976448059,
    "last_eval": {"step": 3000, "train_loss": 0.0934, "eval_loss": 2.9523},
    "metadata": {},
    "path": "checkpoints/latest.pt"
  }
}
```

| Field | What it means |
| --- | --- |
| `block_size` | How much text the model can look at at once, counted in letters (bytes). Here 128. A bigger number lets it keep more context. |
| `n_layer`, `n_head`, `n_embd` | The model's size settings: how many layers, how many "attention heads", and how wide it is. Bigger means more powerful and slower. |
| `vocab_size` | How many different "pieces" the model knows. Always 256. |
| `dropout` | A setting used during training to stop memorizing. 0 means off. |
| `parameters` | The count of adjustable numbers in the model. |
| `device` | `cpu` (normal computer chip) or `cuda` (graphics card). |
| `checkpoint.step` | How many training steps it was trained for. |
| `checkpoint.init_from` | If it started from an older model, the file name. `null` means it started from nothing. |
| `checkpoint.best_eval_loss` | The best exam score it reached during training. **Lower is better.** |
| `checkpoint.last_eval` | The scores at the very end: `train_loss` (on the textbook) and `eval_loss` (on the exam). |

**Reading the scores.** If `train_loss` is tiny (like 0.09) but `eval_loss` is much larger (like 2.95), the model
**memorized** its textbook. It can repeat what it studied but is weak on new wording. Add varied data and
review held-out replies before promoting the checkpoint.

**Common problems.** `503` means no model yet. Train one.

---

## 6.2 Write text

### `POST /generate`
**What it does.** You send a request and Chit writes a response. Set `mode` to `continue` to pass raw text directly.
**Key needed:** yes.
**When to use it.** Use it for a single request to answer, explain, translate, summarize, or create content.

**What you send**

| Field | Required | Default | Allowed | What it means in simple words |
| --- | --- | --- | --- | --- |
| `prompt` | **Yes** | — | 1 to 2000 characters | Your request in the default assistant mode, or a raw text prefix when `mode` is `continue`. Markdown headings, lists, tables, quotes, and code fences are kept in the request. |
| `mode` | No | `assistant` | `assistant` or `continue` | Assistant mode formats the request like `/chat` and adds matching memory. Continue mode sends the prompt directly. |
| `tokens` | No | 100 | 1 to 500 | The most new letters Chit may write. (A "token" is about one letter.) 60 to 120 is enough for a sentence. |
| `temperature` | No | 0.7 | 0 to 2 | How adventurous Chit is. **0** = always the safest choice, so you get the same answer every time. Higher = more random and more mistakes. |
| `top_k` | No | 50 | 1 to 256 | Chit picks each letter from its top few guesses. This sets how many. It does nothing when `temperature` is 0. |
| `stop` | No | assistant turn markers | up to 8 pieces of text | Optional custom stop text. `mode: "continue"` applies only the stop strings you provide. |

**Best settings for steady answers:** `"temperature": 0`. Assistant mode uses chat-turn stop markers by default.

**What you send (example)**
```json
{"prompt": "Explain how memory helps Chit.", "tokens": 100, "temperature": 0}
```

**What you get back**
```json
{"text": "Relevant memories can be included in the request context. Saving a memory does not change model weights."}
```

| Field | What it means |
| --- | --- |
| `text` | The generated response only. **Your prompt is not repeated.** |

**Common problems**

| You see | Why | Fix |
| --- | --- | --- |
| Gibberish | The request or language is not well represented in training. | Add varied examples for that task and language; use `temperature` 0 for steadier output. |
| It keeps writing more lines | The answer format does not match learned turn markers. | Train on `Task: chat` / `User:` / `Chit:` examples or supply a stop string. |
| Slightly different answer each time | `temperature` is above 0. | Set it to 0. |
| `422` | A value is out of range, or `prompt` is empty. | Check the table above. |
| `503` | No model yet. | Train first (section 5). |

---

### `POST /chat`
**What it does.** A request-response call. It builds a message for the model using relevant memory and recent
conversation history, then **saves** the exchange in a conversation (a "session").
**Key needed:** yes.
**When to use it.** When you want a back-and-forth conversation with memory and session history.

**What you send**

| Field | Required | Default | Allowed | What it means in simple words |
| --- | --- | --- | --- | --- |
| `message` | **Yes** | — | 1 to 2000 letters | What the user says. |
| `task` | No | `chat` | up to 50 letters | The task label used in the request prompt. `continue` = send the message straight to the model as a raw text prefix. |
| `temperature` | No | server's own (0.7) | 0 to 2 | Same as in `/generate`. Use 0 for steady answers. |
| `tokens` | No | server's default (256) | 1 to 500 | Maximum new bytes to generate. |
| `session_id` | No | none | the 32-character ID of a conversation | To continue an old conversation, send its ID. **Leave it out to start a new one**: the server makes one and returns its ID. Not allowed with `task: "continue"`. |

**How the chat message is built.** In `chat` mode the model is shown this, filled in:
```
Task: chat
Known memory:
- (up to 5 notes from Memory that match your message)
(the last 8 messages of this conversation)
User: (your message)
Chit:
```
Then Chit writes what comes after `Chit:`. If the whole thing is too long for the model's `block_size`, the oldest
messages are dropped first, then the least matching notes. If the current request still does not fit, its end is
truncated for generation. Every message is saved in full. Markdown structure is preserved unless it falls beyond
the context limit.

**Important.** The model works best when training examples use this same request style (`Task:`, `User:`, and
`Chit:` lines). `task: "continue"` remains available for raw text continuation and does not create a session.

**Example 1: start a conversation**
```json
{"message": "Hello, I am", "temperature": 0}
```
Response:
```json
{
  "text": "...the model's reply...",
  "session_id": "eefa8d7646ca4a99bf1ef6b514cf75c5",
  "metadata": {"task": "chat", "memory_ids": []}
}
```
**Keep that `session_id`.** Send it with your next message:
```json
{"message": "I learn", "session_id": "eefa8d7646ca4a99bf1ef6b514cf75c5", "temperature": 0}
```

**Example 2: raw text continuation (no conversation saved)**
```json
{"message": "Chit is the", "task": "continue", "temperature": 0}
```
Response:
```json
{"text": " model inside Atmini.", "session_id": null, "metadata": {"task": "continue", "memory_ids": []}}
```

**What you get back**

| Field | What it means |
| --- | --- |
| `text` | The model's reply. |
| `session_id` | The conversation this was saved to. `null` when you used `task: "continue"` (nothing is saved). |
| `metadata.task` | The task that was used. |
| `metadata.memory_ids` | The IDs of memory notes that were shown to the model for this reply. Empty means none matched. |

**Common problems**

| You see | Why | Fix |
| --- | --- | --- |
| `404 session not found` | The `session_id` is wrong, or the conversation was deleted. | Omit `session_id` to start a new one. |
| `422` | `session_id` is not 32 characters of 0-9 and a-f, or you used a `session_id` with `continue`. | Fix the ID, or remove it. |
| Nonsense replies | The model was not trained on `User:`/`Chit:` text. | Use `task: "continue"`, or train on that style. |

---

## 6.3 Conversations (sessions)

A **session** is one conversation and all its messages. It is separate from Memory. Memory is a shared notebook
of facts. A session is the chat history of one person.

You usually do not need these endpoints, because `POST /chat` makes sessions for you. Use them to start one in
advance, read the history, or delete it.

**Good to know:** a session keeps the latest **200 messages**. A conversation with no new messages for **30
days** is deleted automatically when the server restarts. A question and its reply count as 2 messages.

### `POST /sessions`
**What it does.** Starts an empty conversation. **Key needed:** yes. **What you send:** nothing.

**What you get back** (status 201)
```json
{
  "id": "b212e85c807546d7a08531db226594f2",
  "created_at": "2026-10-01T08:21:49.769330+00:00",
  "updated_at": "2026-10-01T08:21:49.769330+00:00",
  "turns": 0
}
```

| Field | What it means |
| --- | --- |
| `id` | The conversation's ID. Use it as `session_id` in `/chat`. |
| `created_at` | When it started. Times are in UTC (world time) in this format: year-month-day, then T, then the time. |
| `updated_at` | When the last message was added. |
| `turns` | How many messages it holds so far. |

### `GET /sessions`
**What it does.** Lists conversations, newest activity first. **Key needed:** yes.

**What you send** (added to the address, after a `?`)

| Field | Required | Default | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `limit` | No | 50 | 1 to 500 | How many to show. |
| `offset` | No | 0 | 0 or more | How many to skip. Use it to go to the next page. |

Example address: `/sessions?limit=5`

**What you get back**
```json
{
  "total": 2,
  "limit": 5,
  "offset": 0,
  "sessions": [
    {"id": "b212e85c807546d7a08531db226594f2", "created_at": "...", "updated_at": "...", "turns": 0},
    {"id": "eefa8d7646ca4a99bf1ef6b514cf75c5", "created_at": "...", "updated_at": "...", "turns": 4}
  ]
}
```
`total` is how many conversations exist in all. `sessions` is the page you asked for.

### `GET /sessions/{session_id}`
**What it does.** Shows one conversation with every message. **Key needed:** yes.
Replace `{session_id}` with the real ID: `/sessions/eefa8d7646ca4a99bf1ef6b514cf75c5`.

| Field | Where | Required | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `session_id` | in the address | Yes | 32 characters | Which conversation. |
| `limit` | after `?` | No | 1 to 1000 | Show only the most recent N messages. Default: all. |

**What you get back**
```json
{
  "id": "eefa8d7646ca4a99bf1ef6b514cf75c5",
  "created_at": "2026-10-01T08:21:49.590569+00:00",
  "updated_at": "2026-10-01T08:21:49.683996+00:00",
  "turns": 4,
  "messages": [
    {"role": "user", "content": "Hello, I am", "created_at": "2026-10-01T08:21:49.592302+00:00"},
    {"role": "assistant", "content": "...", "created_at": "2026-10-01T08:21:49.592302+00:00"}
  ]
}
```

| Field | What it means |
| --- | --- |
| `messages` | The messages, oldest first. |
| `role` | `user` = the person. `assistant` = Chit. |
| `content` | The full text of the message. |
| `created_at` | When it was saved. |

### `DELETE /sessions/{session_id}`
**What it does.** Deletes one conversation and all its messages for good. **Key needed:** yes.
**What you get back:** status **204** and an empty body. That means success.

**Common problems (all four):** `404 session not found` means the ID is wrong or already deleted.

**Tip.** Chat text can contain private information. Delete conversations you no longer need.

---

## 6.4 Memory

Memory is a notebook of short facts. You write a fact once, and assistant-mode `/generate` and `/chat` can find it later.
**Putting a fact in memory does not change the model.** It is instant.

### `POST /memory`
**What it does.** Saves one fact in the notebook. **Key needed:** yes.

**What you send**

| Field | Required | Default | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `content` | **Yes** | — | 1 to 2000 letters | The fact itself. Write one clear sentence. |
| `memory_type` | No | `experience` | up to 50 letters | A label such as `fact`, `concept` or `experience`. It is for your own organizing. |
| `importance` | No | 0.5 | 0 to 1 | How much the fact matters. When two notes match equally well, the more important one wins. |
| `tags` | No | none | up to 20 labels | Words to group notes, for example `["pranav", "profile"]`. |

**Example**
```json
{"content": "Pranav lives in India.", "memory_type": "fact", "importance": 0.8, "tags": ["pranav", "profile"]}
```

**What you get back** (status 201)
```json
{
  "id": "64b8a199-5eb2-4d77-934b-ad462a4712d4",
  "type": "fact",
  "content": "Pranav lives in India.",
  "importance": 0.8,
  "tags": ["pranav", "profile"],
  "created_at": "2026-10-01T08:21:49.778092+00:00"
}
```

| Field | What it means |
| --- | --- |
| `id` | The note's ID. **Save it** if you may want to delete it. (Memory IDs have dashes.) |
| `type` | The label you gave in `memory_type`. |
| `content`, `importance`, `tags` | What you sent. |
| `created_at` | When it was saved. |

### `GET /memory/search`
**What it does.** Looks for notes that match some words. **Key needed:** yes.

**What you send** (after `?`)

| Field | Required | Default | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `q` | **Yes** | — | 1 to 200 letters | The words to look for. |
| `limit` | No | 5 | 1 to 50 | The most results to return. |

Example address: `/memory/search?q=Pranav&limit=3`

**How the search works.** It matches **whole words**. It ignores capital letters, punctuation, and very common
words such as "is" and "the". Notes with more matching words come first, then the more important ones, then the
newer ones. **This search uses keyword overlap rather than semantic matching.** Searching `city` will not find a note that only says `Nagpur`.
Use the same words in the note and in the search.

**What you get back**
```json
{
  "results": [
    {"id": "64b8a199-5eb2-4d77-934b-ad462a4712d4", "type": "fact", "content": "Pranav lives in India.",
     "importance": 0.8, "tags": ["pranav", "profile"], "created_at": "2026-10-01T08:21:49.778092+00:00"}
  ]
}
```
No matches gives `{"results": []}`.

### `DELETE /memory/{memory_id}`
**What it does.** Removes one note. **Key needed:** yes. Use the ID from when you saved it:
`/memory/64b8a199-5eb2-4d77-934b-ad462a4712d4`.
**What you get back:** status **204** and nothing else.
**Common problem:** `404 memory not found` means the ID is wrong or it was already deleted.

**Tip.** Write each memory as a short, complete sentence that uses the words a person would search for.

---

## 6.5 Training

**Training** is how the model learns. It reads `train.txt` over and over and slowly improves. It runs in the
**background**: you start it, get a job ID, and check on it as often as you like. By default it creates a
candidate and leaves the served model unchanged. Set `force_promote: true` in the `POST /train` body to
install a successful candidate while bypassing evaluation and reviewer gates; the previous checkpoint is archived.

**Only one training job can run at a time.**

### The idea of a "config" (a preset)
A **config** is a saved settings file with a name, such as `chit_strong`. It decides how big the model is, how
long to train, and which text files to use. You pick one by name. You can also change individual settings for just
one job by adding them to your request (see the tables below).

### `GET /train/configs`
**What it does.** Lists the preset names you can use. **Key needed:** yes (training). **What you send:** nothing.
```json
{"configs": ["chit_assistant_cpu", "chit_cpu_learning", "chit_strong", "chit_tiny", "chit_train_txt"]}
```

### `POST /train`
**What it does.** Starts a training job that studies `train.txt` (and checks itself on `eval.txt`).
**Key needed:** yes (training). Returns status **202**: "accepted, now working".
**When to use it.** After you change `train.txt` or `eval.txt`, or to build a brand new model.

**What you send.** Every field is optional.

| Field | Default | Allowed | What it means in simple words |
| --- | --- | --- | --- |
| `config` | `chit_cpu_learning` | a name from `/train/configs` | Which preset to use. Pass `chit_assistant_cpu` for the 512-byte context and assistant-style examples. |
| `seed` | the preset's | a whole number | A number that fixes the "luck" in training. The same seed gives repeatable results. |
| `device` | the preset's | `auto`, `cpu`, `cuda` | Which chip trains the model. `cuda` is a graphics card and fails if the server has none. |
| `init` | `scratch` | `scratch`, `current`, `auto` | Where learning starts. See the box below. |
| `model` | none | see the model table | Change the model's size for this job only. |
| `training` | none | see the training table | Change training settings for this job only. |
| `promote` | `false` | `true` or `false` | Legacy promotion request. `true` is rejected with `422` unless `force_promote` is also true. |
| `force_promote` | `false` | `true` or `false` | Explicitly install the successful candidate as the live model, bypassing evaluation and reviewer gates. The prior checkpoint is archived. |

**`init`: where does learning start?**

| Value | Meaning | When to use |
| --- | --- | --- |
| `scratch` | Start from a blank brain. The result depends only on your text. | Best for a clean, predictable result. |
| `current` | Continue from the live model, studying more. The model's size must stay the same. It fails if no model is live. | To add more learning faster. May forget some older material. |
| `auto` | Same as `current` if possible, otherwise `scratch`. | When you do not care which. |

**`model` settings** (all optional; leave them out unless you know why you change them)

| Field | Allowed | What it means |
| --- | --- | --- |
| `block_size` | 8 to 2048 | How much text the model reads at once. **Both text files must be longer than this** (in letters). |
| `n_layer` | 1 to 48 | How many layers. More layers = more power, slower. |
| `n_head` | 1 to 64 | How many attention heads. `n_embd` must divide evenly by this number. |
| `n_embd` | 8 to 4096 | The model's width. Bigger = more power, slower. |
| `dropout` | 0 up to just under 1 | Randomly switches parts off while studying, which reduces memorizing. 0 means off. |

**`training` settings** (all optional)

| Field | Allowed | What it means |
| --- | --- | --- |
| `max_steps` | 1 or more (server limit 100000) | How many study steps. More steps = longer training. For a quick test use 60. |
| `batch_size` | 1 to 1024 | How many pieces of text are studied in each step. |
| `learning_rate` | above 0 up to 1 | How big each learning step is. Too big = unstable. Too small = very slow. `0.003` worked for the earlier CPU preset. |
| `weight_decay` | 0 to 1 | A gentle brake that keeps the numbers from growing too large. Usually leave it. |
| `eval_interval` | 1 or more | How often (in steps) to take the "exam" on `eval.txt`. |
| `eval_steps` | 1 to 1000 | How many exam questions in each check. |
| `checkpoint_interval` | 1 or more | How often to save progress. |
| `grad_clip` | above 0 up to 100 | A safety limit on the size of each update. Usually leave it. |
| `warmup_steps` | 0 or more | Starts with tiny steps and grows to the full size over this many steps. Helps stability. |
| `lr_schedule` | `constant` or `cosine` | `cosine` slowly lowers the step size towards the end. |
| `min_lr_ratio` | 0 to 1 | With `cosine`, how small the step size gets at the end. |

**Example (start a full training)**
```json
{"config": "chit_strong", "init": "scratch"}
```
**Example (quick 60-step test)**
```json
{"config": "chit_strong", "init": "scratch", "training": {"max_steps": 60}}
```

**Example (explicitly bypass review and force promotion)**
```json
{"config":"chit_strong","init":"scratch","promote":true,"force_promote":true}
```
Use this only when accepting an unreviewed candidate. The server still checks that it can load the checkpoint and that its tokenizer family matches the served model.

**Checks done before it starts** (a failed check gives a `422` with a list of reasons):
- The files `train.txt` and `eval.txt` must exist.
- **Both files must be longer than `block_size` letters.**
- `n_embd` must divide evenly by `n_head`.
- `max_steps` must not be above the server limit.
- `cuda` can only be asked for if the server has a graphics card.

**What you get back** (status 202). This is a "job":
```json
{
  "id": "1adc741f15164a2e9f0d8c7c883c1103",
  "state": "queued",
  "step": 0,
  "max_steps": 3000,
  "progress": 0.0,
  "latest": null,
  "history": [],
  "config": {"seed": 42, "device": "cpu", "model": {"...": "..."}, "training": {"...": "..."},
             "data": {"train_file": "data/train.txt", "eval_file": "data/eval.txt"}},
  "promote": true,
  "promoted": false,
  "metadata": {"init": "scratch"},
  "created_at": "2026-10-01T08:21:49.800302+00:00",
  "started_at": null,
  "finished_at": null
}
```
The reply also has a `Location` note in its headers pointing to the job's address. **The important field is `id`.**
Every field is explained in "The job" below.

**Common problems**

| You see | Why | Fix |
| --- | --- | --- |
| `404 config not found` | The preset name is wrong. | Check `GET /train/configs`. |
| `409` | A job is already running. The reply names it in `active_job`. | Watch that job, or cancel it. |
| `422` | A setting is out of range, or the text files are too small or missing. | Read the messages. Run `GET /data` to check the files. |
| `403` | Training is switched off (no key on the server). | The server owner must set an API key. |

### `GET /train`
**What it does.** Lists recent jobs, newest first. The server remembers the last 50. **Key needed:** yes.
```json
{"jobs": [{"id": "1adc741f15164a2e9f0d8c7c883c1103", "state": "succeeded", "...": "..."}]}
```
Each item in the list is a "job" as described below.

### `GET /train/{job_id}`
**What it does.** Shows one job: how far it has got and how well it is learning. **Key needed:** yes.
Use the job's ID in the address: `/train/1adc741f15164a2e9f0d8c7c883c1103`. Call it again and again to watch progress.

**What you get back** (a finished job)
```json
{
  "id": "1adc741f15164a2e9f0d8c7c883c1103",
  "state": "succeeded",
  "step": 60,
  "max_steps": 60,
  "progress": 1.0,
  "latest": {"step": 60, "train_loss": 2.902951, "eval_loss": 2.907317, "at": "2026-10-01T08:21:54.165970+00:00"},
  "history": [
    {"step": 1, "train_loss": 5.516232, "eval_loss": 5.513243, "at": "2026-10-01T08:21:51.778800+00:00"},
    {"step": 30, "train_loss": 3.936099, "eval_loss": 3.940216, "at": "2026-10-01T08:21:52.911398+00:00"}
  ],
  "config": {"...": "..."},
  "promote": true,
  "promoted": true,
  "promotion_error": null,
  "checkpoint": "checkpoints/jobs/1adc741f15164a2e9f0d8c7c883c1103/latest.pt",
  "init_checkpoint": null,
  "metadata": {"init": "scratch"},
  "post_success_error": null,
  "error": null,
  "cancel_requested": false,
  "created_at": "2026-10-01T08:21:49.800302+00:00",
  "started_at": "2026-10-01T08:21:49.800661+00:00",
  "finished_at": "2026-10-01T08:21:54.187083+00:00"
}
```

**When is it really done?** Wait for **`state` = `succeeded` AND `promoted` = `true`**. A job can succeed but not
go live, for example if you set `promote` to `false`. If it did not go live because of a problem, the reason is in
`promotion_error`.

### The job (what each field means)

| Field | What it means in simple words |
| --- | --- |
| `id` | The job's name. |
| `state` | `queued` = waiting to start. `running` = studying now. `succeeded` = finished well. `failed` = something went wrong (see `error`). `cancelled` = someone stopped it. |
| `step` and `max_steps` | Steps done, and the total planned. |
| `progress` | `step ÷ max_steps`. 0 is the start, 1 is the end. 0.5 is half done. |
| `latest` | The newest score reading: `step`, `train_loss`, `eval_loss`, and the time. |
| `history` | Every score reading so far. A reading is taken at step 1 and then every `eval_interval` steps. |
| `config` | The exact settings used after your changes. |
| `promote` | Whether it was asked to go live when done. |
| `promoted` | Whether it **did** go live. |
| `promotion_error` | If it should have gone live but could not, why. Otherwise `null`. |
| `checkpoint` | The file name of the finished model. |
| `init_checkpoint` | The model it started from, if you used `current` or `auto`. Otherwise `null`. |
| `metadata` | Extra notes. Knowledge jobs include a `knowledge` section (see 6.6). |
| `post_success_error` | A problem in the last cleanup step (such as marking knowledge as learned). Normally `null`. |
| `error` | If `failed`, the reason. Otherwise `null`. |
| `cancel_requested` | `true` if someone asked it to stop. |
| `created_at`, `started_at`, `finished_at` | The times. `null` until that moment is reached. |

### How to read the scores ("loss")
**Loss** is a score for how wrong the model's guesses are. **Lower is better.**
- `train_loss` is the score on the **textbook** (`train.txt`).
- `eval_loss` is the score on the **exam** (`eval.txt`), which the model never studies from.

A new model starts near **5.5** (pure guessing). A good run drives `train_loss` below 0.2.
If `train_loss` keeps falling but `eval_loss` goes **up**, the model is memorizing. That signals the corpus or training run needs review.
It will repeat what it studied but struggle with new wording. The fix is more varied text.

### `POST /train/{job_id}/cancel`
**What it does.** Asks a running job to stop. **Key needed:** yes. Returns **202**.
Stopping is not instant: the job stops at its next step. The first reply may still say `running` with
`cancel_requested: true`. Check again a moment later and `state` will be `cancelled`. The live model stays exactly
as it was.

If the job is already finished you get `409` with a message such as `job <id> already succeeded`. `404` means no
such job.

---

## 6.6 Knowledge

**Knowledge** is a list of lessons waiting to be studied. Adding a lesson does **not** change the model. It sits
as **`pending`**. When you run **`POST /knowledge/train`**, the model studies them, and they become **`trained`**.

### `POST /knowledge`
**What it does.** Adds one to 500 lessons in one go. **Key needed:** yes (training). Returns **201**.
It is all or nothing: if a single lesson is invalid, **none** are saved.

**What you send**

| Field | Required | What it means |
| --- | --- | --- |
| `items` | **Yes** | A list of 1 to 500 lessons. Each lesson has a `kind`, which decides its shape. |

**Fields that every lesson can have**

| Field | Required | Default | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `kind` | **Yes** | — | `text`, `qa` or `reasoning` | The type of lesson. |
| `tags` | No | none | up to 20 labels; each 1 to 50 characters of letters, digits and `. : / _ -` | Labels to group lessons. You can choose lessons by tag when training. |
| `source` | No | none | up to 200 letters | Where it came from. For your own records only. |
| `remember` | No | `false` | `true` or `false` | If `true`, the lesson is **also** saved as memory, so assistant-mode `/generate` and `/chat` can use it before training. |

**The three kinds of lesson**

| `kind` | Extra fields (all required) | Allowed length | Use it for |
| --- | --- | --- | --- |
| `text` | `text` | 1 to 20000 | A fact or passage in plain sentences. **Best for a model trained on plain sentences.** |
| `qa` | `question`, `answer` | question up to 2000; answer up to 5000 | A question and its answer. Studied as `User: question` and `Chit: answer`. |
| `reasoning` | `input`, `reasoning`, `answer` | 5000, 10000, 5000 | A problem, the steps to solve it, and the result. |

**No duplicates.** If you add the exact same lesson again, it is not stored twice. The reply marks it
`created: false`.

**Example**
```json
{
  "items": [
    {"kind": "qa", "question": "Where is Pranav from?", "answer": "Pranav is from India.",
     "tags": ["profile"], "source": "readme", "remember": true},
    {"kind": "text", "text": "Chit runs on a small CPU server.", "tags": ["infra"]},
    {"kind": "reasoning", "input": "Is 6 even?", "reasoning": "6 divided by 2 is 3 with no remainder.", "answer": "Yes."}
  ]
}
```

**What you get back**
```json
{
  "created": 3,
  "duplicates": 0,
  "items": [
    {
      "id": "c5f696d2dd414f72bcfd2f441bfa20b9",
      "kind": "qa",
      "payload": {"question": "Where is Pranav from?", "answer": "Pranav is from India."},
      "tags": ["profile"],
      "source": "readme",
      "status": "pending",
      "created_at": "2026-10-01T08:21:49.790078+00:00",
      "trained_at": null,
      "trained_job_id": null,
      "created": true,
      "memory_id": "c8a3f59d-0d55-4ec6-85a5-4970ce9427b3"
    }
  ]
}
```
(The real reply lists all three lessons. One is shown here to keep it short.)

| Field | What it means |
| --- | --- |
| `created` (top) | How many lessons were new. |
| `duplicates` | How many already existed. |
| `items` | One entry per lesson you sent, in the same order. |
| `items[].created` | `true` = new. `false` = it already existed. |
| `items[].memory_id` | The memory note made because of `remember: true`. `null` if you did not ask. |

The other fields are explained in "A knowledge entry" below.

**Tip.** At the current data and training scale, Chit may learn familiar wordings more reliably than new combinations. Add the same fact in different words
(as separate lessons). That is far more useful than one lesson.

### `GET /knowledge`
**What it does.** Lists stored lessons, newest first. **Key needed:** yes (training).

**What you send** (after `?`)

| Field | Required | Default | Allowed | What it means |
| --- | --- | --- | --- | --- |
| `status` | No | all | `pending` or `trained` | Only lessons not yet studied, or already studied. |
| `kind` | No | all | `text`, `qa`, `reasoning` | Only this kind. |
| `tag` | No | none | up to 10; repeat it | Only lessons that have **all** the given tags. Example: `?tag=profile&tag=infra`. |
| `limit` | No | 50 | 1 to 500 | Page size. |
| `offset` | No | 0 | 0 or more | How many to skip. |

Example address: `/knowledge?status=pending&limit=2`

**What you get back**
```json
{"total": 3, "limit": 2, "offset": 0, "items": [ {"id": "0323d7db14744225ba9f7d8d563462da", "kind": "reasoning", "...": "..."} ]}
```

### `GET /knowledge/stats`
**What it does.** Gives quick counts. **Key needed:** yes (training). **What you send:** nothing.
```json
{"total": 3, "by_status": {"pending": 3, "trained": 0}, "by_kind": {"text": 1, "qa": 1, "reasoning": 1}}
```
`by_status` says how many are waiting and how many are learned. `by_kind` counts each type.

### `GET /knowledge/{entry_id}`
**What it does.** Shows one lesson. **Key needed:** yes (training). `404 knowledge entry not found` if the ID is wrong.

### `DELETE /knowledge/{entry_id}`
**What it does.** Removes a lesson from future training. **Key needed:** yes (training). Returns **204** (nothing to show).
**Important:** if the model **already learned** the lesson, it keeps what it learned. To truly remove it, delete the
lesson and then retrain from scratch (`init: "scratch"`).

### A knowledge entry (what each field means)

| Field | What it means |
| --- | --- |
| `id` | The lesson's ID. |
| `kind` | `text`, `qa` or `reasoning`. |
| `payload` | The lesson's content. `{text}`, or `{question, answer}`, or `{input, reasoning, answer}`. |
| `tags` | Its labels. |
| `source` | Where it came from, if you said. |
| `status` | `pending` = not studied yet. `trained` = the model has studied it. |
| `created_at` | When it was added. |
| `trained_at` | When it was studied. `null` if still pending. |
| `trained_job_id` | Which training job studied it. `null` if still pending. |

### `POST /knowledge/train`
**What it does.** Starts a training job that studies your stored lessons. It makes a fresh study file out of the
lessons (and by default, also your regular `train.txt`), then trains like `POST /train`.
**Key needed:** yes (training). Returns **202** and a job (see "The job" above).

**What you send.** It accepts **everything `POST /train` accepts** (`config`, `seed`, `device`, `model`,
`training`, `promote`). One difference: `init` defaults to **`auto`** here, not `scratch`. It also has these extra fields:

| Field | Default | Allowed | What it means in simple words |
| --- | --- | --- | --- |
| `select` | `all` | `all` or `pending` | `all` = study every lesson (best, because it keeps older lessons fresh). `pending` = only lessons not yet learned. |
| `tags` | none | up to 10 | Only study lessons that have **all** these tags. |
| `include_base` | `true` | `true` or `false` | Also include the regular `train.txt` text. Keep it `true` so the model does not lose its general text. |
| `repeat` | 3 | 1 to 100 | How many times each lesson appears in the study file. A small set of lessons needs a bigger number (10 to 30) to make a difference. |

**Example**
```json
{"config": "chit_strong", "repeat": 20}
```

**What you get back.** A job. Its `metadata` has a `knowledge` section:
```json
"metadata": {
  "init": "auto",
  "knowledge": {"entries": 3, "select": "all", "tags": [], "repeat": 5, "include_base": true,
                "dataset_bytes": 12737, "dataset_sha256": "5bc98b17...", "manifest": "checkpoints/jobs/<id>/dataset/manifest.json"}
}
```
`entries` is how many lessons were used. `dataset_bytes` is the size of the study file. `dataset_sha256` is a
fingerprint of it (it changes if the content changes). `manifest` is the file listing what was included.

**When do lessons become `trained`?** Only when the job **succeeds and goes live**. If the job fails or is
cancelled, the lessons stay `pending`.

**Common problems:** `422 no knowledge matches this request` means there are no lessons (or none match your
`tags`/`select`): add some with `POST /knowledge`. `409` means a job is already running.

---

## 6.7 Training text files

`train.txt` and `eval.txt` are what training uses. They often arrive from outside the API (for example a folder on
the server). These two endpoints let you check them and prepare them.

### `GET /data`
**What it does.** Inspects the two text files **as they are on the server right now**.
**Key needed:** yes (training).
**When to use it.** Before every training, and after anyone replaces the files.

**What you send** (after `?`)

| Field | Required | Default | What it means |
| --- | --- | --- | --- |
| `config` | No | `chit_cpu_learning` | Which preset's files and `block_size` to check. Name it, for example `?config=chit_strong`. `404` if it does not exist. |

**What you get back**
```json
{
  "config": "chit_strong",
  "block_size": 128,
  "train": {"path": "data/train.txt", "bytes": 11887, "lines": 242, "sha256": "5c977168...", "modified_at": "2026-10-01T08:21:47.369941+00:00"},
  "eval":  {"path": "data/eval.txt",  "bytes": 2198,  "lines": 43,  "sha256": "67e28cc8...", "modified_at": "2026-10-01T08:21:47.369423+00:00"},
  "checks": {
    "train_larger_than_block_size": true,
    "eval_larger_than_block_size": true,
    "eval_distinct_lines": 43,
    "eval_lines_also_in_train": 0,
    "train_repeated_lines": 0
  },
  "warnings": [],
  "ready_to_train": true,
  "sources": [{"name": "eval.txt", "bytes": 2198}, {"name": "prompts.txt", "bytes": 1351}]
}
```

| Field | What it means in simple words |
| --- | --- |
| `block_size` | The model's reading window. The files must be longer than this. |
| `train`, `eval` | Facts about each file: `path` (where it is), `bytes` (size, about one per letter), `lines`, `sha256` (a **fingerprint** that changes if even one letter changes), `modified_at` (last change). `null` if the file is missing. |
| `checks.train_larger_than_block_size` | `true` = big enough. `false` = too small to train on. |
| `checks.eval_larger_than_block_size` | Same, for the exam file. |
| `checks.eval_distinct_lines` | How many different lines the exam has. |
| `checks.eval_lines_also_in_train` | How many exam lines are **also in the textbook**. This should be low. If the exam repeats the textbook, the scores look better than the model really is. (Lines like `I do not know.` repeating is fine.) |
| `checks.train_repeated_lines` | Lines repeated inside the textbook. Just information. Repeating is sometimes on purpose. |
| `warnings` | A list of problems in plain sentences: a missing file, an exam under 1 KB (scores will be noisy), an exam under 2% of the textbook, or too much overlap. |
| `ready_to_train` | **`true` = go ahead.** Both files exist and are longer than `block_size`; configured source streams must also be ready. |
| `training_sources` | For a source-aware preset, its configured streams with weights and file readiness. |
| `sources` | Up to 100 `.txt` or `.md` files in the data folder that `POST /data/split` can use. |

**Tip.** If you replace `train.txt` from outside the API, compare the `sha256` before and after to confirm the new
file really arrived.

### `POST /data/split`
**What it does.** Takes **one big text file** that is already in the server's data folder and cuts it into a
`train.txt` and an `eval.txt`. No line ends up in both.
**Key needed:** yes (training).
This operation is not available for source-aware presets; split or curate the configured source files directly.
**When to use it.** You have one large collection of text and do not want to divide it by hand.

**What you send**

| Field | Required | Default | Allowed | What it means in simple words |
| --- | --- | --- | --- | --- |
| `source` | **Yes** | — | a plain file name, no folders, up to 100 letters | The big file to cut. It must already be in the data folder. See `sources` in `GET /data`. |
| `config` | No | `chit_cpu_learning` | an existing preset | Decides **where the two files are written** and how large they must be (more than its `block_size`). |
| `by` | No | `line` | `line` or `paragraph` | What counts as one piece. `paragraph` keeps blocks separated by an empty line together. Use it for Q&A pairs so a question never gets separated from its answer. |
| `eval_fraction` | No | 0.1 | above 0 and below 0.5 | The share set aside for the exam. 0.1 means 10%. |
| `seed` | No | 42 | 0 to 4294967295 | Fixes the shuffle. The same input and seed always give the same split. |
| `overwrite` | No | `false` | `true` or `false` | You **must** set `true` if the output files already exist. The old files are kept as copies ending in `.bak`. |
| `dry_run` | No | `false` | `true` or `false` | `true` = show what would happen but **write nothing**. |

**What it does with your text.** It removes empty lines and exact repeats (ignoring capital letters and extra
spaces), shuffles everything, and sets the exam share aside. It does not notice sentences that are only reworded.
The files are written safely, so training never reads a half-written file. It is **refused while training is running**.

**Always do a practice run first** (`dry_run`):
```json
{"source": "corpus.txt", "config": "chit_strong", "eval_fraction": 0.1, "dry_run": true}
```
**What you get back**
```json
{
  "source": "corpus.txt",
  "config": "chit_strong",
  "by": "line",
  "seed": 42,
  "duplicates_removed": 0,
  "train": {"path": "data/train.txt", "items": 218, "bytes": 10740},
  "eval": {"path": "data/eval.txt", "items": 24, "bytes": 1147},
  "would_overwrite": ["data/train.txt", "data/eval.txt"],
  "warnings": [],
  "written": false,
  "backups": []
}
```

| Field | What it means |
| --- | --- |
| `duplicates_removed` | How many repeated pieces were dropped. |
| `train`, `eval` | Where each file goes, how many `items` (lines or paragraphs) it gets, and its size in `bytes`. |
| `would_overwrite` | Existing files this would replace. |
| `warnings` | For example, a small exam file. |
| `written` | `false` for a practice run. `true` once files were really written. |
| `backups` | The `.bak` copies that were made of your old files. |

When it looks right, send the same body with `"dry_run": false` and `"overwrite": true`.

**Common problems**

| You see | Why | Fix |
| --- | --- | --- |
| `404` | The source file or preset does not exist, or the file name points outside the data folder. | Check `sources` in `GET /data`. |
| `409` | The files already exist and `overwrite` is `false`, **or** a training job is running. | Set `overwrite` to `true`, or wait for the job. |
| `422` | The name has a slash or odd characters, the file is not plain text, there are fewer than 2 different lines, or a resulting file would not be longer than `block_size`. **Nothing is written.** | Fix the name, or add more text. |
| `500` | The server could not write the files. | The folder may be read-only. Ask the server owner. |

---

## 7. When something goes wrong

Errors come back as JSON with a `detail` message. Here is what they usually mean.

| You see | In plain words | What to do |
| --- | --- | --- |
| `401` `invalid or missing API key` | The key is missing or wrong. | Send the header `X-API-Key: YOUR_KEY`. Check for extra spaces. |
| `403` `training API disabled` | This server has no API key set, so training features are off. | The server owner must set `CHIT_API_KEY`. |
| `404` ... `not found` | The thing you named does not exist. | Check the ID or name. IDs must be copied exactly. |
| `409` | A conflict. A job is already running, or a file would be overwritten. | Read `detail`. It names the running job or the existing files. |
| `422` | Your request has a problem. | Read `detail`. It says which field and why. |
| `500` | A problem inside the server. | Tell the server owner. |
| `503` | No trained model yet. | Train one (section 5). |

### Reading a 422 message
A `422` has one of two shapes.

**Shape 1 — a field is wrong.** It lists each problem with `loc` (where) and `msg` (what):
```json
{"detail": [
  {"type": "string_too_short", "loc": ["body", "prompt"], "msg": "String should have at least 1 character", "input": ""},
  {"type": "less_than_equal", "loc": ["body", "tokens"], "msg": "Input should be less than or equal to 500", "input": 9999}
]}
```
Read it as: "In the body, the field **prompt** is too short (it was empty), and **tokens** must be 500 or less (you sent 9999)."

**Shape 2 — a rule is broken.** A simple list of sentences:
```json
{"detail": ["data.train_file must be larger than model.block_size (128 bytes)"]}
```

**Unknown fields are errors too.** If you spell a field wrong (`temprature`), the server answers `422`
with `extra_forbidden` instead of ignoring it. Check your spelling.

### Reading a 409
```json
{"detail": {"message": "training job 1adc741f15164a2e9f0d8c7c883c1103 is already active",
            "active_job": "1adc741f15164a2e9f0d8c7c883c1103"}}
```
This means "a training job is already running; here is its ID". Watch that one with `GET /train/{id}`.

### If JSON gives you trouble
- Use straight quotation marks `"`, not curly ones `“ ”` (these appear when you copy from Word).
- No comma after the last item in a list or object.
- Put `\n` (a backslash and the letter n) inside quotes for a new line. Do not press Enter inside the quotes.

---

## 8. Step-by-step recipes

### Recipe A: Train on your own text, then ask questions
1. Put your `train.txt` and `eval.txt` in the server's data folder. (Or put one big file there and use
   `POST /data/split`.)
2. `GET /data?config=chit_strong`. Check `ready_to_train` is `true`.
3. `POST /train` with `{"config": "chit_strong", "init": "scratch"}`. Copy the `id`.
4. `GET /train/{id}` every few seconds until `state` is `succeeded` and `promoted` is `true`.
5. `POST /generate` with `{"prompt": "Explain how memory helps Chit.", "tokens": 60, "temperature": 0}`.

### Recipe B: Teach Chit new facts without touching any files
1. `POST /knowledge` with several `text` lessons. Write each fact in 3 or 4 different wordings.
   Add `"remember": true` if you also want assistant-mode `/generate` and `/chat` to use them immediately.
2. `POST /knowledge/train` with `{"config": "chit_strong", "repeat": 20}`. Copy the `id`.
3. Watch `GET /train/{id}` until it succeeds.
4. `GET /knowledge/stats`. The lessons moved from `pending` to `trained`.
5. Test with `POST /generate`.

### Recipe C: Build a chat window
1. Send the first message: `POST /chat` with `{"message": "Hello"}`. **Save the `session_id`** from the reply.
2. Send every next message with the same `session_id`.
3. To show the history: `GET /sessions/{id}`.
4. When finished: `DELETE /sessions/{id}`.

### Recipe D: Make Chit remember something right now (no training)
1. `POST /memory` with `{"content": "The office opens at 9 am.", "importance": 0.9}`.
2. `GET /memory/search?q=office` finds it.
3. `/chat` automatically shows matching notes to the model.

### Recipe E: Stop a training job you started by mistake
1. `GET /train` to see the running job's `id`.
2. `POST /train/{id}/cancel`.
3. `GET /train/{id}` again after a moment. `state` should be `cancelled`. The live model is unchanged.

### Recipe F: Cut one big file into train and exam files
1. Put the file (for example `corpus.txt`) in the data folder.
2. `POST /data/split` with `"dry_run": true`. Check the numbers.
3. Repeat with `"dry_run": false` and `"overwrite": true` (if `train.txt` already exists).
4. `GET /data?config=chit_strong` and confirm `ready_to_train` is `true`.

---

## 9. Tips for better answers

1. **Write requests naturally, including Markdown.** Assistant-mode `/generate` and `/chat` keep headings,
   lists, tables, quotes, and code fences in context. Chit learns how to respond to them from varied examples.
2. **Use `temperature: 0` for steadier answers.** `stop` is optional; assistant mode stops at a turn marker by default.
3. **Do not add extra dots or odd words.** `A GPU can..` (two dots) confused the model once. `A GPU can` worked.
4. **Teach each fact in several wordings.** Four lines saying the same thing in different words beat one line.
5. **More and varied text is the biggest improvement.** A few pages makes a model that repeats. Hundreds of pages
   makes it more flexible.
6. **Keep the exam file different.** `eval.txt` should hold sentences that are **not** in `train.txt`, otherwise its
   score tells you nothing.
7. **Check your results with a fixed list of prompts** after each training, and add text for the ones that fail.
8. **Review difficult answers.** The current corpus and training budget can be expanded within the CPU server's limits.
   Memory and taught knowledge provide context,
   while `/train` and `/knowledge/train` retain their separate training roles.

---

## 10. Glossary

| Word | Simple meaning |
| --- | --- |
| **API** | A way for programs to talk to each other. |
| **API key** | A secret password for the API. |
| **Attention** | The part of the model that decides which earlier words matter for the next one. |
| **Block size** | How much text the model can look at at once, in letters. |
| **Checkpoint** | A saved copy of the model. |
| **Config** | A named settings file (a preset) for training. |
| **Endpoint** | One thing the API can do, with its own address. |
| **Eval / evaluation** | The "exam": text the model is tested on but does not study from. |
| **Fine-tuning** | Continuing to train an existing model with a bit more material. |
| **JSON** | A way to write labeled information with curly brackets. |
| **Job** | One training run. |
| **Knowledge** | Lessons waiting to be studied by the model. |
| **Layer** | One stage of the model. More layers means a more powerful, slower model. |
| **Learning rate** | How big each learning step is. |
| **Loss** | A score of how wrong the model is. Lower is better. |
| **Memory** | The notebook of facts that is not part of the model. |
| **Memorizing (overfitting)** | The model repeats its textbook but cannot handle new wording. |
| **Model** | The "brain" that writes text. |
| **Parameters** | The adjustable numbers inside the model. |
| **Prompt** | The start of the text you give the model. |
| **Session** | One conversation and its saved messages. |
| **Step** | One round of study during training. |
| **Temperature** | Randomness. 0 means steady. Higher means more random. |
| **Token** | A small piece of text. In Chit, about one letter. |
| **Training** | Studying text so the model improves. |
| **Weights** | Another word for the model's adjustable numbers. |

---

## 11. One-page cheat sheet

| What you want | Method and address | Key? | What you send |
| --- | --- | --- | --- |
| Is it alive? | `GET /health` | No | nothing |
| Which model is live? | `GET /model` | Yes | nothing |
| Answer or create from a request | `POST /generate` | Yes | `prompt`, optional `tokens`, `temperature`, `stop` |
| Continue raw text | `POST /generate` | Yes | `prompt`, `mode: "continue"` |
| Chat | `POST /chat` | Yes | `message`, optional `session_id`, `task`, `temperature` |
| Start a conversation | `POST /sessions` | Yes | nothing |
| List conversations | `GET /sessions` | Yes | optional `limit`, `offset` |
| Read a conversation | `GET /sessions/{id}` | Yes | optional `limit` |
| Delete a conversation | `DELETE /sessions/{id}` | Yes | nothing |
| Save a fact | `POST /memory` | Yes | `content`, optional `memory_type`, `importance`, `tags` |
| Search facts | `GET /memory/search?q=...` | Yes | `q`, optional `limit` |
| Delete a fact | `DELETE /memory/{id}` | Yes | nothing |
| See presets | `GET /train/configs` | Yes* | nothing |
| Start training | `POST /train` | Yes* | `config`, optional settings |
| List jobs | `GET /train` | Yes* | nothing |
| Watch a job | `GET /train/{id}` | Yes* | nothing |
| Stop a job | `POST /train/{id}/cancel` | Yes* | nothing |
| Add lessons | `POST /knowledge` | Yes* | `items` |
| List lessons | `GET /knowledge` | Yes* | optional `status`, `kind`, `tag`, `limit`, `offset` |
| Count lessons | `GET /knowledge/stats` | Yes* | nothing |
| One lesson | `GET /knowledge/{id}` | Yes* | nothing |
| Delete a lesson | `DELETE /knowledge/{id}` | Yes* | nothing |
| Train on lessons | `POST /knowledge/train` | Yes* | `config`, optional `repeat`, `select`, `tags`, `include_base` |
| Check text files | `GET /data?config=...` | Yes* | `config` |
| Cut a big file | `POST /data/split` | Yes* | `source`, optional `config`, `by`, `eval_fraction`, `overwrite`, `dry_run` |

\* "Yes*" means the training key rule: the server must have an API key set, and you must send it.

**Remember:** use `temperature: 0` for steadier answers, and wait for
`succeeded` **and** `promoted: true` after training.

## Model Candidates and Administration

These routes allow you to review completed training runs and safely swap the live model in production.

### GET /candidates
Returns a list of all finished candidate models and their Golden Gate evaluation scores.

### POST /candidates/{job_id}/evaluate
Starts a background evaluation of a candidate model against the 50 Golden Gate behavioral prompts. 

### POST /candidates/{job_id}/promote
Promotes an evaluated candidate to be the live Champion, safely hot-swapping the active model. **Requirement:** The candidate must pass the Golden Gate evaluation.

### POST /admin/rollback
Instantly restores the previous live model (Champion) from the archive if a promoted candidate starts behaving poorly.
- **Parameters:** 	o_sha256 (the exact hash of the previous model to restore).

### POST /admin/reload
Force-reloads the active Champion model from the disk into memory.
