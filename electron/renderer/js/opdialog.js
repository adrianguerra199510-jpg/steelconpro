// Ventana de una operacion: al crear una operacion (o al editarla) se abre para elegir sus elementos y parametros.
// Los cambios se ven en vivo en el 3D; «Cancelar» los revierte.
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, btn, tabs, field, selectInput, checkInput, segmented, chip, errorBox, clear, numInput } from './ui.js';
import { renderItems, getPath, setPath } from './forms.js';
import { sectionPicker } from './sectionpicker.js';
import { baseplateForm } from './bpform.js';

const OPK = () => S.C.ops;
export const OP_ICON = { 'Placa simple (corte)': 'square', 'Doble ángulo (corte)': 'square', 'Asiento (ángulo)': 'square', 'Placa extrema a ras (momento)': 'layers', 'Placa extrema extendida (momento)': 'layers',
  'Alas soldadas y alma atornillada (momento)': 'zap', 'Cartela atornillada (diagonal)': 'triangle', 'Cartela con miembro soldado (diagonal)': 'triangle', 'Corte del extremo (cope)': 'scissors',
  'Placas de continuidad': 'layers', 'Placa base (apoyo sobre concreto)': 'box', 'Placa (refuerzo, cartela o rigidizador)': 'square', 'Pernos entre elementos': 'nut', 'Soldadura de filete entre elementos': 'zap', 'Corte de elementos': 'scissors', 'Ángulo (herraje)': 'square', 'Huecos y ranuras': 'nut', 'Recorte contra otro elemento': 'scissors' };
export const OP_COLOR = { 'Conexión de corte': '#4a90d9', 'Conexión de momento': '#e8731a', 'Conexión de diagonal': '#4fae6a', 'Placas, pernos y soldaduras': '#8b5cf6', 'Modificar elementos': '#8a94a0',
  'Rigidizar el miembro principal': '#9b6fc9', 'Apoyo del miembro': '#c9a227' };
export function groupOf(kind) { return S.C.ops.groups.find(([, ks]) => ks.includes(kind))?.[0] || ''; }
export const opColor = (kind) => OP_COLOR[groupOf(kind)] || '#8a94a0';

const HELP = {
  'Placa simple (corte)': 'Placa soldada al miembro principal y atornillada al alma del miembro conectado (una fila vertical de pernos).',
  'Doble ángulo (corte)': 'Dos ángulos en el alma del miembro conectado, atornillados al principal.',
  'Asiento (ángulo)': 'Ángulo de asiento bajo el ala inferior del miembro conectado.',
  'Placa extrema a ras (momento)': 'Placa soldada al extremo del miembro y atornillada al ala del principal; pernos entre las alas.',
  'Placa extrema extendida (momento)': 'Placa extrema que se extiende por encima (y debajo) de las alas; pernos dentro y fuera de ellas.',
  'Alas soldadas y alma atornillada (momento)': 'Alas soldadas al principal; el alma lleva una placa simple atornillada.',
  'Cartela atornillada (diagonal)': 'Cartela soldada al principal y atornillada a la diagonal; las diagonales del mismo plano comparten cartela.',
  'Cartela con miembro soldado (diagonal)': 'Cartela soldada al principal con la diagonal soldada a la cartela (sin pernos).',
  'Corte del extremo (cope)': 'Recorta las alas (y parte del alma) en el extremo de los miembros elegidos.',
  'Placas de continuidad': 'Placas horizontales dentro de la columna I, a la altura de las alas del miembro conectado.',
  'Placa base (apoyo sobre concreto)': 'Placa base con anclajes sobre concreto en el extremo libre de un miembro: cálculo cerrado (AISC DG1, ACI 318) y análisis 3D por elementos finitos.',
  'Placa (refuerzo, cartela o rigidizador)': 'Una placa sobre la cara de un miembro, de la placa base o de otra placa: refuerzo soldado o atornillado, cartela o rigidizador. La placa es un elemento nuevo al que otras operaciones pueden unirse.',
  'Pernos entre elementos': 'Un grupo de pernos que atraviesa los elementos que elija, a partir de una cara.',
  'Soldadura de filete entre elementos': 'Cordón de filete adicional entre las placas elegidas y la cara a la que están unidas.',
  'Corte de elementos': 'Recorte (cope) del extremo de los miembros que elija.',
  'Ángulo (herraje)': 'Un ángulo L como elemento propio, apoyado sobre una cara y unido por soldadura o por pernos. Otras operaciones pueden unirse a sus piernas.',
  'Huecos y ranuras': 'Huecos circulares, ranuras o huecos rectangulares en una grilla, sobre la cara de un elemento.',
  'Recorte contra otro elemento': 'Recorta el extremo de un miembro contra la cara de otro elemento (con holgura) o con un inglete entre dos miembros.',
};

