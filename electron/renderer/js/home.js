// Pantalla de inicio: proyectos y carpetas del espacio de trabajo (como el panel de proyectos de Terrastruct).
import { pickTypology } from './typology.js';
import { call } from './api.js';
import { S, go, setTheme } from './state.js';
import { h, clear, svg, btn, iconBtn, menu, modal, promptBox, confirmBox, toast, errorBox, field, selectInput, textInput, segmented, fmtDate, debounce } from './ui.js';
import { native } from './native.js';

let st = null;            // { data, view: 'all'|'recent'|'fav'|'folder:...', q, sort, mode }

export async function enter(app) {
  st = st || { view: 'all', q: '', sort: 'modified', mode: 'grid', data: null };
  const root = h('div', { class: 'home' });
  app.append(root);
  st.root = root;
  await refresh();
}

export function leave() { return true; }

async function refresh() {
  try { st.data = await call('ws_list', { root: S.root }); } catch (e) { errorBox(e); return; }
  render();
}

function sideItem(label, ic, view, count, cls = '') {
  const b = h('button', { class: `item ${cls} ${st.view === view ? 'on' : ''}`, type: 'button', onclick: () => { st.view = view; render(); } }, svg(ic, 17), h('span', { text: label }),
    count != null ? h('span', { class: 'count', text: count }) : null);
  return b;
}

function folderTree() {
  const { folders, projects } = st.data;
  const out = [];
  const countIn = (p) => projects.filter((x) => x.folder === p || x.folder.startsWith(p + '/')).length;
  const walk = (parent, depth) => {
    for (const f of folders.filter((x) => x.parent === parent)) {
      const it = sideItem(f.name, st.view === `folder:${f.path}` ? 'folder-open' : 'folder', `folder:${f.path}`, countIn(f.path), depth ? `f${Math.min(depth, 2)}` : '');
      it.addEventListener('contextmenu', (e) => { e.preventDefault(); folderMenu(f, null, e); });
      out.push(it);
      walk(f.path, depth + 1);
    }
  };
  walk('', 0);
  return out;
}

function render() {
  const root = st.root;
  clear(root);
  const { projects, folders } = st.data;
  const dark = document.documentElement.dataset.theme === 'dark';
  const side = h('aside', { class: 'side' },
    h('img', { class: 'logo', src: dark ? 'img/logo_dark.png' : 'img/logo.png', alt: 'SteelConPro' }),
    btn('Nuevo proyecto', { icon: 'plus', kind: 'primary lg', onClick: () => newProject() }),
    h('div', { class: 'scroll' },
      h('div', { class: 'nav' },
        sideItem('Todos los proyectos', 'layout-grid', 'all', projects.length),
        sideItem('Recientes', 'clock', 'recent'),
        sideItem('Favoritos', 'star', 'fav', projects.filter((p) => p.favorite).length)),
      h('div', { class: 'nav', style: { marginTop: '14px' } },
        h('div', { class: 'head' }, h('span', { text: 'Carpetas' }), iconBtn('folder-plus', 'Nueva carpeta', () => newFolder(''), { size: 15 })),
        ...folderTree(), folders.length ? null : h('div', { class: 'faint', style: { padding: '4px 10px', fontSize: '12px' }, text: 'Organice sus proyectos en carpetas.' }))),
    h('div', { class: 'nav' },
      h('div', { class: 'head', text: 'Bibliotecas' }),
      h('button', { class: 'item', type: 'button', onclick: async () => (await import('./libraries.js')).openSections() }, svg('shapes', 17), h('span', { text: 'Secciones y Section Designer' })),
      h('button', { class: 'item', type: 'button', onclick: async () => (await import('./libraries.js')).openMaterials() }, svg('database', 17), h('span', { text: 'Materiales' })),
      h('button', { class: 'item', type: 'button', onclick: async () => (await import('./libraries.js')).openTemplates() }, svg('copy', 17), h('span', { text: 'Plantillas' })),
      h('div', { class: 'row', style: { padding: '6px 4px 0', justifyContent: 'space-between' } },
        h('button', { class: 'btn ghost sm', type: 'button', title: S.root, onclick: changeRoot }, svg('folder', 15), h('span', { text: 'Carpeta de trabajo' })),
        iconBtn(dark ? 'sun' : 'moon', 'Tema claro / oscuro', () => { setTheme(dark ? 'light' : 'dark'); render(); }))));

  const list = filtered();
  const title = viewTitle();
  const search = h('div', { class: 'search' }, svg('search', 16), h('input', { class: 'input', type: 'search', placeholder: 'Buscar proyectos', value: st.q,
    oninput: debounce((e) => { st.q = e.target.value; renderContent(); }, 120) }));
  const main = h('main', null,
    h('div', { class: 'topbar' }, h('h1', { text: title }), search, h('div', { class: 'grow' }),
      selectInput({ value: st.sort, options: [{ value: 'modified', label: 'Más recientes' }, { value: 'name', label: 'Nombre' }, { value: 'connections', label: 'Conexiones' }], onChange: (v) => { st.sort = v; renderContent(); }, cls: 'sm' }),
      segmented([{ value: 'grid', icon: 'layout-grid', title: 'Tarjetas' }, { value: 'list', icon: 'list', title: 'Lista' }], st.mode, (v) => { st.mode = v; renderContent(); }),
      btn('Abrir archivo…', { icon: 'upload', onClick: openFile })),
    h('div', { class: 'sub', id: 'home-sub' }),
    h('div', { class: 'content', id: 'home-content' }));
  root.append(side, main);
  renderContent();
}

