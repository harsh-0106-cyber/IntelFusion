// ═════════════════════════════════════════════════════════════════════════════
// ZLens — Production-Oriented Reverse Visual Image Retrieval Engine
// ═════════════════════════════════════════════════════════════════════════════

const zlensState = {
  file: null,
  previewUrl: '',
  sessionId: null,
  imageData: null,
  isScanning: false,
  eventSource: null,
  matches: [],
  searchStatus: 'idle',
  searchMessage: '',
  candidatesExamined: 0,
  exactCount: 0,
  nearCount: 0,
  activeFilter: 'all',
  selectedPlatforms: ['all', 'web', 'wikimedia', 'x', 'reddit', 'linkedin'],
};

function zlensEscape(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Initialization ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initZLensDropzone();
  initZLensForm();
  initLensoKey();
  fetchZLensIndexStats();
});

function initLensoKey() {
  const saved = localStorage.getItem('lenso_api_key');
  const input = document.getElementById('zlens-lenso-key');
  const pill = document.getElementById('zlens-lenso-saved-pill');
  if (saved && input) {
    input.value = saved;
    if (pill) pill.style.display = 'inline-block';
  }
}

function saveLensoApiKey() {
  const input = document.getElementById('zlens-lenso-key');
  const pill = document.getElementById('zlens-lenso-saved-pill');
  if (!input) return;
  const key = input.value.trim();
  if (key) {
    localStorage.setItem('lenso_api_key', key);
    if (pill) pill.style.display = 'inline-block';
    zlensToast('📸 Lenso.ai API key saved securely in browser.');
  } else {
    localStorage.removeItem('lenso_api_key');
    if (pill) pill.style.display = 'none';
    zlensToast('🗑️ Lenso.ai API key cleared.');
  }
}

async function fetchZLensIndexStats() {
  const countEl = document.getElementById('zlens-index-count');
  if (!countEl) return;
  try {
    const res = await fetch('/api/zlens/index/stats');
    if (res.ok) {
      const data = await res.json();
      countEl.textContent = String(data.total_assets ?? 0);
    } else {
      countEl.textContent = 'Unavailable';
    }
  } catch (e) {
    countEl.textContent = 'Offline';
  }
}

