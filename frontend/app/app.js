(() => {
  'use strict';

  const content = document.getElementById('content');
  const apiBase = `http://${window.location.hostname || '127.0.0.1'}:8000`;
  const state = {
    profileId: localStorage.getItem('voltaik-profile') || 'default',
    conversationId: localStorage.getItem('voltaik-conversation') || null,
    // Attachments are objects, not bare names: the UI shows the size and lets a
    // file be removed before the message is sent.
    attachments: [],
    polling: null,
    // Whether the last backend call succeeded. Drives the sidebar status and
    // lets the UI recover automatically when the backend comes back.
    connected: true,
    // Timing constants fetched from the backend so no estimate is hard-coded in
    // the UI.
    defaultEstimate: null,
    queueMaxRuntime: null,
  };

  // The pipeline stages shown in the progress card, in order. The backend
  // reports a stage name; this maps it to a position in the step strip.
  const PIPELINE_STEPS = [
    ['triage', 'Routing'],
    ['rewrite', 'Brief'],
    ['plan', 'Planning'],
    ['specialist', 'Producing'],
    ['backtest', 'Backtest'],
    ['compliance', 'Compliance'],
    ['verify', 'Verifying'],
    ['combine', 'Combining'],
    ['finalize', 'Finalizing'],
    ['artifact', 'Packaging'],
  ];

  // ---------------------------------------------------------------- helpers

  const escapeHtml = value => String(value || '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
  let toastTimer = null;
  const toast = (message, variant = 'info') => {
    const element = document.getElementById('toast');
    if (!element) return;
    element.textContent = message;
    element.classList.toggle('error', variant === 'error');
    element.classList.add('show');
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => element.classList.remove('show'), 3600);
  };
  const formatSize = size => {
    if (!Number.isFinite(size)) return '';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  };
  const formatDuration = seconds => {
    const total = Math.max(0, Math.round(seconds));
    if (total < 60) return `${total}s`;
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    if (minutes < 60) return rest ? `${minutes}m ${rest}s` : `${minutes}m`;
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  };
  const formatTime = value => {
    if (!value) return '';
    const date = new Date(String(value).replace(' ', 'T'));
    if (isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  };
  const initials = name => (name || '?').trim().slice(0, 2).toUpperCase();
  const api = async (path, options = {}) => {
    const response = await fetch(`${apiBase}${path}`, options);
    let data = {};
    try { data = await response.json(); } catch (error) { data = {}; }
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  };
  const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const put = (path, body) => api(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const del = path => api(path, { method: 'DELETE' });

  // Uploads use XMLHttpRequest rather than fetch because only XHR exposes
  // upload progress events, which the attachment chips display.
  const uploadFile = (file, onProgress) => new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `${apiBase}/knowledge/upload`);
    request.upload.addEventListener('progress', event => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener('load', () => {
      let data = {};
      try { data = JSON.parse(request.responseText || '{}'); } catch (error) { data = {}; }
      if (request.status >= 200 && request.status < 300) resolve(data);
      else reject(new Error(data.detail || `Upload failed (${request.status})`));
    });
    request.addEventListener('error', () => reject(new Error('The upload could not reach the backend.')));
    request.addEventListener('abort', () => reject(new Error('The upload was cancelled.')));
    const body = new FormData();
    body.append('file', file);
    request.send(body);
  });

  const setActive = route => {
    document.querySelectorAll('.nav a').forEach(link => link.classList.toggle('active', link.getAttribute('href') === `#${route}`));
    const crumb = document.getElementById('crumb');
    if (crumb) crumb.textContent = route === 'chat' ? 'Chat' : route.replace('-', ' ').replace(/\b\w/g, char => char.toUpperCase());
  };

  // ---------------------------------------------------------- page lifecycle
  //
  // Every rendered page owns timers (queue auto-refresh) and polling loops
  // (chat job progress). Navigating away replaces `#content`, so a surviving
  // timer would write into detached nodes and throw. Each page registers its
  // timers here, and `route` clears them before rendering the next page.
  const pageTimers = new Set();
  // Page-scoped teardown callbacks (a live feed subscription, say). Timers are
  // cleared by id; anything else a page opens registers a function here so it is
  // released when the page is replaced.
  const pageCleanups = new Set();
  let pageToken = 0;

  const trackTimer = id => {
    pageTimers.add(id);
    return id;
  };

  const trackCleanup = fn => {
    pageCleanups.add(fn);
    return fn;
  };

  const clearPageWork = () => {
    pageTimers.forEach(id => {
      window.clearTimeout(id);
      window.clearInterval(id);
    });
    pageTimers.clear();
    pageCleanups.forEach(fn => {
      try { fn(); } catch (error) { /* a failed teardown must not block navigation */ }
    });
    pageCleanups.clear();
    pageToken += 1;
  };

  // A polling loop checks this to know whether its page is still on screen.
  const isCurrentPage = token => token === pageToken;

  // The file input lives in the page shell rather than inside a route's markup,
  // so every visit to Chat or Knowledge would otherwise add another `change`
  // listener to the same node, uploading each chosen file once per past visit.
  // Replacing the node with a clone drops the old listeners before attaching.
  const bindFilePicker = handler => {
    const previous = document.getElementById('fileInput');
    const fresh = previous.cloneNode(true);
    fresh.value = '';
    previous.replaceWith(fresh);
    fresh.addEventListener('change', event => handler(event, fresh));
    return fresh;
  };

  const renderPage = (title, eyebrow, description, actions, bodyHtml) => `
    <div class="page-view">
      <div class="page-header">
        <div><div class="eyebrow">${escapeHtml(eyebrow)}</div><h1>${escapeHtml(title)}</h1><p>${escapeHtml(description)}</p></div>
        <div class="page-actions">${actions}</div>
      </div>
      ${bodyHtml}
    </div>`;

  // ------------------------------------------------------------- progress UI

  // The backend reports the time remaining from the job's own measured pace.
  // Until it is far enough along to project, it reports the default estimate
  // instead, so the label always shows something meaningful.
  const etaText = progress => {
    const info = progress || {};
    if (Number(info.percent) >= 99.5) return 'Finishing up...';
    const raw = info.eta_seconds !== null && info.eta_seconds !== undefined
      ? Number(info.eta_seconds)
      : Number(info.estimate_seconds);
    if (!Number.isFinite(raw)) return 'estimating...';
    return `~${formatDuration(raw)} remaining`;
  };

  const progressStepsHtml = stage => {
    const index = PIPELINE_STEPS.findIndex(([key]) => key === stage);
    return `<div class="progress-steps">${PIPELINE_STEPS.map(([key, label], position) => {
      const cls = position < index ? 'done' : position === index ? 'current' : '';
      return `<span class="${cls}">${escapeHtml(label)}</span>`;
    }).join('')}</div>`;
  };

  // The live activity feed: the running commentary of what the pipeline is
  // actually doing (which agent is working, what it produced, what a check
  // found). The newest entry is last, and the newest entry may carry a `preview`
  // of the text being generated right now, which is what makes the generation
  // itself visible while it happens. Only the tail is shown so the card stays a
  // readable size on a long job.
  const ACTIVITY_VISIBLE = 8;
  const activityFeedHtml = activity => {
    const entries = Array.isArray(activity) ? activity.slice(-ACTIVITY_VISIBLE) : [];
    if (!entries.length) return '';
    const lines = entries.map(entry => {
      const kind = entry.kind === 'ok' ? 'ok' : entry.kind === 'error' ? 'error' : '';
      const agent = entry.agent ? `<span class="activity-agent">${escapeHtml(entry.agent)}</span>` : '';
      const preview = entry.preview
        ? `<pre class="activity-preview">${escapeHtml(entry.preview)}</pre>`
        : '';
      return `<div class="activity-line ${kind}">${agent}<span class="activity-text">${escapeHtml(entry.message || '')}</span>${preview}</div>`;
    }).join('');
    return `<div class="activity-feed" data-activity>${lines}</div>`;
  };

  // Build the live progress card shown while a job runs. `percent` is the
  // backend's estimate; `eta` is derived from the job's own measured pace, so it
  // reflects how long the work is actually taking rather than a guess made
  // before it started. `cancellable` adds a button that asks the backend to stop
  // the job at its next checkpoint.
  const progressCardHtml = ({ label, detail, percent, eta, stage, cancellable, activity }) => `
    <div class="progress-card">
      <div class="avatar">AI</div>
      <div class="progress-body">
        <div class="progress-top">
          <span class="progress-label">${escapeHtml(label || 'Working on your request')}</span>
          <span class="progress-actions">
            <span class="progress-percent">${Math.round(percent)}%</span>
            ${cancellable ? '<button class="cancel-job" data-cancel-job title="Stop this request">Cancel</button>' : ''}
          </span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:${Math.max(2, Math.min(100, percent))}%"></div></div>
        <div class="progress-meta">
          <span>${escapeHtml(detail || 'The manager is coordinating your team.')}</span>
          <span class="eta" data-eta>${escapeHtml(eta || '')}</span>
        </div>
        ${progressStepsHtml(stage)}
        ${activityFeedHtml(activity)}
      </div>
    </div>`;

  // ------------------------------------------------------------- profile state

  async function loadProfiles() {
    try {
      const profiles = await api('/profiles');
      if (!profiles.length) {
        const created = await post('/profiles', { name: 'My business', business_type: 'Service business', description: 'Describe what your business does.' });
        profiles.push(created);
      }
      if (!profiles.some(p => p.id === state.profileId)) {
        state.profileId = profiles[0].id;
        localStorage.setItem('voltaik-profile', state.profileId);
      }
      const current = profiles.find(p => p.id === state.profileId) || profiles[0];
      document.getElementById('profileName').textContent = current.name;
      document.getElementById('profileType').textContent = current.business_type || 'Business profile';
      state.connected = true;
      return profiles;
    } catch (error) {
      markDisconnected();
      return [];
    }
  }

  // The backend can be down when the page loads (or restart while it is open).
  // Without this, the sidebar would stay stuck on "Offline" forever even after
  // the backend came back, which made uploads look broken when they were not.
  function markDisconnected() {
    state.connected = false;
    const name = document.getElementById('profileName');
    const type = document.getElementById('profileType');
    if (name) name.textContent = 'Offline';
    if (type) type.textContent = 'Backend unreachable';
  }

  // Re-check the connection and, when it recovers, restore the real profile and
  // refresh whatever page is showing. Called on a timer so recovery is automatic.
  async function recheckConnection() {
    try {
      await api('/health');
    } catch (error) {
      markDisconnected();
      return;
    }
    if (!state.connected) {
      state.connected = true;
      await loadProfiles();
      route();
      toast('Reconnected to the backend');
    }
  }

  function switchProfile(profileId) {
    state.profileId = profileId;
    state.conversationId = null;
    localStorage.setItem('voltaik-profile', profileId);
    localStorage.removeItem('voltaik-conversation');
    loadProfiles();
    navigate('chat');
    toast('Switched business profile');
  }

  // ------------------------------------------------------------------- chat

  function renderChat() {
    const conversationId = state.conversationId;
    content.innerHTML = renderPage(
      'Chat with your AI team',
      'AI operations',
      'The manager routes your request to the right department, specialists do the work, and the verified result comes back here.',
      `<button class="secondary-action" id="newChatButton">+ New chat</button>`,
      `<div class="chat-shell">
        <section class="panel chat-panel" id="chatPanel">
          <div class="chat-head"><h2 id="chatTitle">${conversationId ? 'Conversation' : 'New conversation'}</h2><span class="eyebrow" id="chatStatus">Ready</span></div>
          <div class="chat-messages" id="chatMessages"><div class="empty-state">Loading conversation...</div></div>
          <div class="attach-chips" id="attachChips" hidden></div>
          <div class="chat-tools">
            <button class="tool" id="attachTool"><svg viewBox="0 0 24 24"><path d="m21.4 11.6-8.8 8.8a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.8-8.8"/></svg> Attach files</button>
            <button class="tool" id="clearChatButton">Clear view</button>
            <span class="eyebrow" style="margin-left:auto;align-self:center">Drop files anywhere on this panel</span>
          </div>
          <div class="chat-composer">
            <textarea id="chatInput" placeholder="Ask your AI team to create, analyze, or plan... (Enter to send, Shift+Enter for newline)"></textarea>
            <button class="send" id="sendButton" title="Send"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>
          </div>
        </section>
        <aside class="side-stack">
          <div class="panel side-panel">
            <div class="panel-title"><h3>Conversations</h3><button class="text-link" id="historyLink">View all</button></div>
            <div class="history-list" id="chatHistoryList"><div class="empty-state">Loading...</div></div>
          </div>
          <div class="panel side-panel">
            <div class="panel-title"><h3>Attachments</h3><span class="eyebrow" id="attachCount">0 files</span></div>
            <div class="history-list" id="attachList"><div class="empty-state">No files attached.</div></div>
          </div>
        </aside>
      </div>`
    );
    setActive('chat');
    bindChat(conversationId);
  }

  function renderMessage(message) {
    const meta = message.meta || {};
    const isError = meta.status === 'error' || (message.role === 'assistant' && meta.error);
    const chips = [];
    if (meta.status === 'ok') chips.push(`<span class="chip ok">✓ delivered</span>`);
    if (meta.status === 'error') chips.push(`<span class="chip err">✗ failed</span>`);
    if (meta.status === 'cancelled') chips.push(`<span class="chip">⊘ cancelled</span>`);
    if (meta.departments && meta.departments.length) chips.push(`<span class="chip">${escapeHtml(meta.departments.join(', '))}</span>`);
    if (meta.knowledge_used) chips.push(`<span class="chip">${meta.knowledge_used} sources</span>`);
    const artifacts = (meta.artifacts || []).map(file => `<a class="artifact-link" href="${apiBase}${escapeHtml(file.download_url)}" download>⬇ ${escapeHtml(file.filename)}</a>`).join('');
    // The error block repeats the headline only when it adds information. The
    // manager's error title is often already the message text, and showing the
    // same sentence twice reads like a bug.
    const errorTitle = meta.error ? (meta.error.message || meta.error.title || '') : '';
    const errorText = errorTitle && errorTitle !== message.content
      ? `<div class="text error">${escapeHtml(errorTitle)}</div>`
      : '';
    const errorHint = meta.error && meta.error.hint ? `<div class="text error">${escapeHtml(meta.error.hint)}</div>` : '';
    return `<div class="msg ${message.role}">
      <div class="avatar">${message.role === 'user' ? 'You' : 'AI'}</div>
      <div class="bubble">
        <span class="who">${message.role === 'user' ? 'You' : 'Manager · AI team'}</span>
        <div class="text ${isError ? 'error' : ''}">${escapeHtml(message.content)}</div>
        ${errorText}
        ${errorHint}
        ${artifacts}
        ${chips.length ? `<div class="meta-row">${chips.join('')}</div>` : ''}
      </div>
    </div>`;
  }

  function bindChat(conversationId) {
    const messagesEl = document.getElementById('chatMessages');
    const input = document.getElementById('chatInput');
    const sendButton = document.getElementById('sendButton');
    const attachTool = document.getElementById('attachTool');
    const fileInput = bindFilePicker(async (event, picker) => {
      await uploadFiles(event.target.files);
      picker.value = '';
    });
    const attachList = document.getElementById('attachList');
    const attachCount = document.getElementById('attachCount');
    const attachChips = document.getElementById('attachChips');
    const chatPanel = document.getElementById('chatPanel');
    const chatStatus = document.getElementById('chatStatus');
    let pendingJob = null;
    let progressEl = null;

    const scrollBottom = () => { messagesEl.scrollTop = messagesEl.scrollHeight; };

    const renderAttachments = () => {
      const files = state.attachments;
      attachCount.textContent = `${files.length} file${files.length === 1 ? '' : 's'}`;
      attachList.innerHTML = files.length
        ? files.map(file => `
          <div class="attach-row">
            <div class="a-body"><strong title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</strong><small>${escapeHtml(file.extension || 'file')} · ${formatSize(file.size)}</small></div>
            <button class="remove" data-remove-attachment="${escapeHtml(file.name)}" title="Remove">×</button>
          </div>`).join('')
        : '<div class="empty-state">No files attached.</div>';
      attachChips.hidden = files.length === 0;
      attachChips.innerHTML = files.map(file => `
        <span class="attach-chip">
          <span class="name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
          <span class="size">${formatSize(file.size)}</span>
          <button class="remove" data-remove-attachment="${escapeHtml(file.name)}" title="Remove">×</button>
        </span>`).join('');
      document.querySelectorAll('[data-remove-attachment]').forEach(button => button.addEventListener('click', () => {
        state.attachments = state.attachments.filter(file => file.name !== button.dataset.removeAttachment);
        renderAttachments();
      }));
    };

    // Upload one file, showing a chip with real byte-level progress while it
    // transfers and a clear failure state if it does not.
    const uploadOne = async file => {
      const chip = document.createElement('span');
      chip.className = 'attach-chip uploading';
      chip.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="bar"><i></i></span>`;
      attachChips.hidden = false;
      attachChips.appendChild(chip);
      const fill = chip.querySelector('.bar i');
      try {
        const data = await uploadFile(file, percent => { fill.style.width = `${percent}%`; });
        chip.remove();
        state.attachments.push({
          name: data.filename,
          size: data.size,
          extension: data.extension,
          readable: data.readable !== false,
        });
        renderAttachments();
        if (data.readable === false) toast(`${data.filename} attached, but this file type cannot be read by the AI team.`, 'error');
        else toast(`${data.filename} attached`);
      } catch (error) {
        chip.classList.remove('uploading');
        chip.classList.add('failed');
        chip.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="size">failed</span>`;
        toast(`Could not upload ${file.name}: ${error.message}`, 'error');
      }
    };

    const uploadFiles = async fileList => {
      const files = Array.from(fileList || []);
      if (!files.length) return;
      for (const file of files) await uploadOne(file);
    };

    const loadMessages = async () => {
      if (!conversationId) {
        messagesEl.innerHTML = '<div class="empty-state">Start a new conversation below. Your AI team is ready.</div>';
        return;
      }
      try {
        const data = await api(`/conversations/${conversationId}`);
        const title = data.messages && data.messages.length ? data.messages[0].content.slice(0, 60) : 'Conversation';
        document.getElementById('chatTitle').textContent = title;
        messagesEl.innerHTML = data.messages.length
          ? data.messages.map(renderMessage).join('')
          : '<div class="empty-state">No messages yet. Ask your team something.</div>';
        scrollBottom();
        // A reload during a running job would otherwise lose the result: the
        // job keeps running in the backend, so resume watching it here.
        await resumeActiveJob();
      } catch (error) {
        messagesEl.innerHTML = `<div class="empty-state">Could not load this conversation: ${escapeHtml(error.message)}</div>`;
      }
    };

    const resumeActiveJob = async () => {
      try {
        const jobs = await api('/queue');
        const active = jobs.find(job => (job.status === 'queued' || job.status === 'running')
          && job.payload && job.payload.conversation_id === conversationId);
        if (active && !pendingJob) {
          pendingJob = active.id;
          sendButton.disabled = true;
          await pollJob(active.id);
          sendButton.disabled = false;
        }
      } catch (error) {
        // The queue may be briefly unreachable; the badge poll will retry.
      }
    };

    // Ask the backend to stop a running job. The job stops at its next
    // checkpoint, so the poll loop keeps running until the status changes.
    const cancelJob = async jobId => {
      try {
        await post(`/queue/${jobId}/cancel`, {});
        toast('Cancelling the request...');
      } catch (error) {
        toast(`Could not cancel the request: ${error.message}`, 'error');
      }
    };

    const pollJob = async jobId => {
      // The backend watchdog fails a job after `MAX_JOB_RUNTIME_SECONDS`, so
      // wait a little longer than that. This way the backend reports the real
      // outcome instead of the UI giving up on a job that is still healthy.
      const maxRuntimeMs = ((state.queueMaxRuntime || 600) + 120) * 1000;
      const MAX_POLL_MS = Math.max(5 * 60 * 1000, maxRuntimeMs);
      const POLL_INTERVAL_MS = 1200;
      const startedAt = Date.now();
      const token = pageToken;
      let consecutiveErrors = 0;
      let lastPercent = 0;

      const removeProgress = () => {
        if (progressEl) { progressEl.remove(); progressEl = null; }
        chatStatus.textContent = 'Ready';
      };

      const showProgress = job => {
        const info = job.progress || {};
        // The backend projects the finish time from the job's own measured pace,
        // so the numbers below come straight from it. The elapsed-time ratio is
        // only a floor for the bar, so a stalled report cannot make it jump back.
        const elapsed = (Date.now() - startedAt) / 1000;
        const estimate = Number(info.estimate_seconds) || Number(state.defaultEstimate) || 270;
        const percent = Math.max(lastPercent, Number(info.percent) || 0, Math.min(95, (elapsed / estimate) * 100));
        lastPercent = percent;
        const html = progressCardHtml({
          label: info.label || 'The manager is working with your team',
          detail: info.detail || '',
          percent,
          eta: etaText({ ...info, percent }),
          stage: info.stage || 'triage',
          cancellable: true,
          activity: info.activity,
        });
        if (!progressEl) {
          // A stable wrapper keeps the card in place while its contents are
          // replaced on every update, so the message list does not jump around.
          progressEl = document.createElement('div');
          progressEl.className = 'progress-slot';
          messagesEl.appendChild(progressEl);
        }
        progressEl.innerHTML = html;
        // The card is rebuilt on every update, so the button is re-bound here.
        const cancelButton = progressEl.querySelector('[data-cancel-job]');
        if (cancelButton) cancelButton.addEventListener('click', () => cancelJob(jobId));
        // Keep the newest activity line in view as the feed grows.
        const feed = progressEl.querySelector('[data-activity]');
        if (feed) feed.scrollTop = feed.scrollHeight;
        chatStatus.textContent = `${Math.round(percent)}%`;
        scrollBottom();
      };

      // Render the outcome of a finished job. Shared by the stream and the poll
      // fallback so both paths produce identical output.
      const finishJob = job => {
        removeProgress();
        if (job.status === 'done') {
          const result = job.result || {};
          const isError = result.status === 'error';
          // On failure show the human-readable title, keeping the technical
          // detail in the error block instead of as the main message.
          const output = isError
            ? (result.message || 'The request failed.')
            : (result.output || result.message || '');
          const meta = {
            status: result.status,
            departments: result.departments,
            artifacts: result.artifacts,
            error: result.error,
            knowledge_used: result.knowledge_used,
          };
          messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg assistant', innerHTML: renderMessage({ role: 'assistant', content: output, meta }) }));
          scrollBottom();
          refreshQueueBadge();
        } else if (job.status === 'failed') {
          messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg assistant', innerHTML: renderMessage({ role: 'assistant', content: 'The request failed.', meta: { status: 'error', error: { message: job.error || 'Unknown error' } } }) }));
          scrollBottom();
        } else if (job.status === 'cancelled') {
          // Cancelling is a deliberate user action, so it is reported plainly
          // rather than as an error the user has to interpret.
          messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg assistant', innerHTML: renderMessage({ role: 'assistant', content: 'Request cancelled. Nothing was delivered.', meta: { status: 'cancelled' } }) }));
          scrollBottom();
          refreshQueueBadge();
        }
      };

      const isTerminal = job => job.status === 'done' || job.status === 'failed' || job.status === 'cancelled';

      // The poll fallback: used when the browser has no `EventSource`, or when
      // the stream cannot be established. It is the original behaviour, so a
      // missing push channel degrades to a working (if less live) UI.
      const pollLoop = async () => {
        const poll = async () => {
          try {
            const job = await api(`/queue/${jobId}`);
            if (!job || typeof job.status !== 'string') {
              // An unexpected response shape is treated as a transient failure
              // rather than a finished job, so the loop does not silently stop.
              throw new Error('Unexpected job status response.');
            }
            consecutiveErrors = 0;
            if (!isTerminal(job)) {
              showProgress(job);
              return true;
            }
            finishJob(job);
            return false;
          } catch (error) {
            consecutiveErrors += 1;
            // Tolerate a few transient polling failures (backend restart, brief
            // network drop) before giving up, so a blip does not look like a hang.
            if (consecutiveErrors < 5) return true;
            removeProgress();
            messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg assistant', innerHTML: renderMessage({ role: 'assistant', content: 'Lost contact with the backend while waiting for a result.', meta: { status: 'error', error: { message: error.message || 'The backend is unreachable.' } } }) }));
            scrollBottom();
            return false;
          }
        };

        while (await poll()) {
          // Leaving the chat page detaches these nodes. The job keeps running in
          // the backend and is picked up again by `resumeActiveJob` on return.
          if (!isCurrentPage(token) || !document.body.contains(messagesEl)) {
            removeProgress();
            break;
          }
          if (Date.now() - startedAt > MAX_POLL_MS) {
            removeProgress();
            messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg assistant', innerHTML: renderMessage({ role: 'assistant', content: 'This request is taking longer than expected.', meta: { status: 'error', error: { message: 'The job is still running. Check the Queue page for its status.' } } }) }));
            scrollBottom();
            break;
          }
          await new Promise(resolve => window.setTimeout(resolve, POLL_INTERVAL_MS));
        }
      };

      // The live path: the backend pushes each progress write as it happens, so
      // the activity feed and the streamed preview update without polling.
      const streamLoop = () => new Promise(resolve => {
        let settled = false;
        let source;
        let guard;
        // `settle` resolves once with the given outcome; `done` is the plain
        // "finished, no fallback needed" case.
        const settle = outcome => {
          if (settled) return;
          settled = true;
          if (guard) window.clearInterval(guard);
          if (source) source.close();
          resolve(outcome);
        };
        const done = () => settle(undefined);
        try {
          source = new EventSource(`${apiBase}/queue/${jobId}/events`);
        } catch (error) {
          // No `EventSource` support: fall back rather than leaving the user
          // staring at a frozen card.
          settle('fallback');
          return;
        }
        source.onmessage = event => {
          let job;
          try { job = JSON.parse(event.data); } catch (error) { return; }
          if (!job || typeof job.status !== 'string') return;
          if (!isTerminal(job)) {
            showProgress(job);
            return;
          }
          finishJob(job);
          done();
        };
        source.onerror = () => {
          // `EventSource` reconnects on its own, but a stream that never opened
          // (or a job the server no longer knows) would retry forever. Hand the
          // job back to the poll loop, which reports the real outcome.
          if (source.readyState === EventSource.CLOSED) settle('fallback');
        };
        // Leaving the page detaches the nodes the stream writes into, so stop
        // listening; the job keeps running and `resumeActiveJob` picks it up.
        guard = window.setInterval(() => {
          if (!isCurrentPage(token) || !document.body.contains(messagesEl)) {
            removeProgress();
            done();
          }
        }, 1000);
        // Bound the stream the same way the poll loop is bounded, so a job that
        // never reports a terminal state cannot leave the card up forever.
        window.setTimeout(() => settle('fallback'), MAX_POLL_MS);
      });

      const outcome = await streamLoop();
      if (outcome === 'fallback') await pollLoop();
    };
    const send = async () => {
      const text = input.value.trim();
      if (!text || sendButton.disabled) return;
      sendButton.disabled = true;
      input.value = '';
      messagesEl.appendChild(Object.assign(document.createElement('div'), { className: 'msg user', innerHTML: renderMessage({ role: 'user', content: text }) }));
      scrollBottom();
      try {
        let targetId = conversationId;
        if (!targetId) {
          const created = await post('/conversations', { profile_id: state.profileId, title: text.slice(0, 60) });
          targetId = created.id;
          state.conversationId = targetId;
          localStorage.setItem('voltaik-conversation', targetId);
          document.getElementById('chatTitle').textContent = text.slice(0, 60);
          loadChatHistory();
        }
        const sent = await post(`/conversations/${targetId}/messages`, {
          content: text,
          profile_id: state.profileId,
          attachment_ids: state.attachments.map(file => file.name),
        });
        state.attachments = [];
        renderAttachments();
        pendingJob = sent.job.id;
        await pollJob(pendingJob);
      } catch (error) {
        messagesEl.insertAdjacentHTML('beforeend', renderMessage({ role: 'assistant', content: 'Could not send the message.', meta: { status: 'error', error: { message: error.message } } }));
        scrollBottom();
      } finally {
        sendButton.disabled = false;
        input.focus();
      }
    };

    sendButton.addEventListener('click', send);
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    });
    document.getElementById('newChatButton').addEventListener('click', () => {
      state.conversationId = null;
      localStorage.removeItem('voltaik-conversation');
      renderChat();
    });
    document.getElementById('clearChatButton').addEventListener('click', () => {
      messagesEl.innerHTML = '<div class="empty-state">View cleared. Your conversation is still saved in History.</div>';
    });
    document.getElementById('historyLink').addEventListener('click', () => navigate('history'));
    attachTool.addEventListener('click', () => fileInput.click());

    // Drag and drop onto the chat panel. `dragenter`/`dragleave` fire for child
    // elements too, so a counter tracks whether the pointer is still inside.
    let dragDepth = 0;
    const showDropHint = () => {
      if (chatPanel.querySelector('.drop-hint')) return;
      chatPanel.classList.add('dragging');
      chatPanel.insertAdjacentHTML('beforeend', '<div class="drop-hint"><span>Drop files to attach them</span></div>');
    };
    const hideDropHint = () => {
      chatPanel.classList.remove('dragging');
      const hint = chatPanel.querySelector('.drop-hint');
      if (hint) hint.remove();
    };
    chatPanel.addEventListener('dragenter', event => {
      if (!event.dataTransfer || !Array.from(event.dataTransfer.types || []).includes('Files')) return;
      event.preventDefault();
      dragDepth += 1;
      showDropHint();
    });
    chatPanel.addEventListener('dragover', event => {
      if (!event.dataTransfer || !Array.from(event.dataTransfer.types || []).includes('Files')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
    });
    chatPanel.addEventListener('dragleave', () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) hideDropHint();
    });
    chatPanel.addEventListener('drop', async event => {
      event.preventDefault();
      dragDepth = 0;
      hideDropHint();
      await uploadFiles(event.dataTransfer && event.dataTransfer.files);
    });
    renderAttachments();
    loadMessages();
  }

  async function loadChatHistory() {
    const listEl = document.getElementById('chatHistoryList');
    if (!listEl) return;
    try {
      const conversations = await api(`/conversations?profile_id=${encodeURIComponent(state.profileId)}`);
      listEl.innerHTML = conversations.length
        ? conversations.slice(0, 12).map(conversation => `
          <div class="history-item ${conversation.id === state.conversationId ? 'current' : ''}" data-open-chat="${conversation.id}">
            <strong>${escapeHtml(conversation.title)}</strong><small>${formatTime(conversation.updated_at)}</small>
          </div>`).join('')
        : '<div class="empty-state">No conversations yet.</div>';
      document.querySelectorAll('[data-open-chat]').forEach(item => item.addEventListener('click', () => {
        state.conversationId = item.dataset.openChat;
        localStorage.setItem('voltaik-conversation', state.conversationId);
        renderChat();
      }));
    } catch (error) {
      listEl.innerHTML = '<div class="empty-state">Could not load conversations.</div>';
    }
  }

  // ------------------------------------------------------------------ queue

  // The most recent snapshot of every job, kept current by the live feed. The
  // sidebar badge and the queue page both read from it, so a job that starts,
  // progresses, or finishes is reflected without a page refresh.
  const queueJobs = new Map();

  // Open the queue-wide Server-Sent Events feed. The backend pushes a snapshot
  // for every job as it changes, so callers never poll. Returns a close
  // function; `onError` fires when the stream cannot be established or has
  // closed for good, which lets the caller fall back to polling.
  const openQueueFeed = (onJob, onError) => {
    let source;
    try {
      source = new EventSource(`${apiBase}/queue/events`);
    } catch (error) {
      // No `EventSource` support: let the caller keep its poll fallback.
      if (onError) onError();
      return () => {};
    }
    source.onmessage = event => {
      let job;
      try { job = JSON.parse(event.data); } catch (error) { return; }
      if (job && job.id) onJob(job);
    };
    source.onerror = () => {
      // `EventSource` reconnects on its own, but a stream that has closed for
      // good would retry forever, so hand control back to the poll fallback.
      if (source.readyState === EventSource.CLOSED && onError) onError();
    };
    return () => source.close();
  };

  const updateQueueBadge = () => {
    const active = [...queueJobs.values()].filter(job => job.status === 'queued' || job.status === 'running').length;
    const badge = document.getElementById('queueBadge');
    if (badge) {
      badge.hidden = active === 0;
      badge.textContent = String(active);
    }
  };

  async function refreshQueueBadge() {
    try {
      const jobs = await api('/queue');
      jobs.forEach(job => queueJobs.set(job.id, job));
      updateQueueBadge();
    } catch (error) { /* backend offline */ }
  }

  function renderQueue() {
    content.innerHTML = renderPage(
      'Job queue',
      'Background work',
      'Long-running requests are processed in the background. Watch their status here and in the sidebar badge.',
      `<button class="secondary-action" id="refreshQueueButton">Refresh</button>`,
      `<div class="panel data-panel"><div class="data-toolbar"><h2>Recent jobs</h2><span class="eyebrow" id="queueCount">Loading...</span></div><div class="queue-grid" id="queueGrid"><div class="empty-state">Loading jobs...</div></div></div>`
    );
    setActive('queue');
    // The grid is only rebuilt when something the user can see actually changed.
    // Replacing the HTML on every update would make the Cancel buttons unstable
    // to click (the node is swapped out mid-click).
    let lastSignature = null;
    // The most recent job rows, so "View output" can show a result without
    // refetching.
    const jobCache = new Map();

    const jobCard = job => {
      const kind = job.kind === 'generate' ? 'Generation' : job.kind === 'build-knowledge' ? 'Knowledge build' : job.kind;
      const prompt = (job.payload && job.payload.prompt) || (job.payload && job.payload.profile_id) || '';
      const statusClass = job.status === 'running' ? 'running' : job.status === 'done' ? 'done' : job.status === 'failed' ? 'failed' : job.status === 'cancelled' ? 'cancelled' : 'queued';
      const spinner = job.status === 'running' ? '<i></i>' : '';
      const info = job.progress || {};
      const active = job.status === 'running' || job.status === 'queued';
      const settled = job.status === 'done' || job.status === 'failed' || job.status === 'cancelled';
      let progressBlock = '';
      if (active) {
        const percent = job.status === 'queued' ? 0 : Math.max(2, Number(info.percent) || 0);
        const label = job.status === 'queued' ? 'Waiting for a free worker' : (info.label || 'Working');
        progressBlock = `<div class="q-progress">
          <div class="progress-track"><div class="progress-fill" style="width:${percent}%"></div></div>
          <div class="progress-meta"><span>${escapeHtml(label)}</span><span class="q-eta">${escapeHtml(job.status === 'queued' ? '' : etaText(info))}</span></div>
          ${activityFeedHtml(info.activity)}
        </div>`;
      }
      const duration = job.started_at && job.completed_at
        ? formatDuration((new Date(job.completed_at.replace(' ', 'T')) - new Date(job.started_at.replace(' ', 'T'))) / 1000)
        : '';
      const cancelling = active && job.cancel_requested;
      const cancelButton = active
        ? `<button class="cancel-job" data-cancel-job="${escapeHtml(job.id)}" ${cancelling ? 'disabled' : ''}>${cancelling ? 'Cancelling...' : 'Cancel'}</button>`
        : '';
      // Every settled job can be inspected: a finished job shows its deliverable,
      // a failed one shows why, and a cancelled one confirms nothing was saved.
      const outputButton = settled
        ? `<button class="mini-action" data-view-job="${escapeHtml(job.id)}">View output</button>`
        : '';
      return `<div class="queue-card" data-job-card="${escapeHtml(job.id)}">
        <div class="q-top"><h3>${escapeHtml(kind)}</h3><span class="status-pill ${statusClass}">${spinner}${escapeHtml(job.status)}</span></div>
        <p>${escapeHtml(prompt)}</p>
        ${progressBlock}
        <div class="q-foot"><span>${formatTime(job.created_at)}</span><span>${escapeHtml(duration)}</span></div>
        ${(cancelButton || outputButton) ? `<div class="q-actions">${outputButton}${cancelButton}</div>` : ''}
        ${job.error ? `<div class="q-error">${escapeHtml(job.error)}</div>` : ''}
      </div>`;
    };

    // Build the human-readable body of a job's stored result. A finished job
    // carries the deliverable plus a small audit trail; the others explain
    // themselves plainly instead of showing a raw blob.
    const jobOutput = job => {
      const result = job.result && typeof job.result === 'object' ? job.result : {};
      if (job.status === 'cancelled') {
        return { title: 'Job cancelled', body: job.error || 'The job was cancelled before it produced a result.' };
      }
      if (job.status === 'failed') {
        return { title: 'Job failed', body: job.error || 'The job failed without a message.' };
      }
      const isError = result.status === 'error';
      const main = result.output || result.message || job.error || 'This job produced no output.';
      const lines = [main];
      if (result.departments && result.departments.length) lines.push('', `Departments: ${result.departments.join(', ')}`);
      if (result.knowledge_used) lines.push(`Knowledge sources used: ${result.knowledge_used}`);
      if (Array.isArray(result.artifacts) && result.artifacts.length) {
        lines.push('', 'Artifacts:');
        result.artifacts.forEach(file => lines.push(`- ${file.filename}`));
      }
      if (result.backtests && result.backtests.length) {
        lines.push('', 'Backtests:');
        result.backtests.forEach(test => lines.push(`- ${test.specialist || 'script'}: ${test.conversion_rate != null ? Math.round(test.conversion_rate * 100) + '%' : 'n/a'} (${test.passed ? 'passed' : 'failed'})`));
      }
      if (result.error && result.error.message && result.error.message !== main) lines.push('', result.error.message);
      return { title: isError ? 'Job error' : 'Job output', body: lines.join('\n') };
    };

    const load = async () => {
      const countEl = document.getElementById('queueCount');
      const gridEl = document.getElementById('queueGrid');
      if (!countEl || !gridEl) return;
      try {
        const jobs = await api('/queue');
        jobs.forEach(job => {
          jobCache.set(job.id, job);
          queueJobs.set(job.id, job);
        });
        updateQueueBadge();
        render(jobs);
      } catch (error) {
        gridEl.innerHTML = '<div class="empty-state">Could not reach the queue service.</div>';
      }
    };

    // Render the given job rows. Only rebuild the grid when something visible
    // changed: replacing the HTML on every tick would swap the Cancel buttons
    // out from under the pointer, making them unreliable to click.
    const render = jobs => {
      const countEl = document.getElementById('queueCount');
      const gridEl = document.getElementById('queueGrid');
      if (!countEl || !gridEl) return;
      countEl.textContent = `${jobs.length} jobs`;
      const signature = JSON.stringify(jobs.map(job => [
        job.id, job.status, job.cancel_requested,
        (job.progress || {}).percent, (job.progress || {}).label,
        (job.progress || {}).eta_seconds, (job.progress || {}).estimate_seconds,
        // The activity feed is part of what the user sees, so a new line must
        // trigger a rebuild. Only the count and the newest preview are needed:
        // the count changes when a line is added, and the preview changes while
        // a generation is still streaming into the last line.
        ((job.progress || {}).activity || []).length,
        (((job.progress || {}).activity || []).slice(-1)[0] || {}).preview,
      ]));
      if (signature === lastSignature) return;
      lastSignature = signature;
      gridEl.innerHTML = jobs.length
        ? jobs.map(jobCard).join('')
        : '<div class="empty-state">No jobs yet. Send a message in Chat to start one.</div>';
      // Cache the job results so View output does not need another request.
      jobs.forEach(job => jobCache.set(job.id, job));
      gridEl.querySelectorAll('[data-cancel-job]').forEach(button => button.addEventListener('click', async () => {
        button.disabled = true;
        button.textContent = 'Cancelling...';
        try {
          await post(`/queue/${button.dataset.cancelJob}/cancel`, {});
          toast('Cancelling the job...');
        } catch (error) {
          toast(`Could not cancel the job: ${error.message}`, 'error');
        }
        load();
      }));
      gridEl.querySelectorAll('[data-view-job]').forEach(button => button.addEventListener('click', () => {
        const job = jobCache.get(button.dataset.viewJob);
        if (!job) return;
        const output = jobOutput(job);
        showModal(output.title, output.body);
      }));
    };

    // The live path: the backend pushes a snapshot for every job as it changes,
    // so the progress bars and the activity feed move without the user having to
    // press Refresh. A progress frame carries only `{id, status, progress}`, so
    // it is merged into the cached row rather than replacing it: the kind, the
    // prompt, and the timestamps come from the last full fetch.
    const applyFeedJob = job => {
      const merged = { ...(jobCache.get(job.id) || {}), ...job };
      jobCache.set(job.id, merged);
      queueJobs.set(job.id, merged);
      updateQueueBadge();
      const jobs = [...jobCache.values()].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
      render(jobs);
    };

    // The poll fallback: used when the browser has no `EventSource`, or when the
    // stream cannot be established. It keeps the page live (if less instantly)
    // rather than leaving it frozen.
    let pollTimer = null;
    const startPolling = () => {
      const tick = async () => {
        await load();
        const active = [...jobCache.values()].some(job => job.status === 'running' || job.status === 'queued');
        window.clearTimeout(pollTimer);
        if (active) pollTimer = trackTimer(window.setTimeout(tick, 2000));
      };
      tick();
    };

    document.getElementById('refreshQueueButton').addEventListener('click', load);
    // Seed the grid from the API, then switch to the live feed. The feed sends
    // the current rows on connect, so the seed is only there to paint instantly.
    load();
    const closeFeed = openQueueFeed(applyFeedJob, () => {
      // The stream is unavailable, so fall back to polling.
      if (!pollTimer) startPolling();
    });
    trackCleanup(closeFeed);
  }

  // The backend owns the timing constants, so the UI asks for them rather than
  // hard-coding numbers that could drift out of sync. Failure is harmless:
  // callers fall back to a sane default.
  async function loadQueueConfig() {
    try {
      const config = await api('/queue/config');
      state.defaultEstimate = Number(config.default_estimate_seconds) || state.defaultEstimate;
      state.queueMaxRuntime = Number(config.max_runtime_seconds) || state.queueMaxRuntime;
    } catch (error) {
      // Keep whatever was last known; the progress card degrades gracefully.
    }
  }

  // ---------------------------------------------------------------- history

  function renderHistory() {
    content.innerHTML = renderPage(
      'Conversation history',
      'Workspace memory',
      'Every conversation with your AI team, ready to pick up where you left off.',
      `<button class="secondary-action" data-route="chat">+ New chat</button>`,
      `<div class="panel data-panel"><div class="data-toolbar"><h2>Conversations</h2><input class="search-input" id="historySearch" placeholder="Search conversations" /></div><div id="historyRows"><div class="empty-state">Loading...</div></div></div>`
    );
    setActive('history');
    const load = async filter => {
      try {
        const conversations = await api(`/conversations?profile_id=${encodeURIComponent(state.profileId)}`);
        const filtered = conversations.filter(conversation => !filter || conversation.title.toLowerCase().includes(filter.toLowerCase()));
        document.getElementById('historyRows').innerHTML = filtered.length
          ? filtered.map(conversation => `
            <div class="data-row">
              <div><strong>${escapeHtml(conversation.title)}</strong><small>${formatTime(conversation.updated_at)}</small></div>
              <div class="row-actions">
                <button class="mini-action" data-open-conv="${conversation.id}">Open</button>
                <button class="mini-action danger" data-delete-conv="${conversation.id}">Delete</button>
              </div>
            </div>`).join('')
          : '<div class="empty-state">No conversations match that search.</div>';
        document.querySelectorAll('[data-open-conv]').forEach(button => button.addEventListener('click', () => {
          state.conversationId = button.dataset.openConv;
          localStorage.setItem('voltaik-conversation', state.conversationId);
          navigate('chat');
        }));
        document.querySelectorAll('[data-delete-conv]').forEach(button => button.addEventListener('click', async () => {
          await del(`/conversations/${button.dataset.deleteConv}`);
          if (state.conversationId === button.dataset.deleteConv) {
            state.conversationId = null;
            localStorage.removeItem('voltaik-conversation');
          }
          toast('Conversation deleted');
          load(document.getElementById('historySearch').value);
        }));
      } catch (error) {
        document.getElementById('historyRows').innerHTML = '<div class="empty-state">Could not load conversations.</div>';
      }
    };
    document.getElementById('historySearch').addEventListener('input', event => load(event.target.value));
    document.querySelectorAll('[data-route]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.route)));
    load('');
  }

  // ----------------------------------------------------------------- memory

  function renderMemory() {
    content.innerHTML = renderPage(
      'Business memory',
      'Persistent context',
      'Facts you want every agent run to remember. Memory is injected into every request so the whole team stays grounded.',
      `<button class="secondary-action" id="memoryRefresh">Refresh</button>`,
      `<div class="panel data-panel">
        <div class="data-toolbar"><h2>Add a memory</h2></div>
        <div class="memory-add">
          <input id="memoryInput" placeholder="e.g. We never promise guaranteed savings in any ad." />
          <select id="memoryCategory"><option value="general">General</option><option value="compliance">Compliance</option><option value="brand">Brand</option><option value="customer">Customer</option><option value="process">Process</option></select>
          <button class="primary-action" id="memoryAddButton">Add memory</button>
        </div>
        <div class="memory-list" id="memoryList"><div class="empty-state">Loading...</div></div>
      </div>`
    );
    setActive('memory');
    const load = async () => {
      try {
        const items = await api(`/memory?profile_id=${encodeURIComponent(state.profileId)}`);
        document.getElementById('memoryList').innerHTML = items.length
          ? items.map(item => `
            <div class="memory-item">
              <div class="m-body"><strong>${escapeHtml(item.content)}</strong><small>${escapeHtml(item.category)} · ${formatTime(item.created_at)}</small></div>
              <button class="mini-action danger" data-delete-memory="${item.id}">Delete</button>
            </div>`).join('')
          : '<div class="empty-state">No memories yet. Add facts your team should always remember.</div>';
        document.querySelectorAll('[data-delete-memory]').forEach(button => button.addEventListener('click', async () => {
          await del(`/memory/${button.dataset.deleteMemory}`);
          toast('Memory removed');
          load();
        }));
      } catch (error) {
        document.getElementById('memoryList').innerHTML = '<div class="empty-state">Could not load memory.</div>';
      }
    };
    document.getElementById('memoryAddButton').addEventListener('click', async () => {
      const input = document.getElementById('memoryInput');
      const text = input.value.trim();
      if (!text) return toast('Write a memory first.');
      try {
        await post('/memory', { profile_id: state.profileId, content: text, category: document.getElementById('memoryCategory').value });
        input.value = '';
        toast('Memory saved — the team will remember this.');
        load();
      } catch (error) {
        toast(error.message);
      }
    });
    document.getElementById('memoryRefresh').addEventListener('click', load);
    load();
  }

  // -------------------------------------------------------------- knowledge

  function renderKnowledge() {
    content.innerHTML = renderPage(
      'Knowledge library',
      'Business context',
      'The documents your AI team grounds every deliverable in. Upload files, create documents, or build a base from a profile.',
      `<button class="secondary-action" id="reindexButton">Re-index library</button><button class="primary-action" id="knowledgeUploadButton">+ Upload file</button>`,
      `<div class="panel data-panel"><div class="data-toolbar"><h2>Library</h2><span class="eyebrow" id="knowledgeCount">Loading...</span></div><div id="knowledgeRows"><div class="empty-state">Loading your knowledge library...</div></div></div>
       <div class="panel data-panel"><div class="panel-title"><h2>Create a file</h2><span class="eyebrow">TXT · PDF · DOCX</span></div>
       <div class="create-form"><label>Filename<input class="setting-input" id="createFilename" value="campaign-brief.txt" /></label><label>Content<textarea id="createContent" placeholder="Write the document content here..."></textarea></label><button class="primary-action" id="createFileButton">Create file</button></div></div>`
    );
    setActive('knowledge');
    const fileInput = bindFilePicker(async (event, picker) => {
      const files = Array.from(event.target.files || []);
      picker.value = '';
      for (const file of files) {
        try {
          const data = await uploadFile(file);
          toast(`${data.filename} uploaded`);
        } catch (error) {
          toast(`Could not upload ${file.name}: ${error.message}`, 'error');
        }
      }
      renderRows();
    });
    const renderRows = async () => {
      const countEl = document.getElementById('knowledgeCount');
      const rowsEl = document.getElementById('knowledgeRows');
      // An upload can finish after the user navigated away, which detaches
      // these nodes. Rendering into them would throw.
      if (!countEl || !rowsEl) return;
      try {
        const [documents, uploads] = await Promise.all([api('/knowledge'), api('/knowledge/uploads')]);
        const rows = [
          ...uploads.map(file => ({ name: file.filename, category: 'Uploaded context', meta: formatSize(file.size), extension: file.extension || '.file', uploaded: true, readable: file.readable !== false })),
          ...documents.map(file => ({ name: file.document, category: file.category, meta: 'Indexed knowledge', extension: '.md', uploaded: false, readable: true })),
        ];
        countEl.textContent = `${rows.length} sources`;
        rowsEl.innerHTML = rows.length
          ? `<div class="file-grid">${rows.map((file, index) => {
              const type = file.extension === '.pdf' ? 'pdf' : file.extension === '.docx' ? 'docx' : file.extension === '.txt' ? 'txt' : 'other';
              return `<article class="file-card"><div class="file-card-top"><div class="file-type ${type}">${type === 'other' ? 'FILE' : type.toUpperCase()}</div><span class="eyebrow">${file.uploaded ? 'Uploaded' : 'Indexed'}</span></div><h3 title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</h3><small>${escapeHtml(file.category)} · ${file.meta}</small>${file.readable ? '' : '<small style="color:var(--red)">Not readable by the AI team</small>'}<div class="file-card-actions"><button class="mini-action" data-preview-file="${index}">Preview</button>${file.uploaded ? `<button class="mini-action danger" data-delete-file="${index}">Remove</button>` : ''}</div></article>`;
            }).join('')}</div>`
          : '<div class="empty-state">No knowledge files found.</div>';
        document.querySelectorAll('[data-preview-file]').forEach(button => button.addEventListener('click', async () => {
          const file = rows[Number(button.dataset.previewFile)];
          if (!file.uploaded) return toast('This indexed source is available to the AI team.');
          try {
            const data = await api(`/knowledge/uploads/${encodeURIComponent(file.name)}/preview`);
            showModal(data.filename, data.preview || 'This file has no readable text preview.');
          } catch (error) {
            toast(error.message, 'error');
          }
        }));
        document.querySelectorAll('[data-delete-file]').forEach(button => button.addEventListener('click', async () => {
          const file = rows[Number(button.dataset.deleteFile)];
          await del(`/knowledge/uploads/${encodeURIComponent(file.name)}`);
          toast(`${file.name} removed`);
          renderRows();
        }));
      } catch (error) {
        rowsEl.innerHTML = '<div class="empty-state">Could not reach the knowledge service. Check that the backend is running.</div>';
      }
    };
    document.getElementById('knowledgeUploadButton').addEventListener('click', () => fileInput.click());
    document.getElementById('reindexButton').addEventListener('click', async event => {
      event.currentTarget.textContent = 'Re-indexing...';
      try {
        const data = await post('/knowledge/reindex', {});
        toast(`Indexed ${data.documents_indexed} documents`);
      } catch (error) {
        toast('Re-index failed');
      }
      event.currentTarget.textContent = 'Re-index library';
    });
    document.getElementById('createFileButton').addEventListener('click', async event => {
      const filename = document.getElementById('createFilename').value.trim();
      const contentText = document.getElementById('createContent').value;
      event.currentTarget.textContent = 'Creating...';
      try {
        const data = await post('/knowledge/create', { filename, content: contentText });
        toast(`${data.filename} created`);
        renderRows();
      } catch (error) {
        toast(error.message);
      }
      event.currentTarget.textContent = 'Create file';
    });
    renderRows();
  }

  // --------------------------------------------------------------- profiles

  const PROFILE_FIELDS = [
    ['name', 'Business name', 'text', 'The name of your business.'],
    ['business_type', 'Business type', 'text', 'e.g. Solar installer, Roofing company, Med spa.'],
    ['industry', 'Industry', 'text', 'e.g. Residential solar, Home services, Healthcare.'],
    ['description', 'What does your business do?', 'textarea', 'A short description of your products and services.'],
    ['target_customer', 'Who is your ideal customer?', 'textarea', 'Demographics, pain points, objections, buying triggers.'],
    ['services', 'Services', 'textarea', 'What you sell, one per line.'],
    ['offers', 'Offers & lead magnets', 'textarea', 'Free consultations, quotes, audits, discounts.'],
    ['pricing', 'Pricing & financing', 'textarea', 'How you price, financing options, payment terms.'],
    ['brand_voice', 'Brand voice', 'textarea', 'How should the AI sound? e.g. Educational, direct, friendly, no hype.'],
    ['marketing_channels', 'Marketing channels', 'textarea', 'Meta ads, Google, SMS, email, cold calls, referrals.'],
    ['sales_process', 'Sales process', 'textarea', 'How leads become customers: setter → closer → install.'],
    ['automation_needs', 'Automation needs', 'textarea', 'Nurture sequences, reminders, follow-ups you want.'],
    ['geographic_focus', 'Geographic focus', 'text', 'States, cities, or service areas.'],
    ['compliance_notes', 'Compliance rules', 'textarea', 'Claims to avoid, guarantees you cannot make, legal notes.'],
  ];

  function profileFormHtml(profile) {
    const value = field => escapeHtml((profile || {})[field] || '');
    return `<div class="profile-form">
      ${PROFILE_FIELDS.map(([field, label, type, hint]) => `
        <div class="form-field ${type === 'textarea' ? 'full' : ''}">
          <label for="pf-${field}">${escapeHtml(label)}</label>
          ${type === 'textarea'
            ? `<textarea id="pf-${field}" placeholder="${escapeHtml(hint)}">${value(field)}</textarea>`
            : `<input id="pf-${field}" type="text" placeholder="${escapeHtml(hint)}" value="${value(field)}" />`}
          <small>${escapeHtml(hint)}</small>
        </div>`).join('')}
    </div>`;
  }

  function collectProfileForm() {
    const data = {};
    PROFILE_FIELDS.forEach(([field]) => {
      const element = document.getElementById(`pf-${field}`);
      data[field] = element ? element.value.trim() : '';
    });
    return data;
  }

  function renderProfiles() {
    content.innerHTML = renderPage(
      'Business profiles',
      'Your businesses',
      'Each profile is a complete picture of one business. Fill in the form and let the AI convert it into a knowledge base your team will use.',
      `<button class="primary-action" id="newProfileButton">+ New profile</button>`,
      `<div class="panel data-panel"><div class="data-toolbar"><h2>Profiles</h2><span class="eyebrow" id="profileCount">Loading...</span></div><div class="profile-grid" id="profileGrid"><div class="empty-state">Loading...</div></div></div>
       <div class="panel data-panel" id="profileEditorPanel" hidden>
         <div class="panel-title"><h2 id="profileEditorTitle">New profile</h2><span class="eyebrow">Fill in what you know — the AI fills the gaps</span></div>
         ${profileFormHtml(null)}
         <div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap">
           <button class="primary-action" id="saveProfileButton">Save profile</button>
           <button class="secondary-action" id="buildKnowledgeButton">Build knowledge base</button>
           <button class="secondary-action" id="cancelProfileButton">Cancel</button>
         </div>
         <div class="build-result" id="buildResult" hidden></div>
       </div>`
    );
    setActive('profiles');
    let editingId = null;

    const load = async () => {
      try {
        const profiles = await api('/profiles');
        document.getElementById('profileCount').textContent = `${profiles.length} profiles`;
        document.getElementById('profileGrid').innerHTML = profiles.length
          ? profiles.map(profile => `
            <div class="profile-card">
              <div class="p-top"><div class="avatar">${escapeHtml(initials(profile.name))}</div><div><h3>${escapeHtml(profile.name)}</h3><small>${escapeHtml(profile.business_type || 'Business')}</small></div></div>
              <p>${escapeHtml(profile.description || 'No description yet.')}</p>
              <div class="p-actions">
                <button class="mini-action" data-edit-profile="${profile.id}">Edit</button>
                <button class="mini-action" data-use-profile="${profile.id}">Use</button>
                <button class="mini-action" data-build-profile="${profile.id}">Build knowledge</button>
                <button class="mini-action danger" data-delete-profile="${profile.id}">Delete</button>
              </div>
            </div>`).join('')
          : '<div class="empty-state">No profiles yet. Create one to get started.</div>';
        document.querySelectorAll('[data-edit-profile]').forEach(button => button.addEventListener('click', () => openEditor(button.dataset.editProfile)));
        document.querySelectorAll('[data-use-profile]').forEach(button => button.addEventListener('click', () => switchProfile(button.dataset.useProfile)));
        document.querySelectorAll('[data-build-profile]').forEach(button => button.addEventListener('click', () => buildKnowledge(button.dataset.buildProfile)));
        document.querySelectorAll('[data-delete-profile]').forEach(button => button.addEventListener('click', async () => {
          await del(`/profiles/${button.dataset.deleteProfile}`);
          toast('Profile deleted');
          load();
        }));
      } catch (error) {
        document.getElementById('profileGrid').innerHTML = '<div class="empty-state">Could not load profiles.</div>';
      }
    };

    const openEditor = async profileId => {
      editingId = profileId;
      const panel = document.getElementById('profileEditorPanel');
      panel.hidden = false;
      document.getElementById('profileEditorTitle').textContent = profileId ? 'Edit profile' : 'New profile';
      document.getElementById('buildResult').hidden = true;
      if (profileId) {
        try {
          const profile = await api(`/profiles/${profileId}`);
          const form = document.createElement('div');
          form.innerHTML = profileFormHtml(profile);
          panel.querySelector('.profile-form').replaceWith(form);
        } catch (error) {
          toast('Could not load profile');
        }
      } else {
        const form = document.createElement('div');
        form.innerHTML = profileFormHtml(null);
        panel.querySelector('.profile-form').replaceWith(form);
      }
    };

    const buildKnowledge = async profileId => {
      const resultEl = document.getElementById('buildResult');
      resultEl.hidden = false;
      resultEl.textContent = 'Building your knowledge base... this can take a moment.';
      try {
        const data = await post(`/profiles/${profileId}/build-knowledge`, {});
        const files = (data.documents || []).map(doc => doc.filename).join(', ');
        resultEl.textContent = `Knowledge base ${data.mode === 'ai' ? 'AI-expanded' : 'built'} — ${data.documents.length} documents: ${files}`;
        toast('Knowledge base built');
      } catch (error) {
        resultEl.textContent = `Could not build the knowledge base: ${error.message}`;
      }
    };

    document.getElementById('newProfileButton').addEventListener('click', () => openEditor(null));
    document.getElementById('cancelProfileButton').addEventListener('click', () => {
      document.getElementById('profileEditorPanel').hidden = true;
    });
    document.getElementById('saveProfileButton').addEventListener('click', async () => {
      const data = collectProfileForm();
      if (!data.name) return toast('Give the profile a name.');
      try {
        if (editingId) {
          await put(`/profiles/${editingId}`, data);
          toast('Profile updated');
        } else {
          const created = await post('/profiles', data);
          editingId = created.id;
          toast('Profile created');
        }
        load();
        loadProfiles();
      } catch (error) {
        toast(error.message);
      }
    });
    document.getElementById('buildKnowledgeButton').addEventListener('click', async () => {
      const data = collectProfileForm();
      if (!data.name) return toast('Save the profile first.');
      let targetId = editingId;
      try {
        if (!targetId) {
          const created = await post('/profiles', data);
          targetId = created.id;
          editingId = targetId;
        } else {
          await put(`/profiles/${targetId}`, data);
        }
        buildKnowledge(targetId);
      } catch (error) {
        toast(error.message);
      }
    });
    load();
  }

  // ------------------------------------------------------------------- team

  function renderTeam() {
    content.innerHTML = renderPage(
      'AI team',
      'Chain of command',
      'The manager is the only agent that talks to you. It routes work to a department head, who assigns specialists and verifies their work before anything comes back.',
      '',
      `<div class="agent-grid" id="agentGrid"><div class="empty-state">Loading your team...</div></div>`
    );
    setActive('team');
    try {
      api('/agents').then(agents => {
        const groups = [
          { key: 'manager', label: 'Top of the chain' },
          { key: 'department_head', label: 'Department heads' },
          { key: 'specialist', label: 'Specialists' },
        ];
        const render = group => agents.filter(agent => agent.role === group.key).map(agent => `
          <article class="agent-card">
            <div class="agent-card-top"><div class="avatar">${escapeHtml(agent.name.slice(0, 1))}</div><div><h3>${escapeHtml(agent.name)}</h3><small>${escapeHtml(agent.role === 'manager' ? 'Only user-facing agent' : agent.role.replace('_', ' '))}</small></div></div>
            <p>${escapeHtml(agent.description || '')}</p>
            ${agent.requires_backtest ? '<small class="eyebrow">Backtested before delivery</small>' : ''}
          </article>`).join('');
        document.getElementById('agentGrid').innerHTML = groups.map(group => {
          const cards = render(group);
          return cards ? `<div class="team-group"><h2>${escapeHtml(group.label)}</h2><div class="agent-grid">${cards}</div></div>` : '';
        }).join('') || '<div class="empty-state">No agents are registered.</div>';
      }).catch(() => {
        document.getElementById('agentGrid').innerHTML = '<div class="empty-state">Could not reach the AI team service.</div>';
      });
    } catch (error) {
      document.getElementById('agentGrid').innerHTML = '<div class="empty-state">Could not reach the AI team service.</div>';
    }
  }

  // ------------------------------------------------------------------ modal

  function showModal(title, contentText) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `<div class="modal-dialog"><header><h2>${escapeHtml(title)}</h2><button class="modal-close" data-close-modal aria-label="Close">×</button></header><div class="preview-content">${escapeHtml(contentText)}</div></div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', event => {
      if (event.target === modal || event.target.closest('[data-close-modal]')) modal.remove();
    });
  }

  // ------------------------------------------------------------------ routes

  function navigate(route) { window.location.hash = route; }

  function route() {
    const routeName = window.location.hash.replace('#', '') || 'chat';
    clearPageWork();
    setActive(routeName);
    if (routeName === 'queue') renderQueue();
    else if (routeName === 'history') renderHistory();
    else if (routeName === 'memory') renderMemory();
    else if (routeName === 'knowledge') renderKnowledge();
    else if (routeName === 'profiles') renderProfiles();
    else if (routeName === 'team') renderTeam();
    else renderChat();
    if (routeName === 'chat') loadChatHistory();
  }

  // ------------------------------------------------------------------- init

  async function checkProviderHealth() {
    try {
      const health = await api('/health/provider');
      if (health.status !== 'ok') {
        const provider = health.provider || {};
        const reason = provider.error || (provider.dns_ok === false ? 'The provider host could not be resolved.' : 'The provider is unreachable.');
        toast(`Model provider unavailable: ${reason}`);
      }
    } catch (error) {
      // The backend itself is unreachable; loadProfiles already surfaces that.
    }
  }

  document.querySelectorAll('.nav a').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    navigate(link.getAttribute('href').slice(1));
  }));
  document.getElementById('profileSwitcher').addEventListener('click', () => navigate('profiles'));
document.getElementById('helpButton').addEventListener('click', () => toast('Ask your AI team anything from Chat. Set up a business profile to build your knowledge base.'));
  window.addEventListener('hashchange', route);

  loadProfiles().then(() => {
    route();
    refreshQueueBadge();
    checkProviderHealth();
    loadQueueConfig();
    // Keep the sidebar badge live from the queue-wide feed, so a job that starts
    // or finishes updates the count without a page refresh. The feed is opened
    // once for the lifetime of the page; the periodic refresh below is only a
    // safety net for a stream that could not be established.
    openQueueFeed(job => {
      queueJobs.set(job.id, job);
      updateQueueBadge();
    });
    window.setInterval(() => refreshQueueBadge(), 30000);
    // Keep the connection status honest: if the backend restarts while the page
    // is open, the sidebar recovers on its own instead of staying "Offline".
    window.setInterval(() => recheckConnection(), 10000);
  });
})();
