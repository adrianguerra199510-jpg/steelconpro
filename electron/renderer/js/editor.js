// Editor de un proyecto: barra superior, árbol (miembros / operaciones / cargas), visor 3D y resultados por operación.
import { call, latest } from './api.js';
import { S, go } from './state.js';
import { UnitSet } from './units.js';
import { h, svg, btn, iconBtn, menu, modal, toast, errorBox, confirmBox, promptBox, tabs, chip, dcBar, spinner, debounce, clear, selectInput, segmented } from './ui.js';
import { Viewer } from './viewer.js';
import { native } from './native.js';
import { openOperation, OP_ICON, opColor, groupOf } from './opdialog.js';
import { openMember, openLoads, openProject, renameRefs } from './editdialogs.js';
import { openSections, openMaterials, openTemplates } from './libraries.js';

const join = (a, b) => `${a.replace(/[\\/]+$/, '')}/${b}`;

export const E = {
  path: '', conns: [], idx: 0, res: null, stale: true, viewer: null, ui: {}, undo: [], redo: [], femView: false, sel: null, dirty: false,
  conn() { return this.conns[this.idx]; },
  us() { return S.us; },
};
window.__E = E;                                     // depuración y pruebas

// ---------------------------------------------------------------------------------------------------- ciclo de vida
export async function enter(app, params) {
  E.abs = params.abs ? params.path : join(S.root, params.path);
  E.rel = params.abs ? null : params.path;
  let book;
  try { book = await call('book_load', { path: E.abs }); } catch (e) { errorBox(e); await go('home'); return; }
  E.conns = book.connections; E.idx = 0; E.res = null; E.stale = true; E.undo = []; E.redo = []; E.femView = false; E.sel = null; E.job = null;
  if (book.skipped && book.skipped.length) toast(`${book.skipped.length} conexión(es) de versiones anteriores no se pudieron abrir.`, 'info', 7000);
  if (E.rel) call('ws_touch', { root: S.root, path: E.rel }).catch(() => {});
  applyUnits();
  build(app);
  await refreshAll();
  window.addEventListener('keydown', onKey);
}

export async function leave() {
  window.removeEventListener('keydown', onKey);
  save.cancel();
  if (E.dirty) await saveNow();
  if (E.viewer) { E.viewer.dispose(); E.viewer = null; }
  if (E.pollTimer) clearInterval(E.pollTimer);
  return true;
}

