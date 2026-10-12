# JARVIS (Local Personal AI Assistant) - Phase 1 Foundation

JARVIS is a local-first, self-hosted, modular personal AI assistant designed to run securely on your computer. This repository contains the monorepo layout, Docker Compose service orchestration, and microservice skeletons representing the system's foundational components.

---

## Directory Layout

```text
jarvis/
├── apps/
│   ├── api/                   # API Gateway (FastAPI, Port 8000)
│   └── desktop/               # Nginx HTML/CSS/JS Dashboard Control Panel (Port 3000)
├── services/
│   ├── orchestrator/          # Coordinator routing decisions to workers (Port 8001)
│   ├── memory/                # Context retrieval and DB indexing adapter (Port 8002)
│   ├── browser/               # Playwright browser agent worker (Port 8003)
│   └── voice/                 # Sound intake, TTS, and STT voice agent worker (Port 8004)
├── shared/
│   ├── contracts/             # Data schemas defining interface protocols
│   ├── config/                # Common environment parses
│   └── security/              # Data encryptors and token auth
├── docs/
│   └── architecture.md        # Deep architectural design details
├── docker-compose.yml         # Container orchestration config
├── .env.example               # Configuration template
├── Makefile                   # UNIX shell script runner
└── run.ps1                    # Windows PowerShell script runner
```

---

## How to Run (Quick Start)

### Requirements
Ensure you have the following installed on your machine:
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker Compose enabled)
* Python 3.11+ (if running scripts locally outside containers)

---

### Step 1: Environment Setup

Create your local `.env` configuration file from the template.

**On UNIX (Linux/macOS):**
```bash
make setup
```

**On Windows (PowerShell):**
```powershell
.\run.ps1 setup
```

---

### Step 2: Launch the Services

Start all database and API microservice containers in the background.

**On UNIX (Linux/macOS):**
```bash
make start
```

**On Windows (PowerShell):**
```powershell
.\run.ps1 start
```

This builds and launches 8 containers:
1. **`postgres`** (Port `5432`) - Database storage
2. **`qdrant`** (Port `6333`, `6334`) - Vector DB memory
3. **`api`** (Port `8000`) - Public gateway
4. **`orchestrator`** (Port `8001`) - Tasks coordinate hub
5. **`memory`** (Port `8002`) - Memory indexing agent
6. **`browser`** (Port `8003`) - Headless web scraper agent
7. **`voice`** (Port `8004`) - Text to speech audio agent
8. **`frontend`** (Port `3000`) - Dashboard Control Panel UI

---

### Step 3: Access the Console

Open your web browser and navigate to:
👉 **[http://localhost:3000](http://localhost:3000)**

You will be greeted by the **JARVIS Control Center Dashboard**. The page will dynamically poll all backend ports and show online indicators. You can use the chat interface to query the Orchestrator, which logs all background agent calls inside the **Orchestrator Trace** panel.

---

## Developer Operations

| Action | UNIX Command | Windows Command |
| :--- | :--- | :--- |
| **Check Logs** | `make logs` | `.\run.ps1 logs` |
| **Check Container Health** | `make status` | `.\run.ps1 status` |
| **Stop Stack** | `make stop` | `.\run.ps1 stop` |
| **Reset & Purge DBs** | `make reset` | `.\run.ps1 reset` |

---

## How Future Agents Plug In

Future capabilities (e.g. `services/research`, `services/code`, `services/tasks`) can be added by:
1. Writing a FastAPI microservice in their respective `services/` subfolder.
2. Registering their routing schema contract in `shared/contracts/schemas.py`.
3. Adding their ports and build triggers to the `docker-compose.yml` file.
4. Implementing the worker integration inside the Orchestrator coordinate routine (`services/orchestrator/main.py`).

Refer to [docs/architecture.md](file:///c:/persnol_project/jarvis/docs/architecture.md) for more details.