function viewTitle() {
  if (st.view === 'all') return 'Todos los proyectos';
  if (st.view === 'recent') return 'Recientes';
  if (st.view === 'fav') return 'Favoritos';
  const f = st.view.slice(7);
  return f.split('/').pop();
}

function filtered() {
  let l = [...st.data.projects];
  if (st.view === 'recent') { const r = st.data.recent; l = r.map((p) => l.find((x) => x.path === p)).filter(Boolean); }
  else if (st.view === 'fav') l = l.filter((p) => p.favorite);
  else if (st.view.startsWith('folder:')) { const f = st.view.slice(7); l = l.filter((p) => p.folder === f || p.folder.startsWith(f + '/')); }
  const q = st.q.trim().toLowerCase();
  if (q) l = l.filter((p) => p.name.toLowerCase().includes(q) || p.elements.some((e) => e.toLowerCase().includes(q)));
  if (st.view !== 'recent') {
    if (st.sort === 'name') l.sort((a, b) => a.name.localeCompare(b.name, 'es'));
    else if (st.sort === 'connections') l.sort((a, b) => b.connections - a.connections);
    else l.sort((a, b) => b.modified - a.modified);
  }
  return l;
}

function renderContent() {
  const c = document.getElementById('home-content');
  const sub = document.getElementById('home-sub');
  if (!c) return;
  clear(c); clear(sub);
  const list = filtered();
  const folder = st.view.startsWith('folder:') ? st.view.slice(7) : '';
  sub.append(h('span', { text: `${list.length} proyecto${list.length === 1 ? '' : 's'}` }));
  if (folder) sub.append(h('span', { class: 'faint', text: '·' }), btn('Nueva carpeta aquí', { icon: 'folder-plus', kind: 'ghost sm', onClick: () => newFolder(folder) }),
    btn('Renombrar', { icon: 'pencil', kind: 'ghost sm', onClick: () => renameFolder(folder) }), btn('Eliminar carpeta', { icon: 'trash-2', kind: 'ghost sm', onClick: () => deleteFolder(folder) }));
  if (!list.length) {
    c.append(h('div', { class: 'empty' }, svg('box', 54, 'big'),
      h('h3', { text: st.q ? 'Sin resultados' : 'Todavía no hay proyectos aquí' }),
      h('p', { text: st.q ? 'Pruebe con otra búsqueda.' : 'Cree un proyecto nuevo o abra un archivo .scp existente.' }),
      st.q ? null : h('div', { class: 'row' }, btn('Nuevo proyecto', { icon: 'plus', kind: 'primary', onClick: () => newProject(folder) }), btn('Abrir archivo…', { icon: 'upload', onClick: openFile }))));
    return;
  }
  if (st.mode === 'grid') {
    const g = h('div', { class: 'grid' });
    if (!st.q) g.append(h('div', { class: 'card new', onclick: () => newProject(folder) }, svg('plus', 28), h('b', { text: 'Nuevo proyecto' }), h('span', { class: 'faint', text: 'Conexión en blanco' })));
    for (const p of list) g.append(card(p));
    c.append(g);
  } else {
    const l = h('div', { class: 'list' });
    for (const p of list) l.append(listRow(p));
    c.append(l);
  }
}

function thumb(p) {
  return p.thumb ? h('img', { src: `data:image/png;base64,${p.thumb}`, alt: '' }) : h('span', { class: 'ph' }, svg('box', 40));
}