function onKey(ev) {
  const mod = ev.ctrlKey || ev.metaKey;
  if (mod && ev.key.toLowerCase() === 'z' && !ev.shiftKey) { if (!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { ev.preventDefault(); undo(); } }
  else if (mod && (ev.key.toLowerCase() === 'y' || (ev.key.toLowerCase() === 'z' && ev.shiftKey))) { if (!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { ev.preventDefault(); redo(); } }
  else if (mod && ev.key.toLowerCase() === 's') { ev.preventDefault(); saveNow(true); }
  else if (ev.key === 'Delete' && E.sel && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !document.querySelector('.modal-back')) deleteSelected();
}

// ---------------------------------------------------------------------------------------------------- unidades y utilidades del modelo
function applyUnits() {
  const c = E.conn();
  S.us = new UnitSet(S.C, c.u_len, c.u_force, c.u_stress, c.u_moment);
  E.us = () => S.us;
  if (E.ui.root) { refreshAll(false); }
}
E.applyUnits = () => { applyUnits(); markDirty(); };

E.replaceConn = (c) => { E.conns[E.idx] = c; };
E.snap = () => { E.undo.push(JSON.stringify(E.conns)); if (E.undo.length > 60) E.undo.shift(); E.redo = []; updateUndo(); };
E.dropSnap = () => { E.undo.pop(); updateUndo(); };
E.refreshTree = () => renderTree();
E.renameElement = (old, nw) => { renameRefs(E.conn().node, old, nw); renderTree(); };

// Vuelve al estado anterior a la última acción (sin dejarlo para «rehacer»): se usa al cancelar una ventana de operación nueva.
function revertSnap() {
  if (!E.undo.length) return;
  E.conns = JSON.parse(E.undo.pop());
  E.idx = Math.min(E.idx, E.conns.length - 1);
  E.sel = null;
  applyUnits(); refreshAll(); markDirty(); updateUndo();
}

function undo() {
  if (!E.undo.length) return;
  E.redo.push(JSON.stringify(E.conns));
  E.conns = JSON.parse(E.undo.pop());
  E.idx = Math.min(E.idx, E.conns.length - 1);
  afterRestore();
}
function redo() {
  if (!E.redo.length) return;
  E.undo.push(JSON.stringify(E.conns));
  E.conns = JSON.parse(E.redo.pop());
  afterRestore();
}
function afterRestore() { applyUnits(); E.sel = null; refreshAll(); markDirty(); updateUndo(); }
function updateUndo() {
  if (!E.ui.undo) return;
  E.ui.undo.disabled = !E.undo.length; E.ui.redo.disabled = !E.redo.length;
}

// ---------------------------------------------------------------------------------------------------- cambios, guardado y recálculo
const refreshMesh = latest(async () => {
  const data = await call('mesh', { connection: E.conn() });
  return data;
});
const runMesh = debounce(async () => {
  if (!E.viewer || E.femView) return;
  try {
    const data = await refreshMesh();
    if (!data) return;
    E.mesh = data;
    E.viewer.setModel(data, { keepView: true });
    E.viewer.setDimTexts((v) => S.us.q('L', v));
    highlight();
    renderNotes(data.notes || []);
  } catch (e) { setStatus(`No se pudo dibujar el modelo: ${e.message}`, true); }
}, 90);

const verify = latest(async () => call('verify', { connection: E.conn() }));
const runVerify = debounce(async () => {
  setVerdict('calc');
  try {
    const r = await verify();
    if (!r) return;
    E.res = r; E.stale = false;
    renderResults(); renderTree(); setVerdict();
  } catch (e) { E.res = null; setVerdict('error', e.message); renderResults(e.message); }
}, 700);

function markDirty() { E.dirty = true; setStatus('Cambios sin guardar…'); save(); }
const save = debounce(() => saveNow(), 1200);
async function saveNow(manual) {
  save.cancel();
  try {
    setStatus('Guardando…');
    await call('book_save', { path: E.abs, connections: E.conns });
    E.dirty = false; setStatus(manual ? 'Guardado' : 'Guardado automáticamente');
    if (manual) toast('Proyecto guardado', 'ok', 1800);
  } catch (e) { errorBox(e); setStatus('No se pudo guardar', true); }
}

E.changed = (opts = {}) => {
  markDirty();
  E.stale = true;
  if (opts.structure) renderTree();
  if (opts.geometry !== false) runMesh();
  runVerify();
  setVerdict('stale');
};

E.removeOperation = async (index, { silent = false } = {}) => {
  const r = await call('delete_operation', { connection: E.conn(), index });
  E.replaceConn(r.connection);
  if (!silent) { E.changed({ structure: true }); if (r.removed.length > 1) toast(`Se quitaron ${r.removed.length} operaciones que dependían de ella.`, 'info', 5000); }
  return r.removed;
};

// ---------------------------------------------------------------------------------------------------- estructura de la pantalla
function build(app) {
  const ui = E.ui = {};
  const root = h('div', { class: 'editor' });
  ui.root = root;
  app.append(root);

  // ---- barra superior
  ui.title = h('div', { class: 'title' }, h('b', { text: '' }), h('small', { text: '' }));
  ui.title.style.cursor = 'pointer'; ui.title.title = 'Datos del proyecto y unidades'; ui.title.onclick = () => openProject(E);
  ui.connTabs = h('div', { class: 'conn-tabs' });
  ui.undo = iconBtn('undo', 'Deshacer (Ctrl+Z)', undo); ui.redo = iconBtn('redo', 'Rehacer (Ctrl+Y)', redo);
  ui.verdict = h('span', { class: 'big-chip idle' });
  ui.calc = btn('Calcular', { icon: 'play', kind: 'primary', onClick: () => { runVerify.flush(); } });
  const libBtn = btn('Bibliotecas', { icon: 'library', onClick: (e) => menu(e.currentTarget, [
    { label: 'Secciones y Section Designer', icon: 'shapes', onClick: () => openSections(E) }, { label: 'Materiales', icon: 'database', onClick: () => openMaterials(E) },
    { label: 'Plantillas de conexión', icon: 'copy', onClick: () => openTemplates(E) }]) });
  const repBtn = btn('Informe', { icon: 'file-text', onClick: (e) => menu(e.currentTarget, [
    { label: 'Informe PDF…', icon: 'file-down', onClick: () => exportReport('pdf') }, { label: 'Informe Word (.docx)…', icon: 'file-down', onClick: () => exportReport('docx') },
    { label: 'Exportar STEP…', icon: 'box', onClick: exportStep }, '-', { label: 'Guardar proyecto', icon: 'save', hint: 'Ctrl+S', onClick: () => saveNow(true) }]) });
  const top = h('div', { class: 'ed-top' },
    iconBtn('arrow-left', 'Volver al inicio', () => go('home')), ui.title, h('div', { class: 'vr' }), ui.connTabs, h('span', { class: 'grow' }),
    ui.undo, ui.redo, h('div', { class: 'vr' }), libBtn, repBtn, ui.calc);

  // ---- panel izquierdo (árbol)
  ui.tree = h('div', { class: 'scroll' });
  const addBtn = btn('Agregar operación', { icon: 'plus', kind: 'primary', onClick: (e) => addMenu(e.currentTarget) });
  addBtn.classList.add('add-menu-btn');
  const left = h('div', { class: 'panel left' }, ui.tree, h('div', { style: { padding: '8px 0 12px', borderTop: '1px solid var(--border)' } }, addBtn));

  // ---- visor
  ui.vhost = h('div', { class: 'viewer' });
  ui.note = h('div', { class: 'vnote' });
  const vtool = h('div', { class: 'vtool' },
    h('div', { class: 'group' }, ...[['iso', 'Isométrica'], ['top', 'Planta'], ['front', 'Frontal'], ['side', 'Lateral']].map(([v, t]) => h('button', { class: 'icon-btn txt', type: 'button', title: t, onclick: () => E.viewer.setView(v), text: t.slice(0, 3) === 'Iso' ? 'Iso' : t }))),
    h('div', { class: 'group' }, iconBtn('crosshair', 'Ajustar a la pantalla', () => E.viewer.fit()), ui.dimBtn = iconBtn('ruler', 'Cotas', () => { const on = !E.viewer.showDims; E.viewer.setDims(on); ui.dimBtn.classList.toggle('on', on); }),
      ui.tagBtn = iconBtn('tag', 'Etiquetas', () => { const on = !E.viewer.showLabels; E.viewer.setLabels(on); ui.tagBtn.classList.toggle('on', on); }),
      ui.hwBtn = iconBtn('bolt', 'Mostrar placas, pernos y soldaduras', () => { const nd = E.conn().node; nd.show_hw = !nd.show_hw; ui.hwBtn.classList.toggle('on', nd.show_hw); E.changed({}); }),
      iconBtn('download', 'Guardar imagen', async () => { const f = await native.saveFile('conexion.png', [{ name: 'Imagen PNG', extensions: ['png'] }]); if (f) { try { await call('save_png', { path: f, data: E.viewer.screenshot() }); toast('Imagen guardada', 'ok'); } catch (e) { errorBox(e); } } })));
  ui.tagBtn.classList.add('on');
  ui.fembar = h('div', { class: 'vhud' });
  const center = h('div', { class: 'viewer-wrap' }, ui.vhost, vtool, ui.note, ui.fembar);

  // ---- panel derecho (resultados)
  ui.right = h('div', { class: 'panel right' });
  const body = h('div', { class: 'ed-body' }, left, center, ui.right);

  ui.status = h('span', { text: '' });
  ui.units = h('span', { class: 'grow', style: { textAlign: 'right' } });
  const bar = h('div', { class: 'statusbar' }, ui.status, ui.units);
  root.append(top, body, bar);

  E.viewer = new Viewer(ui.vhost, { onPick: (name) => pickPart(name) });
  buildRight();
}

function setStatus(t, bad) { if (E.ui.status) { E.ui.status.textContent = t; E.ui.status.style.color = bad ? 'var(--bad)' : ''; } }

function renderNotes(notes) {
  const n = E.ui.note; if (!n) return;
  clear(n);
  for (const t of notes.slice(0, 3)) n.append(h('div', { class: 'warn-row', style: { marginBottom: '4px' } }, svg('alert-triangle', 15), h('span', { text: t })));
}

// ---------------------------------------------------------------------------------------------------- refresco completo
async function refreshAll(rebuildRight = true) {
  const c = E.conn();
  const t = E.ui.title;
  t.firstChild.textContent = c.name || 'Proyecto sin nombre';
  t.lastChild.textContent = `${c.element || ''}${c.author ? ' · ' + c.author : ''}`;
  E.ui.units.textContent = `${c.u_len} · ${c.u_force} · ${c.u_stress}`;
  E.ui.hwBtn.classList.toggle('on', c.node.show_hw);
  renderConnTabs(); renderTree(); updateUndo();
  if (rebuildRight) buildRight();
  E.stale = true; setVerdict('stale');
  runMesh.flush(); runVerify();
}

function renderConnTabs() {
  const box = E.ui.connTabs; clear(box);
  E.conns.forEach((c, i) => {
    const b = h('button', { class: `conn-tab ${i === E.idx ? 'on' : ''}`, type: 'button', onclick: () => switchConn(i), oncontextmenu: (e) => { e.preventDefault(); connMenu(i, e); } }, svg('component', 15), h('span', { text: c.element || `CN-${i + 1}` }));
    box.append(b);
  });
  box.append(iconBtn('plus', 'Nueva conexión en este proyecto', async () => {
    E.snap();
    const c0 = E.conn();
    const nc = await call('connection_new', { n: E.conns.length + 1, name: c0.name, u_len: c0.u_len, u_force: c0.u_force, u_stress: c0.u_stress, u_moment: c0.u_moment });
    E.conns.push(nc); markDirty(); switchConn(E.conns.length - 1);
  }));
}
function connMenu(i, e) {
  menu(null, [
    { label: 'Renombrar…', icon: 'pencil', onClick: async () => { const v = await promptBox('Identificador', E.conns[i].element, { title: 'Renombrar conexión' }); if (v) { E.snap(); E.conns[i].element = v; markDirty(); refreshAll(false); } } },
    { label: 'Duplicar', icon: 'copy', onClick: () => { E.snap(); const c = JSON.parse(JSON.stringify(E.conns[i])); c.element = `${c.element}-copia`; E.conns.splice(i + 1, 0, c); markDirty(); switchConn(i + 1); } },
    { label: 'Eliminar', icon: 'trash', danger: true, disabled: E.conns.length < 2, onClick: async () => { if (await confirmBox(`¿Eliminar la conexión ${E.conns[i].element}?`, { danger: true, ok: 'Eliminar' })) { E.snap(); E.conns.splice(i, 1); E.idx = Math.min(E.idx, E.conns.length - 1); markDirty(); switchConn(E.idx); } } }], { x: e.clientX, y: e.clientY });
}
function switchConn(i) {
  E.idx = i; E.sel = null; E.res = null; E.femView = false; applyUnits(); refreshAll();
}

// ---------------------------------------------------------------------------------------------------- árbol
const SHORT = (k) => k.replace(/ \(.*\)$/, '');
function opTitle(o) {
  const K = S.C.op;
  switch (o.kind) {
    case K.PLATE: return `${o.name || 'Placa'} · ${o.role}`;
    case K.BOLTS: return `Pernos en ${o.parent}`;
    case K.FILLET: return `Soldadura · ${(o.targets || []).join(', ') || '—'}`;
    case K.CUT: case K.COPE: return `Corte · ${(o.targets && o.targets.length ? o.targets : [o.member]).join(', ')}`;
    case K.BASE: return `Placa base · ${o.member || E.conn().node.main_name}`;
    default: return `${SHORT(o.kind)} · ${o.member}`;
  }
}
function opSub(o) {
  const K = S.C.op;
  if (o.kind === K.PLATE) return `sobre ${o.parent} · ${o.face}${o.attach ? ' · ' + o.attach.toLowerCase() : ''}`;
  if (o.kind === K.BOLTS) return `${o.rows}×${o.cols} ${o.bolt_size}" ${o.bolt_grade}`;
  if (o.kind === K.FILLET) return `filete ${S.us.q('L', o.weld_size)}`;
  return groupOf(o.kind);
}
function opRatio(i) {
  if (!E.res || E.stale) return null;
  let max = null;
  for (const c of E.res.checks) {
    const m = /^(\d+)\./.exec(c.group || '');
    if (m && parseInt(m[1], 10) - 1 === i && !c.skip) max = Math.max(max ?? 0, c.ratio);
  }
  return max;
}

function renderTree() {
  const box = E.ui.tree; if (!box) return;
  const nd = E.conn().node;
  const K = S.C.op;
  const scroll = box.scrollTop;
  clear(box);
  const item = ({ ic, color, name, sub, sel, star, onClick, onDbl, acts, ratio, depth = 0 }) => {
    const row = h('div', { class: `tree-item ${sel ? 'sel' : ''}`, onclick: onClick, ondblclick: onDbl },
      color ? h('span', { class: 'dot', style: { background: color } }) : svg(ic || 'component', 16),
      star ? h('span', { class: 'star', title: 'Miembro principal' }, svg('star', 14)) : null,
      h('div', { class: 'grow', style: { minWidth: 0 } }, h('div', { class: 'name', text: name }), sub ? h('div', { class: 'sub', text: sub }) : null),
      ratio != null ? dcBar(ratio) : null,
      h('div', { class: 'acts' }, ...(acts || [])));
    return row;
  };
  // ---- miembros
  const sec = (title, ic, action) => h('div', { class: 'ph' }, svg(ic, 15), h('h3', { text: title }), action || null);
  box.append(sec('Miembros', 'component', iconBtn('plus', 'Agregar miembro', addMember)));
  const members = [{ name: nd.main_name, shape: nd.main_shape, main: true }, ...nd.members.map((m) => ({ name: m.name, shape: m.shape }))];
  const ml = h('div', { class: 'sect' });
  for (const m of members) ml.append(item({ ic: 'component', name: m.name, sub: m.shape, star: m.main, sel: E.sel === `m:${m.name}`,
    onClick: () => select(`m:${m.name}`), onDbl: () => openMember(E, m.name),
    acts: [iconBtn('pencil', 'Editar', (e) => { e.stopPropagation(); openMember(E, m.name); })] }));
  box.append(ml);
  // ---- operaciones
  box.append(sec('Operaciones', 'wrench'));
  const ol = h('div', { class: 'sect' });
  const ops = nd.operations;
  const parentOf = (o) => (o.parent && ops.findIndex((p) => p.kind === K.PLATE && p.name === o.parent) >= 0 && o.kind !== K.PLATE ? o.parent : (o.kind === K.PLATE ? o.parent : ''));
  const plateIdx = (name) => ops.findIndex((p) => p.kind === K.PLATE && p.name === name);
  const parentIndex = (o) => { const p = o.parent ? plateIdx(o.parent) : -1; return p >= 0 ? p : -1; };
  const children = (i) => ops.map((o, j) => [o, j]).filter(([o, j]) => j !== i && parentIndex(o) === i);
  const draw = (o, i, depth) => {
    const node = h('div');
    node.append(item({ ic: OP_ICON[o.kind] || 'box', color: opColor(o.kind), name: `${i + 1}. ${opTitle(o)}`, sub: opSub(o), sel: E.sel === `o:${i}`, ratio: opRatio(i),
      onClick: () => select(`o:${i}`), onDbl: () => editOperation(i),
      acts: [iconBtn('pencil', 'Editar', (e) => { e.stopPropagation(); editOperation(i); }), iconBtn('trash', 'Eliminar', (e) => { e.stopPropagation(); deleteOperation(i); })] }));
    const kids = o.kind === K.PLATE ? children(i) : [];
    if (kids.length) node.append(h('div', { class: 'tree-children' }, kids.map(([c, j]) => draw(c, j, depth + 1))));
    return node;
  };
  ops.forEach((o, i) => { if (parentIndex(o) < 0) ol.append(draw(o, i, 0)); });
  if (!ops.length) ol.append(h('p', { class: 'muted', style: { padding: '4px 10px 8px', fontSize: '12.5px' }, text: 'Aún no hay operaciones. Agregue una placa, pernos, una soldadura, un corte o una placa base.' }));
  box.append(ol);
  // ---- cargas
  box.append(sec('Cargas', 'zap', iconBtn('pencil', 'Editar cargas', () => openLoads(E))));
  const ll = h('div', { class: 'sect' });
  if (nd.loads.length) for (const l of nd.loads) ll.append(item({ ic: 'zap', name: l.case, sub: l.member, onClick: () => openLoads(E) }));
  else ll.append(h('p', { class: 'muted', style: { padding: '4px 10px 8px', fontSize: '12.5px' }, text: 'Sin casos de carga del nudo. Las cargas de la placa base se escriben en su operación.' }));
  box.append(ll);
  box.scrollTop = scroll;
}

function select(sel) {
  E.sel = sel; renderTree(); highlight();
  if (sel && sel.startsWith('o:')) scrollToGroup(parseInt(sel.slice(2), 10));
}
function highlight() {
  if (!E.viewer) return;
  const nd = E.conn().node;
  const names = [];
  if (E.sel && E.sel.startsWith('m:')) names.push(E.sel.slice(2));
  else if (E.sel && E.sel.startsWith('o:')) {
    const o = nd.operations[parseInt(E.sel.slice(2), 10)];
    if (o) {
      const K = S.C.op;
      if (o.kind === K.PLATE) names.push(o.name, o.parent);
      else if (o.kind === K.BOLTS) names.push(o.parent, ...(o.targets || []));
      else if (o.kind === K.FILLET) names.push(...(o.targets || []));
      else if (o.kind === K.CUT) names.push(...(o.targets || []));
      else if (o.kind === K.COPE) names.push(...(o.targets && o.targets.length ? o.targets : [o.member]));
      else if (o.kind === K.BASE) names.push(o.member || nd.main_name);
      else names.push(o.member);
    }
  }
  E.viewer.select(names.filter(Boolean));
}
function pickPart(name) {
  const nd = E.conn().node;
  if (!name) { E.sel = null; renderTree(); highlight(); return; }
  if (name === nd.main_name || nd.members.some((m) => m.name === name)) return select(`m:${name}`);
  const oi = nd.operations.findIndex((o) => o.name === name);
  if (oi >= 0) return select(`o:${oi}`);
  const part = E.viewer.parts.find((p) => p.name === name);
  if (part && part.label) setStatus(part.label);
}

// ---------------------------------------------------------------------------------------------------- miembros y operaciones
async function addMember() {
  try {
    E.snap();
    const r = await call('new_member', { connection: E.conn() });
    E.conn().node.members.push(r.member);
    E.changed({ structure: true });
    select(`m:${r.member.name}`);
    openMember(E, r.member.name);
  } catch (e) { errorBox(e); }
}

function addMenu(anchor) {
  const C = S.C;
  const items = [];
  for (const [title, kinds] of C.ops.groups) {
    items.push({ header: title });
    for (const k of kinds) items.push({ label: k, icon: OP_ICON[k] || 'box', onClick: () => createOperation(k) });
  }
  const m = menu(anchor, items);
  m.classList.add('wide');
}

async function createOperation(kind) {
  const C = S.C;
  const nd = E.conn().node;
  const K = C.op;
  const params = {};
  if (C.ops.connection.includes(kind) || kind === K.COPE || kind === K.CONT) {
    if (!nd.members.length) { toast('Agregue primero un miembro conectado al principal.', 'info', 5000); return; }
    const sel = E.sel && E.sel.startsWith('m:') ? E.sel.slice(2) : '';
    params.member = nd.members.find((m) => m.name === sel)?.name || nd.members[0].name;
  } else if (kind === K.BASE && nd.operations.some((o) => o.kind === K.BASE)) {
    toast('La conexión ya tiene una placa base: edítela o elimínela para cambiarla.', 'info', 5000); return;
  } else if (kind === K.BOLTS || kind === K.FILLET) {
    const plates = nd.operations.filter((o) => o.kind === K.PLATE);
    const last = plates[plates.length - 1];
    if (last && kind === K.BOLTS) { params.parent = last.name; params.targets = [last.parent]; params.pl_s = last.pl_L / 2; params.pl_u = 0; }
    if (last && kind === K.FILLET) params.targets = [last.name];
  }
  E.snap();
  try {
    const before = nd.operations.length;
    const r = await call('add_operation', { connection: E.conn(), kind, params });
    E.replaceConn(r.connection);
    E.sel = `o:${r.index}`;
    if (E.conn().node.operations.length <= before && kind !== K.BASE) toast(`La nueva operación reemplaza la conexión que ya tenía «${params.member}».`, 'info', 5000);
    E.changed({ structure: true });
    const ok = await openOperation(E, r.index, { isNew: true });
    if (!ok) { revertSnap(); return; }
    E.changed({ structure: true });
    renderTree();
  } catch (e) { E.dropSnap(); errorBox(e); }
}

async function editOperation(i) {
  E.snap();
  const before = JSON.stringify(E.conn());
  await openOperation(E, i, {});
  if (JSON.stringify(E.conn()) === before) E.dropSnap();
  else E.changed({ structure: true });
  renderTree();
}

async function deleteOperation(i) {
  const nd = E.conn().node;
  const o = nd.operations[i];
  let deps = [];
  if (o.kind === S.C.op.PLATE) { try { deps = (await call('dependents', { connection: E.conn(), name: o.name })).operations.map((j) => `${j + 1}. ${opTitle(nd.operations[j])}`); } catch (e) { /* sin dependientes */ } }
  const msg = `¿Eliminar la operación «${opTitle(o)}»?`;
  const detail = deps.length ? `También se eliminarán las operaciones que dependen de esta placa: ${deps.join(', ')}.` : '';
  if (!(await confirmBox(msg, { danger: true, ok: 'Eliminar', detail }))) return;
  E.snap();
  try { await E.removeOperation(i); E.sel = null; highlight(); } catch (e) { E.dropSnap(); errorBox(e); }
}
function deleteSelected() {
  if (E.sel && E.sel.startsWith('o:')) deleteOperation(parseInt(E.sel.slice(2), 10));
}

// ---------------------------------------------------------------------------------------------------- veredicto
function setVerdict(state, msg) {
  const v = E.ui.verdict;
  if (!v) return;
  const r = E.res;
  let cls = 'idle', txt = 'Sin calcular', ic = 'circle-help';
  if (state === 'calc') { cls = 'idle'; txt = 'Calculando…'; ic = 'loader'; }
  else if (state === 'error') { cls = 'bad'; txt = msg || 'Error'; ic = 'circle-alert'; }
  else if (r && !E.stale && state !== 'stale' && !r.checks.length) { cls = 'idle'; txt = 'Sin verificaciones'; ic = 'circle-help'; }
  else if (r && !E.stale && state !== 'stale') { cls = r.ok ? 'ok' : 'bad'; txt = `${r.ok ? 'CUMPLE' : 'NO CUMPLE'} · D/C máx ${r.max_ratio.toFixed(3)}`; ic = r.ok ? 'check' : 'circle-alert'; }
  else if (r) { cls = 'stale'; txt = `Desactualizado · último D/C ${r.max_ratio.toFixed(3)}`; ic = 'refresh-cw'; }
  v.className = `big-chip ${cls}`; v.replaceChildren(svg(ic, 16), h('span', { text: txt }));
  if (E.ui.vbadge) { E.ui.vbadge.className = `big-chip ${cls}`; E.ui.vbadge.replaceChildren(svg(ic, 16), h('span', { text: txt })); }
}

// ---------------------------------------------------------------------------------------------------- panel derecho
function buildRight() {
  const right = E.ui.right; clear(right);
  const hasBase = E.conn().node.operations.some((o) => o.kind === S.C.op.BASE);
  E.ui.vbadge = h('span', { class: 'big-chip idle' });
  const items = [
    { id: 'res', label: 'Resultados', icon: 'check', render: () => { E.ui.resBox = h('div', { class: 'scroll', style: { padding: '0 0 12px' } }); renderResults(); return E.ui.resBox; } },
    { id: 'mem', label: 'Memoria', icon: 'file-text', render: () => { E.ui.memBox = h('div', { class: 'scroll memory' }); renderMemory(); return E.ui.memBox; } },
  ];
  if (hasBase) items.push({ id: 'fem', label: 'FEM', icon: 'cpu', render: () => { E.ui.femBox = h('div', { class: 'scroll', style: { padding: '8px 12px' } }); renderFem(); return E.ui.femBox; } });
  const t = tabs(items, { active: E.ui.rtab && items.some((i) => i.id === E.ui.rtab) ? E.ui.rtab : 'res', cls: 'pill', onChange: (id) => { E.ui.rtab = id; } });
  E.ui.rtabs = t;
  right.append(h('div', { style: { padding: '10px 12px 4px', display: 'flex', gap: '8px', alignItems: 'center' } }, E.ui.vbadge), t);
  t.style.padding = '0 8px';
  setVerdict();
}

function scrollToGroup(i) {
  if (!E.ui.rtabs) return;
  E.ui.rtabs.show('res');
  const el = E.ui.resBox && E.ui.resBox.querySelector(`[data-op="${i}"]`);
  if (el) { el.classList.remove('closed'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); el.animate([{ background: 'var(--brand-50)' }, { background: 'transparent' }], { duration: 1200 }); }
}

function renderResults(err) {
  const box = E.ui.resBox; if (!box) return;
  clear(box);
  const r = E.res;
  const us = S.us;
  if (err) { box.append(h('div', { class: 'warns' }, h('div', { class: 'warn-row fatal' }, svg('circle-alert', 15), h('span', { text: err })))); return; }
  if (!r) { box.append(h('div', { style: { padding: '16px' } }, spinner('Calculando…'))); return; }
  box.append(h('div', { class: 'kpis', style: { margin: '6px 0 12px' } },
    h('div', { class: 'kpi' }, h('div', { class: 'k', text: 'D/C máximo' }), h('div', { class: 'v', text: r.max_ratio.toFixed(3) })),
    h('div', { class: 'kpi' }, h('div', { class: 'k', text: 'Gobierna' }), h('div', { class: 'v', style: { fontSize: '12px' }, text: r.governing || '—' })),
    h('div', { class: 'kpi' }, h('div', { class: 'k', text: 'Verificaciones' }), h('div', { class: 'v', text: String(r.checks.filter((c) => !c.skip).length) }))));
  if (r.warnings && r.warnings.length) box.append(h('div', { class: 'warns' }, r.warnings.map((w) => h('div', { class: `warn-row ${/^(ERROR|FATAL)/i.test(w) ? 'fatal' : ''}` }, svg('alert-triangle', 15), h('span', { text: w })))));
  // ---- por operación
  const groups = new Map();
  for (const c of r.checks) { const g = c.group || 'Otras verificaciones'; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(c); }
  const nd = E.conn().node;
  const ordered = [...groups].sort((a, b) => {
    const ia = /^(\d+)\./.exec(a[0]), ib = /^(\d+)\./.exec(b[0]);
    return (ia ? parseInt(ia[1], 10) : 1e9) - (ib ? parseInt(ib[1], 10) : 1e9);
  });
  for (const [g, list] of ordered) {
    const m = /^(\d+)\./.exec(g);
    const oi = m ? parseInt(m[1], 10) - 1 : -1;
    const o = oi >= 0 ? nd.operations[oi] : null;
    const evaluated = list.filter((c) => !c.skip);
    const max = evaluated.length ? Math.max(...evaluated.map((c) => c.ratio)) : null;
    const ok = max == null || max <= 1 + 1e-9;
    const gh = h('div', { class: 'gh', onclick: () => { grp.classList.toggle('closed'); if (oi >= 0) select(`o:${oi}`); } },
      o ? h('span', { class: 'dot', style: { background: opColor(o.kind), width: '9px', height: '9px', borderRadius: '3px', flex: 'none' } }) : svg('check', 15),
      h('span', { class: 'name', text: g }), max != null ? dcBar(max) : chip('sin evaluar', ''), svg('chevron-down', 14));
    const gb = h('div', { class: 'gb' }, list.map((c) => h('div', { class: `chk ${c.skip ? 'na' : ''}` },
      h('div', { class: 't', text: c.title }), c.ref ? h('div', { class: 'r', text: c.ref }) : null,
      c.skip ? h('div', { class: 'v', text: c.note || 'No evaluado' }) : h('div', { class: 'v', text: `${fmt(c.demand)} ${c.unit || ''} ≤ ${fmt(c.capacity)} ${c.unit || ''}` }),
      h('div', { class: 'dcw' }, dcBar(c.ratio, c.skip)))));
    const grp = h('div', { class: `res-group ${ok ? 'closed' : ''}`, dataset: { op: String(oi) } }, gh, gb);
    box.append(grp);
  }
  if (r.combos && r.combos.length > 1) box.append(combosTable(r));
  if (!r.checks.length) box.append(h('p', { class: 'muted', style: { padding: '12px 16px' }, text: 'Todavía no hay verificaciones: agregue operaciones y cargas.' }));
}
function fmt(v) { if (v == null) return '—'; const a = Math.abs(v); return Number(v).toLocaleString('es', { maximumFractionDigits: a >= 100 ? 1 : a >= 1 ? 2 : 3 }); }

function combosTable(r) {
  const tb = h('table', { class: 't compact' }, h('thead', null, h('tr', null, h('th', { text: 'Combinación' }), h('th', { class: 'num', text: 'D/C' }))),
    h('tbody', null, r.combos.map((row, i) => h('tr', { class: i === r.combo_gov ? 'sel' : '' }, h('td', { text: Array.isArray(row) ? row[0] : (row.name ?? String(i + 1)) }), h('td', { class: 'num', text: Array.isArray(row) ? Number(row[row.length - 1]).toFixed(3) : Number(row.ratio ?? row.dc ?? 0).toFixed(3) })))));
  return h('div', { class: 'res-group', style: { marginTop: '10px' } }, h('div', { class: 'gh' }, svg('list', 15), h('span', { class: 'name', text: 'Combinaciones de carga' })), h('div', { class: 'gb' }, tb));
}

function renderMemory() {
  const box = E.ui.memBox; if (!box) return;
  const r = E.res;
  box.innerHTML = r && r.memory ? r.memory : '';
  if (!r || !r.memory) box.append(h('p', { class: 'muted', style: { padding: '16px' }, text: 'La memoria de cálculo aparece cuando hay verificaciones.' }));
}

// ---------------------------------------------------------------------------------------------------- elementos finitos de la placa base
function renderFem() {
  const box = E.ui.femBox; if (!box) return;
  clear(box);
  const c = E.conn();
  const combos = c.combos.map((x, i) => ({ value: String(i), label: x.name }));
  const st = E.fem = E.fem || { combo: '0', field: 'vm', part: 'all', scale: 0 };
  const status = h('div', { class: 'muted', style: { fontSize: '12.5px' } });
  const run = btn('Ejecutar análisis 3D', { icon: 'cpu', kind: 'primary', onClick: async () => {
    try {
      const r = await call('fem_start', { connection: E.conn() });
      E.job = r.job; pollJob(status, run, stop);
    } catch (e) { errorBox(e); }
  } });
  const stop = btn('Cancelar', { icon: 'x', disabled: true, onClick: () => call('job_cancel', { job: E.job }) });
  box.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Análisis sólido 3D (Gmsh + CalculiX)' }),
    h('p', { class: 'hint-text', text: 'Mallado y análisis de la placa base con elementos sólidos. Los resultados (tracción en pernos, presión de contacto, von Mises y fuerzas en la soldadura) entran al veredicto de la placa base.' }),
    h('div', { class: 'row', style: { marginTop: '8px' } }, run, stop), h('div', { style: { height: '8px' } }), status));
  const view = h('div', { class: 'card-sec', style: { marginTop: '12px' } }, h('h4', { text: 'Ver resultados' }),
    h('div', { class: 'form-grid' },
      field2('Combinación', selectInput({ value: st.combo, options: combos, onChange: (v) => { st.combo = v; showFem(); } })),
      field2('Resultado', selectInput({ value: st.field, options: [{ value: 'vm', label: 'Esfuerzo de von Mises' }, { value: 'u', label: 'Desplazamiento |U|' }, { value: 'uz', label: 'Desplazamiento vertical' }], onChange: (v) => { st.field = v; showFem(); } })),
      field2('Escala de deformación', selectInput({ value: String(st.scale), options: [{ value: '0', label: 'Sin deformar' }, { value: '10', label: '×10' }, { value: '50', label: '×50' }, { value: '200', label: '×200' }], onChange: (v) => { st.scale = parseFloat(v); showFem(); } }))),
    h('div', { class: 'row', style: { marginTop: '8px' } }, btn('Mostrar en el visor', { icon: 'eye', onClick: showFem }), btn('Volver al modelo', { icon: 'box', onClick: backToModel })));
  box.append(view);
  if (E.job) pollJob(status, run, stop);
}
const field2 = (l, c) => h('div', { class: 'field' }, h('span', { class: 'lbl', text: l }), c);

