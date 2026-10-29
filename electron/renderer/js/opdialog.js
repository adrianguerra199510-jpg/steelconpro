// Ventana de una operacion: al crear una operacion (o al editarla) se abre para elegir sus elementos y parametros.
// Los cambios se ven en vivo en el 3D; «Cancelar» los revierte.
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, btn, modal, tabs, field, selectInput, checkInput, segmented, chip, errorBox, clear, numInput } from './ui.js';
import { renderItems, getPath, setPath } from './forms.js';
import { sectionPicker } from './sectionpicker.js';
import { baseplateForm } from './bpform.js';

const OPK = () => S.C.ops;
export const OP_ICON = { 'Placa simple (corte)': 'square', 'Doble ángulo (corte)': 'square', 'Asiento (ángulo)': 'square', 'Placa extrema a ras (momento)': 'layers', 'Placa extrema extendida (momento)': 'layers',
  'Alas soldadas y alma atornillada (momento)': 'zap', 'Cartela atornillada (diagonal)': 'triangle', 'Cartela con miembro soldado (diagonal)': 'triangle', 'Corte del extremo (cope)': 'scissors',
  'Placas de continuidad': 'layers', 'Placa base (apoyo sobre concreto)': 'box', 'Placa (refuerzo, cartela o rigidizador)': 'square', 'Pernos entre elementos': 'nut', 'Soldadura de filete entre elementos': 'zap', 'Corte de elementos': 'scissors' };
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
  const isGeneric = [K.PLATE, K.BOLTS, K.FILLET, K.CUT].includes(kind);
  const members = nd.members.map((m) => m.name);
  let mdlRoot;
  const refresh = () => E.changed({ geometry: true });
  const ctx = { us, get: () => op, onChange: () => { refresh(); mdlRoot && mdlRoot.refresh && mdlRoot.refresh(); }, hide: () => false };

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
    if (vis.bolt_size) items.push({ path: 'bolt_size', label: 'Diámetro de los pernos', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad de los pernos', type: 'combo', items: C.bolt_grades });
    if (vis.n_bolts) items.push({ path: 'n_bolts', label: kind.startsWith('Cartela') ? 'Filas de pernos' : 'Pernos por fila', type: 'int', lo: 1, hi: 12 }, numField('Separación de los pernos', 'bolt_s', 'L', 1, 24));
    items.push(numField(kind.startsWith('Cartela') ? 'Espesor de la cartela' : 'Espesor de placa / ángulo', 'plate_t', 'L', 0.0625, 4, 0.0625),
      { path: 'plate_steel', label: 'Acero de la placa', type: 'combo', items: C.plate_steels.map((s) => s.name) });
    if (vis.weld_size) items.push(numField('Cateto del filete', 'weld_size', 'L', 0.0625, 1, 0.0625));
    if (vis.ep_ext) items.push(numField('Extensión de la placa extrema', 'ep_ext', 'L', 0.5, 24));
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
    mdlRoot = weldBody(body, E, op, ctx, info, nd, us, addForm);
  }

  // ---- fuerzas de diseño (operaciones generales)
  if (isGeneric && kind !== K.CUT) {
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Fuerzas de diseño de esta operación (opcional)' }),
      h('p', { class: 'hint-text', text: 'Con estas fuerzas se verifica la unión (pernos, soldadura y placa). Déjelas en cero si solo quiere ver la geometría y las verificaciones geométricas.' }),
      addForm([numField('Cortante de diseño', 'force_V', 'F', 0, 1e6, 1), numField('Tracción de diseño', 'force_T', 'F', 0, 1e6, 1)])));
  }

  return new Promise((resolve) => {
    const finish = (ok) => {
      if (!ok) {
        if (isNew) nd.operations.splice(index, 1); else Object.assign(op, orig);
        E.changed({ geometry: true });
      }
      m.close(); resolve(ok);
    };
    const m = modal({ title: isNew ? `Nueva operación` : 'Editar operación', icon: OP_ICON[kind] || 'box', width: kind === K.BASE ? 860 : 640, cls: 'tall', body,
      footer: [btn('Cancelar', { onClick: () => finish(false) }), btn(isNew ? 'Agregar' : 'Aceptar', { kind: 'primary', icon: 'check', onClick: () => finish(true) })], closable: true, onClose: () => resolve(true) });
    m.back.addEventListener('mousedown', () => {});
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
    items.push({ path: 'plate_steel', label: 'Acero de la placa', type: 'combo', items: C.plate_steels.map((s) => s.name) });
    geom.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Geometría' }), addForm(items)));
    const un = [];
    const att = segmented(C.attaches.map((a) => ({ value: a, label: a })), op.attach, (v) => { op.attach = v; rebuild(); ctx.onChange(); });
    un.push(h('div', { class: 'form-grid' }, field('Unión al elemento', att)));
    const f = [];
    if (op.attach === C.attaches[0] || perp) f.push(numField('Cateto del filete', 'weld_size', 'L', 0.0625, 1, 0.0625), { path: 'weld_all', label: 'Soldar todo el contorno', type: 'check' });
    else f.push({ path: 'bolt_size', label: 'Diámetro de los pernos', type: 'combo', items: C.bolt_sizes }, { path: 'bolt_grade', label: 'Calidad', type: 'combo', items: C.bolt_grades },
      { path: 'rows', label: 'Filas de pernos (a lo largo)', type: 'int', lo: 1, hi: 20 }, { path: 'cols', label: 'Columnas de pernos (a lo ancho)', type: 'int', lo: 1, hi: 10 },
      numField('Separación a lo largo', 'bolt_s', 'L', 1, 40), numField('Separación a lo ancho', 'bolt_g', 'L', 1, 40));
    union.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Unión' }), ...un, h('div', { style: { height: '10px' } }), addForm(f),
      perp && op.attach === C.attaches[1] ? h('p', { class: 'hint-text', text: 'Una placa perpendicular a la cara (rigidizador) se suelda.' }) : null));
  }
  rebuild();
  body.append(root);
  root.refresh = () => {};
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
function weldBody(body, E, op, ctx, info, nd, us, addForm) {
  const plates = info.filter((e) => e.type === 'placa');
  const tg = new Set(op.targets || []);
  const checks = h('div', { class: 'col gap-4' });
  for (const e of plates) checks.append(checkInput({ value: tg.has(e.name), label: `${e.name}`, onChange: (v) => { v ? tg.add(e.name) : tg.delete(e.name); op.targets = [...tg]; ctx.onChange(); } }));
  const root = h('div', { class: 'col gap-12' },
    h('div', { class: 'card-sec' }, h('h4', { text: 'Placas que se sueldan' }), plates.length ? checks : h('p', { class: 'muted', text: 'Primero agregue una operación «Placa»: la soldadura une las placas elegidas con la cara del elemento al que están unidas.' })),
    h('div', { class: 'card-sec' }, h('h4', { text: 'Cordón' }), addForm([numField2('Cateto del filete', 'weld_size', 0.0625, 1), { path: 'weld_all', label: 'Todo el contorno', type: 'check' }])));
  body.append(root);
  return root;
}
function numField(label, path, uk, lo, hi, step, dec, help) { return { path, label, type: 'num', uk, lo, hi, step, dec, help }; }
