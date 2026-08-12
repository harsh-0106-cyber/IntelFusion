/**
 * IntelFusion — OSINT Search Engine Frontend
 * Handles SSE streaming, dynamic result rendering, tag cloud, PeopleRank gauge, and export.
 */

const API_BASE = window.location.origin;

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  query: "",
  keywords: "",
  allResults: [],
  socialResults: [],
  images: [],
  tags: [],
  rankData: null,
  stats: {},
  activeFilter: "all",
  isSearching: false,
  eventSource: null,
};

// ── DOM References ─────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const searchInput    = $("#search-input");
const keywordsInput  = $("#keywords-input");
const searchBtn      = $("#search-btn");
const resultsSection = $("#results-section");
const progressFill   = $("#progress-fill");
const loadingEl      = $("#loading-radar");
const resultsGridEl  = $("#results-grid");
const tagCloudEl     = $("#tag-cloud");
const imageStripEl   = $("#image-strip");
const imagesCardEl   = $("#images-card");
const filterTabsEl   = $("#filter-tabs");
const profileHeaderEl= $("#profile-header");
const exportBarEl    = $("#export-bar");
const homonymAlertEl = $("#homonym-alert");
const lightboxEl     = $("#lightbox");
const lightboxImgEl  = $("#lightbox-img");
const navbarEl       = $(".navbar");

const workInput      = $("#work-input");
const instituteInput = $("#institute-input");
const imageInput     = $("#image-input");
const advancedToggle = $("#advanced-toggle");
const advancedPanel  = $("#advanced-panel");

const visualIntelCardEl  = $("#visual-intel-card");
const visualIntelLinksEl = $("#visual-intel-links");
const researchCardEl     = $("#research-card");
const researchProfilesEl = $("#research-profiles");
const researchPapersEl   = $("#research-papers");

// ── Platform Icons & Colors ────────────────────────────────────────────────────
const PLATFORM_DATA = {
  github:     { emoji: "🐙", color: "#6e40c9", bg: "rgba(110,64,201,0.12)" },
  linkedin:   { emoji: "💼", color: "#0077b5", bg: "rgba(0,119,181,0.12)" },
  twitter:    { emoji: "🐦", color: "#1da1f2", bg: "rgba(29,161,242,0.12)" },
  reddit:     { emoji: "🔴", color: "#ff4500", bg: "rgba(255,69,0,0.12)" },
  wikipedia:  { emoji: "📖", color: "#636466", bg: "rgba(99,100,102,0.15)" },
  youtube:    { emoji: "▶️",  color: "#ff0000", bg: "rgba(255,0,0,0.12)" },
  instagram:  { emoji: "📸", color: "#e1306c", bg: "rgba(225,48,108,0.12)" },
  facebook:   { emoji: "👤", color: "#1877f2", bg: "rgba(24,119,242,0.12)" },
  medium:     { emoji: "✍️",  color: "#00ab6c", bg: "rgba(0,171,108,0.12)" },
  quora:      { emoji: "❓", color: "#b92b27", bg: "rgba(185,43,39,0.12)" },
  pinterest:  { emoji: "📌", color: "#e60023", bg: "rgba(230,0,35,0.12)" },
  tiktok:     { emoji: "🎵", color: "#ff0050", bg: "rgba(255,0,80,0.12)" },
  academic:   { emoji: "🎓", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  web:        { emoji: "🌐", color: "#10b981", bg: "rgba(16,185,129,0.12)" },
  stackoverflow: { emoji: "📚", color: "#f48024", bg: "rgba(244,128,36,0.12)" },
};

const CATEGORY_COLORS = {
  professional: "#0077b5",
  social:       "#8b5cf6",
  news:         "#10b981",
  academic:     "#f59e0b",
  reference:    "#636466",
  blog:         "#00ab6c",
  identity:     "#00d4ff",
  web:          "#10b981",
};

// ── Search Trigger ─────────────────────────────────────────────────────────────
function startSearch() {
  const q = searchInput.value.trim();
  const kw = keywordsInput ? keywordsInput.value.trim() : "";
  if (!q || state.isSearching) return;

  state.query = q;
  state.keywords = kw;
  const fullQuery = kw ? `${q} ${kw}` : q;

  resetState();
  showResults();
  runSearch(fullQuery);
}

searchBtn.addEventListener("click", startSearch);

searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") startSearch();
});