const CONN_FIELDS = (kind, C) => {
  const K = C.op;
  const bolted = [K.TAB, K.DANG, K.SEAT, K.EP_FLUSH, K.EP_EXT, K.WELD, K.GUSSET];
  return {
    bolt_size: bolted.includes(kind), bolt_grade: bolted.includes(kind),
    n_bolts: [K.TAB, K.DANG, K.WELD, K.GUSSET].includes(kind), bolt_s: [K.TAB, K.DANG, K.WELD, K.GUSSET].includes(kind),
    plate_t: true, plate_steel: true, weld_size: kind !== K.SEAT, ep_ext: kind === K.EP_EXT,
  };
};

export async function openOperation(E, index, { isNew = false } = {}) {
  const conn = E.conn();
  const nd = conn.node;
  const op = nd.operations[index];
  const orig = JSON.parse(JSON.stringify(op));
  const us = E.us();
  const C = S.C;
  let info = (await call('element_info', { connection: conn })).elements;
  const names = () => info.map((e) => e.name);
  const el = (n) => info.find((e) => e.name === n);
  const kind = op.kind;
  const K = C.op;
  const isGeneric = [K.PLATE, K.BOLTS, K.FILLET, K.CUT, K.ANGLE, K.HOLE, K.TRIM].includes(kind);
  const members = nd.members.map((m) => m.name);
  let mdlRoot;
  const refresh = () => E.changed({ geometry: true });
  const ctx = { us, get: () => op, onChange: (path) => { refresh(); mdlRoot && mdlRoot.refresh && mdlRoot.refresh(); mdlRoot && mdlRoot.onField && path && mdlRoot.onField(path); }, hide: () => false };

  // ---- partes de los formularios
  const memberSelect = (label, all) => field(label, selectInput({ value: op.member, options: all ? nd_names(nd) : members, onChange: (v) => { op.member = v; ctx.onChange(); } }));
  const nd_names = (n) => [n.main_name, ...n.members.map((m) => m.name)];
  const numField = (label, path, uk, lo, hi, step, dec, help) => ({ path, label, type: 'num', uk, lo, hi, step, dec, help });

  const body = h('div', { class: 'col gap-12' });
  const head = h('div', { class: 'row', style: { alignItems: 'flex-start' } },
    h('div', { class: 'chip-ic', style: { background: opColor(kind), color: '#fff', width: '34px', height: '34px', borderRadius: '9px', display: 'flex', alignItems: 'center', justifyContent: 'center' } }, svg(OP_ICON[kind] || 'box', 18)),
    h('div', { class: 'grow' }, h('div', { style: { fontWeight: 700 }, text: kind }), h('div', { class: 'muted', style: { fontSize: '12.5px' }, text: HELP[kind] || '' })));
  body.append(head);

  const refreshers = [];
  const addForm = (items, opts) => { const g = renderItems(items, ctx, opts); refreshers.push(g.refresh); return g; };

  if (C.ops.connection.includes(kind)) {
    const vis = CONN_FIELDS(kind, C);
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elementos' }),
      h('div', { class: 'form-grid' }, memberSelect('Miembro que se conecta', false), h('div', { class: 'field' }, h('span', { class: 'lbl', text: 'Se conecta a' }), h('div', { class: 'input row', style: { background: 'var(--surface-2)' } }, svg('component', 15), h('span', { text: `Miembro principal «${nd.main_name}»` }))))));
    const items = [];
    const isTab = kind === K.TAB;
    if (vis.bolt_size) items.push({ path: 'bolt_size', label: 'Diámetro de los pernos', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad de los pernos', type: 'combo', items: C.bolt_grades });
    if (vis.n_bolts) items.push({ path: 'n_bolts', label: isTab ? 'Filas de pernos' : kind.startsWith('Cartela') ? 'Filas de pernos' : 'Pernos por fila', type: 'int', lo: 1, hi: 14 });
    if (isTab) items.push({ path: 'n_cols', label: 'Columnas de pernos', type: 'int', lo: 1, hi: 4, help: 'Con más de una columna los pernos se verifican por el método elástico del grupo (conservador).' });
    if (vis.n_bolts) items.push(numField(isTab ? 'Separación entre filas' : 'Separación de los pernos', 'bolt_s', 'L', 1, 24));
    if (isTab) items.push(numField('Separación entre columnas', 'bolt_g', 'L', 1, 24),
      numField('Alto de la placa (0 = automático)', 'tab_H', 'L', 0, 60, null, null, 'A lo largo del peralte de la viga. 0 = (filas − 1)·separación + 3 in.'),
      numField('Ancho de la placa (0 = automático)', 'tab_W', 'L', 0, 40, null, null, 'A lo largo de la viga, desde la cara del soporte. 0 = hasta la última columna + 1.5 in.'));
    items.push(numField(kind.startsWith('Cartela') ? 'Espesor de la cartela' : 'Espesor de placa / ángulo', 'plate_t', 'L', 0.0625, 4, 0.0625),
      { path: 'plate_steel', label: 'Acero de la placa', type: 'combo', items: C.plate_steels.map((s) => s.name) });
    if (vis.weld_size) items.push(numField('Cateto del filete', 'weld_size', 'L', 0.0625, 1, 0.0625));
    if (vis.ep_ext) items.push(numField('Extensión de la placa extrema', 'ep_ext', 'L', 0.5, 24));
    if (isTab || kind === K.DANG) items.push({ path: 'cope_auto', label: 'Cortar la viga secundaria si choca con las alas del principal', type: 'check', wide: true,
      help: 'Calcula, según la posición de la viga en el espacio, el corte (cope) superior e inferior y su largo para que encaje en la viga principal.' });
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Pernos, placas y soldadura' }), addForm(items)));
  } else if (kind === K.COPE || kind === K.CUT) {                   // corte
    const tg = new Set(op.targets && op.targets.length ? op.targets : [op.member]);
    const checks = h('div', { class: 'col gap-4' });
    for (const m of members) checks.append(checkInput({ value: tg.has(m), label: m, onChange: (v) => { v ? tg.add(m) : tg.delete(m); op.targets = [...tg]; op.member = op.targets[0] || ''; ctx.onChange(); } }));
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elementos a cortar' }), members.length ? checks : h('p', { class: 'muted', text: 'Agregue miembros conectados para poder cortarlos.' })));
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Corte' }), addForm([
      { path: 'cut_at', label: 'Extremo', type: 'combo', items: ['Inicio', 'Fin'], help: 'Inicio: el extremo que llega al principal. Fin: el extremo libre.' },
      numField('Corte superior: profundidad', 'cope_top', 'L', 0, 24), numField('Corte inferior: profundidad', 'cope_bot', 'L', 0, 24), numField('Largo del corte desde el extremo', 'cope_len', 'L', 0, 48)])));
  } else if (kind === K.CONT) {                                                // continuidad
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elementos' }), h('div', { class: 'form-grid' }, memberSelect('Miembro cuyas alas continúan', false)), h('div', { style: { height: '8px' } }),
      addForm([numField('Espesor de las placas', 'cont_t', 'L', 0.125, 4, 0.0625)])));
  } else if (kind === K.BASE) {
    const sel = memberSelect('Miembro que lleva la placa base', true);
    const endSel = field('Extremo del principal', selectInput({ value: op.end >= 0 ? '+' : '−', options: [{ value: '−', label: 'Lado − (abajo si es vertical)' }, { value: '+', label: 'Lado +' }], onChange: (v) => { op.end = v === '+' ? 1 : -1; ctx.onChange(); } }));
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elemento' }), h('div', { class: 'form-grid' }, sel, endSel),
      h('p', { class: 'hint-text', style: { marginTop: '8px' }, text: 'La placa queda perpendicular al eje del miembro, en su extremo libre. El perfil es el del miembro; se cambia en Miembros.' })));
    body.append(await baseplateForm(E, ctx));
  } else if (kind === K.PLATE) {                                               // placa
    mdlRoot = plateBody(body, E, op, ctx, info, names, el, nd, us, addForm, index);
  } else if (kind === K.BOLTS) {                                               // pernos
    mdlRoot = boltsBody(body, E, op, ctx, info, el, nd, us, addForm, index);
  } else if (kind === K.FILLET) {                                               // soldadura
    mdlRoot = weldBody(body, E, op, ctx, info, nd, us, addForm, index);
  } else if (kind === K.ANGLE) {
    mdlRoot = angleBody(body, E, op, ctx, info, el, nd, addForm);
  } else if (kind === K.HOLE) {
    mdlRoot = holeBody(body, E, op, ctx, info, el, nd, addForm);
  } else if (kind === K.TRIM) {
    mdlRoot = trimBody(body, E, op, ctx, info, el, nd, addForm);
  }

  // ---- fuerzas de diseño (operaciones generales)
  if (isGeneric && ![K.CUT, K.HOLE, K.TRIM].includes(kind)) {
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Fuerzas de diseño de esta operación (opcional)' }),
      h('p', { class: 'hint-text', text: 'Con estas fuerzas se verifica la unión (pernos, soldadura y placa). Déjelas en cero si solo quiere ver la geometría y las verificaciones geométricas.' }),
      addForm([numField('Cortante de diseño', 'force_V', 'F', 0, 1e6, 1), numField('Tracción de diseño', 'force_T', 'F', 0, 1e6, 1)])));
  }

  // la edicion ocurre en el panel derecho (el visor queda libre): «Cerrar» (X) conserva los cambios, «Cancelar» los revierte
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => {
      if (done) return; done = true;
      if (!ok) {
        if (isNew) nd.operations.splice(index, 1); else Object.assign(op, orig);
        E.changed({ geometry: true });
      }
      panel.close('done'); resolve(ok);
    };
    const panel = E.showPanel({ title: `${isNew ? 'Nueva operación' : 'Operación'} ${index + 1}`, icon: OP_ICON[kind] || 'box', color: opColor(kind), body,
      footer: [btn('Cancelar', { onClick: () => finish(false) }), btn(isNew ? 'Agregar' : 'Aceptar', { kind: 'primary', icon: 'check', onClick: () => finish(true) })],
      onClose: () => { if (!done) { done = true; resolve(true); } } });
  });
}

