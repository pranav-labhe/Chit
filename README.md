# Chit — चित् — Pranav's Atmini Brain

Chit is a from-scratch neural-model layer for Atmini.

Milestones covered by this scaffold:
1. neural fundamentals
2. tiny language model
3. tiny Transformer
4. own tokenizer + weights
5. Chit training data
6. external memory
7. reasoning examples
8. Atmini integration boundary
9. CPU/GPU-ready training
10. checkpoint/export foundation for Chit v1

---

## 📖 Complete Beginner's Guide: How to Run Everything

If you are new to programming or this project, don't worry! Follow these simple step-by-step instructions to set up, run, train, and interact with Chit.

### Step 1: Open Your Terminal
Open your command line or terminal (such as Command Prompt, PowerShell, or bash). Make sure you are inside the `Chit` folder.

### Step 2: Install Python & Dependencies
Make sure you have **Python 3.11 or higher** installed. Then install the required packages:
```bash
pip install -r requirements.txt
```
*(Optional: if you want to run tests and developer tools, also install `pip install -r requirements-dev.txt`)*

### Step 3: Train the AI Model
Before talking to Chit, it needs to learn from its training data. Run this command:
```bash
python -m pranav.chit.tools.train --config configs/chit_cpu_learning.json
```
This creates a trained model file saved at `checkpoints/latest.pt`.

### Step 4: Talk to Chit (Interactive Chat)
You can chat directly with your newly trained model using:
```bash
python try_chit.py
```
Type any prompt (e.g., `Atmini`) and press **Enter**! Type Ctrl-C or Ctrl-D to exit.

---

## 🚀 Running the Web API Server

Chit includes a web server so other apps (like Atmini) or web browsers can talk to it.

### 1. Start the Server
First, set your secret API key (used to secure training and teaching) and start the server using **Uvicorn**:

* **Windows PowerShell:**
  ```powershell
  $env:CHIT_API_KEY="change-me"
  uvicorn pranav.chit.api:app --port 8000
  ```
* **Linux / macOS:**
  ```bash
  export CHIT_API_KEY="change-me"
  uvicorn pranav.chit.api:app --port 8000
  ```

## ⚙️ Environment Variables & Configuration

Chit's server and training tools can be customized using environment variables. Here is what each one does and how to set it across different operating systems:

### Available Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `CHIT_API_KEY` | *(None)* | Secret API key required for training and teaching endpoints (sent via `X-API-Key` header). |
| `CHIT_CHECKPOINT` | `checkpoints/latest.pt` | Path to the served AI model checkpoint file. |
| `CHIT_CONFIG_DIR` | `configs` | Directory containing training configuration JSON files. |
| `CHIT_JOBS_DIR` | `checkpoints/jobs` | Directory where background training job outputs and logs are saved. |
| `CHIT_MAX_TRAIN_STEPS` | `100000` | Safety upper bound for maximum training steps. |
| `CHIT_ALLOW_UNAUTHENTICATED_TRAINING` | *(Unset)* | Set to `1` to allow training and teaching without an API key (**local development only**). |
| `CHIT_KNOWLEDGE_DB` | `data/knowledge.db` | SQLite database file storing taught knowledge items. |
| `CHIT_MAX_DATASET_MB` | `200` | Upper size limit in megabytes for generated training datasets. |
| `CHIT_MEMORY_PATH` | `data/memory.json` | JSON file storing external memory items. |

---

### How to Set Environment Variables

* **Windows PowerShell:**
  ```powershell
  $env:CHIT_API_KEY="my-secret-key"
  $env:CHIT_CHECKPOINT="checkpoints/latest.pt"
  ```
* **Windows Command Prompt (`cmd.exe`):**
  ```cmd
  set CHIT_API_KEY=my-secret-key
  set CHIT_CHECKPOINT=checkpoints/latest.pt
  ```
* **Linux / macOS / Git Bash:**
  ```bash
  export CHIT_API_KEY="my-secret-key"
  export CHIT_CHECKPOINT="checkpoints/latest.pt"
  ```

---

## 🔌 Complete API Usage Guide for Beginners

Below is how to interact with each API endpoint using simple commands (`curl` or Python/Browser). Make sure your server is running (`uvicorn pranav.chit.api:app --port 8000`) in another terminal window before running these.

---

### 1. Check Server Health (`GET /health`)
* **Purpose:** Checks if the server is running and healthy.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl http://localhost:8000/health
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/health"
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl http://localhost:8000/health
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.get("http://localhost:8000/health")
  print(res.json())
  ```

---

### 2. View Loaded Model Details (`GET /model`)
* **Purpose:** Shows information about the currently active AI model checkpoint.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl http://localhost:8000/model
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/model"
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl http://localhost:8000/model
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.get("http://localhost:8000/model")
  print(res.json())
  ```

---