function pollJob(status, run, stop) {
  if (E.pollTimer) clearInterval(E.pollTimer);
  run.disabled = true; stop.disabled = false;
  const tick = async () => {
    try {
      const j = await call('job_status', { job: E.job });
      status.textContent = j.message || (j.done ? '' : 'Trabajando…');
      if (j.done) {
        clearInterval(E.pollTimer); E.pollTimer = null; run.disabled = false; stop.disabled = true;
        if (j.state === 'done') { status.textContent = 'Análisis terminado.'; toast('Análisis FEM terminado', 'ok'); E.job = null; runVerify.flush(); showFem(); }
        else { status.textContent = j.state === 'cancelled' ? 'Cancelado.' : `Error: ${j.error}`; if (j.state !== 'cancelled') errorBox(new Error(j.error)); E.job = null; }
      }
    } catch (e) { clearInterval(E.pollTimer); E.pollTimer = null; errorBox(e); }
  };
  E.pollTimer = setInterval(tick, 900); tick();
}

async function showFem() {
  const st = E.fem;
  try {
    const d = await call('fem_scene', { connection: E.conn(), combo: parseInt(st.combo, 10), field: st.field, scale: st.scale, part: st.part });
    E.femView = true;
    E.viewer.setModel(d, { keepView: true });
    clear(E.ui.fembar);
    if (d.cbar) E.ui.fembar.append(colorbar(d.cbar));
    if (d.message) toast(Array.isArray(d.message) ? d.message[0] : String(d.message), 'info');
  } catch (e) { errorBox(e); }
}
function backToModel() { E.femView = false; clear(E.ui.fembar); runMesh.flush(); }

