// ------------------------------------------------------------------------------
// LOOKMEUP - Email Intelligence Tab (Part 1)
// ------------------------------------------------------------------------------

const lmuState = {
  email: '',
  isSearching: false,
  eventSource: null,
  reportData: {},
  history: JSON.parse(localStorage.getItem('lmu_history') || '[]'),
};

function lmuEscape(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const LMU_PLATFORM_ICONS = {
  'GitHub':'??','Twitter/X':'??','Instagram':'??','Reddit':'??',
  'Medium':'??','Dev.to':'?????','HackerNews':'??','LinkedIn':'??','default':'??',
};

function startEmailLookup() {
  const emailInput = document.getElementById('lmu-email-input');
  if (!emailInput) return;
  const email = emailInput.value.trim().toLowerCase();
  if (!email) { emailInput.focus(); return; }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { lmuShowToast('?? Please enter a valid email address'); emailInput.focus(); return; }
  if (lmuState.isSearching) return;
  lmuState.email = email;
  lmuState.reportData = { email };
  lmuResetUI();
  lmuRunInvestigation(email);
}

document.addEventListener('DOMContentLoaded', () => {
  const emailInput = document.getElementById('lmu-email-input');
  if (emailInput) emailInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') startEmailLookup(); });
  lmuRenderHistory();
});

function lmuResetUI() {
  if (lmuState.eventSource) { lmuState.eventSource.close(); lmuState.eventSource = null; }
  lmuState.isSearching = true;
  const progressWrap = document.getElementById('lmu-progress-wrap');
  if (progressWrap) progressWrap.style.display = 'block';
  lmuSetProgress(0);
  lmuSetStatus('Initialising investigation...');
  const mainGrid = document.getElementById('lmu-main-grid');
  if (mainGrid) mainGrid.style.display = 'none';
  ['lmu-identity-card','lmu-pattern-card','lmu-domain-card','lmu-breach-card',
   'lmu-rep-card','lmu-gravatar-card','lmu-github-card','lmu-social-card',
   'lmu-whois-card','lmu-usernames-card','lmu-web-card','lmu-reddit-card','lmu-export-bar'
  ].forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
  const badge = document.getElementById('lmu-score-badge');
  if (badge) badge.textContent = 'Score: \u2014';
  const identityCard = document.getElementById('lmu-identity-card');
  if (identityCard) identityCard.style.display = 'block';
  const nameEl = document.getElementById('lmu-identity-name'); if (nameEl) nameEl.textContent = 'Investigating...';
  const emailEl = document.getElementById('lmu-identity-email'); if (emailEl) emailEl.textContent = lmuState.email;
  const metaEl = document.getElementById('lmu-identity-meta'); if (metaEl) metaEl.textContent = '';
  const findingsEl = document.getElementById('lmu-key-findings'); if (findingsEl) findingsEl.innerHTML = '';
  const avatarEl = document.getElementById('lmu-identity-avatar'); if (avatarEl) avatarEl.innerHTML = '<div class="lmu-avatar-placeholder">?</div>';
  const btn = document.getElementById('lmu-search-btn'); if (btn) { btn.disabled = true; btn.innerHTML = '\u29f3 Scanning...'; }
}

function lmuRunInvestigation(email) {
  const url = (window.location.origin) + '/api/email-lookup?email=' + encodeURIComponent(email);
  const es = new EventSource(url);
  lmuState.eventSource = es;

  es.addEventListener('start', (e) => {
    const data = JSON.parse(e.data);
    lmuSetStatus(data.message);
    const mainGrid = document.getElementById('lmu-main-grid');
    if (mainGrid) mainGrid.style.display = 'grid';
    const identityCard = document.getElementById('lmu-identity-card');
    if (identityCard) identityCard.style.display = 'block';
  });

  es.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    lmuSetProgress(data.pct);
    lmuSetStatus(data.message);
  });

  es.addEventListener('pattern', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.pattern = data;
    lmuRenderPattern(data);
  });

  es.addEventListener('domain', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.domain = data;
    lmuRenderDomain(data);
  });

  es.addEventListener('gravatar', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.gravatar = data;
    lmuRenderGravatar(data);
    if (data.has_gravatar && data.avatar_url) {
      const avatarEl = document.getElementById('lmu-identity-avatar');
      if (avatarEl) avatarEl.innerHTML = '<img class="lmu-avatar-img" src="' + lmuEscape(data.avatar_url) + '" alt="Profile" onerror="this.parentNode.innerHTML=\'<div class=lmu-avatar-placeholder>?</div>\'" />';
    }
    if (data.display_name) { const nameEl = document.getElementById('lmu-identity-name'); if (nameEl) nameEl.textContent = data.display_name; }
  });

  es.addEventListener('reputation', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.reputation = data;
    lmuRenderReputation(data);
  });

  es.addEventListener('breaches', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.breaches = data;
    lmuRenderBreaches(data);
  });

  es.addEventListener('github', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.github = data;
    lmuRenderGitHub(data);
  });

  es.addEventListener('social', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.social = data;
    lmuRenderSocial(data);
  });

  es.addEventListener('web', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.web = data;
    lmuRenderWeb(data);
  });

  es.addEventListener('reddit', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.reddit = data;
    lmuRenderReddit(data);
  });

  es.addEventListener('whois', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.whois = data;
    lmuRenderWHOIS(data);
  });

  es.addEventListener('photos', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.photos = data;
  });

  es.addEventListener('usernames', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.usernames = data;
    lmuRenderUsernames(data);
  });

  es.addEventListener('summary', (e) => {
    const { data } = JSON.parse(e.data);
    lmuState.reportData.summary = data;
    lmuRenderSummary(data);
  });

  es.addEventListener('done', () => {
    es.close(); lmuState.eventSource = null; lmuState.isSearching = false;
    lmuSetProgress(100); lmuSetStatus('Investigation complete \u2713');
    const btn = document.getElementById('lmu-search-btn');
    if (btn) { btn.disabled = false; btn.innerHTML = '\uD83D\uDD0D Investigate'; }
    const exportBar = document.getElementById('lmu-export-bar');
    if (exportBar) {
      exportBar.style.display = 'flex';
      const exportInfo = document.getElementById('lmu-export-info');
      if (exportInfo) exportInfo.textContent = 'Investigation complete for ' + lmuState.email;
    }
    lmuSaveHistory(lmuState.email);
    const identityCard = document.getElementById('lmu-identity-card');
    if (identityCard) identityCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  es.addEventListener('error', (e) => {
    es.close(); lmuState.isSearching = false;
    let msg = 'Unknown error';
    try { msg = JSON.parse(e.data).message; } catch (_) {}
    lmuSetStatus('\u274C Error: ' + msg);
    const btn = document.getElementById('lmu-search-btn');
    if (btn) { btn.disabled = false; btn.innerHTML = '\uD83D\uDD0D Investigate'; }
  });

  es.onerror = () => {
    if (!lmuState.isSearching) return;
    es.close(); lmuState.isSearching = false;
    lmuSetStatus('Connection error. Please try again.');
    const btn = document.getElementById('lmu-search-btn');
    if (btn) { btn.disabled = false; btn.innerHTML = '\uD83D\uDD0D Investigate'; }
  };
}

// -- Render Functions ----------------------------------------------------------

function lmuRenderPattern(data) {
  const card = document.getElementById('lmu-pattern-card');
  const body = document.getElementById('lmu-pattern-body');
  const pill = document.getElementById('lmu-pattern-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (pill) { pill.textContent = 'Done'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  const fields = [
    { label: 'Local Part', value: data.local_part || '\u2014', mono: true },
    { label: 'Domain', value: data.domain || '\u2014', mono: true },
    { label: 'First Name', value: data.first_name || 'Not detected' },
    { label: 'Last Name', value: data.last_name || 'Not detected' },
    { label: 'Full Name', value: data.full_name || 'Not detected' },
    { label: 'TLD', value: data.tld || '\u2014', mono: true },
    { label: 'Generic Address', value: data.is_generic ? '\u26a0\ufe0f Yes (role-based)' : '\u2713 No (personal)' },
    { label: 'Name Parts', value: (data.name_parts || []).join(', ') || '\u2014', mono: true },
  ];
  body.innerHTML = fields.map(f => '<div class="lmu-field"><div class="lmu-field-label">' + f.label + '</div><div class="lmu-field-value ' + (f.mono ? 'mono' : '') + '">' + lmuEscape(f.value) + '</div></div>').join('');
  const ie = document.getElementById('lmu-identity-email'); if (ie) ie.textContent = data.email || lmuState.email;
  if (data.full_name) { const n = document.getElementById('lmu-identity-name'); if (n && n.textContent === 'Investigating...') n.textContent = data.full_name; }
}

function lmuRenderDomain(data) {
  const card = document.getElementById('lmu-domain-card');
  const body = document.getElementById('lmu-domain-body');
  const pill = document.getElementById('lmu-domain-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (pill) { pill.textContent = data.provider || 'Done'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  const icons = { gmail:'\uD83D\uDD34',microsoft:'\uD83D\uDD35',yahoo:'\uD83D\uDFE3',zoho:'\uD83D\uDFE1',protonmail:'\uD83D\uDFE4',apple:'\u26AA',fastmail:'\uD83D\uDFE2',disposable:'\uD83D\uDDD1\uFE0F',amazon:'\uD83D\uDFE0',mimecast:'\uD83D\uDEE1\uFE0F' };
  const pIcon = icons[data.provider_icon] || '\uD83D\uDCE7';
  const badges = [];
  if (data.is_corporate) badges.push('<span class="lmu-badge positive">\uD83C\uDFE2 Corporate Domain</span>');
  if (data.is_disposable) badges.push('<span class="lmu-badge danger">\uD83D\uDDD1\uFE0F Disposable</span>');
  if (!data.is_corporate && !data.is_disposable) badges.push('<span class="lmu-badge">\uD83D\uDC64 Personal / Free Provider</span>');
  const mxRows = (data.mx_records || []).map(mx => '<tr><td>' + lmuEscape(String(mx.priority)) + '</td><td>' + lmuEscape(mx.host) + '</td></tr>').join('');
  body.innerHTML = '<div class="lmu-provider-row"><div class="lmu-provider-logo">' + pIcon + '</div><div><div class="lmu-provider-name">' + lmuEscape(data.provider || 'Unknown') + '</div><div class="lmu-provider-sub">' + lmuEscape(data.domain || '') + '</div></div></div><div class="lmu-badge-row">' + badges.join('') + '</div>' + (mxRows ? '<table class="lmu-mx-table" style="margin-top:14px"><thead><tr><th>Priority</th><th>MX Host</th></tr></thead><tbody>' + mxRows + '</tbody></table>' : '');
  const meta = document.getElementById('lmu-identity-meta'); if (meta) meta.textContent = 'Provider: ' + (data.provider || 'Unknown') + ' \u00b7 Domain: ' + (data.domain || '');
}

function lmuRenderGravatar(data) {
  const card = document.getElementById('lmu-gravatar-card');
  const body = document.getElementById('lmu-gravatar-body');
  const pill = document.getElementById('lmu-gravatar-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!data.has_gravatar) {
    if (pill) { pill.textContent = 'Not Found'; pill.className = 'lmu-status-pill lmu-pill-muted'; }
    body.innerHTML = '<div class="lmu-empty">\u2B1C No Gravatar profile associated with this email.</div>';
    return;
  }
  if (pill) { pill.textContent = 'Found'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  const accountLinks = (data.accounts || []).map(a => '<a class="lmu-gravatar-account" href="' + lmuEscape(a.url || '#') + '" target="_blank" rel="noopener">' + lmuEscape(a.shortname || a.url) + '</a>').join('');
  const urlLinks = (data.urls || []).map(u => '<a class="lmu-gravatar-account" href="' + lmuEscape(u.value || '#') + '" target="_blank" rel="noopener">' + lmuEscape(u.title || u.value) + '</a>').join('');
  body.innerHTML = '<div class="lmu-gravatar-row">' + (data.avatar_url ? '<img class="lmu-gravatar-avatar" src="' + lmuEscape(data.avatar_url) + '" alt="Gravatar" onerror="this.style.display=\'none\'" />' : '') + '<div><div class="lmu-gravatar-name">' + lmuEscape(data.display_name || 'Gravatar Profile') + '</div>' + (data.profile_url ? '<a href="' + lmuEscape(data.profile_url) + '" target="_blank" rel="noopener" style="font-family:var(--font-mono);font-size:0.78rem;color:var(--cyan)">View Gravatar Profile \u2197</a>' : '') + (data.bio ? '<div class="lmu-gravatar-bio">' + lmuEscape(data.bio) + '</div>' : '') + '</div></div>' + ((accountLinks || urlLinks) ? '<div class="lmu-gravatar-accounts" style="margin-top:12px">' + accountLinks + urlLinks + '</div>' : '');
}

function lmuRenderReputation(data) {
  const card = document.getElementById('lmu-rep-card');
  const body = document.getElementById('lmu-rep-body');
  const pill = document.getElementById('lmu-rep-status');
  if (!card || !body) return;
  card.style.display = 'block';
  const rep = data.reputation || 'unknown';
  const isSusp = data.suspicious;
  const repClass = isSusp ? 'suspicious' : rep;
  const repEmoji = isSusp ? '\u26a0\ufe0f' : (rep === 'high' ? '\u2705' : rep === 'medium' ? '\uD83D\uDD36' : '\u2753');
  const repLabel = isSusp ? 'Suspicious' : (rep === 'high' ? 'High Reputation' : rep === 'medium' ? 'Moderate Reputation' : 'Reputation: ' + rep);
  if (pill) { pill.textContent = repLabel; pill.className = 'lmu-status-pill ' + (isSusp ? 'lmu-pill-red' : rep === 'high' ? 'lmu-pill-green' : 'lmu-pill-amber'); }
  const d = data.details || {};
  const items = [
    {l:'Blacklisted',v:d.blacklisted,danger:true},{l:'Data Breach',v:d.data_breach,danger:true},
    {l:'Credentials Leaked',v:d.credentials_leaked,danger:true},{l:'Spam',v:d.spam,danger:true},
    {l:'Deliverable',v:d.deliverable,danger:false},{l:'Free Provider',v:d.free_provider,danger:false},
    {l:'Disposable',v:d.disposable,danger:true},{l:'Spoofable',v:d.spoofable,danger:true},
  ];
  body.innerHTML = '<div class="lmu-rep-row ' + repClass + '"><span class="lmu-rep-icon">' + repEmoji + '</span><div><div class="lmu-rep-label">' + repLabel + '</div><div class="lmu-rep-sub">References: ' + (data.references || 0) + '</div></div></div>' + (Object.keys(d).length > 0 ? '<div class="lmu-rep-details-grid">' + items.map(item => '<div class="lmu-rep-detail" style="color:' + (item.v && item.danger ? '#ef4444' : item.v ? '#10b981' : 'var(--text-muted)') + '"><span class="lmu-rep-indicator ' + (item.v ? (item.danger ? 'red' : 'green') : 'grey') + '"></span>' + lmuEscape(item.l) + ': ' + (item.v ? 'Yes' : 'No') + '</div>').join('') + '</div>' : '') + (d.first_seen ? '<div style="font-size:0.75rem;color:var(--text-muted);font-family:var(--font-mono);margin-top:10px">First seen: ' + lmuEscape(d.first_seen) + ' \u00b7 Last seen: ' + lmuEscape(d.last_seen || '\u2014') + '</div>' : '');
}

function lmuRenderBreaches(data) {
  const card = document.getElementById('lmu-breach-card');
  const body = document.getElementById('lmu-breach-body');
  const pill = document.getElementById('lmu-breach-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!data.breached) {
    if (pill) { pill.textContent = 'Clean'; pill.className = 'lmu-status-pill lmu-pill-green'; }
    body.innerHTML = '<div class="lmu-no-breach"><span style="font-size:1.5rem">\u2705</span><div><div style="font-weight:600">No breaches found</div><div style="font-size:0.78rem;opacity:0.7">' + lmuEscape(data.note || 'Not found in any known breach database.') + '</div></div></div>';
    return;
  }
  if (pill) { pill.textContent = data.breach_count + ' Breach' + (data.breach_count > 1 ? 'es' : ''); pill.className = 'lmu-status-pill lmu-pill-red'; }
  body.innerHTML = '<div style="margin-bottom:12px;padding:10px 14px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);border-radius:8px;color:#ef4444;font-weight:600;">\u26a0\ufe0f Found in ' + data.breach_count + ' known data breach' + (data.breach_count > 1 ? 'es' : '') + '</div>' + (data.breaches || []).map(b => '<div class="lmu-breach-found"><div class="lmu-breach-title">\uD83D\uDD13 ' + lmuEscape(b.title || b.name || 'Unknown Breach') + '</div><div class="lmu-breach-meta">' + (b.domain ? lmuEscape(b.domain) + ' \u00b7 ' : '') + (b.date ? 'Breached: ' + lmuEscape(b.date) + ' \u00b7 ' : '') + (b.pwn_count ? Number(b.pwn_count).toLocaleString() + ' accounts' : '') + '</div>' + (b.data_classes && b.data_classes.length > 0 ? '<div class="lmu-data-classes">' + b.data_classes.map(dc => '<span class="lmu-data-class">' + lmuEscape(dc) + '</span>').join('') + '</div>' : '') + '</div>').join('');
  lmuAddFindingTag('\u26a0\ufe0f ' + data.breach_count + ' breach(es)', 'breach');
}

function lmuRenderGitHub(data) {
  const card = document.getElementById('lmu-github-card');
  const body = document.getElementById('lmu-github-body');
  const pill = document.getElementById('lmu-github-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!data.found) {
    if (pill) { pill.textContent = 'Not Found'; pill.className = 'lmu-status-pill lmu-pill-muted'; }
    body.innerHTML = '<div class="lmu-empty">\uD83D\uDC19 No GitHub account found linked to this email.</div>';
    return;
  }
  if (pill) { pill.textContent = '@' + data.username; pill.className = 'lmu-status-pill lmu-pill-violet'; }
  body.innerHTML = '<div class="lmu-github-profile">' + (data.avatar_url ? '<img class="lmu-github-avatar" src="' + lmuEscape(data.avatar_url) + '" alt="GitHub" onerror="this.style.display=\'none\'" />' : '') + '<div style="flex:1"><div class="lmu-github-name">' + lmuEscape(data.name || data.username) + '</div><a href="' + lmuEscape(data.profile_url) + '" target="_blank" rel="noopener" class="lmu-github-handle">@' + lmuEscape(data.username) + ' \u2197</a>' + (data.bio ? '<div style="font-size:0.82rem;color:var(--text-secondary);margin-top:6px">' + lmuEscape(data.bio) + '</div>' : '') + '<div class="lmu-github-stats"><div class="lmu-github-stat"><div class="lmu-github-stat-val">' + (data.public_repos || 0) + '</div><div class="lmu-github-stat-lbl">Repos</div></div><div class="lmu-github-stat"><div class="lmu-github-stat-val">' + (data.followers || 0) + '</div><div class="lmu-github-stat-lbl">Followers</div></div></div><div class="lmu-badge-row" style="margin-top:10px">' + (data.location ? '<span class="lmu-badge">\uD83D\uDCCD ' + lmuEscape(data.location) + '</span>' : '') + (data.company ? '<span class="lmu-badge">\uD83C\uDFE2 ' + lmuEscape(data.company) + '</span>' : '') + (data.created_at ? '<span class="lmu-badge">\uD83D\uDCC5 Joined ' + lmuEscape(data.created_at) + '</span>' : '') + (data.blog ? '<a href="' + lmuEscape(data.blog) + '" target="_blank" rel="noopener" class="lmu-badge positive">\uD83C\uDF10 Website \u2197</a>' : '') + '</div></div></div>';
  lmuAddFindingTag('GitHub: @' + data.username, 'positive');
}

function lmuRenderSocial(accounts) {
  const card = document.getElementById('lmu-social-card');
  const body = document.getElementById('lmu-social-body');
  const pill = document.getElementById('lmu-social-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!accounts || accounts.length === 0) {
    if (pill) { pill.textContent = 'None Found'; pill.className = 'lmu-status-pill lmu-pill-muted'; }
    body.innerHTML = '<div class="lmu-empty">\uD83D\uDCF1 No correlated social accounts found via username patterns.</div>';
    return;
  }
  if (pill) { pill.textContent = accounts.length + ' Found'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  body.innerHTML = accounts.map(acc => '<a class="lmu-social-item" href="' + lmuEscape(acc.url) + '" target="_blank" rel="noopener"><span class="lmu-social-icon">' + (LMU_PLATFORM_ICONS[acc.platform] || LMU_PLATFORM_ICONS.default) + '</span><div><div class="lmu-social-platform">' + lmuEscape(acc.platform) + '</div><div class="lmu-social-username">@' + lmuEscape(acc.username) + '</div></div><span class="lmu-social-arrow">\u2197</span></a>').join('');
  lmuAddFindingTag(accounts.length + ' social account(s)', 'positive');
}

function lmuRenderWHOIS(data) {
  const card = document.getElementById('lmu-whois-card');
  const body = document.getElementById('lmu-whois-body');
  const pill = document.getElementById('lmu-whois-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (pill) { pill.textContent = 'Done'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  if (!data.registrar && !data.created && !data.expires) { body.innerHTML = '<div class="lmu-empty">\u2139\ufe0f WHOIS data not available for this domain.</div>'; return; }
  const fields = [
    {l:'Registrar',v:data.registrar||'\u2014'},{l:'Domain Created',v:data.created||'\u2014',mono:true},
    {l:'Domain Expires',v:data.expires||'\u2014',mono:true},{l:'Last Updated',v:data.updated||'\u2014',mono:true},
    {l:'Organisation',v:data.org||'\u2014'},{l:'Country',v:data.country||'\u2014'},
  ];
  body.innerHTML = '<div class="lmu-grid-2">' + fields.map(f => '<div class="lmu-field"><div class="lmu-field-label">' + f.l + '</div><div class="lmu-field-value ' + (f.mono ? 'mono' : '') + '">' + lmuEscape(f.v) + '</div></div>').join('') + '</div>' + (data.name_servers && data.name_servers.length > 0 ? '<div style="margin-top:12px"><div class="lmu-field-label" style="margin-bottom:6px">Name Servers</div><div class="lmu-badge-row">' + data.name_servers.map(ns => '<span class="lmu-badge">' + lmuEscape(ns) + '</span>').join('') + '</div></div>' : '');
}

function lmuRenderUsernames(usernames) {
  const card = document.getElementById('lmu-usernames-card');
  const body = document.getElementById('lmu-usernames-body');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!usernames || usernames.length === 0) { body.innerHTML = '<div class="lmu-empty">No username candidates generated.</div>'; return; }
  body.innerHTML = '<div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:12px">Possible usernames derived from email pattern \u2014 click to search on Google:</div><div class="lmu-username-chips">' + usernames.map(u => '<span class="lmu-username-chip" onclick="window.open(\'https://www.google.com/search?q=%22' + encodeURIComponent(u) + '%22\',\'_blank\')" title="Search: ' + lmuEscape(u) + '">' + lmuEscape(u) + '</span>').join('') + '</div>';
}

function lmuRenderWeb(results) {
  const card = document.getElementById('lmu-web-card');
  const body = document.getElementById('lmu-web-body');
  const pill = document.getElementById('lmu-web-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!results || results.length === 0) {
    if (pill) { pill.textContent = 'No Results'; pill.className = 'lmu-status-pill lmu-pill-muted'; }
    body.innerHTML = '<div class="lmu-empty" style="grid-column:1/-1">\uD83C\uDF10 No web references found.</div>';
    return;
  }
  if (pill) { pill.textContent = results.length + ' Results'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  body.innerHTML = results.map(r => '<a class="lmu-web-result" href="' + lmuEscape(r.url) + '" target="_blank" rel="noopener"><div class="lmu-web-result-title">' + lmuEscape(r.title || 'Web Result') + '</div><div class="lmu-web-result-domain">' + lmuEscape(r.domain || '') + '</div>' + (r.snippet ? '<div class="lmu-web-result-snippet">' + lmuEscape(r.snippet) + '</div>' : '') + '</a>').join('');
}

function lmuRenderReddit(mentions) {
  const card = document.getElementById('lmu-reddit-card');
  const body = document.getElementById('lmu-reddit-body');
  const pill = document.getElementById('lmu-reddit-status');
  if (!card || !body) return;
  card.style.display = 'block';
  if (!mentions || mentions.length === 0) {
    if (pill) { pill.textContent = 'No Mentions'; pill.className = 'lmu-status-pill lmu-pill-muted'; }
    body.innerHTML = '<div class="lmu-empty">\uD83D\uDD34 No Reddit mentions found.</div>';
    return;
  }
  if (pill) { pill.textContent = mentions.length + ' Found'; pill.className = 'lmu-status-pill lmu-pill-green'; }
  body.innerHTML = mentions.map(m => '<div class="lmu-reddit-item"><div class="lmu-reddit-title"><a href="' + lmuEscape(m.url) + '" target="_blank" rel="noopener" style="color:var(--text-primary);text-decoration:none">' + lmuEscape(m.title) + '</a></div><div class="lmu-reddit-meta">' + lmuEscape(m.subreddit || '') + ' \u00b7 Score: ' + (m.score || 0) + '</div>' + (m.snippet ? '<div class="lmu-reddit-snippet">' + lmuEscape(m.snippet) + '</div>' : '') + '</div>').join('');
}

function lmuRenderSummary(data) {
  const badge = document.getElementById('lmu-score-badge');
  if (badge) {
    badge.textContent = 'Score: ' + data.score + '/100 \u00b7 ' + data.grade;
    badge.style.background = data.score >= 50 ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)';
    badge.style.borderColor = data.score >= 50 ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)';
    badge.style.color = data.score >= 50 ? '#10b981' : '#f59e0b';
  }
  const scoreRow = document.getElementById('lmu-score-row');
  const scoreFill = document.getElementById('lmu-score-fill');
  const scoreLabel = document.getElementById('lmu-score-label');
  if (scoreRow && scoreFill && scoreLabel) {
    scoreRow.style.display = 'flex';
    setTimeout(() => { scoreFill.style.width = data.score + '%'; }, 100);
    scoreLabel.textContent = data.score + ' / 100 \u2014 ' + data.label;
  }
  const nameEl = document.getElementById('lmu-identity-name');
  if (nameEl && nameEl.textContent === 'Investigating...') nameEl.textContent = lmuState.email.split('@')[0] || lmuState.email;
  (data.key_findings || []).forEach(f => lmuAddFindingTag(f, f.includes('breach') ? 'breach' : 'positive'));
}

function lmuAddFindingTag(text, type) {
  const container = document.getElementById('lmu-key-findings');
  if (!container) return;
  const existing = Array.from(container.querySelectorAll('.lmu-finding-tag')).map(el => el.textContent.trim());
  if (existing.includes(text)) return;
  const tag = document.createElement('span');
  tag.className = 'lmu-finding-tag ' + (type || '');
  tag.textContent = text;
  container.appendChild(tag);
}

function lmuSetProgress(pct) { const fill = document.getElementById('lmu-progress-fill'); if (fill) fill.style.width = pct + '%'; }
function lmuSetStatus(msg) { const el = document.getElementById('lmu-progress-status'); if (el) el.textContent = msg; }

function lmuSaveHistory(email) {
  lmuState.history = lmuState.history.filter(h => h.email !== email);
  lmuState.history.unshift({ email, ts: Date.now() });
  if (lmuState.history.length > 15) lmuState.history.pop();
  localStorage.setItem('lmu_history', JSON.stringify(lmuState.history));
  lmuRenderHistory();
}

function lmuRenderHistory() {
  const listEl = document.getElementById('lmu-history-list');
  if (!listEl) return;
  if (!lmuState.history.length) { listEl.innerHTML = '<div class="lmu-history-empty">No investigations yet.</div>'; return; }
  listEl.innerHTML = lmuState.history.map((h, i) => '<div class="lmu-history-item"><span class="lmu-history-email" onclick="lmuLoadHistory(\'' + lmuEscape(h.email) + '\')" title="Re-investigate">' + lmuEscape(h.email) + '</span><span class="lmu-history-time">' + lmuTimeAgo(h.ts) + '</span><button class="lmu-history-delete" onclick="lmuDeleteHistory(' + i + ')" title="Remove">\u2715</button></div>').join('');
}

function lmuLoadHistory(email) { const ei = document.getElementById('lmu-email-input'); if (ei) { ei.value = email; startEmailLookup(); } }
function lmuDeleteHistory(i) { lmuState.history.splice(i, 1); localStorage.setItem('lmu_history', JSON.stringify(lmuState.history)); lmuRenderHistory(); }
function lmuTimeAgo(ts) { const diff = Date.now() - ts; const mins = Math.floor(diff/60000); if (mins < 1) return 'just now'; if (mins < 60) return mins + 'm ago'; const hrs = Math.floor(mins/60); if (hrs < 24) return hrs + 'h ago'; return Math.floor(hrs/24) + 'd ago'; }

function exportEmailReport() {
  const data = { tool: 'TruSINT LookMeUp', timestamp: new Date().toISOString(), email: lmuState.email, ...lmuState.reportData };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lookmeup_' + lmuState.email.replace(/[@.]/g, '_') + '_' + Date.now() + '.json';
  a.click();
}

function printEmailReport() { window.print(); }

function lmuShowToast(message) {
  let toast = document.getElementById('lmu-toast');
  if (!toast) { toast = document.createElement('div'); toast.id = 'lmu-toast'; toast.className = 'copy-toast'; document.body.appendChild(toast); }
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('show'), 2800);
}