### 3. Generate Text (`POST /generate`)
* **Purpose:** Ask the model to continue or complete a piece of text.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST http://localhost:8000/generate \\
    -H "X-API-Key: change-me" \\
    -H "Content-Type: application/json" \\
    -d '{"prompt": "Atmini is", "tokens": 50}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/generate" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"prompt": "Atmini is", "tokens": 50}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST http://localhost:8000/generate -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"prompt\": \"Atmini is\", \"tokens\": 50}"
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.post(
      "http://localhost:8000/generate",
      headers={"X-API-Key": "change-me"},
      json={"prompt": "Atmini is", "tokens": 50}
  )
  print(res.json())
  ```

---

### 4. Chat with Chit (`POST /chat`)
* **Purpose:** Have a conversation using Chit's Q&A and memory format.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "X-API-Key: change-me" \
    -H "Content-Type: application/json" \
    -d '{"message": "Hello Chit!"}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/chat" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"message": "Hello Chit!"}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST http://localhost:8000/chat -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"message\": \"Hello Chit!\"}"
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.post(
      "http://localhost:8000/chat",
      headers={"X-API-Key": "change-me"},
      json={"message": "Hello Chit!"}
  )
  print(res.json())
  ```

---

### 5. Add Memory (`POST /memory`)
* **Purpose:** Store a quick fact in external memory so Chit can recall it instantly during chats.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST http://localhost:8000/memory \
    -H "X-API-Key: change-me" \
    -H "Content-Type: application/json" \
    -d '{"content": "Pranav lives in India."}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/memory" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"content": "Pranav lives in India."}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST http://localhost:8000/memory -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"content\": \"Pranav lives in India.\"}"
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.post(
      "http://localhost:8000/memory",
      headers={"X-API-Key": "change-me"},
      json={"content": "Pranav lives in India."}
  )
  print(res.json())
  ```

---

### 6. Search Memory (`GET /memory/search`)
* **Purpose:** Search through stored memories.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl "http://localhost:8000/memory/search?q=Pranav"
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/memory/search?q=Pranav"
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl "http://localhost:8000/memory/search?q=Pranav"
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.get(
      "http://localhost:8000/memory/search",
      params={"q": "Pranav"}
  )
  print(res.json())
  ```

---

### 7. Delete Memory (`DELETE /memory/{id}`)
* **Purpose:** Remove a specific memory item by its ID.
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X DELETE localhost:8000/memory/1
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/memory/1" -Method Delete
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X DELETE localhost:8000/memory/1
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.delete("http://localhost:8000/memory/1")
  print(res.status_code)
  ```

---

### 8. Teach Chit New Knowledge (`POST /knowledge`)
* **Purpose:** Store new facts or Q&A pairs to be learned in future training sessions. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST localhost:8000/knowledge \
    -H "X-API-Key: change-me" \
    -H "Content-Type: application/json" \
    -d '{"items": [{"kind": "qa", "question": "Who created Chit?", "answer": "Pranav created Chit."}]}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/knowledge" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"items": [{"kind": "qa", "question": "Who created Chit?", "answer": "Pranav created Chit."}]}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST localhost:8000/knowledge -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"items\": [{\"kind\": \"qa\", \"question\": \"Who created Chit?\", \"answer\": \"Pranav created Chit.\"}]}"
  ```
* **Python equivalent:**
  ```python
  import requests
  headers = {"X-API-Key": "change-me"}
  payload = {
      "items": [
          {"kind": "qa", "question": "Who created Chit?", "answer": "Pranav created Chit."}
      ]
  }
  res = requests.post("http://localhost:8000/knowledge", json=payload, headers=headers)
  print(res.json())
  ```

---

### 9. Train on Taught Knowledge (`POST /knowledge/train`)
* **Purpose:** Start a background training job using all the knowledge you taught Chit. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST localhost:8000/knowledge/train \
    -H "X-API-Key: change-me" \
    -H "Content-Type: application/json" \
    -d '{"training": {"max_steps": 300}}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/knowledge/train" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"training": {"max_steps": 300}}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST localhost:8000/knowledge/train -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"training\": {\"max_steps\": 300}}"
  ```
* **Python equivalent:**
  ```python
  import requests
  headers = {"X-API-Key": "change-me"}
  payload = {"training": {"max_steps": 300}}
  res = requests.post("http://localhost:8000/knowledge/train", json=payload, headers=headers)
  print(res.json())
  ```

---

### 10. Start General Training (`POST /train`)
* **Purpose:** Train a new model using built-in configuration files. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST localhost:8000/train \
    -H "X-API-Key: change-me" \
    -H "Content-Type: application/json" \
    -d '{"config": "chit_cpu_learning", "training": {"max_steps": 300}}'
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/train" -Method Post -Headers @{"X-API-Key"="change-me"} -ContentType "application/json" -Body '{"config": "chit_cpu_learning", "training": {"max_steps": 300}}'
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST localhost:8000/train -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"config\": \"chit_cpu_learning\", \"training\": {\"max_steps\": 300}}"
  ```
