import { call } from './api.js';
import { S, go, setTheme, registerView } from './state.js';
import { errorBox } from './ui.js';
import * as home from './home.js';
import * as editor from './editor.js';

registerView('home', home);
registerView('editor', editor);

async function boot() {
  let theme = 'light';
  try { theme = localStorage.getItem('scp.theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch (e) { /* */ }
  setTheme(theme);
  try {
    S.C = await call('constants');
    let root = '';
    try { root = localStorage.getItem('scp.root') || ''; } catch (e) { /* */ }
    if (!root) root = (await call('ws_default')).root;
    S.root = root;
    const q = new URLSearchParams(location.search);
    if (q.get('open')) await go('editor', { path: q.get('open'), abs: true });
    else await go('home');
  } catch (e) { errorBox(e); document.getElementById('app').textContent = 'No se pudo iniciar: ' + e.message; }
}
window.addEventListener('unhandledrejection', (ev) => errorBox(ev.reason));
boot();