// ---------------------------------------------------------------------------------------------------------- placa
function descendants(nd, name) {
  const out = new Set([name]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const o of nd.operations) if (o.kind === S.C.op.PLATE && (out.has(o.parent) || (o.targets || []).some((t) => out.has(t))) && !out.has(o.name)) { out.add(o.name); grew = true; }
  }
  return out;
}

function plateBody(body, E, op, ctx, info, names, el, nd, us, addForm, index) {
  const C = S.C;
  const bad = descendants(nd, op.name);
  const root = h('div', { class: 'col gap-12' });
  const parentSel = h('div');
  const faceSel = h('div');
  const buildParent = () => {
    clear(parentSel); clear(faceSel);
    const opts = info.filter((e) => !bad.has(e.name)).map((e) => ({ value: e.name, label: `${e.name} — ${e.type}${e.main ? ' (principal)' : ''}` }));
    parentSel.append(field('Se une al elemento', selectInput({ value: op.parent, options: opts, onChange: (v) => { op.parent = v; const e = el(v); if (e && !e.faces.includes(op.face)) op.face = e.faces[0]; buildParent(); ctx.onChange(); } })));
    const e = el(op.parent);
    faceSel.append(field('En la cara', selectInput({ value: op.face, options: (e ? e.faces : []), onChange: (v) => { op.face = v; ctx.onChange(); } })));
  };
  buildParent();
  const roleSeg = segmented(C.roles.map((r) => ({ value: r, label: r })), op.role, async (v) => {
    op.role = v;
    const d = await call('op_defaults', { kind: op.kind, role: v });
    for (const k of ['orient', 'shape', 'pl_L', 'pl_W', 'plate_t', 'pl_clip']) if (k in d) op[k] = d[k];
    rebuild(); ctx.onChange();
  });
  const nameInp = h('input', { class: 'input', type: 'text', value: op.name, onchange: (e) => { const v = e.target.value.trim(); if (v && v !== op.name && !info.some((x) => x.name === v)) { E.renameElement(op.name, v); op.name = v; } else e.target.value = op.name; ctx.onChange(); } });
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Placa' }), h('div', { class: 'form-grid' }, field('Nombre del elemento', nameInp), field('Función', roleSeg)),
    h('div', { style: { height: '10px' } }), h('div', { class: 'form-grid' }, parentSel, faceSel)));
  const geom = h('div'); const union = h('div');
  root.append(geom, union);
  function rebuild() {
    clear(geom); clear(union);
    const perp = op.orient !== C.orients[0];
    const items = [];
    if (op.role === 'Rigidizador') items.push({ path: 'orient', label: 'Orientación', type: 'combo', items: C.orients, wide: false });
    items.push({ path: 'shape', label: 'Forma', type: 'combo', items: C.shapes });
    items.push(numField(perp ? 'Largo transversal / longitudinal' : 'Largo (a lo largo del elemento)', 'pl_L', 'L', 0.5, 600), numField(perp ? 'Altura sobre la cara' : 'Ancho (a lo ancho de la cara)', 'pl_W', 'L', 0.5, 600),
      numField('Posición del centro a lo largo del elemento', 'pl_s', 'L', -600, 6000, null, null, 'Medida desde el inicio del elemento padre.'), numField('Desplazamiento transversal del centro', 'pl_u', 'L', -600, 600),
      numField('Giro en el plano de la cara', 'pl_rot', '-', -180, 180, 5, 1), numField('Espesor', 'plate_t', 'L', 0.0625, 4, 0.0625));
    if (op.shape === C.shapes[2]) items.push(numField('Lado del recorte de la esquina', 'pl_clip', 'L', 0, 100));
    if (op.shape === C.shapes[4]) items.push(numField('Ancho de la base superior (0 = igual)', 'pl_L2', 'L', 0, 600));
    items.push({ path: 'plate_steel', label: 'Acero de la placa', type: 'combo', items: C.plate_steels.map((s) => s.name) });
    geom.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Geometría' }), addForm(items)));
    if (op.shape === C.shapes[6]) geom.append(polyEditor(op, ctx));
    const oi = [{ path: 'opening', label: 'Abertura en la placa', type: 'combo', items: C.openings }];
    if (op.opening === C.openings[1]) oi.push(numField('Diámetro', 'op_D', 'L', 0.1, 200), numField('Desplazamiento en el largo', 'op_x', 'L', -300, 300), numField('Desplazamiento en el ancho', 'op_y', 'L', -300, 300));
    if (op.opening === C.openings[2]) oi.push(numField('Ancho', 'op_W', 'L', 0.1, 200), numField('Alto', 'op_H', 'L', 0.1, 200), numField('Desplazamiento en el largo', 'op_x', 'L', -300, 300), numField('Desplazamiento en el ancho', 'op_y', 'L', -300, 300));
    if (op.opening === C.openings[3]) {
      oi.push({ path: 'op_member', label: 'Miembro que atraviesa la placa', type: 'combo', items: info.filter((e) => e.type === 'miembro').map((e) => e.name) }, numField('Holgura alrededor', 'op_clear', 'L', 0, 12));
    }
    const og = addForm(oi);
    geom.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Abertura' }), og));
    const un = [];
    const att = segmented(C.attaches.map((a) => ({ value: a, label: a })), op.attach, (v) => { op.attach = v; rebuild(); ctx.onChange(); });
    un.push(h('div', { class: 'form-grid' }, field('Unión al elemento', att)));
    const f = [];
    if (op.attach === C.attaches[0] || perp) f.push(numField('Cateto / garganta', 'weld_size', 'L', 0.0625, 1, 0.0625), { path: 'weld_type', label: 'Tipo de soldadura', type: 'combo', items: C.weld_types }, { path: 'weld_all', label: 'Soldar todo el contorno', type: 'check', wide: true });
    else f.push({ path: 'bolt_size', label: 'Diámetro de los pernos', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad', type: 'combo', items: C.bolt_grades },
      { path: 'rows', label: 'Filas de pernos (a lo largo)', type: 'int', lo: 1, hi: 20 }, { path: 'cols', label: 'Columnas de pernos (a lo ancho)', type: 'int', lo: 1, hi: 10 },
      numField('Separación a lo largo', 'bolt_s', 'L', 1, 40), numField('Separación a lo ancho', 'bolt_g', 'L', 1, 40));
    union.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Unión' }), ...un, h('div', { style: { height: '10px' } }), addForm(f),
      (op.attach === C.attaches[0] || perp) && !op.weld_all ? edgePicker(E, op, ctx, index) : null,
      perp && op.attach === C.attaches[1] ? h('p', { class: 'hint-text', text: 'Una placa perpendicular a la cara (rigidizador) se suelda.' }) : null));
  }
  rebuild();
  body.append(root);
  root.refresh = () => {};
  root.onField = (p) => { if (['shape', 'opening', 'weld_all', 'orient', 'weld_type'].includes(p)) rebuild(); };
  return root;
}

