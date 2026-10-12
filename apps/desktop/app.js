const API_GATEWAY_URL = 'http://localhost:8000';
const SERVICES = {
  api: { name: 'API Gateway', url: 'http://localhost:8000/healthz', cardId: 'card-api' },
  orchestrator: { name: 'Orchestrator', url: 'http://localhost:8001/healthz', cardId: 'card-orchestrator' },
  memory: { name: 'Memory Service', url: 'http://localhost:8002/healthz', cardId: 'card-memory' },
  browser: { name: 'Browser Service', url: 'http://localhost:8003/healthz', cardId: 'card-browser' },
  voice: { name: 'Voice Service', url: 'http://localhost:8004/healthz', cardId: 'card-voice' },
  desktop: { name: 'Desktop Agent', url: 'http://localhost:8005/healthz', cardId: 'card-desktop' },
  qdrant: { name: 'Qdrant Vector DB', url: 'http://localhost:6333/', cardId: 'card-qdrant' }
};

let activeSessionId = null;
let isTTSEnabled = true;
let recognition = null;
let isListening = false;

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
  activeSessionId = 'session_' + Math.random().toString(36).substring(2, 11);
  document.getElementById('session-id-label').textContent = `Session ID: ${activeSessionId}`;
  
  // Start health status checks
  pollHealthStatus();
  setInterval(pollHealthStatus, 4000);

  // Bind Form Submit
  const chatForm = document.getElementById('chat-form');
  chatForm.addEventListener('submit', handleChatSubmit);

  // Bind Voice Toggle Button
  const ttsBtn = document.getElementById('tts-toggle-btn');
  if (ttsBtn) ttsBtn.addEventListener('click', toggleTTS);

  // Setup Speech Recognition (STT)
  setupSpeechRecognition();

  // Load voices for Speech Synthesis
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }
});

// Voice synthesis and Speech Recognition functions
function toggleTTS() {
  isTTSEnabled = !isTTSEnabled;
  const btn = document.getElementById('tts-toggle-btn');
  const icon = document.getElementById('tts-icon');
  const label = document.getElementById('tts-label');
  if (isTTSEnabled) {
    btn.className = 'voice-toggle-btn active';
    icon.textContent = '🔊';
    label.textContent = 'Voice: ON';
    speakText('Voice output enabled');
  } else {
    btn.className = 'voice-toggle-btn muted';
    icon.textContent = '🔇';
    label.textContent = 'Voice: OFF';
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  }
}

function cleanTextForSpeech(text) {
  if (!text) return '';
  let cleaned = text.replace(/\[Executed:.*?\]/g, '').replace(/\{.*?\}/g, '');
  cleaned = cleaned.replace(/http[s]?:\/\/\S+/g, 'link');
  return cleaned.trim();
}

function speakText(text) {
  const toSpeak = cleanTextForSpeech(text);
  if (!toSpeak) return;
  
  // 1. Trigger Native Windows SAPI Speech through physical speakers
  try {
    fetch('http://localhost:8005/api/v1/desktop/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: toSpeak }),
      mode: 'cors'
    }).catch(e => console.warn('Desktop SAPI speak error:', e));
  } catch (err) {
    console.warn('Native SAPI speak failed:', err);
  }

  // 2. Also trigger Browser Web Speech Synthesis
  if ('speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(toSpeak);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      
      const voices = window.speechSynthesis.getVoices();
      if (voices && voices.length > 0) {
        const preferredVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('David') || v.name.includes('Guy')));
        if (preferredVoice) utterance.voice = preferredVoice;
      }
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn('Browser SpeechSynthesis error:', e);
    }
  }
}

