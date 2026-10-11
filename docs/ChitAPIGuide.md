# Chit API Guide

This guide provides practical instructions and best practices for interacting with the Chit API. For a full technical specification, see [API.md](../API.md).

## 🚀 Getting Started

To interact with Chit, you need an `X-API-Key`. If you are running the server locally, this is set via the `CHIT_API_KEY` environment variable.

**Authentication Header:**
`X-API-Key: your_secret_key_here`

---

## 💬 Conversational AI (`/chat`)

The `/chat` endpoint is designed for natural, context-aware dialogue.

### Understanding the "Cognitive Loop"
When you send a message to `/chat`, Chit performs the following steps:
1. **Recall:** It searches the `MemoryStore` for facts related to your message.
2. **Context Assembly:** It retrieves the recent history of your session from the `SessionStore`.
3. **Fact Injection:** It injects extracted session facts (entities, preferences) into the prompt.
4. **Generation:** The model generates a response based on this combined context.

### Best Practices for Chat
- **Maintain Session IDs:** Always capture the `session_id` from the first response and send it back in subsequent requests. This is how Chit "remembers" the current conversation.
- **Task Switching:** Use the `task` parameter to change how Chit behaves. Use `"chat"` for general dialogue and `"continue"` for raw text completion.
- **Handling Overload:** Because Chit uses a bounded inference queue, you may receive a `429 Too Many Requests` error during peak load. Implement a simple **exponential backoff** (wait 1s, then 2s, then 4s) in your client.

### Deep Thinking & Chain-of-Thought
Chit supports native test-time compute via Chain-of-Thought (CoT). Passing `"think": true` activates Chit's reasoning attention heads, generating an intermediate deduction scratchpad before the final answer.

**Request Payload (`POST /chat`):**
```json
{
  "message": "Ravi has 8 apples. He gives 3 to Soham. How many remain?",
  "session_id": "9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c",
  "think": true
}
```

**Response Payload:**
```json
{
  "text": "5 apples.",
  "session_id": "9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c",
  "confidence": 0.942,
  "is_incomplete": false,
  "is_uncertain": false,
  "metadata": {
    "task": "chat",
    "memory_ids": [],
    "thoughts": "Ravi starts with 8 apples. He gives away 3. 8 minus 3 equals 5.",
    "thought_tokens": 19,
    "confidence": 0.942,
    "is_incomplete": false,
    "is_uncertain": false,
    "needs_retrieval": false
  }
}
```

### Inference Confidence & Completeness Detection
Chit evaluates token-level softmax probabilities during generation to calibrate mathematical uncertainty and completeness:
- **`confidence`**: Geometric mean of chosen token probabilities in $[0.0, 1.0]$.
- **`is_incomplete`**: Set to `true` if generation reached the token limit mid-sentence without terminal punctuation (`.`, `!`, `?`, `"`, `'`, `\n`).
- **`is_uncertain`**: Set to `true` if confidence drops below 0.40, indicating model uncertainty on unseen or out-of-distribution topics.
- **`needs_retrieval`**: Triggers when uncertainty is high or local memory has no match, autonomously initiating web search.

### Autonomous Internet Search (Self-RAG)
Chit features a built-in, zero-dependency autonomous web retrieval engine:
- **Autonomous Two-Pass Self-RAG**: When asked about unknown entities or facts, Chit generates an initial response. If confidence is low ($C < 0.40$) and local memory has no answer (`needs_retrieval = true`), Chit automatically queries DuckDuckGo in the background, extracts and budgets the top factual snippets, injects them into `Known memory: - [Web] ...`, and regenerates a grounded answer.
- **Explicit Web Search (`search: true`)**: You can also force real-time web retrieval on any chat turn by passing `"search": true` in the request body (or clicking "🌐 Search Web" in the UI).
- **Web Grounding Metadata**: When an answer is grounded via search, the response includes `"web_grounded": true` and `"sources": ["..."]` containing the retrieved web snippets.

**When to use Thinking & Search:**
- **Use `think: true`**: For multi-step math, word puzzles, logical deductions, or strict rule following where immediate token generation could lead to premature reasoning mistakes.
- **Use `search: true`**: When asking about real-time events, live facts, or specific topics outside the model's training data.
- **Use standard chat**: For everyday conversation, greetings, and general queries. Chit will still autonomously search the web if it detects it doesn't know the answer!

---

## ⚡ Direct Generation (`/generate`)

The `POST /generate` endpoint supports both single-shot assistant answers and raw text continuation.

### Assistant Mode (`mode: "assistant"`, default)
Assistant mode formats the request as an assistant turn (`User: ... \n Chit:`), recalls relevant long-term memories, and returns rich inference metadata.
- **Web Search & Thinking**: Just like `/chat`, `/generate` supports `"search": true` for live web retrieval grounding and `"think": true` for chain-of-thought deduction.
- **Rich Response Payload**:
  ```json
  {
    "text": "Relevant memories can be included in the request context.",
    "confidence": 0.912,
    "web_grounded": false,
    "sources": [],
    "is_uncertain": false,
    "is_incomplete": false,
    "metadata": { "task": "chat", ... }
  }
  ```

### Raw Continuation Mode (`mode: "continue"`)
In `continue` mode, the prompt is sent directly to the model as an unformatted prefix.
- Returns the standard raw schema: `{"text": "..."}`.
- Setting `"search": true` or `"think": true` in `continue` mode is disallowed and rejected with HTTP `422 Unprocessable Entity`.

---

## 🧠 Managing Long-term Memory (`/memory`)

Memory allows you to give Chit "permanent" knowledge without needing to retrain the model.

### Writing Effective Memories
To ensure high-quality recall, write memories as **short, self-contained statements**.
- **Bad:** "He lives there." (No context)
- **Good:** "Pranav lives in Nagpur, India." (Self-contained)

### Hybrid Search
Chit uses a hybrid search (Keyword + Vector). This means:
- **Exact matches** (like specific IDs or unique names) are found via keyword search.
- **Conceptual matches** (like "where does he live?" $\rightarrow$ "Pranav lives in India") are found via semantic vector search.

---

## 📚 Teaching the Brain (`/knowledge` & `/train`)

Knowledge is for structured data that should be "baked" into the model's weights.

### The Teaching Workflow
1. **Queue:** Use `POST /knowledge` to add facts, Q&A pairs, or reasoning steps.
2. **Bake:** Use `POST /knowledge/train` to start a training job.
3. **Verify:** Check `GET /train/{id}` to ensure the job succeeded and the model was promoted.

**When to use Memory vs. Knowledge?**
- Use **Memory** for dynamic, user-specific facts (e.g., "The user prefers Python").
- Use **Knowledge** for static, universal truths (e.g., "The capital of France is Paris").

---

## 🛠️ Technical Constraints

### Context Budgeting
Chit has a finite `block_size` (context window). If a request is too long:
1. The oldest session messages are dropped first.
2. Lowest-ranked memories are dropped next.
3. The request prompt itself is truncated last.

### Tokenization
Depending on the loaded model, Chit uses either **Byte-level** or **BPE** tokenization. 
- **Byte models:** One token $\approx$ one UTF-8 byte.
- **BPE models:** One token $\approx$ a common sub-word.
The API handles this transparently, but you can check the active tokenizer via `GET /model`.