// ---------------------------------------------------------------------------------------------------------- pernos
function boltsBody(body, E, op, ctx, info, el, nd, us, addForm) {
  const C = S.C;
  const root = h('div', { class: 'col gap-12' });
  const parentSel = h('div'); const faceSel = h('div');
  const build = () => {
    clear(parentSel); clear(faceSel);
    parentSel.append(field('Elemento de partida (cara donde apoyan las cabezas)', selectInput({ value: op.parent, options: info.map((e) => ({ value: e.name, label: `${e.name} — ${e.type}` })),
      onChange: (v) => { op.parent = v; const e = el(v); if (e && !e.faces.includes(op.face)) op.face = e.faces[0]; if (e && e.type === 'placa' && e.op != null) { op.pl_s = nd.operations[e.op].pl_L / 2; op.pl_u = 0; } build(); ctx.onChange(); if (mdlRoot && mdlRoot.refresh) mdlRoot.refresh(); } })));
    const e = el(op.parent);
    faceSel.append(field('Cara', selectInput({ value: op.face, options: e ? e.faces : [], onChange: (v) => { op.face = v; ctx.onChange(); } })));
  };
  build();
  const tg = new Set(op.targets || []);
  const checks = h('div', { class: 'col gap-4' });
  for (const e of info.filter((x) => x.name !== op.parent)) checks.append(checkInput({ value: tg.has(e.name), label: `${e.name} — ${e.type}`, onChange: (v) => { v ? tg.add(e.name) : tg.delete(e.name); op.targets = info.map((x) => x.name).filter((n) => tg.has(n)); ctx.onChange(); } }));
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elementos' }), h('div', { class: 'form-grid' }, parentSel, faceSel), h('div', { style: { height: '10px' } }),
    h('div', { class: 'lbl muted', style: { fontSize: '12px', fontWeight: 600, marginBottom: '6px' }, text: 'Otros elementos que atraviesan los pernos (hacia adentro, en el orden de la lista)' }), checks));
  const grid = addForm([
    { path: 'bolt_size', label: 'Diámetro', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad', type: 'combo', items: C.bolt_grades },
    { path: 'rows', label: 'Filas (a lo largo)', type: 'int', lo: 1, hi: 20 }, { path: 'cols', label: 'Columnas (a lo ancho)', type: 'int', lo: 1, hi: 10 },
    numField2('Separación a lo largo', 'bolt_s', 1, 40), numField2('Separación a lo ancho', 'bolt_g', 1, 40),
    numField2('Posición del centro a lo largo', 'pl_s', -600, 6000), numField2('Desplazamiento transversal', 'pl_u', -600, 600)]);
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Grupo de pernos' }), grid));
  root.refresh = () => grid.refresh();
  body.append(root);
  return root;
}
function numField2(label, path, lo, hi) { return { path, label, type: 'num', uk: 'L', lo, hi }; }

