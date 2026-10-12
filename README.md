# 🌌 JARVIS (Project Mark 21)
### *Local Personal Cognitive Engine & Autonomous Multi-Agent Desktop Assistant*

[![Architecture: Microservices](https://img.shields.io/badge/Architecture-Event--Driven%20Microservices-blue.svg)](docs/architecture.md)
[![Platform: Windows 10/11](https://img.shields.io/badge/Platform-Windows%2010%2F11%20Native-0078D6.svg)]()
[![AI: Groq LLM](https://img.shields.io/badge/AI-Groq%20Llama%203%20%2F%20GPT--OSS-orange.svg)]()
[![Container: Docker Compose](https://img.shields.io/badge/Orchestration-Docker%20Compose-2496ED.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()

---

## 📖 Overview

**JARVIS (Project Mark 21)** is an advanced, local-first, autonomous cognitive assistant inspired by Tony Stark's iconic AI. Built from the ground up as an enterprise-grade microservice ecosystem, JARVIS combines high-speed Large Language Model (LLM) reasoning, native operating system automation, intelligent browser interaction, bi-directional voice recognition, and semantic long-term memory.

Unlike standard cloud chatbots that are confined to a browser tab, JARVIS has direct physical agency on your computer: it can launch local software, search the web, compose messages on WhatsApp, look up and play YouTube videos, write algorithms into code editors, and speak back to you through your system speakers.

---

## 🌟 Real-World Scenarios & Key Benefits

JARVIS was engineered not just as a developer tool, but as an empowering cognitive assistant for real-world scenarios:

### 1. 🦮 Assistive Technology & Accessibility for the Visually Impaired
* **The Challenge:** Visually impaired and blind individuals often struggle with complex screen-reader keyboard combinations, inaccessible modern graphical interfaces, and dynamic web layouts.
* **How JARVIS Helps:** With vocal interaction and native OS control, users can navigate their entire digital life using natural spoken language:
  * *"Open WhatsApp and text Mom that I'll be home in 10 minutes"* &rarr; JARVIS launches WhatsApp, finds the contact, writes the message, and confirms verbally.
  * *"Open YouTube and play relaxing instrumental music"* &rarr; JARVIS fetches the top search result, opens the direct video stream, and plays audio through the speakers hands-free.
  * *"What is 350 times 18?"* or *"Summarize the latest space exploration news"* &rarr; JARVIS answers clearly and reads the response out loud.

### 2. ⚡ Hands-Free Engineering & Developer Productivity
* **The Challenge:** Developers frequently lose focus when switching between terminal windows, editors, documentation browsers, and messaging apps.
* **How JARVIS Helps:**
  * Voice-driven task offloading: *"Open Notepad and write a new nucleus sampling algorithm"* &rarr; JARVIS synthesizes the code via Groq and pastes it directly into your active workspace.
  * Rapid contextual lookups and calculations without breaking focus from coding tasks.

### 3. 🍳 Multitasking & Everyday Home Automation
* **The Challenge:** When your hands are occupied (cooking, working out, repairing hardware, or cleaning), reaching for a mouse and keyboard is inconvenient or impossible.
* **How JARVIS Helps:** Users can trigger media playback, draft quick notes, query calculations, and check system metrics across the room using microphone voice input.

### 4. 👵 Accessibility for Non-Tech-Savvy & Elderly Users
* **The Challenge:** Navigating deep Windows hierarchies, Start Menu folders, browser tabs, and application search bars is intimidating for non-technical users.
* **How JARVIS Helps:** Replaces nested menus and complex operating system UI steps with a single spoken command.

### 5. 🔒 Absolute Privacy & Local-First Security
* **The Challenge:** Proprietary cloud assistants send voice transcripts, personal habits, and application state to remote servers.
* **How JARVIS Helps:** JARVIS runs locally in Docker containers and local Python processes. Your vector databases (Qdrant), relational storage (PostgreSQL), and OS controls stay under your sovereign control.

---

## ✨ Features End-to-End

| Category | Capability | Details |
| :--- | :--- | :--- |
| **🧠 Cognitive Core** | **LLM Planner & Router** | Powered by high-speed Groq inference (`openai/gpt-oss-120b` / `llama3`). Performs intent classification, argument extraction, risk assessment, and task delegation. |
| **🖥️ Desktop Automation** | **Native Windows Control** | Native background agent running on Port `8005` with `pywinauto`, `pyautogui`, and `pyperclip`. |
| | **App Registry & Launching** | Instant registry matching for WhatsApp, YouTube, Chrome, Notepad, VS Code, Calculator, Spotify, Command Prompt, etc. |
| | **Automated Content Typing** | Capable of generating code, algorithms, or documents via LLM and typing/pasting directly into editors (e.g. Notepad). |
| | **Direct YouTube Playback** | Scrapes top YouTube search results dynamically and opens direct video URLs (`/watch?v=...`) to start instant playback. |
| | **WhatsApp Automation** | Automatically focuses WhatsApp, searches contacts, types messages, and prepares messages for delivery. |
| **🎙️ Voice Engine** | **Bi-Directional Voice** | Integrated speech recognition (STT) and text-to-speech (TTS) audio feedback through physical PC speakers. |
| | **Spoken UI Controls** | Live microphone listening, "Voice Mode: ON/OFF" toggle, and per-message audio replay buttons. |
| **🌐 Browser Agent** | **Autonomous Web Scraper** | Playwright-powered browser service (Port `8003`) capable of headless browsing, search queries, and content parsing. |
| **💾 Memory & Context** | **Hybrid Storage** | Qdrant vector database (Port `6333`) for semantic memory combined with PostgreSQL (Port `5432`) for structured session persistence. |
| **🎛️ Stark HUD Console** | **Web Control Dashboard** | Glassmorphic dark-mode dashboard (Port `3000`) with real-time health monitors, live RPC Orchestrator Traces, and chat stream. |

---

## 🏛️ System Architecture

```text
                                  +---------------------------------------+
                                  |         User (Voice / Text)           |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |       JARVIS Web HUD (Port 3000)      |
                                  |   Glassmorphic Dashboard & Controls   |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |      API Gateway (FastAPI :8000)      |
                                  |      Authentication & Event Queue     |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |       Orchestrator Hub (:8001)        |
                                  |    Cognitive LLM Planner & Router     |
                                  +---------------------------------------+
                                       /              |              \
                                      /               |               \
                                     v                v                v
                 +-----------------------+ +--------------------+ +----------------------+
                 | Windows Desktop Agent | |   Browser Worker   | |    Memory Service    |
                 |      (Port 8005)      | |    (Port 8003)     | |     (Port 8002)      |
                 |   Native OS Control   | | Playwright Scraper | |  Qdrant & PostgreSQL |
                 +-----------------------+ +--------------------+ +----------------------+
                             |
                             +--> OS Actions: Launch Apps, Play YouTube,
                                  Automate WhatsApp, Write to Notepad,
                                  Play Audio via Physical Speakers
```

---

## 📂 Project Structure

```text
jarvis/
├── apps/
│   ├── api/                   # API Gateway (FastAPI, Port 8000)
│   └── desktop/               # Stark HUD Dashboard UI (Port 3000)
├── services/
│   ├── orchestrator/          # Cognitive LLM Planner & Task Dispatcher (Port 8001)
│   ├── desktop/               # Native Windows Desktop Automation Agent (Port 8005)
│   ├── memory/                # Qdrant & PostgreSQL Context Vector Store (Port 8002)
│   ├── browser/               # Playwright Web Automation Agent (Port 8003)
│   └── voice/                 # Speech Recognition & TTS Audio Engine (Port 8004)
├── shared/
│   ├── contracts/             # Pydantic schemas and RPC protocols
│   ├── config/                # Centralized environment settings
│   └── security/              # Token auth and encryption helpers
├── tests/                     # Automated test suites & end-to-end integration tests
├── docker-compose.yml         # Container orchestration manifest
├── requirements.txt           # Master project dependencies
├── .env.example               # Configuration template
├── Makefile                   # UNIX shell task runner
└── run.ps1                    # Windows PowerShell master runner
```

---

## 💻 Hardware & Software Requirements

### System Requirements
* **Operating System:** Windows 10 or Windows 11 (64-bit recommended for native desktop automation features).
* **Processor:** Modern multi-core CPU (Intel Core i5/i7/i9 or AMD Ryzen 5/7/9).
* **Memory:** Minimum 8 GB RAM (16 GB recommended for concurrent Docker containers).
* **Audio:** Microphone and speakers/headphones for voice interaction.

### Software Prerequisites
1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/):** Installed with Docker Compose enabled.
2. **[Python 3.11+](https://www.python.org/downloads/):** Installed and added to system `PATH`.
3. **[Git](https://git-scm.com/):** For version control.
4. **Groq API Key:** A free API key from [Groq Console](https://console.groq.com/) for lightning-fast LLM planning.

---

## 🚀 Quick Start Guide

### Step 1: Clone the Repository
```bash
git clone https://github.com/rohith198023/Project_Mark_21.git
cd Project_Mark_21
```

### Step 2: Configure Environment Variables
Create your local `.env` file from the provided template:

**Windows (PowerShell):**
```powershell
.\run.ps1 setup
```

**Linux / macOS:**
```bash
make setup
```

Open `.env` and add your Groq API key:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

---

### Step 3: Launch Docker Microservices
Start the containerized stack (API Gateway, Orchestrator, Memory, Browser, Voice, and Dashboard):

**Windows (PowerShell):**
```powershell
.\run.ps1 start
```

**Linux / macOS:**
```bash
make start
```

This automatically boots 8 services:
* **PostgreSQL** (`5432`)
* **Qdrant Vector DB** (`6333`, `6334`)
* **API Gateway** (`8000`)
* **Orchestrator** (`8001`)
* **Memory Service** (`8002`)
* **Browser Service** (`8003`)
* **Voice Service** (`8004`)
* **Dashboard Frontend** (`3000`)

---

### Step 4: Start the Windows Desktop Agent
To allow JARVIS to control your Windows desktop (launch apps, type into Notepad, automate WhatsApp, play YouTube):

Open a separate PowerShell terminal as Administrator and run:
```powershell
.\run.ps1 desktop
```
*This installs native desktop requirements (`pywinauto`, `pyautogui`, `pyperclip`) and runs the agent on port `8005`.*

---

### Step 5: Access the JARVIS HUD
Open your browser and navigate to:
👉 **[http://localhost:3000](http://localhost:3000)**

1. Check that all status indicators in the **System Monitor** are green (`ONLINE`).
2. Type or click the **Microphone** icon to give voice commands!

---

## 🗣️ Example Commands

| Command | Action Performed |
| :--- | :--- |
| `"open YouTube and play rrr song"` | Finds the top YouTube video and plays it immediately in your browser with audio. |
| `"open Notepad and write a new nucleus algorithm"` | Launches Notepad, synthesizes the algorithm using Groq, and pastes it in. |
| `"open WhatsApp and text Siddhartha hello"` | Opens WhatsApp, selects the contact, and drafts the message. |
| `"open calculator"` | Launches Windows Calculator directly. |
| `"what is 45 * 80?"` | Computes the answer instantly and speaks the result back aloud. |
| `"tell me a short joke"` | Conversational response generated and read via text-to-speech. |

---

## 🛠️ Management & Developer CLI

| Action | Windows PowerShell | Linux / macOS |
| :--- | :--- | :--- |
| **Setup Config** | `.\run.ps1 setup` | `make setup` |
| **Start Containers** | `.\run.ps1 start` | `make start` |
| **Launch Desktop Agent** | `.\run.ps1 desktop` | *Windows Only* |
| **View Live Logs** | `.\run.ps1 logs` | `make logs` |
| **Check Container Status** | `.\run.ps1 status` | `make status` |
| **Stop All Services** | `.\run.ps1 stop` | `make stop` |
| **Reset Data & Volumes** | `.\run.ps1 reset` | `make reset` |

---

## 🧪 Testing

Run automated integration and unit test suites:
```bash
pytest tests/ -v
```

---

## 📄 License
This project is licensed under the MIT License. Built with ❤️ for open-source AI and accessible computing.