* **Python equivalent:**
  ```python
  import requests
  headers = {"X-API-Key": "change-me"}
  payload = {
      "config": "chit_cpu_learning",
      "training": {"max_steps": 300}
  }
  res = requests.post("http://localhost:8000/train", json=payload, headers=headers)
  print(res.json())
  ```

---

### 11. Check Training Job Status (`GET /train/{id}`)
* **Purpose:** Check progress, loss, and success/failure of a training job.
* **How to run:**
  ```bash
  curl localhost:8000/train/JOB_ID_HERE
  ```
* **Python equivalent:**
  ```python
  import requests
  job_id = "YOUR_JOB_ID_HERE"
  res = requests.get(f"http://localhost:8000/train/{job_id}")
  print(res.json())
  ```

---

### 12. List Available Training Configs (`GET /train/configs`)
* **Purpose:** See which `.json` configuration files are available on the server for training. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -H "X-API-Key: change-me" http://localhost:8000/train/configs
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/train/configs" -Headers @{"X-API-Key"="change-me"}
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -H "X-API-Key: change-me" http://localhost:8000/train/configs
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.get("http://localhost:8000/train/configs", headers={"X-API-Key": "change-me"})
  print(res.json())
  ```

---

### 13. List All Training Jobs (`GET /train`)
* **Purpose:** See a list of all previous and current training jobs. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -H "X-API-Key: change-me" http://localhost:8000/train
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/train" -Headers @{"X-API-Key"="change-me"}
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -H "X-API-Key: change-me" http://localhost:8000/train
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.get("http://localhost:8000/train", headers={"X-API-Key": "change-me"})
  print(res.json())
  ```

---

### 14. Cancel a Training Job (`POST /train/{id}/cancel`)
* **Purpose:** Stop a running training job immediately. *(Requires API Key)*
* **cURL (Linux / macOS / Git Bash):**
  ```bash
  curl -X POST -H "X-API-Key: change-me" http://localhost:8000/train/JOB_ID_HERE/cancel
  ```
* **PowerShell (Windows):**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/train/JOB_ID_HERE/cancel" -Method Post -Headers @{"X-API-Key"="change-me"}
  ```
* **Command Prompt (cmd.exe):**
  ```cmd
  curl -X POST -H "X-API-Key: change-me" http://localhost:8000/train/JOB_ID_HERE/cancel
  ```
* **Python equivalent:**
  ```python
  import requests
  res = requests.post("http://localhost:8000/train/JOB_ID_HERE/cancel", headers={"X-API-Key": "change-me"})
  print(res.json())
  ```

---

### 15. Manage Knowledge Base (`/knowledge` endpoints)
* **List Knowledge (`GET /knowledge`):** List all taught facts. *(Requires API Key)*
  * **cURL:** `curl -H "X-API-Key: change-me" "http://localhost:8000/knowledge?limit=10"`
  * **PowerShell:** `Invoke-RestMethod -Uri "http://localhost:8000/knowledge?limit=10" -Headers @{"X-API-Key"="change-me"}`
  * **Python:** `requests.get("http://localhost:8000/knowledge", headers={"X-API-Key": "change-me"}, params={"limit": 10}).json()`

* **Knowledge Stats (`GET /knowledge/stats`):** Get total count of items. *(Requires API Key)*
  * **cURL:** `curl -H "X-API-Key: change-me" http://localhost:8000/knowledge/stats`
  * **PowerShell:** `Invoke-RestMethod -Uri "http://localhost:8000/knowledge/stats" -Headers @{"X-API-Key"="change-me"}`
  * **Python:** `requests.get("http://localhost:8000/knowledge/stats", headers={"X-API-Key": "change-me"}).json()`

* **Get Single Entry (`GET /knowledge/{id}`):** View a specific fact. *(Requires API Key)*
  * **cURL:** `curl -H "X-API-Key: change-me" http://localhost:8000/knowledge/ENTRY_ID`
  * **PowerShell:** `Invoke-RestMethod -Uri "http://localhost:8000/knowledge/ENTRY_ID" -Headers @{"X-API-Key"="change-me"}`
  * **Python:** `requests.get("http://localhost:8000/knowledge/ENTRY_ID", headers={"X-API-Key": "change-me"}).json()`

* **Delete Entry (`DELETE /knowledge/{id}`):** Remove a fact. *(Requires API Key)*
  * **cURL:** `curl -X DELETE -H "X-API-Key: change-me" http://localhost:8000/knowledge/ENTRY_ID`
  * **PowerShell:** `Invoke-RestMethod -Uri "http://localhost:8000/knowledge/ENTRY_ID" -Method Delete -Headers @{"X-API-Key"="change-me"}`
  * **Python:** `requests.delete("http://localhost:8000/knowledge/ENTRY_ID", headers={"X-API-Key": "change-me"}).status_code`

---

## 🧪 Running Tests
To verify all unit tests pass correctly:
```bash
python -m pytest
```