// ---------------------------------------------------------------------------------------------------------- soldadura
function weldBody(body, E, op, ctx, info, nd, us, addForm, index) {
  const C = S.C;
  const root = h('div', { class: 'col gap-12' });
  const sel = h('div'); const edges = h('div'); const cord = h('div');
  const rebuild = () => {
    clear(sel); clear(edges); clear(cord);
    const contour = op.weld_mode === C.weld_modes[1];
    const tg = new Set(op.targets || []);
    if (!contour) {
      const plates = info.filter((e) => e.type === 'placa' || e.type === 'ángulo');
      const checks = h('div', { class: 'col gap-4' });
      for (const e of plates) checks.append(checkInput({ value: tg.has(e.name), label: `${e.name}`, onChange: (v) => { v ? tg.add(e.name) : tg.delete(e.name); op.targets = [...tg]; ctx.onChange(); } }));
      sel.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Placas que se sueldan' }), plates.length ? checks : h('p', { class: 'muted', text: 'Primero agregue una operación «Placa»: la soldadura une las placas elegidas con la cara del elemento al que están unidas.' }),
        h('p', { class: 'hint-text', style: { marginTop: '8px' }, text: 'Opcional: elija abajo otro elemento y su cara para soldar la placa contra él (por ejemplo, el borde de una placa contra el ala de otro miembro).' })));
    } else {
      sel.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Miembro cuyo contorno se suelda' }), h('div', { class: 'form-grid' },
        field('Miembro', selectInput({ value: (op.targets || [])[0] || '', options: [{ value: '', label: '—' }, ...info.filter((e) => e.type === 'miembro').map((e) => ({ value: e.name, label: e.name }))], onChange: (v) => { op.targets = v ? [v] : []; ctx.onChange(); } })))));
    }
    const e = info.find((x) => x.name === op.parent);
    sel.append(h('div', { class: 'card-sec' }, h('h4', { text: contour ? 'Elemento y cara donde se suelda' : 'Soldar contra (opcional)' }), h('div', { class: 'form-grid' },
      field('Elemento', selectInput({ value: op.parent, options: [{ value: '', label: contour ? '—' : 'La cara a la que se une la placa' }, ...info.map((x) => ({ value: x.name, label: `${x.name} — ${x.type}` }))], onChange: (v) => { op.parent = v; const x = info.find((y) => y.name === v); op.face = x ? x.faces[0] : ''; rebuild(); ctx.onChange(); } })),
      field('Cara', selectInput({ value: op.face, options: e ? e.faces : [], onChange: (v) => { op.face = v; ctx.onChange(); } })))));
    cord.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Cordón' }), addForm([numField('Cateto / garganta', 'weld_size', 'L', 0.0625, 1, 0.0625), { path: 'weld_type', label: 'Tipo', type: 'combo', items: C.weld_types },
      { path: 'weld_all', label: 'Todos los bordes', type: 'check', wide: true }, numField('Inicio del cordón en cada borde', 'weld_a', 'L', 0, 600), numField('Largo del cordón (0 = todo el borde)', 'weld_len', 'L', 0, 600)])));
    if (!op.weld_all && !contour) edges.append(edgePicker(E, op, ctx, index, (op.targets || [])[0]));
  };
  const modeSeg = segmented(C.weld_modes.map((m) => ({ value: m, label: m })), op.weld_mode, (v) => { op.weld_mode = v; op.targets = []; rebuild(); ctx.onChange(); });
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Qué se suelda' }), modeSeg), sel, cord, edges);
  rebuild();
  root.onField = (p) => { if (p === 'weld_all') rebuild(); };
  body.append(root);
  return root;
}

