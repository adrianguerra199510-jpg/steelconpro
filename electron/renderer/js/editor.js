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
import { renderItems } from './forms.js';
import { pickTypology } from './typology.js';

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
  if (E.panel) E.panel.close('switch');
  if (E.report) E.report.win.close();
  window.removeEventListener('keydown', onKey);
  save.cancel();
  if (E.dirty) await saveNow();
  if (E.viewer) { E.viewer.dispose(); E.viewer = null; }
  Object.values(E.pollers || {}).forEach((t) => t && clearInterval(t));
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
    applyLoads();
    highlight();
    renderNotes(data.notes || []);
  } catch (e) { setStatus(`No se pudo dibujar el modelo: ${e.message}`, true); }
}, 90);

// el equilibrio del nudo (cargas de los extremos) se mantiene al día para dibujar las flechas; las verificaciones (D/C) SOLO se calculan con «Calcular»
const runNodal = debounce(async () => {
  try { E.nodal = await call('nodal', { connection: E.conn() }); } catch (e) { E.nodal = null; }
  renderNodal(); applyLoads();
}, 300);
const verify = latest(async () => call('verify', { connection: E.conn() }));
const runVerify = debounce(async () => {
  setVerdict('calc'); E.calculating = true; renderResults();
  try {
    const r = await verify();
    if (!r) return;
    E.res = r; E.stale = false; E.calculating = false;
    try { E.nodal = await call('nodal', { connection: E.conn() }); } catch (e) { E.nodal = null; }
    renderResults(); renderNodal(); applyLoads(); renderTree(); setVerdict(); if (E.report) E.report.refresh();
  } catch (e) { E.calculating = false; E.res = null; setVerdict('error', e.message); renderResults(e.message); }
}, 100);

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
  E.stale = true; E.res = null; E.calculating = false;                        // un cambio descarta los resultados: sin D/C hasta volver a calcular
  if (opts.structure) renderTree(); else renderTree();
  if (opts.geometry !== false) runMesh();
  runNodal();
  renderResults();
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
  const libBtn = btn('Bibliotecas', { icon: 'library', onClick: (e) => menu(e.currentTarget, [
    { label: 'Secciones y Section Designer', icon: 'shapes', onClick: () => openSections(E) }, { label: 'Materiales', icon: 'database', onClick: () => openMaterials(E) },
    { label: 'Plantillas de conexión', icon: 'copy', onClick: () => openTemplates(E) }]) });
  const repBtn = btn('Informe', { icon: 'file-text', onClick: () => openReport() });
  const top = h('div', { class: 'ed-top' },
    iconBtn('arrow-left', 'Volver al inicio', () => go('home')), ui.title, h('div', { class: 'vr' }), ui.connTabs, h('span', { class: 'grow' }),
    ui.undo, ui.redo, h('div', { class: 'vr' }), libBtn, repBtn);

  // ---- panel izquierdo (árbol)
  ui.tree = h('div', { class: 'scroll' });
  const left = h('div', { class: 'panel left' }, ui.tree);

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
  ui.loadSel = h('select', { title: 'Caso de carga que se dibuja', onchange: () => { E.loadCase = parseInt(ui.loadSel.value, 10) || 0; applyLoads(); } });
  ui.loadBtn = iconBtn('zap', 'Mostrar las cargas', () => { E.showLoadsOn = !E.showLoadsOn; ui.loadBtn.classList.toggle('on', E.showLoadsOn); E.viewer.setLoadsVisible(E.showLoadsOn); ui.loadSel.style.display = E.showLoadsOn ? '' : 'none'; });
  ui.loadBtn.classList.add('on'); E.showLoadsOn = true;
  vtool.append(h('div', { class: 'group' }, ui.loadBtn, ui.loadSel));
  ui.fembar = h('div', { class: 'vhud' });
  const center = h('div', { class: 'viewer-wrap' }, ui.vhost, vtool, ui.note, ui.fembar);

  // ---- panel derecho (resultados)
  ui.rview = h('div', { class: 'rview' });
  ui.pview = h('div', { class: 'pview hidden' });
  ui.right = h('div', { class: 'panel right' }, ui.rview, ui.pview);
  ui.resizer = h('div', { class: 'resizer', title: 'Arrastre para cambiar el ancho del panel' });
  const body = h('div', { class: 'ed-body' }, left, center, ui.resizer, ui.right);
  ui.resizer.addEventListener('pointerdown', (ev) => {
    ui.resizer.setPointerCapture(ev.pointerId); ui.resizer.classList.add('drag');
    const mv = (e) => { const w = Math.max(360, Math.min(900, body.getBoundingClientRect().right - e.clientX)); body.style.setProperty('--rw', `${w}px`); };
    const up = () => { ui.resizer.classList.remove('drag'); ui.resizer.removeEventListener('pointermove', mv); ui.resizer.removeEventListener('pointerup', up); };
    ui.resizer.addEventListener('pointermove', mv); ui.resizer.addEventListener('pointerup', up);
  });

  ui.status = h('span', { text: '' });
  ui.units = h('span', { class: 'grow', style: { textAlign: 'right' } });
  const bar = h('div', { class: 'statusbar' }, ui.status, ui.units);
  root.append(top, body, bar);

  E.viewer = new Viewer(ui.vhost, { onPick: (name, part) => pickPart(name, part) });
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
  E.stale = true; E.res = null; setVerdict('stale');
  runMesh.flush(); runNodal.flush(); renderResults();
}