function card(p) {
  const more = iconBtn('more-horizontal', 'Más acciones', (e) => { e.stopPropagation(); projectMenu(p, more); }, { size: 17 });
  more.classList.add('more');
  const fav = iconBtn('star', p.favorite ? 'Quitar de favoritos' : 'Agregar a favoritos', async (e) => { e.stopPropagation(); await toggleFav(p); }, { size: 16 });
  fav.classList.add('fav'); if (p.favorite) fav.classList.add('on');
  const el = h('div', { class: 'card', onclick: () => open(p), oncontextmenu: (e) => { e.preventDefault(); projectMenu(p, null, e); } },
    h('div', { class: 'thumb' }, thumb(p)), fav, more,
    h('div', { class: 'info' }, h('div', { class: 'name', title: p.name, text: p.name }),
      h('div', { class: 'meta' }, h('span', { text: `${p.connections} conexión${p.connections === 1 ? '' : 'es'}` }), h('span', { class: 'faint', text: '·' }), h('span', { text: fmtDate(p.modified) }),
        p.folder ? h('span', { class: 'chip', text: p.folder.split('/').pop() }) : null)));
  return el;
}

function listRow(p) {
  return h('div', { class: 'li', onclick: () => open(p), oncontextmenu: (e) => { e.preventDefault(); projectMenu(p, null, e); } },
    p.thumb ? h('img', { src: `data:image/png;base64,${p.thumb}`, alt: '' }) : h('span'),
    h('div', null, h('div', { style: { fontWeight: 650 }, text: p.name }), h('div', { class: 'faint', style: { fontSize: '12px' }, text: p.folder || 'Raíz' })),
    h('span', { class: 'muted', text: `${p.connections} conexión${p.connections === 1 ? '' : 'es'}` }), h('span', { class: 'muted', text: fmtDate(p.modified) }),
    h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, iconBtn('star', 'Favorito', async (e) => { e.stopPropagation(); await toggleFav(p); }, { kind: p.favorite ? 'on' : '' }),
      iconBtn('more-horizontal', 'Más', (e) => { e.stopPropagation(); projectMenu(p, e.currentTarget); })));
}

// ------------------------------------------------------------------ acciones
async function open(p) { await go('editor', { path: p.path }); }

async function toggleFav(p) {
  try { await call('ws_favorite', { root: S.root, path: p.path }); await refresh(); } catch (e) { errorBox(e); }
}

function projectMenu(p, anchor, ev) {
  const items = [
    { label: 'Abrir', icon: 'folder-open', onClick: () => open(p) },
    { label: 'Renombrar', icon: 'pencil', onClick: async () => { const n = await promptBox('Nombre del proyecto', p.name, { title: 'Renombrar proyecto' }); if (n) await run(() => call('ws_rename', { root: S.root, path: p.path, name: n })); } },
    { label: 'Duplicar', icon: 'copy', onClick: () => run(() => call('ws_duplicate', { root: S.root, path: p.path })) },
    { label: 'Mover a…', icon: 'folder', onClick: () => moveTo(p) },
    { label: p.favorite ? 'Quitar de favoritos' : 'Agregar a favoritos', icon: 'star', onClick: () => toggleFav(p) },
    '-',
    { label: 'Mostrar en el explorador', icon: 'file', onClick: () => native.showItem(`${S.root}/${p.path}`), disabled: !native.available },
    { label: 'Eliminar', icon: 'trash-2', danger: true, onClick: async () => { if (await confirmBox(`¿Eliminar el proyecto «${p.name}»? No se puede deshacer.`, { danger: true, ok: 'Eliminar', title: 'Eliminar proyecto' })) await run(() => call('ws_delete', { root: S.root, path: p.path })); } },
  ];
  if (anchor) menu(anchor, items, { align: 'right' }); else menu(null, items, { x: ev.clientX, y: ev.clientY });
}

async function run(fn, okMsg) { try { await fn(); await refresh(); if (okMsg) toast(okMsg, 'ok'); } catch (e) { errorBox(e); } }

function folderMenu(f, anchor, ev) {
  menu(null, [{ label: 'Nueva subcarpeta', icon: 'folder-plus', onClick: () => newFolder(f.path) }, { label: 'Renombrar', icon: 'pencil', onClick: () => renameFolder(f.path) },
    { label: 'Eliminar', icon: 'trash-2', danger: true, onClick: () => deleteFolder(f.path) }], { x: ev.clientX, y: ev.clientY });
}