// bordes de una placa para elegir donde se suelda (casillas por borde con su largo)
function edgePicker(E, op, ctx, index, plateName) {
  const box = h('div', { class: 'card-sec' }, h('h4', { text: 'Bordes que se sueldan' }));
  const list = h('div', { class: 'col gap-4' });
  box.append(list);
  const conn = E.conn();
  const idx = plateName ? conn.node.operations.findIndex((o) => o.name === plateName) : index;
  if (idx < 0) { list.append(h('p', { class: 'muted', text: 'Elija primero una placa.' })); return box; }
  call('plate_edges', { connection: conn, index: idx }).then((r) => {
    const sel = new Set(op.weld_edges || []);
    clear(list);
    for (const ed of r.edges) list.append(checkInput({ value: sel.has(ed.index), label: `Borde ${ed.index + 1} — largo ${E.us().out('L', ed.length).toFixed(2)} ${E.us().label('L')}`, onChange: (v) => { v ? sel.add(ed.index) : sel.delete(ed.index); op.weld_edges = [...sel].sort((a, b) => a - b); ctx.onChange(); } }));
  }).catch(() => {});
  return box;
}

// vertices de un poligono libre (u, v respecto del centro), uno por linea
function polyEditor(op, ctx) {
  const ta = h('textarea', { class: 'input', rows: 6, style: { fontFamily: 'monospace', width: '100%' } });
  ta.value = (op.pts && op.pts.length ? op.pts : [[-4, -3], [4, -3], [4, 3], [-4, 3]]).map((p) => `${p[0]}, ${p[1]}`).join('\n');
  const parse = () => {
    const pts = ta.value.split('\n').map((l) => l.split(/[,;\s]+/).filter(Boolean).map(Number)).filter((p) => p.length === 2 && p.every(Number.isFinite));
    if (pts.length >= 3) { op.pts = pts; ctx.onChange(); }
  };
  ta.addEventListener('change', parse);
  if (!op.pts || !op.pts.length) parse();
  return h('div', { class: 'card-sec' }, h('h4', { text: 'Vértices del polígono' }), h('p', { class: 'hint-text', text: 'Un vértice «u, v» por línea (in), medido desde el centro de la placa; mínimo 3.' }), ta);
}

