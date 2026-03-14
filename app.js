// ─────────────────────────────────────────────────────────────
// Winchester TMMA Lookup — App Logic
// Pure client-side JS, no dependencies.
// ─────────────────────────────────────────────────────────────

(function () {
  'use strict';

  // ── DOM refs ───────────────────────────────────────────────
  const streetInput    = document.getElementById('street-input');
  const searchBtn      = document.getElementById('search-btn');
  const suggestionsList = document.getElementById('suggestions-list');
  const resultsSection = document.getElementById('results-section');
  const statusArea     = document.getElementById('status-area');
  const multiArea      = document.getElementById('multi-precinct-area');
  const resultsArea    = document.getElementById('results-area');

  // House number UI
  const houseLabel  = document.getElementById('house-label');
  const houseRow    = document.getElementById('house-row');
  const houseInput  = document.getElementById('house-input');
  const houseBtn    = document.getElementById('house-btn');
  const houseHint   = document.getElementById('house-hint');

  // ── URL state helpers ────────────────────────────────────────
  function setUrlState(params) {
    const sp = new URLSearchParams(window.location.search);
    Object.entries(params).forEach(([k, v]) => {
      if (v === null || v === undefined) sp.delete(k);
      else sp.set(k, v);
    });
    const qs = sp.toString();
    history.replaceState(null, '', qs ? '?' + qs : window.location.pathname);
  }

  function getUrlState() {
    const sp = new URLSearchParams(window.location.search);
    return {
      street:   sp.get('street')   || '',
      house:    sp.get('house')    || '',
      precinct: sp.get('precinct') ? parseInt(sp.get('precinct'), 10) : null,
    };
  }

  // ── Dark mode toggle ───────────────────────────────────────
  (function () {
    const toggle = document.querySelector('[data-theme-toggle]');
    const root   = document.documentElement;
    let theme    = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
    root.setAttribute('data-theme', theme);
    updateToggleIcon(toggle, theme);

    toggle && toggle.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', theme);
      updateToggleIcon(toggle, theme);
      toggle.setAttribute('aria-label', 'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' mode');
    });

    function updateToggleIcon(btn, t) {
      if (!btn) return;
      btn.innerHTML = t === 'dark'
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    }
  })();

  // ── Street index helpers ───────────────────────────────────
  const streets        = TMMA_DATA.streets;
  const housePrecincts = TMMA_DATA.housePrecincts || {};

  // State: currently selected street key
  let selectedStreetKey = null;

  // Normalise a street string to the canonical key format
  function normaliseStreet(raw) {
    return raw
      .trim()
      .toUpperCase()
      // strip leading house number if entered accidentally
      .replace(/^\d+\s+/, '')
      // collapse multiple spaces
      .replace(/\s+/g, ' ')
      // expand common abbreviations
      .replace(/\bST\.?$/, 'ST')
      .replace(/\bAVE?\.?$/, 'AVE')
      .replace(/\bRD\.?$/, 'RD')
      .replace(/\bDR\.?$/, 'DR')
      .replace(/\bLN\.?$/, 'LN')
      .replace(/\bPL\.?$/, 'PL')
      .replace(/\bCT\.?$/, 'CT')
      .replace(/\bTER\.?$/, 'TER')
      .replace(/\bCIR\.?$/, 'CIR')
      .replace(/\bPKY\.?$/, 'PKY')
      .replace(/\bPKWY\.?$/, 'PKWY')
      .replace(/\bBLVD\.?$/, 'BLVD')
      .replace(/\bHWY\.?$/, 'HWY')
      .replace(/\bWAY\.?$/, 'WAY');
  }

  // Fuzzy match: find candidate keys
  function findMatches(query) {
    const q = normaliseStreet(query);
    if (q.length < 2) return [];
    const results = [];
    for (const key of Object.keys(streets)) {
      if (key.startsWith(q)) results.push({ key, precincts: streets[key], score: 2 });
      else if (key.includes(q)) results.push({ key, precincts: streets[key], score: 1 });
    }
    results.sort((a, b) => b.score - a.score || a.key.localeCompare(b.key));
    return results;
  }

  // ── Autocomplete / suggestions ─────────────────────────────
  let activeIdx = -1;
  let currentMatches = [];

  streetInput.addEventListener('input', () => {
    const val = streetInput.value.trim();
    activeIdx = -1;
    // If user edits street, hide house row, reset, and clear URL state
    hideHouseRow();
    selectedStreetKey = null;
    setUrlState({ street: null, house: null, precinct: null });
    if (val.length < 2) {
      hideSuggestions();
      return;
    }
    currentMatches = findMatches(val);
    if (currentMatches.length === 0) {
      hideSuggestions();
      return;
    }
    renderSuggestions(currentMatches.slice(0, 12));
  });

  streetInput.addEventListener('keydown', (e) => {
    const items = suggestionsList.querySelectorAll('li');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, items.length - 1);
      updateActive(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, -1);
      updateActive(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIdx >= 0 && items[activeIdx]) {
        selectSuggestion(currentMatches[activeIdx]);
      } else {
        doStreetSearch();
      }
    } else if (e.key === 'Escape') {
      hideSuggestions();
    }
  });

  function updateActive(items) {
    items.forEach((li, i) => li.setAttribute('aria-selected', i === activeIdx ? 'true' : 'false'));
  }

  function renderSuggestions(matches) {
    suggestionsList.innerHTML = '';
    matches.forEach((m, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', 'false');
      li.setAttribute('id', 'suggestion-' + i);
      const pLabel = m.precincts.length === 1
        ? 'Precinct ' + m.precincts[0]
        : 'Precincts ' + m.precincts.join(', ');
      li.innerHTML =
        toTitleCase(m.key) +
        '<span class="suggestion-precinct">' + pLabel + '</span>';
      li.addEventListener('mousedown', (e) => { e.preventDefault(); });
      li.addEventListener('click', () => selectSuggestion(m));
      suggestionsList.appendChild(li);
    });
    suggestionsList.classList.remove('hidden');
  }

  function selectSuggestion(match) {
    streetInput.value = toTitleCase(match.key);
    hideSuggestions();
    handleStreetSelected(normaliseStreet(match.key), match.precincts);
  }

  function hideSuggestions() {
    suggestionsList.classList.add('hidden');
    suggestionsList.innerHTML = '';
  }

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.suggestions-wrap') && !e.target.closest('.search-btn')) {
      hideSuggestions();
    }
  });

  // ── Street search button ───────────────────────────────────
  searchBtn.addEventListener('click', doStreetSearch);

  function doStreetSearch() {
    hideSuggestions();
    const raw = streetInput.value.trim();
    if (!raw) {
      streetInput.focus();
      return;
    }
    const normalised = normaliseStreet(raw);
    const exact = streets[normalised];
    if (exact) {
      handleStreetSelected(normalised, exact);
      return;
    }
    // Try partial match
    const matches = findMatches(raw);
    if (matches.length === 1) {
      streetInput.value = toTitleCase(matches[0].key);
      handleStreetSelected(matches[0].key, matches[0].precincts);
      return;
    }
    if (matches.length > 1) {
      showMultipleStreets(matches, raw);
      return;
    }
    showNotFound(raw);
  }

  // ── House number flow ──────────────────────────────────────

  function handleStreetSelected(streetKey, precincts) {
    selectedStreetKey = streetKey;
    if (precincts.length === 1) {
      // Single precinct — no house number needed
      hideHouseRow();
      clearResults();
      renderMemberList(streetKey, precincts[0]);
    } else {
      // Multi-precinct — always ask for house number
      showHouseRow(streetKey, precincts);
    }
  }

  function showHouseRow(streetKey, precincts) {
    houseLabel.classList.remove('hidden');
    houseRow.classList.remove('hidden');
    houseInput.value = '';
    houseHint.className = 'house-hint';
    houseHint.textContent = toTitleCase(streetKey) + ' spans precincts ' + precincts.join(', ') + '. Enter your house number to find your exact precinct.';
    houseHint.classList.remove('hidden');
    houseInput.focus();
    // Clear results while waiting for house number
    resultsSection.classList.add('hidden');
    statusArea.innerHTML = '';
    multiArea.innerHTML = '';
    resultsArea.innerHTML = '';
  }

  function hideHouseRow() {
    houseLabel.classList.add('hidden');
    houseRow.classList.add('hidden');
    houseHint.classList.add('hidden');
    houseInput.value = '';
  }

  houseBtn.addEventListener('click', doHouseLookup);
  houseInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); doHouseLookup(); }
  });

  function doHouseLookup() {
    if (!selectedStreetKey) return;
    const rawNum = houseInput.value.trim();
    if (!rawNum) {
      houseInput.focus();
      return;
    }

    const streetHP = housePrecincts[selectedStreetKey];
    const precincts = streets[selectedStreetKey] || [];

    if (!streetHP) {
      // No per-address data — fall back to choice buttons
      clearResults();
      showMultiPrecinctChoice(selectedStreetKey, precincts);
      return;
    }

    // Normalise house number: strip leading zeros but preserve suffix (e.g. "12A")
    const normNum = rawNum.toUpperCase().replace(/^0+(\d)/, '$1');

    // Try exact match first
    let precinct = streetHP[normNum];

    // If not found, try stripping non-numeric suffix (e.g. "12A" → "12")
    if (precinct === undefined) {
      const numOnly = normNum.replace(/[^0-9]/g, '');
      precinct = streetHP[numOnly];
    }

    // If still not found, try with original casing variations
    if (precinct === undefined) {
      // Try just the raw number as-is
      precinct = streetHP[rawNum];
    }

    if (precinct !== undefined) {
      // Found exact match
      hideHouseRow();
      clearResults();
      renderMemberList(selectedStreetKey, precinct, rawNum);
    } else {
      // Not found — hide house row, show friendly inline precinct picker
      hideHouseRow();
      clearResults();
      showNotFoundPrecinct(selectedStreetKey, precincts, rawNum);
    }
  }

  // ── Display functions ──────────────────────────────────────

  function showNotFoundPrecinct(streetKey, precincts, houseNum) {
    // Friendly inline precinct picker when house# isn't in our voter data
    // (house may exist but have no registered voters, or be a new address)
    multiArea.innerHTML = `
      <div class="multi-precinct-prompt">
        <h3>Select your precinct for ${toTitleCase(streetKey)}</h3>
        <p>House number <strong>${escapeHtml(houseNum)}</strong> wasn't in our voter records for this street,
           but the street spans multiple precincts. Select yours below, or check the
           <a href="https://www.winchester.us/213/Precinct-Maps" target="_blank" rel="noopener">precinct maps</a>
           to confirm.</p>
        <div class="precinct-btn-group">
          ${precincts.map(p => `<button class="precinct-select-btn" data-precinct="${p}">Precinct ${p}</button>`).join('')}
        </div>
      </div>`;
    multiArea.querySelectorAll('.precinct-select-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = parseInt(btn.getAttribute('data-precinct'), 10);
        multiArea.innerHTML = '';
        renderMemberList(streetKey, p, houseNum);
      });
    });
  }

  function clearResults() {
    statusArea.innerHTML = '';
    multiArea.innerHTML = '';
    resultsArea.innerHTML = '';
    resultsSection.classList.remove('hidden');
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showNotFound(query) {
    hideHouseRow();
    clearResults();
    statusArea.innerHTML = `
      <div class="status-msg error">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <div>
          <strong>Street not found:</strong> "<em>${escapeHtml(query)}</em>"<br>
          <small>Try a shorter version of the street name, or check spelling. Alternatively, use the
          <a href="https://www.sec.state.ma.us/WhereDoIVoteMA/WhereDoIVote" target="_blank" rel="noopener">
          MA Secretary of State voter lookup</a> to find your precinct, then browse
          <a href="https://www.winchestertmma.org/directory/by-precinct-1-8" target="_blank" rel="noopener">
          the TMMA directory</a>.</small>
        </div>
      </div>`;
  }

  function showMultipleStreets(matches, query) {
    hideHouseRow();
    clearResults();
    const limited = matches.slice(0, 8);
    const buttons = limited.map(m =>
      `<button class="precinct-select-btn" data-key="${escapeHtml(m.key)}">${toTitleCase(m.key)}</button>`
    ).join('');
    multiArea.innerHTML = `
      <div class="multi-precinct-prompt">
        <h3>Did you mean…</h3>
        <p>Multiple streets match "<strong>${escapeHtml(query)}</strong>". Select the correct street:</p>
        <div class="precinct-btn-group">${buttons}</div>
      </div>`;
    multiArea.querySelectorAll('.precinct-select-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.getAttribute('data-key');
        streetInput.value = toTitleCase(key);
        multiArea.innerHTML = '';
        handleStreetSelected(key, streets[key]);
      });
    });
  }

  function showMultiPrecinctChoice(streetKey, precincts) {
    multiArea.innerHTML = `
      <div class="multi-precinct-prompt">
        <h3>${toTitleCase(streetKey)} spans multiple precincts</h3>
        <p>We couldn't pinpoint your exact precinct from that house number. Select your precinct below, or check the
           <a href="https://www.winchester.us/213/Precinct-Maps" target="_blank" rel="noopener">precinct maps</a>
           to confirm.</p>
        <div class="precinct-btn-group">
          ${precincts.map(p => `<button class="precinct-select-btn" data-precinct="${p}">Precinct ${p}</button>`).join('')}
        </div>
      </div>`;
    multiArea.querySelectorAll('.precinct-select-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = parseInt(btn.getAttribute('data-precinct'), 10);
        multiArea.innerHTML = '';
        renderMemberList(streetKey, p);
      });
    });
  }

  function renderMemberList(streetKey, precinct, houseNum) {
    // Persist to URL so this result can be bookmarked / shared
    setUrlState({
      street:   streetKey,
      house:    houseNum || null,
      precinct: precinct,
    });
    const members = TMMA_DATA.members[precinct];
    if (!members) {
      statusArea.innerHTML = `<div class="status-msg error">No data found for Precinct ${precinct}.</div>`;
      return;
    }

    const sorted = [...members].sort((a, b) => a.last.localeCompare(b.last));
    const currentYear = new Date().getFullYear();

    const cards = sorted.map(m => {
      const expiring = m.termEnds <= currentYear + 1;
      const indicator = expiring
        ? '<span class="term-indicator expires-soon" title="Term ends ' + m.termEnds + '"></span>'
        : '<span class="term-indicator ok" title="Term ends ' + m.termEnds + '"></span>';
      return `
        <div class="member-card">
          <div class="member-name">${escapeHtml(m.first)} ${escapeHtml(m.last)}</div>
          <div class="member-term">${indicator}Term ends ${m.termEnds}</div>
        </div>`;
    }).join('');

    const addressLabel = houseNum
      ? `${houseNum} ${toTitleCase(streetKey)}`
      : toTitleCase(streetKey);

    resultsArea.innerHTML = `
      <div class="precinct-header">
        <div>
          <div><span class="precinct-badge">Precinct ${precinct}</span></div>
          <div class="precinct-title">Town Meeting Members</div>
          <div class="precinct-meta">
            ${members.length} elected members &middot; ${addressLabel}
          </div>
        </div>
        <div class="precinct-actions">
          <a class="btn-outline" href="https://www.winchestertmma.org/directory/by-precinct-1-8"
             target="_blank" rel="noopener">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            TMMA Directory
          </a>
          <a class="btn-outline" href="https://www.winchester.us/213/Precinct-Maps"
             target="_blank" rel="noopener">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
              <circle cx="12" cy="10" r="3"/>
            </svg>
            Precinct Map
          </a>
        </div>
      </div>
      <p class="search-summary">
        Showing <strong>${members.length} Town Meeting Members</strong> for
        <strong>${escapeHtml(addressLabel)}</strong> in <strong>Precinct ${precinct}</strong>.
        Data as of ${TMMA_DATA.dataAsOf}.
      </p>
      <div class="members-grid">${cards}</div>`;
  }

  // ── Utilities ──────────────────────────────────────────────
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toTitleCase(str) {
    return str.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
  }

  // ── Restore from URL on page load ──────────────────────────
  (function restoreFromUrl() {
    const { street, house, precinct } = getUrlState();
    if (!street || !precinct) return;
    // Validate street exists in data
    const precincts = streets[street];
    if (!precincts) return;
    // Validate precinct is valid for that street
    if (!precincts.includes(precinct)) return;
    // Restore the UI
    streetInput.value = toTitleCase(street);
    if (house) houseInput.value = house;
    selectedStreetKey = street;
    renderMemberList(street, precinct, house || undefined);
  })();

})();