function renderConnTabs() {
  const box = E.ui.connTabs; clear(box);
  E.conns.forEach((c, i) => {
    const b = h('button', { class: `conn-tab ${i === E.idx ? 'on' : ''}`, type: 'button', onclick: () => switchConn(i), oncontextmenu: (e) => { e.preventDefault(); connMenu(i, e); } }, svg('component', 15), h('span', { text: c.element || `CN-${i + 1}` }));
    box.append(b);
  });
  box.append(iconBtn('plus', 'Nueva conexión en este proyecto', async () => {
    const pick = await pickTypology();
    if (!pick) return;
    E.snap();
    const c0 = E.conn();
    const nc = await call('connection_new', { n: E.conns.length + 1, name: c0.name, u_len: c0.u_len, u_force: c0.u_force, u_stress: c0.u_stress, u_moment: c0.u_moment, typology: pick.typology, params: pick.params });
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
  if (E.panel) E.panel.close('switch');
  E.idx = i; E.sel = null; E.res = null; E.femView = false; applyUnits(); refreshAll();
}

// ---------------------------------------------------------------------------------------------------- árbol
const SHORT = (k) => k.replace(/ \(.*\)$/, '');
function opTitle(o) {
  const K = S.C.op;
  switch (o.kind) {
    case K.PLATE: return `${o.name || 'Placa'} · ${o.role}`;
    case K.ANGLE: return `${o.name || 'Ángulo'} · L${o.leg_a}×${o.leg_b}`;
    case K.HOLE: return `Huecos en ${o.parent}`;
    case K.TRIM: return `Recorte · ${(o.targets || []).join(', ') || '—'}`;
    case K.BOLTS: return `Pernos en ${o.parent}`;
    case K.FILLET: return `Soldadura · ${o.weld_main || (o.targets || []).join(', ') || '—'}`;
    case K.CUT: case K.COPE: return `Corte · ${(o.targets && o.targets.length ? o.targets : [o.member]).join(', ')}`;
    case K.BASE: return `Placa base · ${o.member || E.conn().node.main_name}`;
    default: return `${SHORT(o.kind)} · ${o.member}`;
  }
}
function opSub(o) {
  const K = S.C.op;
  if (o.kind === K.HOLE) return `${o.rows}×${o.cols} · ${o.hole_shape.toLowerCase()}`;
  if (o.kind === K.TRIM) return `${o.trim_mode.toLowerCase()}`;
  if (o.kind === K.PLATE || o.kind === K.ANGLE) return `sobre ${o.parent} · ${o.face}${o.attach ? ' · ' + o.attach.toLowerCase() : ''}`;
  if (o.kind === K.BOLTS) return `${o.rows}×${o.cols} ${o.bolt_size}" ${o.bolt_grade}`;
  if (o.kind === K.FILLET) return `${o.weld_main && (o.weld_to || []).length ? 'a ' + o.weld_to.map((t) => t[0]).join(', ') + ' · ' : ''}${(o.weld_type || 'Filete').split(' ')[0].toLowerCase()} ${S.us.q('L', o.weld_size)}`;
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
    onClick: () => select(`m:${m.name}`),
    acts: [iconBtn('pencil', 'Editar', (e) => { e.stopPropagation(); openMember(E, m.name); })] }));
  box.append(ml);
  // ---- operaciones
  box.append(sec('Operaciones', 'wrench', iconBtn('plus', 'Agregar operación', (e) => addMenu(e.currentTarget))));
  const ol = h('div', { class: 'sect' });
  const ops = nd.operations;
    const plateIdx = (name) => ops.findIndex((p) => (p.kind === K.PLATE || p.kind === K.ANGLE) && p.name === name);
  const parentIndex = (o) => { const p = o.parent ? plateIdx(o.parent) : -1; return p >= 0 ? p : -1; };
  const children = (i) => ops.map((o, j) => [o, j]).filter(([o, j]) => j !== i && parentIndex(o) === i);
  const draw = (o, i, depth) => {
    const node = h('div');
    node.append(item({ ic: OP_ICON[o.kind] || 'box', color: opColor(o.kind), name: `${i + 1}. ${opTitle(o)}`, sub: opSub(o), sel: E.sel === `o:${i}`, ratio: opRatio(i),
      onClick: () => select(`o:${i}`),
      acts: [iconBtn('chevron-up', 'Subir (se aplica antes)', (e) => { e.stopPropagation(); moveOperation(i, -1); }), iconBtn('chevron-down', 'Bajar (se aplica después)', (e) => { e.stopPropagation(); moveOperation(i, 1); }),
        iconBtn('pencil', 'Editar', (e) => { e.stopPropagation(); editOperation(i); }), iconBtn('trash', 'Eliminar', (e) => { e.stopPropagation(); deleteOperation(i); })] }));
    const kids = (o.kind === K.PLATE || o.kind === K.ANGLE) ? children(i) : [];
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

function select(sel, open = true) {
  E.sel = sel; renderTree(); highlight();
  if (sel && sel.startsWith('o:')) scrollToGroup(parseInt(sel.slice(2), 10));
  if (open && sel) openFor(sel);
}
function openFor(sel) {
  if (sel.startsWith('m:')) openMember(E, sel.slice(2));
  else if (sel.startsWith('o:')) editOperation(parseInt(sel.slice(2), 10));
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
      if (o.kind === K.PLATE || o.kind === K.ANGLE) names.push(o.name, o.parent);
      else if (o.kind === K.HOLE) names.push(o.parent);
      else if (o.kind === K.TRIM) names.push(...(o.targets || []), o.parent);
      else if (o.kind === K.BOLTS) names.push(o.parent, ...(o.targets || []));
      else if (o.kind === K.FILLET) names.push(...(o.weld_main ? [o.weld_main, ...(o.weld_to || []).map((t) => t[0])] : (o.targets || [])));
      else if (o.kind === K.CUT) names.push(...(o.targets || []));
      else if (o.kind === K.COPE) names.push(...(o.targets && o.targets.length ? o.targets : [o.member]));
      else if (o.kind === K.BASE) names.push(o.member || nd.main_name);
      else names.push(o.member);
    }
  }
  E.viewer.select(names.filter(Boolean));
}
function pickPart(name, part) {
  const nd = E.conn().node, K = S.C.op;
  if (!name) { E.sel = null; renderTree(); highlight(); return; }
  if (name === nd.main_name || nd.members.some((m) => m.name === name)) return select(`m:${name}`);
  const oi = nd.operations.findIndex((o) => o.name === name && (o.kind === K.PLATE || o.kind === K.ANGLE));
  if (oi >= 0) return select(`o:${oi}`);
  const owner = part ? part.owner : '';
  if (owner === 'op:base') { const bi = nd.operations.findIndex((o) => o.kind === K.BASE); if (bi >= 0) return select(`o:${bi}`); }
  if (owner && owner.startsWith('op:')) return select(`o:${parseInt(owner.slice(3), 10)}`);
  if (owner) { const ci = nd.operations.findIndex((o) => o.member === owner && S.C.ops.connection.includes(o.kind)); if (ci >= 0) return select(`o:${ci}`); }
  if (part && part.kind === 'gusset') { const gi = nd.operations.findIndex((o) => o.kind === K.GUSSET || o.kind === K.GUSSET_W); if (gi >= 0) return select(`o:${gi}`); }
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

E.createOperation = (k) => createOperation(k);
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
  } else if (kind === K.TRIM) {
    const sel = E.sel && E.sel.startsWith('m:') ? E.sel.slice(2) : '';
    const m = nd.members.find((x) => x.name === sel) || nd.members[0];
    if (!m) { toast('Agregue primero un miembro conectado para recortarlo.', 'info', 5000); return; }
    params.targets = [m.name]; params.parent = nd.main_name; params.face = S.C.faces_i[0];
  } else if (kind === K.BOLTS || kind === K.FILLET) {
    const plates = nd.operations.filter((o) => o.kind === K.PLATE || o.kind === K.ANGLE);
    const last = plates[plates.length - 1];
    if (last && kind === K.BOLTS) { params.parent = last.name; params.targets = [last.parent]; params.pl_s = last.pl_L / 2; params.pl_u = 0; }
    if (last && kind === K.FILLET) { params.weld_main = last.name; params.weld_to = last.parent ? [[last.parent, '']] : []; }
  }
  E.snap();
  try {
    const before = nd.operations.length;
    const r = await call('add_operation', { connection: E.conn(), kind, params });
    E.replaceConn(r.connection);
    E.sel = `o:${r.index}`;
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

// las operaciones se aplican en el orden de la lista: una posterior puede apoyarse en lo que dejó una anterior
function moveOperation(i, d) {
  const ops = E.conn().node.operations;
  const j = i + d;
  if (j < 0 || j >= ops.length) return;
  E.snap();
  [ops[i], ops[j]] = [ops[j], ops[i]];
  E.sel = `o:${j}`;
  E.changed({ structure: true });
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
  else if (r && !E.stale && state !== 'stale' && (!r.checks.length || !(r.max_ratio > 0))) { cls = 'idle'; txt = 'Sin verificaciones'; ic = 'circle-help'; }
  else if (r && !E.stale && state !== 'stale') { cls = r.ok ? 'ok' : 'bad'; txt = `${r.ok ? 'CUMPLE' : 'NO CUMPLE'} · D/C máx ${r.max_ratio.toFixed(3)}`; ic = r.ok ? 'check' : 'circle-alert'; }
  else if (r) { cls = 'stale'; txt = 'Desactualizado: calcule de nuevo'; ic = 'refresh-cw'; }
  v.className = `big-chip ${cls}`; v.replaceChildren(svg(ic, 16), h('span', { text: txt }));
  if (E.ui.vbadge) { E.ui.vbadge.className = `big-chip ${cls}`; E.ui.vbadge.replaceChildren(svg(ic, 16), h('span', { text: txt })); }
  if (E.ui.pchip) { E.ui.pchip.className = `big-chip ${cls}`; E.ui.pchip.style.height = '26px'; E.ui.pchip.style.padding = '0 10px'; E.ui.pchip.style.fontSize = '12px'; E.ui.pchip.replaceChildren(h('span', { text: txt })); }
}

// ---------------------------------------------------------------------------------------------------- panel derecho
function buildRight() {
  const right = E.ui.rview; clear(right);
  const hasBase = E.conn().node.operations.some((o) => o.kind === S.C.op.BASE);
  E.ui.vbadge = h('span', { class: 'big-chip idle' });
  const items = [
    { id: 'res', label: 'Resultados', icon: 'check', render: () => { E.ui.resBox = h('div', { class: 'scroll', style: { padding: '0 0 12px' } }); renderResults(); return E.ui.resBox; } },
    { id: 'nod', label: 'Nudo', icon: 'zap', render: () => { E.ui.nodBox = h('div', { class: 'scroll', style: { padding: '0 12px 12px' } }); renderNodal(); return E.ui.nodBox; } },
    { id: 'mem', label: 'Memoria', icon: 'file-text', render: () => { E.ui.memBox = h('div', { class: 'scroll memory' }); renderMemory(); return E.ui.memBox; } },
  ];
  items.push({ id: 'fem', label: 'FEM', icon: 'cpu', render: () => { E.ui.femBox = h('div', { class: 'scroll', style: { padding: '8px 12px' } }); renderFem(); return E.ui.femBox; } });
  const t = tabs(items, { active: E.ui.rtab && items.some((i) => i.id === E.ui.rtab) ? E.ui.rtab : 'res', cls: 'pill', onChange: (id) => { E.ui.rtab = id; } });
  E.ui.rtabs = t;
  const calc = btn('Calcular', { icon: 'play', kind: 'primary', onClick: () => runVerify.flush() });
  calc.classList.add('calc');
  const memTab = t.querySelector('.tab[data-id="mem"]');
  if (memTab) memTab.before(calc); else t.querySelector('.tabbar').append(calc);
  right.append(h('div', { style: { padding: '10px 12px 4px', display: 'flex', gap: '8px', alignItems: 'center' } }, E.ui.vbadge), t);
  t.style.padding = '0 8px';
  setVerdict();
}

// ---- edicion en el panel derecho (operaciones y miembros): reemplaza las ventanas que tapaban el visor
E.panel = null;
E.showPanel = ({ title, icon: ic, color, body, footer, onClose }) => {
  if (E.panel) E.panel.close('switch');
  const ui = E.ui;
  clear(ui.pview);
  const chip = h('span', { class: 'big-chip idle', style: { height: '26px', padding: '0 10px', fontSize: '12px', boxShadow: 'none' } });
  ui.pchip = chip;
  const closeBtn = iconBtn('x', 'Cerrar (conserva los cambios)', () => api.close('close'));
  const head = h('div', { class: 'pedit' }, color ? h('span', { class: 'dot', style: { background: color, width: '11px', height: '11px', borderRadius: '4px' } }) : svg(ic || 'wrench', 18), h('h3', { text: title }), chip, closeBtn);
  ui.pview.append(head, h('div', { class: 'scroll pbody' }, body));
  if (footer && footer.length) ui.pview.append(h('div', { class: 'pfoot' }, footer));
  ui.rview.classList.add('hidden'); ui.pview.classList.remove('hidden');
  let closed = false;
  const api = {
    body,
    close(reason = 'close') {
      if (closed) return; closed = true;
      if (E.panel === api) E.panel = null;
      if (reason !== 'switch') { ui.pview.classList.add('hidden'); ui.rview.classList.remove('hidden'); clear(ui.pview); ui.pchip = null; }
      if (onClose) onClose(reason);
    },
  };
  E.panel = api;
  setVerdict();
  return api;
};

function scrollToGroup(i) {
  if (!E.ui.rtabs) return;
  E.ui.rtabs.show('res');
  const el = E.ui.resBox && E.ui.resBox.querySelector(`[data-op="${i}"]`);
  if (el) { el.classList.remove('closed'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); el.animate([{ background: 'var(--brand-50)' }, { background: 'transparent' }], { duration: 1200 }); }
}

function renderResults(err) { if (E.ui.resBox) fillResults(E.ui.resBox, err); renderMemory(); if (E.report) E.report.refresh(); }

function fillResults(box, err, { forceOpen = false, pick = true } = {}) {
  clear(box);
  const r = E.res;
  const us = S.us;
  if (err) { box.append(h('div', { class: 'warns' }, h('div', { class: 'warn-row fatal' }, svg('circle-alert', 15), h('span', { text: err })))); return; }
  if (!r) { box.append(E.calculating ? h('div', { style: { padding: '16px' } }, spinner('Calculando…')) : h('div', { class: 'muted', style: { padding: '18px 14px', fontSize: '13px' }, text: 'Todavía no se ha calculado. Presione «Calcular» para ver las verificaciones y los D/C de cada operación.' })); return; }
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
    const gh = h('div', { class: 'gh', onclick: () => { grp.classList.toggle('closed'); if (pick && oi >= 0) select(`o:${oi}`); } },
      o ? h('span', { class: 'dot', style: { background: opColor(o.kind), width: '9px', height: '9px', borderRadius: '3px', flex: 'none' } }) : svg('check', 15),
      h('span', { class: 'name', text: g }), max != null ? dcBar(max) : chip('sin evaluar', ''), svg('chevron-down', 14));
    const gb = h('div', { class: 'gb' }, list.map((c) => h('div', { class: `chk ${c.skip ? 'na' : ''}` },
      h('div', { class: 't', text: c.title }), c.ref ? h('div', { class: 'r', text: c.ref }) : null,
      c.skip ? h('div', { class: 'v', text: c.note || 'No evaluado' }) : h('div', { class: 'v', text: `${fmt(c.demand)} ${c.unit || ''} ≤ ${fmt(c.capacity)} ${c.unit || ''}` }),
      h('div', { class: 'dcw' }, dcBar(c.ratio, c.skip)))));
    const grp = h('div', { class: `res-group ${ok || forceOpen ? (forceOpen ? '' : 'closed') : ''}`, dataset: { op: String(oi) } }, gh, gb);
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

const FORCE_COL = { member: '#d62728', ext: '#c0392b', main: '#d62728', reaction: '#1e8449', base: '#e8731a' };
function applyLoads() {
  const v = E.viewer; if (!v) return;
  const a = E.nodal, us = S.us, sel = E.ui.loadSel;
  if (sel) {
    const n = a ? a.cases.length : 0;
    if (sel.options.length !== n) { sel.replaceChildren(...(a ? a.cases : []).map((c, i) => h('option', { value: String(i), text: c.case }))); }
    E.loadCase = Math.min(E.loadCase || 0, Math.max(n - 1, 0)); sel.value = String(E.loadCase);
    sel.style.display = n && E.showLoadsOn ? '' : 'none';
  }
  if (!a || !a.cases.length || E.femView) { v.setLoads([]); return; }
  const c = a.cases[Math.min(E.loadCase || 0, a.cases.length - 1)];
  const nrm = (x) => Math.hypot(x[0], x[1], x[2]);
  v.setLoads(c.draw.map((d) => ({ pos: d.pos, F: d.F, M: d.M, color: FORCE_COL[d.kind] || '#d62728', colorM: '#8e44ad',
    textF: nrm(d.F) > 1e-9 ? `${d.name}: ${us.q('F', nrm(d.F), 2)}` : '', textM: nrm(d.M) > 1e-9 ? `${d.name}: ${us.q('M', nrm(d.M), 1)}` : '' })));
}

function renderNodal() {
  const box = E.ui.nodBox; if (!box) return;
  clear(box);
  const nd = E.conn().node, us = S.us, a = E.nodal;
  box.append(h('p', { class: 'hint-text', style: { margin: '8px 0' }, text: 'Equilibrio del nudo por caso de carga: acciones de los miembros sobre el nudo (ejes globales, momentos respecto del cruce de ejes) y reacción del miembro principal por equilibrio.' }),
    btn('Editar cargas', { icon: 'pencil', onClick: () => openLoads(E) }));
  if (!a || !a.cases.length) { box.append(h('p', { class: 'muted', style: { padding: '10px 2px' }, text: 'Sin casos de carga.' })); return; }
  const f = (v) => us.fmt('F', v, 2), m = (v) => us.fmt('M', v, 1);
  for (const c of a.cases) {
    const rows = c.rows.map((r) => h('tr', { class: r.given ? '' : 'sel' }, h('td', { text: r.member }), ...r.F.map((x) => h('td', { class: 'num', text: f(x) })), ...r.M.map((x) => h('td', { class: 'num', text: m(x) }))));
    const tb = h('table', { class: 't compact' }, h('thead', null, h('tr', null, h('th', { text: 'Acción sobre el nudo' }), ...['Fx', 'Fy', 'Fz'].map((k) => h('th', { class: 'num', text: `${k} (${us.label('F')})` })), ...['Mx', 'My', 'Mz'].map((k) => h('th', { class: 'num', text: `${k} (${us.label('M')})` })))),
      h('tbody', null, rows, h('tr', null, h('td', { text: 'Σ (con la reacción)', style: { fontWeight: 650 } }), ...[0, 1, 2].map(() => h('td', { class: 'num', text: '0' })), ...[0, 1, 2].map(() => h('td', { class: 'num', text: '0' })))));
    const ml = c.main_local;
    const info = h('div', { class: 'muted', style: { fontSize: '12px', marginTop: '6px' } },
      `Reacción de «${nd.main_name}» (lado ${c.side > 0 ? '+' : '−'}, ejes locales): N = ${f(ml.N)}, Vy = ${f(ml.Vy)}, Vz = ${f(ml.Vz)} ${us.label('F')}; T = ${m(ml.T)}, My = ${m(ml.My)}, Mz = ${m(ml.Mz)} ${us.label('M')}.`);
    const base = c.base ? h('div', { style: { marginTop: '4px', fontSize: '12.5px', fontWeight: 600 } }, `Placa base: Pu = ${f(c.base.Pu)} ${us.label('F')}, Mux = ${m(c.base.Mux)}, Muy = ${m(c.base.Muy)} ${us.label('M')}, Vux = ${f(c.base.Vux)}, Vuy = ${f(c.base.Vuy)} ${us.label('F')}`) : null;
    box.append(h('div', { class: 'card-sec', style: { marginTop: '10px' } }, h('h4', { text: c.case }), h('div', { style: { overflow: 'auto' } }, tb), info, base));
  }
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
  const hasBase = E.conn().node.operations.some((o) => o.kind === S.C.op.BASE);
  box.append(femSection('node', { title: 'Análisis FEM del nudo (miembros, placas, pernos y soldaduras)',
    desc: 'Modelo sólido con Gmsh + CalculiX: cada miembro se recorta a 30 in del nudo; el lado que equilibra del principal queda empotrado y en los demás extremos se aplican las cargas del análisis nodal. '
      + 'Los pernos son resortes entre cuerpos rígidos, los cordones de filete unen las placas, y el acero es elasto-plástico (φ·Fy). El veredicto incluye lo que sale del FEM: fuerza en los pernos, esfuerzo en las soldaduras y deformación plástica de miembros y placas.',
    start: (st) => call('fem_node_start', { connection: E.conn(), force: !!st.force }), scene: (st) => call('fem_node_scene', { connection: E.conn(), case: parseInt(st.combo, 10), field: st.field, scale: st.scale, part: st.part }),
    cases: () => (E.nodal ? E.nodal.cases.map((c, i) => ({ value: String(i), label: c.case })) : []), caseLabel: 'Caso de carga', mesh: true, config: femConfig }));
  if (hasBase) box.append(h('div', { style: { height: '12px' } }), femSection('base', { title: 'Análisis sólido 3D de la placa base',
    desc: 'Mallado y análisis de la placa base con anclajes, concreto, llave de corte y rigidizadores. Sus resultados (tracción en pernos, presión de contacto, von Mises y fuerzas en la soldadura) entran al veredicto de la placa base.',
    start: () => call('fem_start', { connection: E.conn() }), scene: (st) => call('fem_scene', { connection: E.conn(), combo: parseInt(st.combo, 10), field: st.field, scale: st.scale, part: st.part }),
    cases: () => E.conn().combos.map((x, i) => ({ value: String(i), label: x.name })), caseLabel: 'Combinación', mesh: true, meshApi: ['fem_base_mesh_start', 'fem_base_mesh_scene', 'combo'] }));
}
// opciones del análisis FEM del nudo (se guardan con la conexión: conn.fea)
function femConfig() {
  const C = S.C; const F = C.fea;
  const num = (label, path, uk, lo, hi, help) => ({ path, label, type: 'num', uk, lo, hi, help });
  const ctx = { us: E.us(), get: () => E.conn().fea, onChange: () => { E.changed({ geometry: false }); }, hide: () => false };
  const g1 = renderItems([
    num('Largo de cada miembro modelado desde el nudo', 'fem_len', 'L', 8, 120, 'Más largo = más fiel el empotramiento, pero más elementos y más tiempo.'),
    { path: 'mesh3d_mode', label: 'Calidad de la malla', type: 'combo', items: F.mesh_modes },
    num('Tamaño de elemento manual (0 = automático)', 'mesh3d', 'L', 0, 10, 'Tamaño máximo en las placas; los miembros usan 1.6 veces este valor.'),
    num('Tamaño de malla en las soldaduras (0 = automático)', 'weld_mesh', 'L', 0, 2),
    { path: 'contacts', label: 'Contacto entre piezas (superficies que pueden separarse)', type: 'check', wide: true, help: 'Si se desactiva, las piezas quedan unidas donde se tocan: más estable pero menos realista.' },
    { path: 'plastic', label: 'Acero elasto-plástico (límite φ·Fy)', type: 'check', wide: true },
    num('Deformación plástica máxima admitida (%)', 'plastic_limit', '-', 0.1, 20),
    { path: 'weld_model', label: 'Modelo de las soldaduras', type: 'combo', items: F.weld_models, wide: true },
    { path: 'weld_criterion', label: 'Criterio de las soldaduras', type: 'combo', items: F.weld_criteria, wide: true },
    num('Deformación plástica de la garganta con D/C = 1 (%)', 'weld_plastic_limit', '-', 1, 20),
    num('Factor para el D/C pico de la soldadura', 'weld_peak_factor', '-', 1, 3)], ctx, { cols: 2 });
  return h('details', { class: 'card-sec', style: { marginTop: '8px' } }, h('summary', { style: { cursor: 'pointer', fontWeight: 700 }, text: 'Configuración del análisis FEM' }), h('div', { style: { height: '8px' } }), g1);
}
// malla de elementos finitos en el visor (sin resolver)
async function showMesh(kind, cfg, status) {
  const st = E.fems[kind];
  try {
    status.textContent = 'Generando la malla…';
    const [startFn, sceneFn, key] = cfg.meshApi || ['fem_mesh_start', 'fem_mesh_scene', 'case'];
    const r = await call(startFn, { connection: E.conn(), [key]: parseInt(st.combo, 10) || 0, force: false });
    for (;;) {
      const j = await call('job_status', { job: r.job });
      status.textContent = j.message || 'Generando la malla…';
      if (j.done) { if (j.state !== 'done') throw new Error(j.error || 'No se pudo generar la malla.'); break; }
      await new Promise((ok) => setTimeout(ok, 800));
    }
    const d = await call(sceneFn, { connection: E.conn(), [key]: parseInt(st.combo, 10) || 0, part: st.meshPart || 'all' });
    E.femView = true;
    E.viewer.setModel(d, { keepView: true });
    E.viewer.setLoads([]);
    clear(E.ui.fembar);
    st.meshParts = d.parts_list;
    status.textContent = `Malla: ${d.mesh.nodes.toLocaleString('es')} nodos · ${d.mesh.elements.toLocaleString('es')} elementos tetraédricos`;
    setStatus(status.textContent);
  } catch (e) { status.textContent = ''; errorBox(e); }
}
const field2 = (l, c) => h('div', { class: 'field' }, h('span', { class: 'lbl', text: l }), c);

function femSection(kind, cfg) {
  E.fems = E.fems || {}; E.jobs = E.jobs || {};
  const st = E.fems[kind] = E.fems[kind] || { combo: '0', field: 'vm', part: 'all', scale: 0, parts: [], fields: [] };
  const status = h('div', { class: 'muted', style: { fontSize: '12.5px', whiteSpace: 'pre-line' } });
  const run = btn('Ejecutar análisis', { icon: 'cpu', kind: 'primary', onClick: async () => {
    try { const r = await cfg.start(st); E.jobs[kind] = r.job; pollJob(kind, status, run, stop, cfg); } catch (e) { errorBox(e); }
  } });
  const stop = btn('Cancelar', { icon: 'x', disabled: true, onClick: () => call('job_cancel', { job: E.jobs[kind] }) });
  const cases = cfg.cases();
  const fields = st.fields.length ? st.fields : [{ id: 'vm', label: 'Esfuerzo de von Mises' }, { id: 'u', label: 'Desplazamiento |U|' }, { id: 'uz', label: 'Desplazamiento vertical' }, { id: 'peeq', label: 'Deformación plástica (PEEQ)' }];
  const parts = [{ id: 'all', label: 'Todo el conjunto' }, ...st.parts.filter((p) => p.id !== 'all')];
  const show = () => showFem(kind, cfg);
  const view = h('div', { style: { marginTop: '10px', borderTop: '1px solid var(--border)', paddingTop: '10px' } }, h('h4', { text: 'Ver resultados: deformada y esfuerzos', style: { marginBottom: '8px' } }),
    h('div', { class: 'form-grid' },
      cases.length ? field2(cfg.caseLabel, selectInput({ value: st.combo, options: cases, onChange: (v) => { st.combo = v; show(); } })) : null,
      field2('Resultado', selectInput({ value: st.field, options: fields.map((f) => ({ value: f.id, label: f.label })), onChange: (v) => { st.field = v; show(); } })),
      field2('Deformada', selectInput({ value: String(st.scale), options: [{ value: '0', label: 'Sin deformar' }, { value: '10', label: '×10' }, { value: '50', label: '×50' }, { value: '200', label: '×200' }, { value: '1000', label: '×1000' }], onChange: (v) => { st.scale = parseFloat(v); show(); } })),
      field2('Pieza', selectInput({ value: st.part, options: parts.map((p) => ({ value: p.id, label: p.label })), onChange: (v) => { st.part = v; show(); } }))),
    h('div', { class: 'row', style: { marginTop: '8px' } }, btn('Mostrar en el visor', { icon: 'eye', onClick: show }), btn('Volver al modelo', { icon: 'box', onClick: backToModel })));
  const meshStatus = h('div', { class: 'muted', style: { fontSize: '12.5px', marginTop: '6px' } });
  const meshBox = cfg.mesh ? h('div', { style: { marginTop: '10px', borderTop: '1px solid var(--border)', paddingTop: '10px' } }, h('h4', { text: 'Ver el modelo mallado', style: { marginBottom: '8px' } }),
    h('p', { class: 'hint-text', text: 'Genera solo la malla (sin resolver) con el tamaño de elemento de la configuración y la muestra en el visor con sus aristas, pieza por pieza.' }),
    h('div', { class: 'row', style: { marginTop: '8px', flexWrap: 'wrap' } },
      cases.length ? field2(cfg.caseLabel, selectInput({ value: st.combo, options: cases, onChange: (v) => { st.combo = v; } })) : null,
      field2('Pieza', h('div', { class: 'mesh-part-slot' }, selectInput({ value: st.meshPart || 'all', options: [{ value: 'all', label: 'Todo el conjunto' }, ...(st.meshParts || []).filter((x) => x.id !== 'all').map((x) => ({ value: x.id, label: x.label }))], onChange: (v) => { st.meshPart = v; if (E.femView) showMesh(kind, cfg, meshStatus); } }))),
      btn('Ver malla en el visor', { icon: 'layers', kind: 'primary', onClick: () => showMesh(kind, cfg, meshStatus) }), btn('Volver al modelo', { icon: 'box', onClick: backToModel })), meshStatus) : null;
  const card = h('div', { class: 'card-sec' }, h('h4', { text: cfg.title }), h('p', { class: 'hint-text', text: cfg.desc }),
    h('div', { class: 'row', style: { marginTop: '8px' } }, run, stop), h('div', { style: { height: '6px' } }), status, cfg.config ? cfg.config() : null, meshBox, view);
  if (E.jobs[kind]) pollJob(kind, status, run, stop, cfg);
  return card;
}

function pollJob(kind, status, run, stop, cfg) {
  E.pollers = E.pollers || {};
  if (E.pollers[kind]) clearInterval(E.pollers[kind]);
  run.disabled = true; stop.disabled = false;
  const tick = async () => {
    try {
      const j = await call('job_status', { job: E.jobs[kind] });
      status.textContent = j.message || (j.done ? '' : 'Trabajando…');
      if (j.done) {
        clearInterval(E.pollers[kind]); E.pollers[kind] = null; run.disabled = false; stop.disabled = true;
        if (j.state === 'done') { status.textContent = 'Análisis terminado.'; toast('Análisis FEM terminado', 'ok'); E.jobs[kind] = null; runVerify.flush(); showFem(kind, cfg); }
        else { status.textContent = j.state === 'cancelled' ? 'Cancelado.' : `Error: ${j.error}`; if (j.state !== 'cancelled') errorBox(new Error(j.error)); E.jobs[kind] = null; }
      }
    } catch (e) { clearInterval(E.pollers[kind]); E.pollers[kind] = null; errorBox(e); }
  };
  E.pollers[kind] = setInterval(tick, 1000); tick();
}

async function showFem(kind, cfg) {
  const st = E.fems[kind];
  try {
    const d = await cfg.scene(st);
    E.femView = true;
    E.viewer.setModel(d, { keepView: true });
    E.viewer.setLoads([]);
    clear(E.ui.fembar);
    if (d.cbar) E.ui.fembar.append(colorbar(d.cbar));
    if (d.parts_list) st.parts = d.parts_list;
    if (d.fields) st.fields = d.fields;
    if (d.summary) setStatus(`FEM: ${d.summary.nodes.toLocaleString('es')} nodos · |U|máx = ${S.us.q('L', d.summary.umax, 3)} · von Mises máx = ${S.us.q('S', d.summary.vmmax, 1)}`);
    if (d.message) toast(Array.isArray(d.message) ? d.message[0] : String(d.message), 'info');
  } catch (e) { errorBox(e); }
}
function backToModel() { E.femView = false; clear(E.ui.fembar); runMesh.flush(); applyLoads(); }

function colorbar(cb) {
  const cv = h('canvas', { width: 14, height: 140, style: { borderRadius: '4px', border: '1px solid var(--border)' } });
  const g = cv.getContext('2d'); const n = cb.colors.length;
  for (let i = 0; i < n; i++) { const c = cb.colors[n - 1 - i]; g.fillStyle = `rgb(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)})`; g.fillRect(0, (i * 140) / n, 14, 140 / n + 1); }
  return h('div', { class: 'card-sec', style: { display: 'flex', gap: '8px', padding: '8px 10px', alignItems: 'stretch' } }, cv,
    h('div', { style: { display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: '11.5px' } }, h('b', { text: cb.title }), h('span', { text: fmt(cb.vmax) }), h('span', { text: fmt((cb.vmax + cb.vmin) / 2) }), h('span', { text: fmt(cb.vmin) })));
}

// ---------------------------------------------------------------------------------------------------- informe (ventana flotante y movible)
function openReport() {
  if (E.report) { E.report.win.close(); return; }
  const box = h('div', { class: 'scroll', style: { padding: '4px 14px 14px' } });
  const mem = h('div', { class: 'memory', style: { padding: '4px 18px 18px', overflow: 'auto', flex: 1 } });
  const nod = h('div', { class: 'scroll', style: { padding: '4px 14px 14px' } });
  const t = tabs([
    { id: 'res', label: 'Resultados por operación', icon: 'check', render: () => { fillResults(box, null, { forceOpen: true, pick: false }); return box; } },
    { id: 'mem', label: 'Memoria de cálculo (fórmulas)', icon: 'file-text', render: () => { mem.innerHTML = E.res && E.res.memory ? E.res.memory : '<p class="muted" style="padding:14px">Sin memoria: calcule primero.</p>'; return mem; } },
    { id: 'nod', label: 'Análisis nodal', icon: 'zap', render: () => { const keep = E.ui.nodBox; E.ui.nodBox = nod; renderNodal(); E.ui.nodBox = keep; return nod; } },
  ], { cls: 'pill' });
  t.style.flex = '1'; t.style.minHeight = '0';
  const body = h('div', { class: 'report-dock' }, t);
  const win = modal({ title: `Informe de cálculo — ${E.conn().name || E.conn().element}`, icon: 'file-text', width: 880, floating: true, pos: { x: Math.max(20, innerWidth - 920), y: 64 }, body,
    footer: [btn('PDF…', { icon: 'file-down', onClick: () => exportReport('pdf') }), btn('Word…', { icon: 'file-down', onClick: () => exportReport('docx') }), btn('STEP…', { icon: 'box', onClick: exportStep }), h('span', { class: 'grow' }),
      btn('Cerrar', { onClick: () => win.close() })],
    onClose: () => { E.report = null; } });
  win.el.style.height = '70vh';
  win.body.style.padding = '0'; win.body.style.display = 'flex';
  E.report = { win, refresh: () => { if (!E.report) return; const cur = t.current(); t.show(cur); } };
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
