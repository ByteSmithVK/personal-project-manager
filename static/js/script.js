// script.js
// ---------------------------------------------------------------
// Handles:
//  1. Light/dark theme toggle (persisted in localStorage)
//  2. Styled delete confirmation dialog
// ---------------------------------------------------------------

(function () {
  const STORAGE_KEY = 'ppm-theme';
  const root = document.documentElement;
  const toggleBtn = document.getElementById('theme-toggle');

  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
  }

  function getPreferredTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') {
      return saved;
    }
    // Default to light theme always (pastel theme).
    return 'light';
  }

  // Apply the saved/preferred theme as early as possible.
  applyTheme(getPreferredTheme());

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      const current = root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem(STORAGE_KEY, next);
    });
  }
})();


// ---------------------------------------------------------------
// Styled delete confirmation dialog
// ---------------------------------------------------------------

function confirmDelete(message) {
  // Build modal overlay
  const overlay = document.createElement('div');
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'z-index:9999',
    'background:rgba(15,23,42,0.55)', 'display:flex',
    'align-items:center', 'justify-content:center',
    'padding:20px', 'backdrop-filter:blur(2px)'
  ].join(';');

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const bg      = isDark ? '#1e293b' : '#ffffff';
  const text     = isDark ? '#e2e8f0' : '#1a2640';
  const border   = isDark ? '#334155' : '#d0d9e4';
  const muted    = isDark ? '#94a3b8' : '#5a6e85';

  overlay.innerHTML = `
    <div style="
      background:${bg};
      border:1px solid ${border};
      border-radius:12px;
      padding:28px 32px;
      max-width:420px;
      width:100%;
      box-shadow:0 20px 60px rgba(0,0,0,0.35);
      text-align:center;
    ">
      <div style="font-size:2.2rem;margin-bottom:12px;">🗑️</div>
      <h3 style="margin:0 0 8px;color:${text};font-size:1.1rem;">Confirm Delete</h3>
      <p style="margin:0 0 24px;color:${muted};font-size:0.9rem;line-height:1.5;">${message}</p>
      <div style="display:flex;gap:10px;justify-content:center;">
        <button id="ppm-cancel" style="
          padding:9px 22px;border-radius:8px;border:1px solid ${border};
          background:transparent;color:${muted};font-weight:700;
          font-size:0.88rem;cursor:pointer;
        ">Cancel</button>
        <button id="ppm-confirm" style="
          padding:9px 22px;border-radius:8px;border:none;
          background:#e11d48;color:#fff;font-weight:700;
          font-size:0.88rem;cursor:pointer;
        ">Yes, Delete</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  return new Promise((resolve) => {
    overlay.querySelector('#ppm-cancel').addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(false);
    });
    overlay.querySelector('#ppm-confirm').addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(true);
    });
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        document.body.removeChild(overlay);
        resolve(false);
      }
    });
  });
}

// Intercept all delete form submissions and show the custom dialog
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      const msg = form.getAttribute('data-confirm');
      const confirmed = await confirmDelete(msg);
      if (confirmed) {
        form.submit();
      }
    });
  });
});