async function newFolder(parent) {
  const n = await promptBox('Nombre de la carpeta', '', { title: 'Nueva carpeta', placeholder: 'Por ejemplo: Edificio A' });
  if (n) await run(() => call('ws_create_folder', { root: S.root, parent, name: n }));
}
async function renameFolder(path) {
  const n = await promptBox('Nombre de la carpeta', path.split('/').pop(), { title: 'Renombrar carpeta' });
  if (!n) return;
  try { const r = await call('ws_rename', { root: S.root, path, name: n }); st.view = `folder:${r.path}`; await refresh(); } catch (e) { errorBox(e); }
}
async function deleteFolder(path) {
  if (!(await confirmBox(`¿Eliminar la carpeta «${path.split('/').pop()}» con todos sus proyectos?`, { danger: true, ok: 'Eliminar', title: 'Eliminar carpeta' }))) return;
  st.view = 'all';
  await run(() => call('ws_delete', { root: S.root, path }));
}

function moveTo(p) {
  const folders = [{ value: '', label: 'Raíz' }, ...st.data.folders.map((f) => ({ value: f.path, label: f.path.replaceAll('/', ' / ') }))];
  let val = p.folder;
  const sel = selectInput({ value: val, options: folders, onChange: (v) => { val = v; } });
  const m = modal({ title: 'Mover proyecto', icon: 'folder', width: 420, body: field('Carpeta de destino', sel),
    footer: [btn('Cancelar', { onClick: () => m.close() }), btn('Mover', { kind: 'primary', onClick: async () => { m.close(); await run(() => call('ws_move', { root: S.root, path: p.path, folder: val })); } })] });
}

async function openFile() {
  const f = await native.openFile([{ name: 'Proyectos de SteelConPro', extensions: ['scp', 'pbase', 'json'] }]);
  if (!f) return;
  try {
    const r = await call('ws_import', { root: S.root, source: f, folder: st.view.startsWith('folder:') ? st.view.slice(7) : '' });
    toast('Proyecto importado al espacio de trabajo', 'ok');
    await go('editor', { path: r.path });
  } catch (e) { errorBox(e); }
}

async function changeRoot() {
  const f = await native.chooseFolder();
  if (!f) return;
  S.root = f;
  try { localStorage.setItem('scp.root', f); } catch (e) { /* */ }
  await refresh();
}

function newProject(folder = '') {
  const u = S.C.units.sets;
  let name = '', unitSet = 'SI (mm, kN, MPa)', fld = folder || (st.view.startsWith('folder:') ? st.view.slice(7) : '');
  const nameInp = textInput({ value: '', placeholder: 'Por ejemplo: Nave industrial — nudo N1', onChange: (v) => { name = v; } });
  nameInp.addEventListener('input', () => { name = nameInp.value; });
  const folders = [{ value: '', label: 'Raíz' }, ...st.data.folders.map((f) => ({ value: f.path, label: f.path.replaceAll('/', ' / ') }))];
  const m = modal({ title: 'Nuevo proyecto', icon: 'plus', width: 460,
    body: h('div', { class: 'col gap-12' }, field('Nombre', nameInp), field('Carpeta', selectInput({ value: fld, options: folders, onChange: (v) => { fld = v; } })),
      field('Unidades', selectInput({ value: unitSet, options: Object.keys(u), onChange: (v) => { unitSet = v; } }), { hint: 'Se pueden cambiar después en el proyecto.' })),
    footer: [btn('Cancelar', { onClick: () => m.close() }), btn('Crear proyecto', { kind: 'primary', icon: 'check', onClick: create })] });
  nameInp.addEventListener('keydown', (e) => { if (e.key === 'Enter') create(); });
  setTimeout(() => nameInp.focus(), 40);
  async function create() {
    name = nameInp.value.trim() || 'Proyecto sin nombre';
    const [ul, uf, us] = u[unitSet];
    const um = { 'kN': 'kN·m', 'kip': 'kip·in', 'tonf': 'tonf·m' }[uf] || 'kN·m';
    try {
      m.close();
      const pick = await pickTypology();
      if (!pick) return;
      const r = await call('ws_create_project', { root: S.root, folder: fld, name, u_len: ul, u_force: uf, u_stress: us, u_moment: um, typology: pick.typology, params: pick.params });
      await go('editor', { path: r.rel });
    } catch (e) { errorBox(e); }
  }
}
