(() => {
  const content = document.querySelector('.content');
  const studioTemplate = content.innerHTML;
  const historyKey = 'voltaik-chat-history';
  const settingsKey = 'voltaik-settings';
  const apiBase = `http://${window.location.hostname || '127.0.0.1'}:8000`;

  const pageStyles = document.createElement('style');
  pageStyles.textContent = `
    @keyframes page-enter { from { opacity:0; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
    @keyframes item-enter { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
    .page-view { padding-bottom: 40px; animation:page-enter .6s cubic-bezier(.23,1,.32,1) both; }
    .page-header { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin-bottom:24px; }
    .page-header p { max-width:520px; color:var(--muted); font-size:13px; margin-top:10px; }
    .page-actions { display:flex; gap:8px; flex-wrap:wrap; }
    .primary-action,.secondary-action { display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:36px; padding:0 13px; border-radius:8px; font-size:11px; font-weight:700; }
    .primary-action { color:#180b2f; background:linear-gradient(120deg,var(--violet2),var(--amber)); }
    .secondary-action { color:#ddd3eb; border:1px solid var(--line); background:rgba(255,255,255,.035); }
    .secondary-action:hover { border-color:rgba(173,107,255,.5); color:var(--paper); }
    .data-panel { padding:18px; margin-bottom:18px; animation:item-enter .55s .12s both; }
    .file-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:12px; }
    .file-card { position:relative; min-height:172px; padding:15px; border:1px solid var(--line); border-radius:11px; background:rgba(255,255,255,.025); animation:item-enter .45s both; transition:transform .25s,border-color .25s,background .25s; }
    .file-card:nth-child(1) { animation-delay:.16s; } .file-card:nth-child(2) { animation-delay:.22s; } .file-card:nth-child(3) { animation-delay:.28s; } .file-card:nth-child(4) { animation-delay:.34s; }
    .file-card:hover { transform:translateY(-4px); border-color:rgba(173,107,255,.42); background:rgba(139,59,255,.07); }
    .file-card-top { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
    .file-type { display:grid; place-items:center; width:38px; height:38px; border-radius:9px; color:#180b2f; font-size:10px; font-weight:800; background:var(--violet2); }
    .file-type.pdf { color:#fff0f0; background:#c95570; } .file-type.docx { color:#e7f0ff; background:#487bd1; } .file-type.txt { color:#20172d; background:var(--amber); } .file-type.other { color:#eee5ff; background:#694d8d; }
    .file-card h3 { overflow:hidden; margin:16px 0 4px; color:#e5dcf1; font:600 12px 'Bricolage Grotesque',sans-serif; text-overflow:ellipsis; white-space:nowrap; }
    .file-card small { color:var(--muted); font-size:10px; }
    .file-card-actions { display:flex; gap:6px; margin-top:15px; }
    .preview-modal { position:fixed; inset:0; z-index:50; display:grid; place-items:center; padding:22px; background:rgba(3,2,9,.76); backdrop-filter:blur(8px); animation:page-enter .25s both; }
    .preview-dialog { width:min(760px,100%); max-height:min(720px,90vh); overflow:auto; padding:20px; border:1px solid rgba(173,107,255,.35); border-radius:14px; background:#160a2d; box-shadow:0 25px 100px rgba(0,0,0,.5); }
    .preview-dialog header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; } .preview-dialog h2 { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .preview-content { min-height:260px; max-height:520px; overflow:auto; padding:16px; color:#ddd3eb; border:1px solid var(--line); border-radius:9px; background:rgba(5,3,13,.7); font:12px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; }
    .create-form { display:grid; grid-template-columns:180px 1fr auto; gap:10px; align-items:end; } .create-form label { display:grid; gap:6px; color:#d9cdeb; font-size:10px; } .create-form textarea { min-height:42px; height:42px; resize:vertical; padding:10px; font-size:11px; }
    .data-toolbar { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; }
    .search-input,.setting-input { width:100%; padding:10px 12px; color:var(--paper); border:1px solid var(--line); border-radius:8px; outline:0; background:rgba(5,3,13,.6); }
    .search-input { max-width:300px; }
    .search-input:focus,.setting-input:focus { border-color:rgba(173,107,255,.6); }
    .data-row { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:13px 0; border-top:1px solid var(--line); animation:item-enter .42s both; }
    .data-row:nth-child(1) { animation-delay:.18s; } .data-row:nth-child(2) { animation-delay:.24s; } .data-row:nth-child(3) { animation-delay:.30s; } .data-row:nth-child(4) { animation-delay:.36s; } .data-row:nth-child(5) { animation-delay:.42s; } .data-row:nth-child(6) { animation-delay:.48s; }
    .data-row:first-child { border-top:0; }
    .data-row strong { display:block; color:#e5dcf1; font-size:12px; font-weight:600; }
    .data-row small { color:var(--muted); font-size:10px; }
    .row-actions { display:flex; gap:7px; flex-shrink:0; }
    .mini-action { padding:6px 9px; color:var(--violet2); border:1px solid var(--line); border-radius:6px; background:transparent; font-size:10px; }
    .mini-action.danger { color:#ff9d9d; }
    .mini-action:hover { border-color:rgba(173,107,255,.5); }
    .empty-state { padding:28px 8px; color:#766b88; text-align:center; font-size:12px; }
    .agent-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    .agent-card { padding:16px; border:1px solid var(--line); border-radius:10px; background:rgba(255,255,255,.025); animation:item-enter .5s both; transition:transform .25s,border-color .25s,background .25s; }
    .agent-card:nth-child(1) { animation-delay:.16s; } .agent-card:nth-child(2) { animation-delay:.24s; } .agent-card:nth-child(3) { animation-delay:.32s; } .agent-card:hover { transform:translateY(-4px); border-color:rgba(173,107,255,.4); background:rgba(139,59,255,.07); }
    .agent-card .agent-card-top { display:flex; align-items:center; gap:10px; margin-bottom:15px; }
    .agent-card .avatar { color:var(--paper); background:var(--plum2); }
    .agent-card h3 { font:700 14px 'Bricolage Grotesque',sans-serif; }
    .agent-card p { min-height:42px; color:var(--muted); font-size:11px; }
    .setting-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .setting { display:grid; gap:7px; }
    .setting label { color:#d9cdeb; font-size:11px; }
    .setting small { color:var(--muted); font-size:10px; }
    .switch-row { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 0; border-top:1px solid var(--line); }
    .switch { position:relative; width:36px; height:20px; flex:none; }
    .switch input { opacity:0; width:0; height:0; }
    .slider { position:absolute; inset:0; border-radius:20px; background:#39264f; cursor:pointer; transition:.2s; }
    .slider:before { position:absolute; content:''; width:14px; height:14px; left:3px; top:3px; border-radius:50%; background:#aa9bbd; transition:.2s; }
    .switch input:checked + .slider { background:var(--violet); }
    .switch input:checked + .slider:before { transform:translateX(16px); background:white; }
    @media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; } }
    @media (prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; } }
    @media (max-width:680px) { .page-header { display:block; } .page-actions { margin-top:18px; } .data-toolbar { align-items:stretch; flex-direction:column; } .search-input { max-width:none; } .agent-grid,.setting-grid { grid-template-columns:1fr; } .data-row { align-items:flex-start; flex-direction:column; } .row-actions { width:100%; } .file-grid { grid-template-columns:1fr 1fr; } .create-form { grid-template-columns:1fr; } }
    @media (max-width:440px) { .file-grid { grid-template-columns:1fr; } }
  `;
  document.head.appendChild(pageStyles);

  const escapeHtml = value => String(value || '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;' }[char]));
  const toast = message => { const element = document.getElementById('toast'); if (!element) return; element.textContent = message; element.classList.add('show'); window.setTimeout(() => element.classList.remove('show'), 2800); };
  const historyItems = () => JSON.parse(localStorage.getItem(historyKey) || '[]');
  const saveSettings = settings => localStorage.setItem(settingsKey, JSON.stringify(settings));
  const getSettings = () => ({ name:'Solar growth team', model:'openrouter/free', notifications:true, ...JSON.parse(localStorage.getItem(settingsKey) || '{}') });
  const formatSize = size => `${Math.max(0.1, size / 1024).toFixed(1)} KB`;

  function setActive(route) {
    document.querySelectorAll('.nav a').forEach(link => link.classList.toggle('active', link.getAttribute('href') === `#${route}`));
    const crumb = document.querySelector('.crumbs b');
    if (crumb) crumb.textContent = route === 'studio' ? 'Studio' : route.replace('-', ' ').replace(/\b\w/g, char => char.toUpperCase());
  }

  function renderStudio() {
    content.innerHTML = studioTemplate;
    setActive('studio');
    bindStudio();
  }

  function renderHistory() {
    const rows = historyItems();
    content.innerHTML = `<div class="page-view"><div class="page-header"><div><div class="eyebrow">Workspace memory</div><h1>History</h1><p>Every prompt your team has completed, ready to pick up where you left off.</p></div><div class="page-actions"><button class="secondary-action" data-route="studio">New conversation</button></div></div><div class="panel data-panel"><div class="data-toolbar"><h2>Conversations</h2><input class="search-input" id="historySearch" placeholder="Search conversations" /></div><div id="historyRows"></div></div></div>`;
    const renderRows = filter => {
      const filtered = rows.filter(item => item.prompt.toLowerCase().includes(filter.toLowerCase()));
      document.getElementById('historyRows').innerHTML = filtered.length ? filtered.map((item, index) => `<div class="data-row"><div><strong>${escapeHtml(item.prompt)}</strong><small>${escapeHtml(item.time || 'Saved conversation')}</small></div><div class="row-actions"><button class="mini-action" data-open-history="${index}">Open</button><button class="mini-action danger" data-delete-history="${index}">Delete</button></div></div>`).join('') : '<div class="empty-state">No conversations match that search.</div>';
      document.querySelectorAll('[data-open-history]').forEach(button => button.addEventListener('click', () => { const item = filtered[Number(button.dataset.openHistory)]; localStorage.setItem('voltaik-pending-prompt', item.prompt); navigate('studio'); toast('Conversation loaded into Studio'); }));
      document.querySelectorAll('[data-delete-history]').forEach(button => button.addEventListener('click', () => { const target = filtered[Number(button.dataset.deleteHistory)]; localStorage.setItem(historyKey, JSON.stringify(rows.filter(item => item.prompt !== target.prompt))); renderHistory(); toast('Conversation deleted'); }));
    };
    renderRows('');
    document.getElementById('historySearch').addEventListener('input', event => renderRows(event.target.value));
    document.querySelectorAll('[data-route]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.route)));
  }

  async function renderKnowledge() {
    content.innerHTML = `<div class="page-view"><div class="page-header"><div><div class="eyebrow">Business context</div><h1>Knowledge files</h1><p>Manage the documents your AI team can use when it creates, evaluates, and plans.</p></div><div class="page-actions"><button class="secondary-action" id="reindexButton">Re-index library</button><button class="primary-action" id="knowledgeUploadButton">+ Upload file</button></div></div><div class="panel data-panel"><div class="data-toolbar"><h2>Library</h2><span class="eyebrow" id="knowledgeCount">Loading...</span></div><div id="knowledgeRows"><div class="empty-state">Loading your knowledge library...</div></div></div><div class="panel data-panel"><div class="panel-title"><h2>Create a file</h2><span class="eyebrow">TXT · PDF · DOCX</span></div><div class="create-form"><label>Filename<input class="setting-input" id="createFilename" value="campaign-brief.docx" /></label><label>Content<textarea id="createContent" placeholder="Write the document content here..."></textarea></label><button class="primary-action" id="createFileButton">Create file</button></div></div><input id="knowledgeInput" type="file" hidden multiple accept=".txt,.md,.csv,.json,.html,.pdf,.doc,.docx" /></div>`;
    const renderRows = async () => {
      const [documents, uploads] = await Promise.all([fetch(`${apiBase}/knowledge`).then(response => response.json()), fetch(`${apiBase}/knowledge/uploads`).then(response => response.json())]);
      const rows = [...uploads.map(file => ({ name:file.filename, category:'Uploaded context', meta:formatSize(file.size), extension:file.extension || '.file', uploaded:true })), ...documents.map(file => ({ name:file.document, category:file.category, meta:'Indexed knowledge', extension:'.md', uploaded:false }))];
      document.getElementById('knowledgeCount').textContent = `${rows.length} sources`;
      document.getElementById('knowledgeRows').innerHTML = rows.length ? `<div class="file-grid">${rows.map((file, index) => { const type = file.extension === '.pdf' ? 'pdf' : file.extension === '.docx' ? 'docx' : file.extension === '.txt' ? 'txt' : 'other'; return `<article class="file-card"><div class="file-card-top"><div class="file-type ${type}">${type === 'other' ? 'FILE' : type.toUpperCase()}</div><span class="eyebrow">${file.uploaded ? 'Uploaded' : 'Indexed'}</span></div><h3 title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</h3><small>${escapeHtml(file.category)} · ${file.meta}</small><div class="file-card-actions"><button class="mini-action" data-preview-file="${index}">Preview</button>${file.uploaded ? `<button class="mini-action danger" data-delete-file="${index}">Remove</button>` : ''}</div></article>`; }).join('')}</div>` : '<div class="empty-state">No knowledge files found.</div>';
      document.querySelectorAll('[data-preview-file]').forEach(button => button.addEventListener('click', async () => { const file = rows[Number(button.dataset.previewFile)]; if (!file.uploaded) return toast('This indexed source is available to the AI team.'); const response = await fetch(`${apiBase}/knowledge/uploads/${encodeURIComponent(file.name)}/preview`); const data = await response.json(); if (!response.ok) return toast(data.detail || 'Preview unavailable'); showPreview(data.filename, data.preview); }));
      document.querySelectorAll('[data-delete-file]').forEach(button => button.addEventListener('click', async () => { const file = rows[Number(button.dataset.deleteFile)]; const response = await fetch(`${apiBase}/knowledge/uploads/${encodeURIComponent(file.name)}`, { method:'DELETE' }); toast(response.ok ? `${file.name} removed` : 'Could not remove file'); renderRows(); }));
    };
    const input = document.getElementById('knowledgeInput');
    document.getElementById('knowledgeUploadButton').addEventListener('click', () => input.click());
    input.addEventListener('change', async event => { for (const file of event.target.files) { const body = new FormData(); body.append('file', file); const response = await fetch(`${apiBase}/knowledge/upload`, { method:'POST', body }); if (response.ok) toast(`${file.name} uploaded`); else toast(`Could not upload ${file.name}`); } input.value = ''; renderRows(); });
    document.getElementById('reindexButton').addEventListener('click', async event => { event.currentTarget.textContent = 'Re-indexing...'; const response = await fetch(`${apiBase}/knowledge/reindex`, { method:'POST' }); event.currentTarget.textContent = 'Re-index library'; toast(response.ok ? 'Knowledge library re-indexed' : 'Re-index failed'); });
    document.getElementById('createFileButton').addEventListener('click', async event => { const filename = document.getElementById('createFilename').value.trim(); const contentText = document.getElementById('createContent').value; event.currentTarget.textContent = 'Creating...'; const response = await fetch(`${apiBase}/knowledge/create`, { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ filename, content:contentText }) }); const data = await response.json(); event.currentTarget.textContent = 'Create file'; if (!response.ok) return toast(data.detail || 'Could not create file'); toast(`${data.filename} created`); renderRows(); });
    try { await renderRows(); } catch (error) { document.getElementById('knowledgeRows').innerHTML = '<div class="empty-state">Could not reach the knowledge service. Check that the backend is running.</div>'; }
  }

  function showPreview(filename, preview) {
    const modal = document.createElement('div');
    modal.className = 'preview-modal';
    modal.innerHTML = `<div class="preview-dialog"><header><h2>${escapeHtml(filename)}</h2><button class="icon-button" data-close-preview aria-label="Close preview">×</button></header><div class="preview-content">${escapeHtml(preview || 'This file has no readable text preview.')}</div></div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', event => { if (event.target === modal || event.target.closest('[data-close-preview]')) modal.remove(); });
  }

  async function renderTeam() {
    content.innerHTML = `<div class="page-view"><div class="page-header"><div><div class="eyebrow">Your digital operators</div><h1>AI team</h1><p>Choose a specialist, see what they own, and bring them into the next task.</p></div></div><div class="agent-grid" id="agentGrid"><div class="empty-state">Loading your team...</div></div></div>`;
    try {
      const response = await fetch(`${apiBase}/agents`); const agents = await response.json();
      document.getElementById('agentGrid').innerHTML = agents.map(agent => `<article class="agent-card"><div class="agent-card-top"><div class="avatar">${escapeHtml(agent.name.slice(0,1))}</div><div><h3>${escapeHtml(agent.name)}</h3><small>${escapeHtml(agent.department)}</small></div></div><p>${escapeHtml({ manager:'Routes work to the right specialist and keeps context aligned.', marketing:'Turns positioning and business context into compelling campaign assets.', sales:'Builds conversations, qualifies intent, and moves prospects forward.' }[agent.id] || 'A focused operator for your business workflow.')}</p><button class="secondary-action" data-use-agent="${escapeHtml(agent.name)}">Use this agent</button></article>`).join('');
      document.querySelectorAll('[data-use-agent]').forEach(button => button.addEventListener('click', () => { localStorage.setItem('voltaik-agent', button.dataset.useAgent); navigate('studio'); toast(`${button.dataset.useAgent} is ready in Studio`); }));
    } catch (error) { document.getElementById('agentGrid').innerHTML = '<div class="empty-state">Could not reach the AI team service.</div>'; }
  }

  function renderSettings() {
    const settings = getSettings();
    content.innerHTML = `<div class="page-view"><div class="page-header"><div><div class="eyebrow">Workspace controls</div><h1>Settings</h1><p>Shape the workspace around your team and decide how it keeps you informed.</p></div><div class="page-actions"><button class="primary-action" id="saveSettings">Save changes</button></div></div><div class="panel data-panel"><h2>Workspace preferences</h2><div class="setting-grid" style="margin-top:18px"><div class="setting"><label for="workspaceName">Workspace name</label><input class="setting-input" id="workspaceName" value="${escapeHtml(settings.name)}" /><small>Shown in your sidebar and workspace header.</small></div><div class="setting"><label for="modelName">Default model</label><input class="setting-input" id="modelName" value="${escapeHtml(settings.model)}" /><small>Used as the default model selection for new tasks.</small></div></div><div class="switch-row" style="margin-top:20px"><div><strong>Workspace notifications</strong><small style="display:block">Show completion and upload feedback in this browser.</small></div><label class="switch"><input id="notifications" type="checkbox" ${settings.notifications ? 'checked' : ''} /><span class="slider"></span></label></div></div><div class="panel data-panel"><h2>Connection</h2><div class="data-row"><div><strong>Backend API</strong><small>${apiBase}</small></div><span class="status"><span class="dot"></span> Connected</span></div></div></div>`;
    document.getElementById('saveSettings').addEventListener('click', () => { const next = { name:document.getElementById('workspaceName').value.trim() || 'Solar growth team', model:document.getElementById('modelName').value.trim() || 'openrouter/free', notifications:document.getElementById('notifications').checked }; saveSettings(next); document.querySelector('.workspace strong').textContent = next.name; toast('Settings saved'); });
  }

  function bindStudio() {
    const pending = localStorage.getItem('voltaik-pending-prompt');
    if (pending) { const prompt = document.getElementById('prompt'); if (prompt) prompt.value = pending; localStorage.removeItem('voltaik-pending-prompt'); }
    const selectedAgent = localStorage.getItem('voltaik-agent');
    const chip = document.querySelector('.agent-chip');
    if (selectedAgent && chip) { chip.innerHTML = `<i></i> ${escapeHtml(selectedAgent)} · ready`; localStorage.removeItem('voltaik-agent'); }
    const generateButton = document.getElementById('generateButton');
    const fileInput = document.getElementById('fileInput');
    const prompt = document.getElementById('prompt');
    const result = document.getElementById('result');
    const generate = async () => { if (!prompt.value.trim()) return toast('Add a prompt first.'); generateButton.disabled = true; generateButton.textContent = 'Working with your team...'; result.className = 'result'; result.innerHTML = '<div class="result-content">Thinking through the best next move...</div>'; try { const response = await fetch(`${apiBase}/generate`, { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify({ prompt:prompt.value.trim(), project_id:'demo-project' }) }); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Request failed'); result.innerHTML = `<div class="result-meta"><span>${escapeHtml(data.decision?.agent || 'AI team')}</span><span>${data.knowledge_used || 0} knowledge sources used</span></div><div class="result-content">${escapeHtml(data.output)}</div>`; const history = historyItems().filter(item => item.prompt !== prompt.value.trim()); history.unshift({ prompt:prompt.value.trim(), time:'Just now' }); localStorage.setItem(historyKey, JSON.stringify(history.slice(0,8))); } catch (error) { result.innerHTML = `<div class="result-content">Unable to reach the AI team: ${escapeHtml(error.message)}</div>`; } finally { generateButton.disabled = false; generateButton.textContent = 'Generate with team'; } };
    generateButton.addEventListener('click', generate);
    document.getElementById('clearButton')?.addEventListener('click', () => { prompt.value = ''; result.className = 'result empty'; result.innerHTML = '<div>Your team\'s response will appear here.</div>'; });
    document.getElementById('attachButton')?.addEventListener('click', () => fileInput.click());
    fileInput?.addEventListener('change', async event => { for (const file of event.target.files) { const body = new FormData(); body.append('file', file); const response = await fetch(`${apiBase}/knowledge/upload`, { method:'POST', body }); toast(response.ok ? `${file.name} added to workspace` : `Could not upload ${file.name}`); } });
    document.getElementById('addFileLink')?.addEventListener('click', () => fileInput.click());
    document.getElementById('clearHistory')?.addEventListener('click', () => { localStorage.removeItem(historyKey); document.getElementById('historyList').innerHTML = '<div class="empty-files">No conversations yet.</div>'; toast('Conversation history cleared'); });
  }

  function navigate(route) { window.location.hash = route; }
  function route() { const routeName = window.location.hash.replace('#','') || 'studio'; setActive(routeName); if (routeName === 'history') renderHistory(); else if (routeName === 'knowledge') renderKnowledge(); else if (routeName === 'team') renderTeam(); else if (routeName === 'settings') renderSettings(); else renderStudio(); }

  document.querySelectorAll('.nav a').forEach(link => link.addEventListener('click', event => { event.preventDefault(); navigate(link.getAttribute('href').slice(1)); }));
  document.querySelector('.workspace')?.addEventListener('click', () => toast('Workspace switcher is ready for multiple workspaces.'));
  document.querySelectorAll('.top-actions button').forEach(button => button.addEventListener('click', () => toast(button.title === 'Help' ? 'Ask your AI team anything from Studio.' : 'You are all caught up.')));
  window.addEventListener('hashchange', route);
  route();
})();
