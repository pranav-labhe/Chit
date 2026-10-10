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