function colorbar(cb) {
  const cv = h('canvas', { width: 14, height: 140, style: { borderRadius: '4px', border: '1px solid var(--border)' } });
  const g = cv.getContext('2d'); const n = cb.colors.length;
  for (let i = 0; i < n; i++) { const c = cb.colors[n - 1 - i]; g.fillStyle = `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`; g.fillRect(0, (i * 140) / n, 14, 140 / n + 1); }
  return h('div', { class: 'card-sec', style: { display: 'flex', gap: '8px', padding: '8px 10px', alignItems: 'stretch' } }, cv,
    h('div', { style: { display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: '11.5px' } }, h('b', { text: cb.title }), h('span', { text: fmt(cb.vmax) }), h('span', { text: fmt((cb.vmax + cb.vmin) / 2) }), h('span', { text: fmt(cb.vmin) })));
}

// ---------------------------------------------------------------------------------------------------- informes
async function exportReport(format) {
  const c = E.conn();
  const f = await native.saveFile(`${c.name || 'conexion'}_${c.element || ''}.${format}`, [{ name: format === 'pdf' ? 'PDF' : 'Word', extensions: [format] }]);
  if (!f) return;
  const t = toast('Generando informe…', 'info', 60000);
  try { await call('report', { connection: c, path: f, format }); t.remove(); toast('Informe generado', 'ok'); native.showItem(f); } catch (e) { t.remove(); errorBox(e); }
}
async function exportStep() {
  const f = await native.saveFile(`${E.conn().element || 'conexion'}.step`, [{ name: 'STEP', extensions: ['step', 'stp'] }]);
  if (!f) return;
  try { await call('export_step', { connection: E.conn(), path: f }); toast('Modelo STEP exportado', 'ok'); } catch (e) { errorBox(e); }
}
