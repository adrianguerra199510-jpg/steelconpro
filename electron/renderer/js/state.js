// Estado global de la aplicacion y navegacion entre pantallas (inicio / editor).
export const S = { C: null, root: '', theme: 'light', view: null, views: {} };

export function registerView(name, mod) { S.views[name] = mod; }

export async function go(name, params = {}) {
  if (S.view && S.view.leave) { const ok = await S.view.leave(); if (ok === false) return; }
  const app = document.getElementById('app');
  app.replaceChildren();
  const v = S.views[name];
  S.view = v;
  await v.enter(app, params);
}

export function setTheme(t) {
  S.theme = t;
  document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light';
  try { localStorage.setItem('scp.theme', t); } catch (e) { /* sin almacenamiento */ }
  window.dispatchEvent(new CustomEvent('scp-theme', { detail: t }));
}
