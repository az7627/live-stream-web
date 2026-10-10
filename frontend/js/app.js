/**
 * Shared utilities used by all pages.
 */

const API_BASE = window.location.pathname.startsWith('/live') ? '/live' : '';

/** Wrapper around fetch that throws on non-2xx with the JSON error message. */
async function api(path, { signal, ...opts } = {}) {
  const url = API_BASE + path;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    signal,
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return body;
}

async function apiPost(path, data) {
  return api(path, { method: 'POST', body: JSON.stringify(data) });
}

/** Escape HTML entities (XSS prevention). */
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