// ---------------------------------------------------------------------------------------------------------- ángulo
function angleBody(body, E, op, ctx, info, el, nd, addForm) {
  const C = S.C;
  const root = h('div', { class: 'col gap-12' });
  const parentSel = h('div'); const faceSel = h('div'); const nameInp = h('input', { class: 'input', type: 'text', value: op.name, onchange: (e) => { const v = e.target.value.trim(); if (v && v !== op.name && !info.some((x) => x.name === v)) { E.renameElement(op.name, v); op.name = v; } else e.target.value = op.name; ctx.onChange(); } });
  const bad = descendants(nd, op.name);
  const build = () => {
    clear(parentSel); clear(faceSel);
    parentSel.append(field('Se apoya en el elemento', selectInput({ value: op.parent, options: info.filter((e) => !bad.has(e.name)).map((e) => ({ value: e.name, label: `${e.name} — ${e.type}` })), onChange: (v) => { op.parent = v; const e = el(v); if (e && !e.faces.includes(op.face)) op.face = e.faces[0]; build(); ctx.onChange(); } })));
    const e = el(op.parent);
    faceSel.append(field('En la cara', selectInput({ value: op.face, options: e ? e.faces : [], onChange: (v) => { op.face = v; ctx.onChange(); } })));
  };
  build();
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Ángulo' }), h('div', { class: 'form-grid' }, field('Nombre del elemento', nameInp), h('div'), parentSel, faceSel)));
  const un = h('div');
  const rebuild = () => {
    clear(un);
    const f = [];
    if (op.attach === C.attaches[0]) f.push(numField('Cateto del filete', 'weld_size', 'L', 0.0625, 1, 0.0625), { path: 'weld_type', label: 'Tipo de soldadura', type: 'combo', items: C.weld_types });
    else f.push({ path: 'bolt_size', label: 'Diámetro de los pernos', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad', type: 'combo', items: C.bolt_grades },
      { path: 'rows', label: 'Filas (a lo largo)', type: 'int', lo: 1, hi: 20 }, { path: 'cols', label: 'Columnas (a lo ancho)', type: 'int', lo: 1, hi: 10 }, numField('Separación a lo largo', 'bolt_s', 'L', 1, 40), numField('Separación a lo ancho', 'bolt_g', 'L', 1, 40));
    un.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Unión a la cara' }), h('div', { class: 'form-grid' }, field('Unión', segmented(C.attaches.map((a) => ({ value: a, label: a })), op.attach, (v) => { op.attach = v; rebuild(); ctx.onChange(); }))), h('div', { style: { height: '10px' } }), addForm(f)));
  };
  rebuild();
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Geometría' }), addForm([
    numField('Pierna sobre la cara (a lo ancho)', 'leg_a', 'L', 0.5, 40), numField('Pierna saliente', 'leg_b', 'L', 0.5, 40), numField('Espesor', 'plate_t', 'L', 0.0625, 3, 0.0625), numField('Largo del ángulo', 'pl_L', 'L', 0.5, 600),
    numField('Posición del centro a lo largo', 'pl_s', 'L', -600, 6000), numField('Desplazamiento transversal', 'pl_u', 'L', -600, 600),
    { path: 'leg_side', label: 'Pierna saliente hacia', type: 'combo', items: [1, -1] }, { path: 'plate_steel', label: 'Acero', type: 'combo', items: C.plate_steels.map((s) => s.name) }])), un);
  body.append(root);
  return root;
}