if (keywordsInput) {
  keywordsInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") startSearch();
  });
}

// Quick-search hint tags
$$(".search-hint-tag").forEach((tag) => {
  tag.addEventListener("click", () => {
    searchInput.value = tag.dataset.query || tag.textContent.trim();
    if (keywordsInput) keywordsInput.value = "";
    if (workInput) workInput.value = "";
    if (instituteInput) instituteInput.value = "";
    if (imageInput) imageInput.value = "";
    startSearch();
  });
});

// Advanced search toggle
if (advancedToggle && advancedPanel) {
  advancedToggle.addEventListener("click", () => {
    advancedPanel.style.display = advancedPanel.style.display === "none" ? "block" : "none";
  });
}

// Navbar scroll effect
window.addEventListener("scroll", () => {
  navbarEl.classList.toggle("scrolled", window.scrollY > 40);
});

// ── Reset & Init ───────────────────────────────────────────────────────────────
function resetState() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
  state.allResults = [];
  state.socialResults = [];
  state.images = [];
  state.tags = [];
  state.rankData = null;
  state.stats = {};
  state.activeFilter = "all";
  state.isSearching = true;

  // Reset UI
  progressFill.style.width = "0%";
  resultsGridEl.innerHTML = "";
  tagCloudEl.innerHTML = "";
  imageStripEl.innerHTML = "";
  profileHeaderEl.style.display = "none";
  imagesCardEl.style.display = "none";
  exportBarEl.style.display = "none";
  homonymAlertEl.style.display = "none";
  loadingEl.style.display = "block";
  filterTabsEl.innerHTML = "";
  if (visualIntelCardEl) visualIntelCardEl.style.display = "none";
  if (researchCardEl) researchCardEl.style.display = "none";
  const commentsCardEl = $("#comments-card");
  if (commentsCardEl) { commentsCardEl.style.display = "none"; }
  const commentsListEl = $("#comments-list");
  if (commentsListEl) commentsListEl.innerHTML = "";

  // Update search button
  searchBtn.disabled = true;
  searchBtn.innerHTML = `<span class="btn-spinner">⟳</span> Scanning...`;
}