function setupSpeechRecognition() {
  const micBtn = document.getElementById('mic-btn');
  const inputEl = document.getElementById('user-input');
  if (!micBtn) return;
  
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.title = 'Speech recognition requires Chrome or Edge browser';
    micBtn.addEventListener('click', () => {
      alert('Speech-to-Text (STT) requires Chrome, Edge, or a browser with Web Speech API support.');
    });
    return;
  }
  
  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  
  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add('listening');
    inputEl.placeholder = '🎙️ Listening... Speak your command now';
  };
  
  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    inputEl.value = transcript;
  };
  
  recognition.onerror = (event) => {
    console.warn('Speech recognition error:', event.error);
    stopListening();
  };
  
  recognition.onend = () => {
    stopListening();
    if (inputEl.value.trim().length > 0) {
      document.getElementById('chat-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
  };
  
  function stopListening() {
    isListening = false;
    micBtn.classList.remove('listening');
    inputEl.placeholder = 'Type or click 🎙️ to speak commands...';
  }
  
  micBtn.addEventListener('click', () => {
    if (isListening) {
      recognition.stop();
    } else {
      inputEl.value = '';
      try {
        recognition.start();
      } catch (e) {
        console.warn('Recognition start error:', e);
      }
    }
  });
}

// Use template button prompts
function usePrompt(text) {
  const input = document.getElementById('user-input');
  input.value = text;
  input.focus();
}

// Poll each individual service's liveness check
async function pollHealthStatus() {
  let gatewayOnline = false;
  let serviceStatusMap = {};

  // 1. Fetch aggregate service health status from the API Gateway
  try {
    const resp = await fetch(`${API_GATEWAY_URL}/api/v1/services/health`, {
      method: 'GET',
      mode: 'cors',
      cache: 'no-store'
    });
    if (resp.status >= 200 && resp.status < 300) {
      gatewayOnline = true;
      const healthData = await resp.json();
      if (healthData && healthData.services) {
        serviceStatusMap = healthData.services;
      }
    }
  } catch (err) {
    console.warn('Failed to query gateway aggregate health:', err);
  }

  // Update Gateway Card
  const apiCard = document.getElementById('card-api');
  if (apiCard) {
    const apiBadge = apiCard.querySelector('.service-badge');
    if (gatewayOnline) {
      apiBadge.textContent = 'ONLINE';
      apiBadge.className = 'service-badge status-online-badge';
    } else {
      apiBadge.textContent = 'OFFLINE';
      apiBadge.className = 'service-badge status-offline-badge';
    }
  }

  // Update Qdrant Card (direct CORS-compatible query or fallback)
  const qdrantCard = document.getElementById('card-qdrant');
  if (qdrantCard) {
    const qdrantBadge = qdrantCard.querySelector('.service-badge');
    try {
      const resp = await fetch(SERVICES.qdrant.url, { method: 'GET', mode: 'cors', cache: 'no-store' });
      if (resp.status >= 200 && resp.status < 300) {
        qdrantBadge.textContent = 'ONLINE';
        qdrantBadge.className = 'service-badge status-online-badge';
      } else {
        qdrantBadge.textContent = 'OFFLINE';
        qdrantBadge.className = 'service-badge status-offline-badge';
      }
    } catch (err) {
      qdrantBadge.textContent = 'OFFLINE';
      qdrantBadge.className = 'service-badge status-offline-badge';
    }
  }

  // Update Monitored Python Services (Orchestrator, Memory, Browser, Voice)
  for (const [key, svc] of Object.entries(SERVICES)) {
    if (key === 'api' || key === 'qdrant') continue;
    const cardEl = document.getElementById(svc.cardId);
    if (!cardEl) continue;
    const badgeEl = cardEl.querySelector('.service-badge');

    if (gatewayOnline && serviceStatusMap[key]) {
      const state = serviceStatusMap[key].status;
      if (state === 'healthy') {
        badgeEl.textContent = 'ONLINE';
        badgeEl.className = 'service-badge status-online-badge';
      } else {
        badgeEl.textContent = 'OFFLINE';
        badgeEl.className = 'service-badge status-offline-badge';
      }
    } else {
      badgeEl.textContent = 'OFFLINE';
      badgeEl.className = 'service-badge status-offline-badge';
    }
  }

  // Update Postgres Card status (implicitly map it from memory service status)
  const postgresCard = document.getElementById('card-postgres');
  if (postgresCard) {
    const memoryBadge = document.getElementById('card-memory').querySelector('.service-badge');
    const pgBadge = postgresCard.querySelector('.service-badge');
    if (memoryBadge.classList.contains('status-online-badge')) {
      pgBadge.textContent = 'CONNECTED';
      pgBadge.className = 'service-badge status-online-badge';
    } else {
      pgBadge.textContent = 'OFFLINE';
      pgBadge.className = 'service-badge status-offline-badge';
    }
  }

  // Update Header gateway pulse
  const headerIndicator = document.getElementById('gateway-indicator');
  const headerStatusText = document.getElementById('gateway-status-text');
  
  if (gatewayOnline) {
    headerIndicator.className = 'pulse-indicator status-online';
    headerStatusText.textContent = 'GATEWAY ONLINE';
  } else {
    headerIndicator.className = 'pulse-indicator status-offline';
    headerStatusText.textContent = 'GATEWAY OFFLINE';
  }
}

// Handle Chat Message Dispatch
async function handleChatSubmit(e) {
  e.preventDefault();
  const inputEl = document.getElementById('user-input');
  const messageText = inputEl.value.trim();
  if (!messageText) return;

  // Render User Message
  appendMessage(messageText, 'user');
  inputEl.value = '';

  // Render Typing Indicator
  const typingIndicator = appendTypingIndicator();

  // Send request to API Gateway
  try {
    const response = await fetch(`${API_GATEWAY_URL}/api/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: messageText,
        session_id: activeSessionId,
        context: {}
      })
    });

    typingIndicator.remove();

    if (response.status === 200) {
      const data = await response.json();
      
      // Look for task routing trace
      const routingAction = data.actions_taken && data.actions_taken.find(
        a => a.service === 'orchestrator' && a.action === 'task_routing'
      );
      const task = routingAction ? routingAction.output : null;
      
      appendMessage(data.response, 'assistant', task);
      renderTraceLog(data.actions_taken);
      
      if (task && task.status === 'requires_confirmation') {
        showConfirmationModal(task);
      }
    } else {
      const errText = await response.text();
      appendMessage(`Error: Unable to connect to assistant core (HTTP ${response.status}). Details: ${errText}`, 'system');
    }
  } catch (err) {
    typingIndicator.remove();
    appendMessage(`Network Error: Could not connect to API Gateway on Port 8000. Is Docker running?`, 'system');
    console.error(err);
  }
}

// Append Chat Message HTML
function appendMessage(text, sender, task = null) {
  const container = document.getElementById('chat-messages');
  const msgEl = document.createElement('div');
  msgEl.className = `message ${sender}-message`;
  
  const contentEl = document.createElement('div');
  contentEl.className = 'message-content';
  
  // Set main response text
  const textEl = document.createElement('span');
  textEl.textContent = text;
  contentEl.appendChild(textEl);
  
  // Inject metadata layout if task routing exists
  if (task) {
    const statusClass = task.status === 'success' ? 'status-success' : (task.status === 'requires_confirmation' ? 'status-confirm' : 'status-failed');
    const statusLabel = task.status === 'requires_confirmation' ? 'CONFIRMATION REQUIRED' : task.status.toUpperCase();
    const riskClass = `risk-${task.permission_level}`;
    
    let taskCardHtml = `
      <div class="task-card" id="task-card-${task.id}">
        <div class="task-header">
          <span>${task.id}</span>
          <span class="badge-status ${statusClass}" id="badge-status-${task.id}">${statusLabel}</span>
        </div>
        <div class="task-detail-row">
          <span class="task-detail-label">Intent:</span>
          <span class="task-detail-val">${task.intent}</span>
        </div>
        <div class="task-detail-row">
          <span class="task-detail-label">Target Agent:</span>
          <span class="task-detail-val">${task.target_agent}</span>
        </div>
        <div class="task-detail-row">
          <span class="task-detail-label">Risk Level:</span>
          <span class="badge-risk ${riskClass}">${task.permission_level.toUpperCase()}</span>
        </div>
      </div>
    `;
    
    if (task.status === 'requires_confirmation') {
      taskCardHtml += `
        <div class="task-blocked-box" id="blocked-box-${task.id}">
          ⚠️ <strong>Action Blocked:</strong> High-risk tasks are gated. Manual confirmation is required.
          <div class="confirm-actions">
            <button class="in-card-btn allow-btn" onclick="triggerTaskConfirm('${task.id}')">Allow</button>
            <button class="in-card-btn block-btn" onclick="triggerTaskCancel('${task.id}')">Cancel</button>
          </div>
        </div>
      `;
    }
    
    const cardContainer = document.createElement('div');
    cardContainer.innerHTML = taskCardHtml;
    contentEl.appendChild(cardContainer);
  }
  
  if (sender === 'assistant') {
    const speakBtn = document.createElement('button');
    speakBtn.type = 'button';
    speakBtn.className = 'speak-msg-btn';
    speakBtn.innerHTML = '🔊 Speak';
    speakBtn.title = 'Speak this message aloud';
    speakBtn.onclick = () => speakText(text);
    contentEl.appendChild(speakBtn);
    
    if (isTTSEnabled) {
      speakText(text);
    }
  }
  
  msgEl.appendChild(contentEl);
  container.appendChild(msgEl);
  container.scrollTop = container.scrollHeight;
}

// Show Confirmation modal popup dialog
function showConfirmationModal(task) {
  const modal = document.getElementById('confirm-modal');
  if (!modal) return;
  
  document.getElementById('modal-task-id').textContent = `Task: ${task.id}`;
  document.getElementById('modal-task-command').textContent = task.user_input;
  document.getElementById('modal-task-agent').textContent = task.target_agent;
  
  const riskVal = document.getElementById('modal-task-risk');
  riskVal.textContent = task.permission_level.toUpperCase();
  riskVal.className = `modal-task-val badge-risk risk-${task.permission_level}`;
  
  // Bind buttons with new event listeners (cloning keeps them fresh)
  const confirmBtn = document.getElementById('modal-confirm-btn');
  const cancelBtn = document.getElementById('modal-cancel-btn');
  
  const newConfirmBtn = confirmBtn.cloneNode(true);
  const newCancelBtn = cancelBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
  cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
  
  newConfirmBtn.addEventListener('click', async () => {
    modal.classList.remove('active');
    await executeConfirm(task.id);
  });
  
  newCancelBtn.addEventListener('click', async () => {
    modal.classList.remove('active');
    await executeCancel(task.id);
  });
  
  modal.classList.add('active');
}

// Execute Task Confirmation request
async function executeConfirm(taskId) {
  const typingIndicator = appendTypingIndicator();
  
  try {
    const response = await fetch(`${API_GATEWAY_URL}/api/v1/tasks/${taskId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    typingIndicator.remove();
    
    if (response.status === 200) {
      const data = await response.json();
      
      updateTaskCardStatus(taskId, 'success', 'SUCCESS');
      appendMessage(data.response, 'assistant');
      renderTraceLog(data.actions_taken);
    } else {
      const errText = await response.text();
      appendMessage(`Error: Task confirmation failed (HTTP ${response.status}). Details: ${errText}`, 'system');
      updateTaskCardStatus(taskId, 'failed', 'FAILED');
    }
  } catch (err) {
    typingIndicator.remove();
    appendMessage(`Network Error: Failed to connect to API Gateway.`, 'system');
    updateTaskCardStatus(taskId, 'failed', 'FAILED');
    console.error(err);
  }
}

// Execute Task Cancellation request
async function executeCancel(taskId) {
  const typingIndicator = appendTypingIndicator();
  
  try {
    const response = await fetch(`${API_GATEWAY_URL}/api/v1/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    typingIndicator.remove();
    
    if (response.status === 200) {
      const data = await response.json();
      
      updateTaskCardStatus(taskId, 'failed', 'FAILED');
      appendMessage(data.response, 'assistant');
      renderTraceLog(data.actions_taken);
    } else {
      const errText = await response.text();
      appendMessage(`Error: Task cancellation failed (HTTP ${response.status}). Details: ${errText}`, 'system');
    }
  } catch (err) {
    typingIndicator.remove();
    appendMessage(`Network Error: Failed to connect to API Gateway.`, 'system');
    console.error(err);
  }
}

// Update task card status badge and blocked-box HTML in chat stream
function updateTaskCardStatus(taskId, statusClass, statusLabel) {
  const badgeEl = document.getElementById(`badge-status-${taskId}`);
  if (badgeEl) {
    badgeEl.textContent = statusLabel;
    badgeEl.className = `badge-status status-${statusClass}`;
  }
   
  
  const blockedBox = document.getElementById(`blocked-box-${taskId}`);
  if (blockedBox) {
    if (statusClass === 'success') {
      blockedBox.style.display = 'none';
    } else if (statusClass === 'failed') {
      blockedBox.innerHTML = `❌ <strong>Action Blocked & Cancelled:</strong> Gated by user choice.`;
      blockedBox.style.borderLeftColor = 'var(--color-offline)';
    }
  }
}

// Expose click triggers globally for HTML onclick inline call strings
window.triggerTaskConfirm = (taskId) => {
  executeConfirm(taskId);
};

window.triggerTaskCancel = (taskId) => {
  executeCancel(taskId);
};

// Append Typing Indicator HTML
function appendTypingIndicator() {
  const container = document.getElementById('chat-messages');
  const msgEl = document.createElement('div');
  msgEl.className = 'message assistant-message typing-msg';
  
  const contentEl = document.createElement('div');
  contentEl.className = 'message-content';
  contentEl.innerHTML = `
    <div class="typing-indicator">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;
  
  msgEl.appendChild(contentEl);
  container.appendChild(msgEl);
  container.scrollTop = container.scrollHeight;
  return msgEl;
}

// Render Trace logs in right panel
function renderTraceLog(actions) {
  const logContainer = document.getElementById('trace-log');
  logContainer.innerHTML = ''; // Clear placeholder or old logs

  if (!actions || actions.length === 0) {
    logContainer.innerHTML = `
      <div class="trace-placeholder">
        No background RPC requests triggered for this query.
      </div>
    `;
    return;
  }

  actions.forEach(action => {
    const traceEl = document.createElement('div');
    traceEl.className = 'trace-item';

    const headerEl = document.createElement('div');
    headerEl.className = 'trace-title';
    headerEl.innerHTML = `
      <span>rpc::${action.service}::${action.action}</span>
      <span class="trace-status ${action.status}">${action.status.toUpperCase()}</span>
    `;

    const bodyEl = document.createElement('div');
    bodyEl.className = 'trace-body';
    bodyEl.textContent = JSON.stringify(action.output || action.error, null, 2);

    traceEl.appendChild(headerEl);
    traceEl.appendChild(bodyEl);
    logContainer.appendChild(traceEl);
  });
}