// ---------------------------------------------------------------------------------------------------------- huecos y ranuras
function holeBody(body, E, op, ctx, info, el, nd, addForm) {
  const C = S.C;
  const root = h('div', { class: 'col gap-12' });
  const parentSel = h('div'); const faceSel = h('div');
  const build = () => {
    clear(parentSel); clear(faceSel);
    parentSel.append(field('Elemento a perforar', selectInput({ value: op.parent, options: info.map((e) => ({ value: e.name, label: `${e.name} — ${e.type}` })), onChange: (v) => { op.parent = v; const e = el(v); if (e && !e.faces.includes(op.face)) op.face = e.faces[0]; build(); ctx.onChange(); } })));
    const e = el(op.parent);
    faceSel.append(field('Cara desde la que se perfora', selectInput({ value: op.face, options: e ? e.faces : [], onChange: (v) => { op.face = v; ctx.onChange(); } })));
  };
  build();
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elemento' }), h('div', { class: 'form-grid' }, parentSel, faceSel)));
  const geo = h('div');
  const rebuild = () => {
    clear(geo);
    const f = [{ path: 'hole_shape', label: 'Forma', type: 'combo', items: C.hole_shapes }];
    if (op.hole_shape === C.hole_shapes[0]) f.push(numField('Diámetro', 'hole_D', 'L', 0.1, 60));
    else if (op.hole_shape === C.hole_shapes[1]) f.push(numField('Largo total de la ranura', 'hole_L', 'L', 0.2, 60), numField('Ancho de la ranura', 'hole_D', 'L', 0.1, 30), numField('Giro', 'hole_rot', '-', -180, 180, 5, 1));
    else f.push(numField('Largo', 'hole_L', 'L', 0.2, 60), numField('Ancho', 'hole_W', 'L', 0.1, 60), numField('Giro', 'hole_rot', '-', -180, 180, 5, 1));
    f.push({ path: 'rows', label: 'Filas (a lo largo)', type: 'int', lo: 1, hi: 30 }, { path: 'cols', label: 'Columnas (a lo ancho)', type: 'int', lo: 1, hi: 30 },
      numField('Separación a lo largo', 'bolt_s', 'L', 0.5, 120), numField('Separación a lo ancho', 'bolt_g', 'L', 0.5, 120), numField('Posición del centro a lo largo', 'pl_s', 'L', -600, 6000), numField('Desplazamiento transversal', 'pl_u', 'L', -600, 600));
    geo.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Huecos' }), addForm(f)));
  };
  rebuild();
  root.append(geo);
  root.onField = (p) => { if (p === 'hole_shape') rebuild(); };
  body.append(root);
  return root;
}

// ---------------------------------------------------------------------------------------------------------- recorte contra otro elemento
function trimBody(body, E, op, ctx, info, el, nd, addForm) {
  const C = S.C;
  const root = h('div', { class: 'col gap-12' });
  const box = h('div');
  const build = () => {
    clear(box);
    const miter = op.trim_mode === C.trim_modes[1];
    const members = info.filter((e) => e.type === 'miembro');
    const e = el(op.parent);
    box.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Elementos' }), h('div', { class: 'form-grid' },
      field('Miembro que se recorta', selectInput({ value: (op.targets || [])[0] || '', options: [{ value: '', label: '—' }, ...members.map((m) => ({ value: m.name, label: m.name }))], onChange: (v) => { op.targets = v ? [v] : []; ctx.onChange(); } })),
      field('Extremo', selectInput({ value: op.trim_end, options: ['Inicio', 'Fin'], onChange: (v) => { op.trim_end = v; ctx.onChange(); } })),
      field(miter ? 'Otro miembro del inglete' : 'Elemento contra el que se recorta', selectInput({ value: op.parent, options: [{ value: '', label: '—' }, ...(miter ? members : info).map((x) => ({ value: x.name, label: `${x.name} — ${x.type}` }))], onChange: (v) => { op.parent = v; const x = el(v); if (x && !x.faces.includes(op.face)) op.face = x.faces[0]; build(); ctx.onChange(); } })),
      miter ? h('div') : field('Cara', selectInput({ value: op.face, options: e ? e.faces : [], onChange: (v) => { op.face = v; ctx.onChange(); } }))),
    miter ? null : h('div', { style: { height: '10px' } }), miter ? null : addForm([numField('Holgura respecto de la cara', 'trim_gap', 'L', -6, 12)])));
  };
  root.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Tipo de recorte' }), segmented(C.trim_modes.map((m) => ({ value: m, label: m })), op.trim_mode, (v) => { op.trim_mode = v; build(); ctx.onChange(); })), box);
  build();
  body.append(root);
  return root;
}
function numField(label, path, uk, lo, hi, step, dec, help) { return { path, label, type: 'num', uk, lo, hi, step, dec, help }; }