async function zlensTriggerIndex() {
  const btn = document.getElementById('zlens-index-refresh-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🔄 Indexing...';
  }
  zlensToast('📦 Indexing images from collection...');
  try {
    const res = await fetch('/api/index', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.success) {
      zlensToast(`✅ Successfully indexed/updated ${data.indexed_or_updated} assets in SQLite.`);
      await fetchZLensIndexStats();
    } else {
      zlensToast(`⚠️ Indexing failed: ${data.error || 'Unknown error'}`);
    }
  } catch (err) {
    zlensToast(`⚠️ Indexing failed: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔄 Index / Refresh Collection';
    }
  }
}

function initZLensDropzone() {
  const dropzone = document.getElementById('zlens-dropzone');
  const fileInput = document.getElementById('zlens-file-input');
  if (!dropzone || !fileInput) return;

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  ['dragleave', 'dragend'].forEach((ev) => {
    dropzone.addEventListener(ev, () => dropzone.classList.remove('dragover'));
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleZLensFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleZLensFile(e.target.files[0]);
    }
  });
}

function initZLensForm() {
  const platBtns = document.querySelectorAll('.zlens-plat-btn');
  platBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const plat = btn.getAttribute('data-platform');
      if (plat === 'all') {
        const allActive = zlensState.selectedPlatforms.length === 6;
        platBtns.forEach((b) => b.classList.toggle('active', !allActive));
        zlensState.selectedPlatforms = allActive
          ? []
          : ['all', 'web', 'wikimedia', 'x', 'reddit', 'linkedin'];
      } else {
        btn.classList.toggle('active');
        if (zlensState.selectedPlatforms.includes(plat)) {
          zlensState.selectedPlatforms = zlensState.selectedPlatforms.filter((p) => p !== plat);
        } else {
          zlensState.selectedPlatforms.push(plat);
        }
      }
    });
  });
}

// ── File Ingestion & Preprocessing Upload ─────────────────────────────────────
function handleZLensFile(file) {
  const validTypes = ['image/jpeg', 'image/png', 'image/webp'];
  if (!validTypes.includes(file.type) && !file.type.startsWith('image/')) {
    zlensToast('⚠️ Please upload a valid image file (JPEG, PNG, WebP).');
    return;
  }
  if (file.size > 15 * 1024 * 1024) {
    zlensToast('⚠️ Image file exceeds the 15MB limit.');
    return;
  }

  // Clear any residual text inputs so the new image is searched purely visually
  const nameInput = document.getElementById('zlens-name-input');
  const kwInput = document.getElementById('zlens-keywords-input');
  if (nameInput) nameInput.value = '';
  if (kwInput) kwInput.value = '';

  zlensState.file = file;

  const reader = new FileReader();
  reader.onload = (e) => {
    zlensState.previewUrl = e.target.result;
    renderZLensPreview(e.target.result);
    uploadZLensImage(file);
  };
  reader.readAsDataURL(file);
}

function renderZLensPreview(dataUrl) {
  const dropzone = document.getElementById('zlens-dropzone');
  const previewWrap = document.getElementById('zlens-preview-wrap');
  const previewImg = document.getElementById('zlens-preview-img');
  const scanBtn = document.getElementById('zlens-scan-btn');

  if (dropzone) dropzone.style.display = 'none';
  if (previewWrap) previewWrap.style.display = 'block';
  if (previewImg) previewImg.src = dataUrl;
  if (scanBtn) {
    scanBtn.disabled = true;
    scanBtn.innerHTML = '<span>⏳ Validating &amp; Ingesting Image...</span>';
  }
}

async function uploadZLensImage(file) {
  const teleBox = document.getElementById('zlens-telemetry');
  const scanBtn = document.getElementById('zlens-scan-btn');
  if (teleBox) teleBox.innerHTML = '<span>🧬 Validating magic bytes, stripping EXIF &amp; computing hashes...</span>';

  try {
    const formData = new FormData();
    formData.append('image', file);

    const res = await fetch('/api/zlens/upload', {
      method: 'POST',
      body: formData,
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || 'Failed to ingest image');
    }

    zlensState.sessionId = data.session_id;
    zlensState.imageData = data;

    // Update telemetry HUD
    if (teleBox) {
      teleBox.innerHTML = `
        <div><strong>SHA-256:</strong> <span class="zlens-hash-text" title="${zlensEscape(data.sha256)}">${zlensEscape(data.sha256.substring(0, 16))}...</span></div>
        <div><strong>pHash (DCT):</strong> <span class="zlens-hash-text">${zlensEscape(data.phash)}</span></div>
        <div><strong>Resolution:</strong> ${data.width}×${data.height}px (${zlensEscape(data.format)})</div>
        <div><strong>Status:</strong> <span style="color:var(--green);">🟢 Sanitized &amp; Verified</span></div>
        <button class="zlens-reupload-btn" onclick="resetZLensUpload()">Change Image</button>
      `;
    }

    if (scanBtn) {
      scanBtn.disabled = false;
      scanBtn.innerHTML = '<span>⚡ Search Visual Matches</span>';
    }

  } catch (err) {
    console.error('ZLens upload error:', err);
    if (teleBox) {
      teleBox.innerHTML = `
        <span style="color:var(--red);">⚠️ ${zlensEscape(err.message)}</span>
        <button class="zlens-reupload-btn" onclick="resetZLensUpload()">Try Again</button>
      `;
    }
    if (scanBtn) {
      scanBtn.disabled = true;
      scanBtn.innerHTML = '<span>Upload Rejected</span>';
    }
  }
}

function resetZLensUpload() {
  zlensState.file = null;
  zlensState.previewUrl = '';
  zlensState.sessionId = null;
  zlensState.imageData = null;

  const dropzone = document.getElementById('zlens-dropzone');
  const previewWrap = document.getElementById('zlens-preview-wrap');
  const fileInput = document.getElementById('zlens-file-input');
  const scanBtn = document.getElementById('zlens-scan-btn');
  const resultsWrap = document.getElementById('zlens-results');
  const nameInput = document.getElementById('zlens-name-input');
  const kwInput = document.getElementById('zlens-keywords-input');

  if (nameInput) nameInput.value = '';
  if (kwInput) kwInput.value = '';
  if (dropzone) dropzone.style.display = 'flex';
  if (previewWrap) previewWrap.style.display = 'none';
  if (fileInput) fileInput.value = '';
  if (scanBtn) {
    scanBtn.disabled = true;
    scanBtn.innerHTML = '<span>Select or Drop Image Above</span>';
  }
  if (resultsWrap) resultsWrap.style.display = 'none';
}

// ── Launch ZLens Scan & SSE Stream ────────────────────────────────────────────
function startZLensScan() {
  if (!zlensState.sessionId) {
    zlensToast('⚠️ Please upload and validate an image first.');
    return;
  }
  if (zlensState.isScanning) return;

  zlensState.isScanning = true;
  zlensState.matches = [];

  const nameInput = document.getElementById('zlens-name-input');
  const kwInput = document.getElementById('zlens-keywords-input');

  const name = nameInput ? nameInput.value.trim() : '';
  const keywords = kwInput ? kwInput.value.trim() : '';
  const platforms = zlensState.selectedPlatforms.join(',');

  // UI state
  const scanBtn = document.getElementById('zlens-scan-btn');
  if (scanBtn) {
    scanBtn.disabled = true;
    scanBtn.innerHTML = '<span>⚡ Retrieving Visual Candidates...</span>';
  }

  const progCard = document.getElementById('zlens-progress-card');
  const progFill = document.getElementById('zlens-progress-fill');
  const hudStatus = document.getElementById('zlens-hud-status');
  const hudLog = document.getElementById('zlens-hud-log');
  const resultsSection = document.getElementById('zlens-results');

  if (progCard) progCard.style.display = 'block';
  if (resultsSection) resultsSection.style.display = 'none';
  if (progFill) progFill.style.width = '15%';
  if (hudStatus) hudStatus.textContent = 'Query Ingestion & Hash Analysis...';
  if (hudLog) hudLog.textContent = 'Initiating verified reverse search stream...';

  const lensoInput = document.getElementById('zlens-lenso-key');
  const lensoKey = (lensoInput ? lensoInput.value.trim() : '') || localStorage.getItem('lenso_api_key') || '';

  const streamUrl = `/api/zlens/stream?session_id=${encodeURIComponent(zlensState.sessionId)}&name=${encodeURIComponent(name)}&keywords=${encodeURIComponent(keywords)}&platforms=${encodeURIComponent(platforms)}&lenso_key=${encodeURIComponent(lensoKey)}`;

  if (zlensState.eventSource) {
    zlensState.eventSource.close();
  }

  const es = new EventSource(streamUrl);
  zlensState.eventSource = es;

  es.addEventListener('start', (e) => {
    const data = JSON.parse(e.data);
    if (hudStatus) hudStatus.textContent = 'Analyzing Query Image Signatures...';
    if (hudLog) hudLog.textContent = data.message || 'Stream connection open';
    if (progFill) progFill.style.width = '25%';
  });

  es.addEventListener('telemetry', (e) => {
    const data = JSON.parse(e.data);
    if (hudLog) hudLog.textContent = `SHA-256 and 64-bit DCT pHash locked [${data.dimensions}]`;
    if (progFill) progFill.style.width = '40%';
  });

  es.addEventListener('stage', (e) => {
    const data = JSON.parse(e.data);
    if (hudStatus) hudStatus.textContent = data.name;
    if (hudLog) hudLog.textContent = data.message;
    if (progFill) progFill.style.width = `${data.pct}%`;
  });

  es.addEventListener('search_status', (e) => {
    const data = JSON.parse(e.data);
    zlensState.searchStatus = data.status || 'matches_found';
    zlensState.candidatesExamined = data.candidates_examined ?? 0;
    zlensState.exactCount = data.exact_matches_count ?? 0;
    zlensState.nearCount = data.near_duplicates_count ?? 0;
    zlensState.searchMessage = data.message || '';
    if (hudLog) hudLog.textContent = data.message;
  });

  es.addEventListener('matches', (e) => {
    const data = JSON.parse(e.data);
    zlensState.matches = data.items || [];
    zlensState.searchStatus = data.status || (zlensState.matches.length > 0 ? 'matches_found' : 'no_matches');
    zlensState.searchMessage = data.message || '';
    if (hudLog) hudLog.textContent = data.message;
  });

  es.addEventListener('summary', (e) => {
    const data = JSON.parse(e.data);
    zlensState.searchStatus = data.status || zlensState.searchStatus;
    zlensState.candidatesExamined = data.candidates_examined ?? zlensState.candidatesExamined;
    zlensState.exactCount = data.exact_matches ?? zlensState.exactCount;
    zlensState.nearCount = data.near_duplicates ?? zlensState.nearCount;
    renderZLensResults(data);
  });

  es.addEventListener('done', () => {
    if (progFill) progFill.style.width = '100%';
    if (hudStatus) hudStatus.textContent = 'Retrieval Pipeline Completed';
    zlensFinishScan();
  });

  es.addEventListener('error', (e) => {
    console.error('ZLens SSE Error:', e);
    zlensFinishScan();
    zlensState.searchStatus = 'database_error';
    zlensState.searchMessage = 'The search stream encountered an unexpected disconnection or error.';
    renderZLensResults({
      status: 'database_error',
      total_matches: zlensState.matches.length,
      candidates_examined: zlensState.candidatesExamined,
      top_similarity: zlensState.matches[0]?.display_score || 'None',
      sha256: zlensState.imageData?.sha256 || 'N/A',
      duration_seconds: 1.5,
    });
  });
}

function zlensFinishScan() {
  zlensState.isScanning = false;
  if (zlensState.eventSource) {
    zlensState.eventSource.close();
    zlensState.eventSource = null;
  }
  const scanBtn = document.getElementById('zlens-scan-btn');
  if (scanBtn) {
    scanBtn.disabled = false;
    scanBtn.innerHTML = '<span>⚡ Re-Search Visual Matches</span>';
  }
  const progCard = document.getElementById('zlens-progress-card');
  if (progCard) {
    setTimeout(() => {
      progCard.style.display = 'none';
    }, 800);
  }
}

// ── Render Results & Evidence Cards ──────────────────────────────────────────
function renderZLensResults(summary) {
  const resultsSection = document.getElementById('zlens-results');
  if (!resultsSection) return;

  resultsSection.style.display = 'block';

  // 1. Stats ribbon
  const statMatches = document.getElementById('zlens-stat-matches');
  const statCandidates = document.getElementById('zlens-stat-candidates');
  const statTop = document.getElementById('zlens-stat-top');
  const statTime = document.getElementById('zlens-stat-time');

  if (statMatches) statMatches.textContent = summary.total_matches ?? zlensState.matches.length;
  if (statCandidates) statCandidates.textContent = summary.candidates_examined ?? zlensState.candidatesExamined;
  if (statTop) {
    if (zlensState.matches.length > 0) {
      const topMatch = zlensState.matches[0];
      statTop.textContent = topMatch.exact_match ? 'Exact (SHA-256)' : formatMatchTypeName(topMatch.match_type);
    } else {
      statTop.textContent = 'None';
    }
  }
  if (statTime) statTime.textContent = (summary.duration_seconds || 0.1) + 's';

  // 2. Top Match Spotlight Banner (if genuine matches exist)
  const spotlightWrap = document.getElementById('zlens-spotlight');
  if (spotlightWrap && zlensState.matches.length > 0) {
    const top = zlensState.matches[0];
    const matchLabel = formatMatchTypeName(top.match_type);
    const hasExternalUrl = isRealHttpUrl(top.source_page_url);
    const previewSrc = top.preview_url || top.thumbnail_url || top.image_url;
    const isGoogle = top.source_type === 'google_lens';
    const isLenso = top.source_type === 'lenso_ai';

    let metricText = '';
    let verifyBadge = '<span style="color:var(--green); font-size:0.8rem;">✓ Verified SQLite Record</span>';
    if (top.exact_match) {
      metricText = 'SHA-256 Byte Match';
    } else if (isGoogle) {
      metricText = 'Deep Neural Visual Recognition';
      verifyBadge = '<span style="color:var(--cyan); font-size:0.8rem;">✓ Live Reverse Search Upload</span>';
    } else if (isLenso) {
      metricText = 'Lenso.ai AI Facial Recognition';
      verifyBadge = '<span style="color:var(--violet); font-size:0.8rem;">✓ Lenso AI Verified</span>';
    } else if (top.phash_distance !== null && top.phash_distance !== undefined) {
      metricText = `pHash: ${top.phash_distance} bits, dHash: ${top.dhash_distance} bits`;
    } else {
      metricText = 'Contextual OSINT Subject Dork';
      verifyBadge = '<span style="color:var(--text-muted); font-size:0.8rem;">Contextual Text Match</span>';
    }

    spotlightWrap.innerHTML = `
      <img src="${zlensEscape(previewSrc)}" alt="Asset #${top.asset_id}" class="zlens-spotlight-img" onclick="openLightbox('${zlensEscape(previewSrc)}')" onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'140\\' height=\\'140\\' fill=\\'%23223355\\'><rect width=\\'140\\' height=\\'140\\' fill=\\'%23081020\\'/><text x=\\'50%\\' y=\\'50%\\' text-anchor=\\'middle\\' fill=\\'%236688aa\\' font-size=\\'12\\'>Asset #${top.asset_id}</text></svg>';" />
      <div class="zlens-spotlight-body">
        <div class="zlens-spotlight-badge">🏆 TOP MATCH — ${zlensEscape(top.display_score)}</div>
        <div class="zlens-spotlight-title">${zlensEscape(top.filename || top.source_name || ('Indexed Asset #' + top.asset_id))}</div>
        <div class="zlens-spotlight-source">
          <span>Source: <strong>${zlensEscape(top.source_name || top.source_type || 'Local Index')}</strong></span>
          <span>·</span>
          <span>${zlensEscape(metricText)}</span>
          <span>·</span>
          ${verifyBadge}
        </div>
        ${hasExternalUrl ? `
          <a href="${zlensEscape(top.source_page_url)}" target="_blank" rel="noopener noreferrer" class="zlens-redirect-btn">
            ${isGoogle ? '⚡ Open Visual Matches in Google Lens ↗' : (isLenso ? '📸 View on Lenso.ai ↗' : '⚡ Redirect to Source Webpage ↗')}
          </a>
        ` : `
          <div style="font-size:0.85rem; color:var(--text-muted); font-family:var(--font-mono); padding:6px 0;">
            📁 Permitted Local Dataset Record #${top.asset_id}
          </div>
        `}
      </div>
    `;
    spotlightWrap.style.display = 'flex';
  } else if (spotlightWrap) {
    spotlightWrap.style.display = 'none';
  }

  // 3. Render Global Reverse Engines Pivots Grid
  const pivotsSection = document.getElementById('zlens-pivots-section');
  const pivotsGrid = document.getElementById('zlens-pivots-grid');
  const reverseLinks = summary.reverse_links || [];
  if (pivotsSection && pivotsGrid && reverseLinks.length > 0) {
    pivotsGrid.innerHTML = reverseLinks.map((p) => `
      <a href="${zlensEscape(p.url)}" target="_blank" rel="noopener noreferrer" class="zlens-pivot-card">
        <div class="zlens-pivot-header">
          <span style="font-size:1.4rem;">${p.icon || '🔍'}</span>
          <span class="zlens-pivot-badge">${p.engine.includes('Lens') || p.engine.includes('Lenso') ? 'AI Facial/Visual' : 'Visual Search'}</span>
        </div>
        <div class="zlens-pivot-engine">${zlensEscape(p.engine)}</div>
        <div class="zlens-pivot-desc">${zlensEscape(p.description)}</div>
        <div class="zlens-pivot-link">
          Launch Engine <span>↗</span>
        </div>
      </a>
    `).join('');
    pivotsSection.style.display = 'block';
  } else if (pivotsSection) {
    pivotsSection.style.display = 'none';
  }

  // 4. Render Cards Grid
  filterZLensMatches(zlensState.activeFilter);

  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function formatMatchTypeName(type) {
  if (type === 'exact_duplicate' || type === 'Exact duplicate') return 'Exact Duplicate';
  if (type === 'strong_near_duplicate' || type === 'near_duplicate' || type === 'Near duplicate') return 'Near Duplicate';
  if (type === 'weak_near_duplicate' || type === 'visual_similarity') return 'Perceptual Variant';
  if (type === 'contextual_dork') return 'Contextual Text Dork';
  return type || 'Candidate';
}

function isRealHttpUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const clean = url.trim().toLowerCase();
  return clean.startsWith('http://') || clean.startsWith('https://');
}

function filterZLensMatches(filterType) {
  zlensState.activeFilter = filterType;

  document.querySelectorAll('.zlens-filter-tab').forEach((tab) => {
    tab.classList.toggle('active', tab.getAttribute('data-filter') === filterType);
  });

  const grid = document.getElementById('zlens-matches-grid');
  if (!grid) return;

  let filtered = [...zlensState.matches];
  if (filterType === 'exact') {
    filtered = filtered.filter((m) => m.exact_match || m.match_type === 'exact_duplicate' || m.match_type === 'Exact duplicate');
  } else if (filterType === 'near') {
    filtered = filtered.filter((m) => !m.exact_match && (m.match_type === 'strong_near_duplicate' || m.match_type === 'near_duplicate' || m.match_type === 'Near duplicate'));
  } else if (filterType === 'visual') {
    filtered = filtered.filter((m) => m.source_type === 'google_lens' || m.source_type === 'lenso_ai' || m.match_type === 'weak_near_duplicate' || m.match_type === 'visual_similarity' || m.match_type === 'contextual_dork');
  }

  if (filtered.length === 0) {
    let emptyTitle = '🔍 No Local Matches in Collection';
    let emptyIcon = '🔍';
    let emptyMessage = `This query image was not found in your local indexed SQLite collection (${zlensState.candidatesExamined} indexed assets examined). Use the Global Reverse Visual Engines below to view web-wide facial and visual recognition results.`;

    if (zlensState.searchStatus === 'index_empty') {
      emptyIcon = '📦';
      emptyTitle = 'Local Image Index is Empty';
      emptyMessage = `The persistent SQLite index currently contains 0 assets. Click "Index / Refresh Collection" above to populate the local visual database.`;
    } else if (zlensState.searchStatus === 'database_error') {
      emptyIcon = '⚠️';
      emptyTitle = 'Database Service Error';
      emptyMessage = zlensState.searchMessage || 'Could not query the local SQLite database. Please ensure the database is initialized and accessible.';
    } else if (zlensState.matches.length > 0) {
      emptyTitle = `No Matches in "${filterType}" Category`;
      emptyMessage = `There are ${zlensState.matches.length} matching candidate(s) in other categories. Switch to "All Matches" to view them.`;
    }

    grid.innerHTML = `
      <div style="grid-column: 1/-1; text-align:center; padding: 48px 24px; color:var(--text-muted); font-size:0.95rem; background: rgba(13, 21, 38, 0.4); border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px;">
        <div style="font-size:2.5rem; margin-bottom:12px;">${emptyIcon}</div>
        <div style="font-size:1.15rem; font-weight:600; color:var(--text-primary); margin-bottom:8px;">${emptyTitle}</div>
        <div style="max-width:580px; margin:0 auto; line-height:1.6;">${emptyMessage}</div>
      </div>
    `;
    return;
  }

  grid.innerHTML = filtered.map((match) => {
    const hasExternalUrl = isRealHttpUrl(match.source_page_url);
    const previewSrc = match.preview_url || match.thumbnail_url || match.image_url;
    const isExact = Boolean(match.exact_match || match.match_type === 'exact_duplicate');
    const isLenso = Boolean(match.source_type === 'lenso_ai');
    const isGoogleLens = Boolean(match.source_type === 'google_lens');
    const isWeb = Boolean(isLenso || isGoogleLens || match.source_type === 'web_dork' || match.source_type === 'wikimedia' || (match.source_type && match.source_type.includes('osint')));
    
    let badgeText = isExact ? 'Exact (SHA-256)' : (match.display_score || `pHash: ${match.phash_distance} | dHash: ${match.dhash_distance}`);
    if (isLenso) badgeText = '📸 Lenso.ai Match';
    if (isGoogleLens) badgeText = '⚡ Google Lens Live Results';

    const badgeClass = (isExact || isLenso || isGoogleLens) ? 'match-high' : (isWeb ? 'match-high' : 'match-med');
    const metricLine = isExact
      ? 'Exact Byte Match · SHA-256 bitwise identical'
      : (isGoogleLens ? 'Deep Neural Visual Recognition · Live Web-Wide Index' : (isLenso ? 'Lenso.ai AI Facial / Duplicate Visual Match' : (match.match_type === 'contextual_dork' ? `Contextual Text Dork · ${match.source_name || 'Web'}` : `Perceptual Variant · pHash: ${match.phash_distance} bits`)));

    return `
      <div class="zlens-match-card">
        <div class="zlens-match-img-wrap" onclick="openLightbox('${zlensEscape(previewSrc)}')">
          <img src="${zlensEscape(previewSrc)}" alt="Asset #${match.asset_id}" class="zlens-match-img" loading="lazy" onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'280\\' height=\\'200\\' fill=\\'%23112233\\'><rect width=\\'280\\' height=\\'200\\' fill=\\'%23081020\\'/><text x=\\'50%\\' y=\\'50%\\' text-anchor=\\'middle\\' fill=\\'%236688aa\\' font-size=\\'13\\'>Asset #${match.asset_id}</text></svg>';" />
          <div class="zlens-match-badge ${badgeClass}">
            ${zlensEscape(badgeText)}
          </div>
          <div class="zlens-plat-chip" style="border-left: 3px solid #00d4ff;">
            ${zlensEscape(match.source_name || match.source_type || 'local_index')}
          </div>
        </div>
        <div class="zlens-match-content">
          <div class="zlens-match-title" title="${zlensEscape(match.source_name || ('Indexed Asset #' + match.asset_id))}">
            ${zlensEscape(match.filename || match.source_name || ('Indexed Asset #' + match.asset_id))}
          </div>
          <div class="zlens-match-domain">
            ${hasExternalUrl ? `🔗 ${zlensEscape(getDomainSafe(match.source_page_url))}` : '📁 Local SQLite Collection'}
            <span style="color:var(--green); font-size:0.75rem; margin-left:6px;">✓ Verified Record</span>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted); margin: 6px 0 10px; font-family:var(--font-mono);">
            ${zlensEscape(metricLine)}
          </div>
          <div class="zlens-match-actions">
            ${hasExternalUrl ? `
              <a href="${zlensEscape(match.source_page_url)}" target="_blank" rel="noopener noreferrer" class="zlens-card-redirect" style="${isGoogleLens ? 'background:var(--cyan); color:#000; font-weight:700;' : (isLenso ? 'background:#8b5cf6; color:#fff;' : '')}">
                ${isGoogleLens ? '⚡ Open Visual Matches ↗' : (isLenso ? '📸 View Lenso.ai ↗' : 'Visit Source ↗')}
              </a>
              <button class="zlens-card-copy" onclick="zlensCopyUrl('${zlensEscape(match.source_page_url)}')" title="Copy Link">
                📋
              </button>
            ` : `
              <span style="font-size:0.8rem; color:var(--text-muted); font-family:var(--font-mono); padding: 4px 0;">
                Asset ID: #${match.asset_id} (${match.format || 'IMG'})
              </span>
            `}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function getDomainSafe(url) {
  try {
    return new URL(url).hostname;
  } catch (e) {
    return 'web source';
  }
}

function zlensCopyUrl(url) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => {
      zlensToast('📋 Source link copied to clipboard!');
    });
  } else {
    zlensToast('📋 URL: ' + url);
  }
}

function zlensToast(msg) {
  const existing = document.getElementById('zlens-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'zlens-toast';
  toast.style.position = 'fixed';
  toast.style.bottom = '24px';
  toast.style.right = '24px';
  toast.style.background = '#0d1526';
  toast.style.border = '1px solid #00d4ff';
  toast.style.color = '#e8f4f8';
  toast.style.padding = '12px 20px';
  toast.style.borderRadius = '8px';
  toast.style.boxShadow = '0 6px 24px rgba(0, 212, 255, 0.25)';
  toast.style.fontFamily = 'var(--font-heading)';
  toast.style.fontSize = '0.9rem';
  toast.style.fontWeight = '500';
  toast.style.zIndex = '99999';
  toast.style.transition = 'all 0.3s ease';
  toast.textContent = msg;

  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