function showResults() {
  resultsSection.classList.add("visible");
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── SSE Stream Handler ─────────────────────────────────────────────────────────
function runSearch(query) {
  let url = `${API_BASE}/api/search?q=${encodeURIComponent(query)}`;
  if (workInput && workInput.value) url += `&work=${encodeURIComponent(workInput.value.trim())}`;
  if (instituteInput && instituteInput.value) url += `&institute=${encodeURIComponent(instituteInput.value.trim())}`;
  if (imageInput && imageInput.value) url += `&image=${encodeURIComponent(imageInput.value.trim())}`;
  
  const es = new EventSource(url);
  state.eventSource = es;

  // ── start ──────────────────────────────────────────────────────────────────
  es.addEventListener("start", (e) => {
    const data = JSON.parse(e.data);
    updateLoadingStatus("Initialising OSINT scan...", "Parsing query");
  });

  // ── progress ───────────────────────────────────────────────────────────────
  es.addEventListener("progress", (e) => {
    const data = JSON.parse(e.data);
    setProgress(data.pct);
    updateLoadingStatus(data.message, data.stage);
  });

  // ── web results ────────────────────────────────────────────────────────────
  es.addEventListener("results", (e) => {
    const data = JSON.parse(e.data);
    state.allResults.push(...data.items);
    updateLoadingStatus(data.message, "web_search");
  });

  // ── social results ─────────────────────────────────────────────────────────
  es.addEventListener("social", (e) => {
    const data = JSON.parse(e.data);
    state.socialResults.push(...data.items);
    updateLoadingStatus(data.message, "social_probe");
  });

  // ── accounts ───────────────────────────────────────────────────────────────
  es.addEventListener("accounts", (e) => {
    const data = JSON.parse(e.data);
    state.socialResults.push(...data.items);
    updateLoadingStatus(data.message, "account_linker");
  });

  // ── comments ───────────────────────────────────────────────────────────────
  es.addEventListener("comments", (e) => {
    const data = JSON.parse(e.data);
    const d = data.data;
    const commentsCardEl = $("#comments-card");
    const commentsListEl = $("#comments-list");
    if (d && commentsListEl) {
      const allComments = d.all_comments || [];
      if (allComments.length > 0) {
        if (commentsCardEl) commentsCardEl.style.display = "block";
        commentsListEl.innerHTML = allComments.slice(0, 20).map(c => {
          const platformEmoji = {
            "Reddit": "🔴", "Hacker News": "🟠", "forum_post": "💬",
            "Quora": "❓", "Stack Overflow": "📚", "Dev.to": "🧑‍💻",
            "Hacker News": "🟠", "Product Hunt": "🔵",
          }[c.platform] || "💬";
          const content = escapeHtml(c.content || "").slice(0, 400);
          const author  = c.author ? `<span class="comment-author">${escapeHtml(c.author)}</span>` : "";
          const context = c.context ? `<span class="comment-context">${escapeHtml(c.context)}</span>` : "";
          const link    = c.url ? `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">View original ↗</a>` : "";
          return `<div class="comment-item">
            <div class="comment-item-header">
              <span class="comment-platform-badge">${platformEmoji} ${escapeHtml(c.platform || "Forum")}</span>
              ${author}${context}
            </div>
            <div class="comment-content">${content}</div>
            ${link}
          </div>`;
        }).join("");
      }
    }
    updateLoadingStatus(data.message, "comments_finder");
  });

  // ── visual ─────────────────────────────────────────────────────────────────
  es.addEventListener("visual", (e) => {
    const data = JSON.parse(e.data);
    if (data.items && data.items.length > 0 && visualIntelCardEl && visualIntelLinksEl) {
        visualIntelCardEl.style.display = "block";
        visualIntelLinksEl.innerHTML = data.items.map(l => 
            `<a href="${l.url}" target="_blank" class="visual-link" style="border-color:${l.color}">
                <span style="color:${l.color}">🌐</span> ${l.platform}
             </a>`
        ).join("");
    }
    updateLoadingStatus(data.message, "visual_intel");
  });

  // ── research ───────────────────────────────────────────────────────────────
  es.addEventListener("research", (e) => {
    const data = JSON.parse(e.data);
    const d = data.data;
    if (d && d.has_research && researchCardEl && researchProfilesEl && researchPapersEl) {
        researchCardEl.style.display = "block";
        
        const profilesHtml = [];
        if (d.orcid) profilesHtml.push(...d.orcid);
        if (d.profiles) profilesHtml.push(...d.profiles);
        
        researchProfilesEl.innerHTML = profilesHtml.map(p => 
            `<a href="${p.url}" target="_blank" class="research-profile" style="border-color:${p.color}">
                <span style="color:${p.color}">🎓</span> ${p.title || p.name}
             </a>`
        ).join("");
        
        researchPapersEl.innerHTML = (d.papers || []).slice(0, 5).map(p => 
            `<div class="research-paper">
                <h4><a href="${p.url}" target="_blank">${p.title}</a></h4>
                <div class="research-paper-meta">
                    ${p.year ? `Year: <span>${p.year}</span> &nbsp;&bull;&nbsp; ` : ""}
                    ${p.venue ? `Venue: <span>${p.venue}</span> &nbsp;&bull;&nbsp; ` : ""}
                    Authors: <span>${(p.authors || []).join(", ")}</span>
                </div>
                <div class="research-paper-abstract">${p.abstract || ""}</div>
             </div>`
        ).join("");
    }
    updateLoadingStatus(data.message, "research_finder");
  });

  // ── images ─────────────────────────────────────────────────────────────────
  es.addEventListener("images", (e) => {
    const data = JSON.parse(e.data);
    state.images = data.items;
    if (data.items.length > 0) {
      renderImages(data.items);
    }
    updateLoadingStatus(data.message, "image_harvest");
  });

  // ── tags ───────────────────────────────────────────────────────────────────
  es.addEventListener("tags", (e) => {
    const data = JSON.parse(e.data);
    state.tags = data.items;
    renderTagCloud(data.items);
    if (data.homonym_groups > 1) {
      homonymAlertEl.style.display = "flex";
    }
    updateLoadingStatus(data.message, "resolving");
  });

  // ── rank ───────────────────────────────────────────────────────────────────
  es.addEventListener("rank", (e) => {
    const data = JSON.parse(e.data);
    state.rankData = data;
    updateLoadingStatus("PeopleRank computed!", "ranking");
  });

  // ── stats ──────────────────────────────────────────────────────────────────
  es.addEventListener("stats", (e) => {
    const data = JSON.parse(e.data);
    state.stats = data;
  });

  // ── done ───────────────────────────────────────────────────────────────────
  es.addEventListener("done", (e) => {
    es.close();
    state.isSearching = false;
    finalisResults();
  });

  // ── error ──────────────────────────────────────────────────────────────────
  es.addEventListener("error", (e) => {
    es.close();
    state.isSearching = false;
    let msg = "An error occurred during the search.";
    try { msg = JSON.parse(e.data).message; } catch(_) {}
    showError(msg);
    resetSearchBtn();
  });

  es.onerror = () => {
    if (!state.isSearching) return;
    es.close();
    state.isSearching = false;
    finalisResults(); // try to show whatever we have
  };
}

// ── Finalise Results ───────────────────────────────────────────────────────────
function finalisResults() {
  loadingEl.style.display = "none";
  setProgress(100);

  const combined = [
    ...state.socialResults,
    ...state.allResults,
  ];

  if (combined.length === 0 && state.images.length === 0) {
    resultsGridEl.innerHTML = `
      <div class="no-results" style="grid-column:1/-1">
        <div class="no-results-icon">🔍</div>
        <h3>No results found</h3>
        <p>Try a different name or add more keywords for better results.</p>
      </div>`;
  } else {
    buildFilterTabs(combined);
    renderResultsFiltered(combined, "all");
  }

  if (state.rankData) {
    renderProfileHeader(state.rankData);
  }

  exportBarEl.style.display = "flex";
  updateExportBar(combined.length);

  resetSearchBtn();
}

// ── Profile Header (PeopleRank) ────────────────────────────────────────────────
function renderProfileHeader(rankData) {
  profileHeaderEl.style.display = "flex";
  const { score, grade, label, breakdown, interpretation } = rankData;
  const name = state.query;
  const stats = state.stats;

  // SVG gauge circumference for 75% arc (270°)
  const circumference = 220;
  const offset = circumference - (score / 100) * circumference;

  // Score color
  const gradeColor = score >= 70 ? "#00d4ff" : score >= 40 ? "#f59e0b" : "#ef4444";

  // Platform badges from social results
  const platformsHTML = buildPlatformBadges(state.socialResults);

  // Breakdown bars
  const breakdownHTML = Object.entries(breakdown).map(([key, val]) => `
    <div class="breakdown-row">
      <span class="breakdown-label">${formatBreakdownKey(key)}</span>
      <div class="breakdown-bar-wrap">
        <div class="breakdown-bar-fill" data-target="${(val.score / val.max) * 100}%"></div>
      </div>
      <span class="breakdown-val">${val.score}/${val.max}</span>
    </div>
  `).join("");

  profileHeaderEl.innerHTML = `
    <div class="rank-gauge-wrap">
      <svg class="rank-gauge-svg" width="110" height="110" viewBox="0 0 110 110">
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stop-color="${gradeColor}" />
            <stop offset="100%" stop-color="#8b5cf6" />
          </linearGradient>
        </defs>
        <circle class="rank-track" cx="55" cy="55" r="42"
          stroke-dasharray="${circumference}" stroke-dashoffset="0"
          transform="rotate(135 55 55)" />
        <circle class="rank-fill" cx="55" cy="55" r="42"
          stroke-dasharray="${circumference}" stroke-dashoffset="${circumference}"
          transform="rotate(135 55 55)"
          id="gauge-fill" />
        <text class="rank-score-text" x="55" y="52" text-anchor="middle" dominant-baseline="middle"
          fill="${gradeColor}" id="gauge-score">0</text>
        <text class="rank-label-text" x="55" y="66" text-anchor="middle"
          fill="rgba(255,255,255,0.4)">PEOPLERANK</text>
      </svg>
      <div class="rank-grade-badge" style="color:${gradeColor}; border-color:${gradeColor}40; background:${gradeColor}15">
        Grade ${grade} · ${label}
      </div>
    </div>

    <div class="profile-info">
      <div class="profile-name">${escapeHtml(name)}</div>
      <div class="profile-rank-label">
        Online visibility analysis
        <span class="label-badge">${label}</span>
      </div>

      <div class="profile-stats">
        <div class="profile-stat">
          <div class="profile-stat-val" id="stat-total">${stats.total_results || 0}</div>
          <div class="profile-stat-lbl">Results Found</div>
        </div>
        <div class="profile-stat">
          <div class="profile-stat-val" id="stat-domains">${stats.unique_domains || 0}</div>
          <div class="profile-stat-lbl">Unique Domains</div>
        </div>
        <div class="profile-stat">
          <div class="profile-stat-val" id="stat-images">${state.images.length}</div>
          <div class="profile-stat-lbl">Images Found</div>
        </div>
        <div class="profile-stat">
          <div class="profile-stat-val">${stats.social_hits || 0}</div>
          <div class="profile-stat-lbl">Social Hits</div>
        </div>
      </div>

      <div class="score-breakdown" style="margin-top:20px">
        ${breakdownHTML}
      </div>

      ${platformsHTML ? `<div class="platform-badges" style="margin-top:20px">${platformsHTML}</div>` : ""}

      <p style="margin-top:16px; font-size:0.82rem; color:var(--text-muted); font-style:italic;">
        ${escapeHtml(interpretation)}
      </p>
    </div>
  `;

  // Animate gauge after render
  requestAnimationFrame(() => {
    setTimeout(() => {
      const fillEl = document.getElementById("gauge-fill");
      const scoreEl = document.getElementById("gauge-score");
      if (fillEl) {
        fillEl.style.strokeDashoffset = offset;
      }
      if (scoreEl) {
        animateNumber(scoreEl, 0, score, 1500, (n) => {
          scoreEl.textContent = n;
        });
      }
      // Animate breakdown bars
      $$(".breakdown-bar-fill").forEach((bar) => {
        setTimeout(() => { bar.style.width = bar.dataset.target; }, 200);
      });
    }, 100);
  });
}

// ── Filter Tabs ────────────────────────────────────────────────────────────────
function buildFilterTabs(combined) {
  const categories = {};
  combined.forEach((r) => {
    const cat = r.category || "web";
    categories[cat] = (categories[cat] || 0) + 1;
  });

  const tabOrder = ["all", "social", "professional", "news", "academic", "reference", "blog"];
  const tabs = [
    { id: "all", label: "All Results", count: combined.length },
    ...Object.entries(categories)
      .sort((a, b) => b[1] - a[1])
      .map(([cat, count]) => ({ id: cat, label: capitalize(cat), count })),
  ];

  filterTabsEl.innerHTML = tabs.map((tab) => `
    <button class="filter-tab ${tab.id === "all" ? "active" : ""}"
            data-filter="${tab.id}"
            onclick="applyFilter(this, '${tab.id}')">
      ${tab.label}
      <span class="tab-count">${tab.count}</span>
    </button>
  `).join("");

  window._combinedResults = combined; // store for filtering
}

window.applyFilter = function(btn, filter) {
  $$(".filter-tab").forEach((t) => t.classList.remove("active"));
  btn.classList.add("active");
  state.activeFilter = filter;
  renderResultsFiltered(window._combinedResults, filter);
};

// ── Results Grid ───────────────────────────────────────────────────────────────
function renderResultsFiltered(results, filter) {
  const filtered = filter === "all"
    ? results
    : results.filter((r) => (r.category || "web") === filter);

  resultsGridEl.innerHTML = "";

  if (filtered.length === 0) {
    resultsGridEl.innerHTML = `
      <div class="no-results" style="grid-column:1/-1">
        <div class="no-results-icon">📭</div>
        <h3>No ${filter} results</h3>
        <p>No results found for this category.</p>
      </div>`;
    return;
  }

  filtered.forEach((r, i) => {
    const card = buildResultCard(r, i);
    resultsGridEl.appendChild(card);
  });
}

function buildResultCard(r, index) {
  const iconKey = r.icon || guessIcon(r.url || "");
  const pd = PLATFORM_DATA[iconKey] || PLATFORM_DATA.web;
  const catColor = CATEGORY_COLORS[r.category] || "#10b981";

  const card = document.createElement("a");
  card.className = "result-card";
  card.href = r.url || "#";
  card.target = "_blank";
  card.rel = "noopener noreferrer";
  card.style.cssText = `
    --card-accent: ${pd.color};
    animation-delay: ${Math.min(index * 0.04, 0.8)}s;
  `;

  const domain = r.domain || extractDomain(r.url || "");
  const title = r.title || "Untitled";
  const snippet = r.description || r.snippet || "";

  card.innerHTML = `
    <div class="result-header">
      <div class="result-platform-icon" style="background:${pd.bg}; color:${pd.color}">
        ${pd.emoji}
      </div>
      <div class="result-meta">
        <div class="result-title">${escapeHtml(title)}</div>
        <div class="result-domain">${escapeHtml(domain)}</div>
      </div>
    </div>
    ${snippet ? `<div class="result-snippet">${escapeHtml(snippet)}</div>` : ""}
    <div class="result-footer">
      <span class="result-category-tag" style="background:${catColor}18; color:${catColor}; border:1px solid ${catColor}30">
        ${capitalize(r.category || "web")}
      </span>
      <span class="result-link-icon">↗</span>
    </div>
  `;

  return card;
}

// ── Tag Cloud ──────────────────────────────────────────────────────────────────
function renderTagCloud(tags) {
  tagCloudEl.innerHTML = "";
  tags.forEach((tag, i) => {
    const el = document.createElement("span");
    el.className = "tag-item";
    el.textContent = tag.word;
    el.style.cssText = `
      font-size: ${tag.size}px;
      animation-delay: ${i * 0.04}s;
    `;
    el.title = `Relevance weight: ${tag.weight}`;
    el.addEventListener("click", () => {
      searchInput.value = `${state.query} ${tag.word}`;
      startSearch();
    });
    tagCloudEl.appendChild(el);
  });
}

// ── Image Strip ────────────────────────────────────────────────────────────────
function renderImages(images) {
  imagesCardEl.style.display = "block";
  imageStripEl.innerHTML = "";

  images.forEach((img) => {
    if (!img.url) return;
    const el = document.createElement("img");
    el.className = "image-thumb";
    el.src = img.thumbnail || img.url;
    el.alt = img.title || "Found image";
    el.loading = "lazy";
    el.title = img.title || "";

    el.addEventListener("error", () => { el.remove(); });
    el.addEventListener("click", () => openLightbox(img.url, img.title));

    imageStripEl.appendChild(el);
  });
}

// ── Lightbox ───────────────────────────────────────────────────────────────────
function openLightbox(url, title) {
  lightboxImgEl.src = url;
  lightboxImgEl.alt = title || "";
  lightboxEl.classList.add("open");
}

lightboxEl.addEventListener("click", (e) => {
  if (e.target === lightboxEl || e.target.classList.contains("lightbox-close")) {
    lightboxEl.classList.remove("open");
    lightboxImgEl.src = "";
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") lightboxEl.classList.remove("open");
});

// ── Platform Badges ────────────────────────────────────────────────────────────
function buildPlatformBadges(socialResults) {
  const seen = new Set();
  return socialResults
    .filter((r) => {
      const p = r.platform;
      if (seen.has(p)) return false;
      seen.add(p);
      return true;
    })
    .slice(0, 8)
    .map((r) => {
      const key = r.icon || guessIcon(r.url || "");
      const pd = PLATFORM_DATA[key] || PLATFORM_DATA.web;
      return `<a class="platform-badge"
          href="${escapeHtml(r.url)}"
          target="_blank" rel="noopener"
          style="color:${pd.color}; border-color:${pd.color}30; background:${pd.bg}">
          ${pd.emoji} ${escapeHtml(r.platform)}
        </a>`;
    })
    .join("");
}

// ── Export ─────────────────────────────────────────────────────────────────────
function updateExportBar(count) {
  const now = new Date().toLocaleString();
  $("#export-info").innerHTML = `
    Showing <strong>${count} results</strong> for
    <strong>"${escapeHtml(state.query)}"</strong> · Scanned at ${now}
  `;
}

window.exportJSON = function() {
  const data = {
    query: state.query,
    keywords: state.keywords,
    timestamp: new Date().toISOString(),
    people_rank: state.rankData,
    stats: state.stats,
    results: [...state.socialResults, ...state.allResults],
    images: state.images,
    tags: state.tags,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `intelfusion_${state.query.replace(/\s+/g, "_")}_${Date.now()}.json`;
  a.click();
};

window.printReport = function() {
  window.print();
};

// ── Progress & Status ──────────────────────────────────────────────────────────
function setProgress(pct) {
  progressFill.style.width = `${pct}%`;
}

function updateLoadingStatus(message, stage) {
  const statusEl = $("#loading-status");
  const stageEl  = $("#loading-stage");
  if (statusEl) statusEl.textContent = message;
  if (stageEl)  stageEl.textContent  = `Stage: ${formatBreakdownKey(stage)}`;
}

function showError(msg) {
  loadingEl.style.display = "none";
  resultsGridEl.innerHTML = `
    <div class="no-results" style="grid-column:1/-1">
      <div class="no-results-icon">⚠️</div>
      <h3>Search Error</h3>
      <p>${escapeHtml(msg)}</p>
    </div>`;
}

function resetSearchBtn() {
  searchBtn.disabled = false;
  searchBtn.innerHTML = `🔍 Search`;
  state.isSearching = false;
}

// ── Utilities ──────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function extractDomain(url) {
  try { return new URL(url).hostname.replace("www.", ""); }
  catch (_) { return url; }
}

function guessIcon(url) {
  const u = url.toLowerCase();
  if (u.includes("github"))      return "github";
  if (u.includes("linkedin"))    return "linkedin";
  if (u.includes("twitter") || u.includes("x.com")) return "twitter";
  if (u.includes("reddit"))      return "reddit";
  if (u.includes("wikipedia"))   return "wikipedia";
  if (u.includes("youtube"))     return "youtube";
  if (u.includes("instagram"))   return "instagram";
  if (u.includes("facebook"))    return "facebook";
  if (u.includes("medium"))      return "medium";
  if (u.includes("quora"))       return "quora";
  if (u.includes("pinterest"))   return "pinterest";
  if (u.includes("tiktok"))      return "tiktok";
  if (u.includes("stackoverflow")) return "stackoverflow";
  if (u.includes("arxiv") || u.includes("researchgate") || u.includes("scholar")) return "academic";
  return "web";
}

function formatBreakdownKey(key) {
  if (!key) return "";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function animateNumber(el, from, to, duration, callback) {
  const start = performance.now();
  function tick(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const ease = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    const current = Math.round(from + (to - from) * ease);
    callback(current);
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
