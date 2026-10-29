// Bibliotecas: secciones (con Section Designer), materiales del usuario y plantillas de conexión.
import { call, latest } from './api.js';
import { S } from './state.js';
import { h, svg, btn, iconBtn, modal, field, selectInput, textInput, numInput, tabs, errorBox, toast, confirmBox, promptBox, clear, debounce, checkInput } from './ui.js';
import { openPicker, resetFamilies } from './sectionpicker.js';

// ================================================================================================== secciones
export async function openSections(E) {
  const us = S.us;
  let fams;
  try { fams = (await call('catalog_families', { free: true })).families; } catch (e) { return errorBox(e); }
  let fam = fams.find((f) => /personaliz|libres/i.test(f.label))?.id || fams[0].id, sel = null, q = '';
  const list = h('div', { style: { overflow: 'auto', flex: 1, border: '1px solid var(--border)', borderRadius: '9px', minHeight: '300px' } });
  const info = h('div', { class: 'card-sec', style: { fontSize: '12.5px', minHeight: '70px' } });
  const famSel = selectInput({ value: fam, options: fams.map((f) => ({ value: f.id, label: f.label })), onChange: (v) => { fam = v; load(); } });
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Buscar…' });
  search.addEventListener('input', debounce(() => { q = search.value; load(); }, 150));
  const editBtn = btn('Editar / copiar en Section Designer', { icon: 'pencil', onClick: () => sel && openDesigner(E, sel, load) });
  const delBtn = btn('Eliminar', { icon: 'trash', kind: 'danger', onClick: async () => {
    if (!sel || !(await confirmBox(`¿Eliminar la sección «${sel.label}»?`, { danger: true, ok: 'Eliminar' }))) return;
    try { await call('section_delete', { label: sel.label }); resetFamilies(); sel = null; load(); } catch (e) { errorBox(e); }
  } });
  const m = modal({ title: 'Secciones', icon: 'shapes', width: 760, cls: 'tall',
    body: h('div', { class: 'col', style: { height: '100%' } }, h('div', { class: 'row' }, h('div', { style: { width: '240px' } }, famSel), h('div', { class: 'grow' }, search)), list, info),
    footer: [btn('Nueva sección…', { icon: 'plus', onClick: () => openDesigner(E, null, load) }), editBtn, delBtn, h('span', { class: 'grow' }), btn('Cerrar', { kind: 'primary', onClick: () => m.close() })] });
  async function load() {
    clear(list);
    try {
      const r = q ? await call('catalog_search', { q, limit: 300 }) : await call('catalog_shapes', { family: fam, limit: 1000 });
      const tb = h('table', { class: 't' }, h('thead', null, h('tr', null, h('th', { text: 'Perfil' }), h('th', { text: 'Familia' }), h('th', { class: 'num', text: `d (${us.length})` }), h('th', { class: 'num', text: `bf (${us.length})` }))));
      const body = h('tbody');
      for (const s of r.shapes) {
        const tr = h('tr', { style: { cursor: 'pointer' }, class: sel && sel.label === s.label ? 'sel' : '', onclick: () => { sel = s; body.querySelectorAll('tr').forEach((x) => x.classList.remove('sel')); tr.classList.add('sel'); show(); } },
          h('td', { text: s.label, style: { fontWeight: 600 } }), h('td', { text: s.family }), h('td', { class: 'num', text: s.d ? us.fmt('L', s.d) : '' }), h('td', { class: 'num', text: s.bf ? us.fmt('L', s.bf) : '' }));
        body.append(tr);
      }
      tb.append(body); list.append(tb);
      if (!r.shapes.length) list.append(h('div', { class: 'muted', style: { padding: '14px' }, text: 'Sin secciones en esta familia. Cree una con «Nueva sección».' }));
    } catch (e) { errorBox(e); }
  }
  async function show() {
    clear(info);
    if (!sel) return;
    try {
      const f = await call('section_info', { label: sel.label });
      info.append(h('div', { style: { fontWeight: 700 }, text: `${f.label} · ${f.family}${f.source && f.source !== 'AISC' ? ' · propia' : ''}` }),
        h('div', { class: 'muted', text: `A = ${us.q('A', f.A)}   Ix = ${(f.Ix / us.fl ** 4).toPrecision(4)} ${us.length}⁴   Iy = ${(f.Iy / us.fl ** 4).toPrecision(4)} ${us.length}⁴   Zx = ${(f.Zx / us.fl ** 3).toPrecision(4)} ${us.length}³` }));
      delBtn.disabled = !(f.source && f.source !== 'AISC');
    } catch (e) { /* */ }
  }
  load();
}

// ---------------------------------------------------------------------------------------------------- Section Designer
function svgEl(tag, attrs, ...kids) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  for (const k of kids) e.append(k);
  return e;
}

export async function openDesigner(E, shape, onSaved) {
  const us = S.us;
  let tpls;
  try { tpls = (await call('section_templates')).templates; } catch (e) { return errorBox(e); }
  let comps, name = shape ? (shape.source !== 'AISC' && shape.kind === 'GEN' ? shape.label : `${shape.label}-copia`) : 'SECCION-LIBRE-1';
  const orig = shape && shape.kind === 'GEN' && shape.source !== 'AISC' ? shape.label : '';
  if (shape) { try { comps = (await call('section_components', { label: shape.label })).components; } catch (e) { return errorBox(e); } }
  else comps = (await call('section_build', { template: tpls[0].name })).components;
  let selIdx = 0, props = null, outlines = [], errors = [];
  const canvas = h('div', { style: { flex: 1, minHeight: '380px', background: 'var(--viewer-bg)', borderRadius: '10px', border: '1px solid var(--border)', position: 'relative' } });
  const propBox = h('div', { class: 'card-sec', style: { fontSize: '12.5px' } });
  const listBox = h('div', { class: 'col gap-4' });
  const formBox = h('div');
  const nameInp = textInput({ value: name, onChange: (v) => { name = v; } });

  const analyze = latest(async () => call('section_analyze', { components: comps }));
  const update = async () => {
    try {
      const r = await analyze();
      if (!r) return;
      props = r.props; outlines = r.outlines; errors = r.errors;
      drawCanvas(); drawProps(r); drawList();
    } catch (e) { errorBox(e); }
  };
  const updateDeb = debounce(update, 120);

  function drawCanvas() {
    clear(canvas);
    const pts = outlines.flat(2).filter(Boolean);
    let x0 = -1, y0 = -1, x1 = 1, y1 = 1;
    for (const ring of outlines.flat(1)) if (ring) for (const [x, y] of ring) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    const w = Math.max(x1 - x0, 1), hh = Math.max(y1 - y0, 1), pad = Math.max(w, hh) * 0.12;
    const s = svgEl('svg', { viewBox: `${x0 - pad} ${-(y1 + pad)} ${w + 2 * pad} ${hh + 2 * pad}`, style: 'position:absolute;inset:0;width:100%;height:100%' });
    const sw = Math.max(w, hh) / 300;
    s.append(svgEl('line', { x1: x0 - pad, x2: x1 + pad, y1: 0, y2: 0, stroke: 'var(--border-strong)', 'stroke-width': sw, 'stroke-dasharray': `${sw * 6} ${sw * 4}` }),
      svgEl('line', { y1: -(y1 + pad), y2: -(y0 - pad), x1: 0, x2: 0, stroke: 'var(--border-strong)', 'stroke-width': sw, 'stroke-dasharray': `${sw * 6} ${sw * 4}` }));
    comps.forEach((c, i) => {
      const rings = outlines[i];
      if (!rings) return;
      const d = rings.map((ring) => 'M' + ring.map(([x, y]) => `${x},${-y}`).join('L') + 'Z').join(' ');
      const isRing = c.t === 'ring';
      let dd = d;
      if (isRing) {
        const ro = c.d / 2, ri = Math.max(ro - c.ti, 0), circ = (r) => `M${c.x - r},${-c.y}a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0Z`;
        dd = circ(ro) + circ(ri);
      } else if (c.t === 'circ') { const r = c.d / 2; dd = `M${c.x - r},${-c.y}a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0Z`; }
      const p = svgEl('path', { d: dd, 'fill-rule': 'evenodd', fill: i === selIdx ? 'rgba(232,93,12,.45)' : 'rgba(80,120,190,.40)', stroke: i === selIdx ? '#e85d0c' : '#35538a', 'stroke-width': sw * 1.6, style: 'cursor:pointer' });
      p.addEventListener('click', () => { selIdx = i; drawForm(); drawCanvas(); drawList(); });
      s.append(p);
    });
    if (props && props.A) {
      s.append(svgEl('circle', { cx: props.cx, cy: -props.cy, r: sw * 4, fill: '#c0392b' }));
    }
    canvas.append(s);
  }
  function drawProps(r) {
    clear(propBox);
    if (!props || !props.A) { propBox.append(h('span', { class: 'muted', text: 'Sin propiedades: revise los componentes.' })); return; }
    const L4 = (v) => `${(v / us.fl ** 4).toPrecision(4)} ${us.length}⁴`, L3 = (v) => `${(v / us.fl ** 3).toPrecision(4)} ${us.length}³`;
    propBox.append(h('div', { style: { fontWeight: 700, marginBottom: '4px' }, text: 'Propiedades de la sección' }),
      h('div', { class: 'muted', text: `A = ${us.q('A', props.A)}  ·  ancho ${us.q('L', props.W)}  ·  alto ${us.q('L', props.H)}` }),
      h('div', { class: 'muted', text: `Ix = ${L4(props.Ix)}  Iy = ${L4(props.Iy)}  J = ${L4(props.J)}` }),
      h('div', { class: 'muted', text: `Sx = ${L3(props.Sx)}  Sy = ${L3(props.Sy)}  Zx = ${L3(props.Zx)}  Zy = ${L3(props.Zy)}` }),
      h('div', { class: 'muted', text: `rx = ${us.q('L', props.rx)}  ry = ${us.q('L', props.ry)}  ·  peso ${(props.weight).toFixed(1)} lb/ft` }));
    if (r.overlap > 1e-6) propBox.append(h('div', { class: 'warn-row', style: { marginTop: '6px' } }, svg('alert-triangle', 14), h('span', { text: `Hay ${us.q('A', r.overlap)} de área traslapada entre componentes.` })));
  }
  const desc = (c) => ({ rect: `Rectángulo ${us.fmt('L', c.w)} × ${us.fmt('L', c.h)}`, circ: `Círculo Ø${us.fmt('L', c.d)}`, ring: `Tubo Ø${us.fmt('L', c.d)} t=${us.fmt('L', c.ti)}`, poly: `Polígono (${(c.pts || []).length} vértices)` }[c.t] || c.t);
  function drawList() {
    clear(listBox);
    comps.forEach((c, i) => listBox.append(h('div', { class: `tree-item ${i === selIdx ? 'sel' : ''}`, onclick: () => { selIdx = i; drawForm(); drawCanvas(); drawList(); } },
      svg(c.t === 'rect' ? 'square' : c.t === 'poly' ? 'triangle' : 'crosshair', 15), h('div', { class: 'grow' }, h('div', { class: 'name', text: `${i + 1}. ${desc(c)}` }), errors[i] ? h('div', { class: 'sub', style: { color: 'var(--bad)' }, text: errors[i] }) : null),
      h('div', { class: 'acts' }, iconBtn('copy', 'Duplicar', (e) => { e.stopPropagation(); comps.splice(i + 1, 0, JSON.parse(JSON.stringify({ ...c, x: (c.x || 0) + 1, y: (c.y || 0) + 1 }))); selIdx = i + 1; drawForm(); update(); }),
        iconBtn('trash', 'Quitar', (e) => { e.stopPropagation(); comps.splice(i, 1); selIdx = Math.max(0, selIdx - 1); drawForm(); update(); })))));
  }
  function drawForm() {
    clear(formBox);
    const c = comps[selIdx];
    if (!c) return;
    const nf = (label, key, step = 0.25) => field(label, numInput({ value: us.out('L', c[key] ?? 0), dec: us.dec('L'), step: us.step('L') / 4, onChange: (v) => { c[key] = us.inn('L', v); updateDeb(); } }));
    const grid = h('div', { class: 'form-grid' });
    if (c.t === 'rect') grid.append(nf('Centro x', 'x'), nf('Centro y', 'y'), nf('Ancho', 'w'), nf('Alto', 'h'), field('Giro (°)', numInput({ value: c.rot || 0, dec: 1, onChange: (v) => { c.rot = v; updateDeb(); } })));
    else if (c.t === 'circ') grid.append(nf('Centro x', 'x'), nf('Centro y', 'y'), nf('Diámetro', 'd'));
    else if (c.t === 'ring') grid.append(nf('Centro x', 'x'), nf('Centro y', 'y'), nf('Diámetro exterior', 'd'), nf('Espesor de pared', 'ti'));
    else if (c.t === 'poly') {
      const ta = h('textarea', { class: 'input', rows: 6, style: { fontFamily: 'ui-monospace, monospace', gridColumn: '1 / -1' } });
      ta.value = (c.pts || []).map(([x, y]) => `${us.out('L', x)}\t${us.out('L', y)}`).join('\n');
      ta.addEventListener('change', () => {
        const pts = ta.value.split(/\r?\n/).map((l) => l.trim().split(/[\s;,]+/).map((x) => parseFloat(x))).filter((r) => r.length >= 2 && isFinite(r[0]) && isFinite(r[1])).map((r) => [us.inn('L', r[0]), us.inn('L', r[1])]);
        c.pts = pts; updateDeb();
      });
      grid.append(h('p', { class: 'hint-text', style: { gridColumn: '1 / -1' }, text: `Un vértice por línea: x y (${us.length}). Puede pegar desde Excel.` }), ta);
    }
    formBox.append(h('div', { class: 'card-sec' }, h('h4', { text: `Componente ${selIdx + 1}` }), grid));
  }
  const addComp = (t) => {
    const d = { rect: { t: 'rect', x: 0, y: 0, w: 4, h: 0.5, rot: 0 }, circ: { t: 'circ', x: 0, y: 0, d: 2 }, ring: { t: 'ring', x: 0, y: 0, d: 6, ti: 0.375 }, poly: { t: 'poly', pts: [[0, 0], [4, 0], [0, 4]] } }[t];
    comps.push(d); selIdx = comps.length - 1; drawForm(); update();
  };
  const tplSel = selectInput({ value: '', options: [{ value: '', label: 'Cargar plantilla…' }, ...tpls.map((t) => ({ value: t.name, label: t.name }))], onChange: async (v) => {
    if (!v) return;
    const t = tpls.find((x) => x.name === v);
    const values = {};
    const m2 = modal({ title: v, icon: 'shapes', width: 460,
      body: h('div', { class: 'form-grid c1' }, t.params.map((p) => { values[p.key] = p.default; return field(p.label, numInput({ value: p.length ? us.out('L', p.default) : p.default, dec: p.length ? us.dec('L') : 0, onChange: (x) => { values[p.key] = p.length ? us.inn('L', x) : x; } })); })),
      footer: [btn('Cancelar', { onClick: () => m2.close() }), btn('Usar plantilla', { kind: 'primary', icon: 'check', onClick: async () => {
        try { comps = (await call('section_build', { template: v, values })).components; selIdx = 0; drawForm(); update(); m2.close(); } catch (e) { errorBox(e); }
      } })] });
    tplSel.set('');
  } });
  const body = h('div', { style: { display: 'grid', gridTemplateColumns: '300px 1fr', gap: '14px', height: '100%' } },
    h('div', { class: 'col gap-12', style: { overflow: 'auto' } }, field('Nombre', nameInp), tplSel, h('div', { class: 'row', style: { flexWrap: 'wrap' } }, ...[['rect', 'Rect.'], ['circ', 'Círculo'], ['ring', 'Tubo'], ['poly', 'Polígono']].map(([t, l]) => btn(l, { icon: 'plus', onClick: () => addComp(t) }))), listBox, formBox),
    h('div', { class: 'col gap-12', style: { minHeight: 0 } }, canvas, propBox));
  const m = modal({ title: 'Section Designer', icon: 'shapes', width: 1040, cls: 'tall', body,
    footer: [btn('Cancelar', { onClick: () => m.close() }), btn('Guardar sección', { kind: 'primary', icon: 'save', onClick: async () => {
      try {
        const r = await call('section_save', { name, components: comps, replace: orig && orig === name ? orig : '' });
        resetFamilies(); toast(`Sección «${r.shape.label}» guardada`, 'ok'); m.close(); onSaved && onSaved();
      } catch (e) { errorBox(e); }
    } })] });
  drawForm(); update();
}

// ================================================================================================== materiales
export async function openMaterials(E) {
  let data;
  try { data = await call('materials_get'); } catch (e) { return errorBox(e); }
  const us = S.us;
  const KINDS = [
    ['steel', 'Aceros', [['name', 'Nombre', 'text'], ['Fy', 'Fy', 'S'], ['Fu', 'Fu', 'S']]],
    ['bolt', 'Pernos', [['name', 'Nombre', 'text'], ['Fnt', 'Fnt', 'S'], ['Fnv', 'Fnv', 'S']]],
    ['electrode', 'Electrodos', [['name', 'Nombre', 'text'], ['FEXX', 'FEXX', 'S']]],
    ['anchor', 'Anclajes', [['name', 'Nombre', 'text'], ['Fy', 'Fy', 'S'], ['Fu', 'Fu', 'S'], ['dmax', 'Ø máx (in)', 'raw']]],
    ['concrete', 'Concretos', [['name', 'Nombre', 'text'], ['fc', "f'c", 'S'], ['lam', 'λ', 'raw']]],
  ];
  const user = JSON.parse(JSON.stringify(data.user));
  for (const [k] of KINDS) user[k] = user[k] || [];
  const mk = (kind) => ({ steel: { name: 'Acero propio', Fy: 50, Fu: 65, E: 29000, nu: 0.3, rho: 0.2836 }, bolt: { name: 'Perno propio', Fnt: 90, Fnv: 54 }, electrode: { name: 'Electrodo propio', FEXX: 70 },
    anchor: { name: 'Anclaje propio', Fy: 55, Fu: 75, dmax: 4, ductile: true }, concrete: { name: 'Concreto propio', fc: 4, lam: 1 } }[kind]);
  const t = tabs(KINDS.map(([kind, label, cols]) => ({ id: kind, label, render: () => {
    const wrap = h('div', { class: 'col gap-12' });
    const builtin = data.all[kind].filter((x) => !x.extra);
    const bt = h('table', { class: 't compact' }, h('thead', null, h('tr', null, cols.map(([, l, ty]) => h('th', { class: ty === 'text' ? '' : 'num', text: l })))),
      h('tbody', null, builtin.map((r) => h('tr', null, cols.map(([k, , ty]) => h('td', { class: ty === 'text' ? '' : 'num', text: ty === 'S' ? us.fmt('S', r[k]) : String(r[k] ?? '') }))))));
    const ut = h('tbody');
    const drawUser = () => {
      clear(ut);
      user[kind].forEach((r, i) => ut.append(h('tr', null, ...cols.map(([k, , ty]) => h('td', { class: ty === 'text' ? '' : 'num' }, ty === 'text' ? textInput({ value: r[k], onChange: (v) => { r[k] = v; } })
        : numInput({ value: ty === 'S' ? us.out('S', r[k]) : r[k], dec: ty === 'S' ? us.dec('S') : 3, onChange: (v) => { r[k] = ty === 'S' ? us.inn('S', v) : v; } }))), h('td', null, iconBtn('trash', 'Quitar', () => { user[kind].splice(i, 1); drawUser(); })))));
      if (!user[kind].length) ut.append(h('tr', null, h('td', { colspan: cols.length + 1, class: 'muted', style: { padding: '10px' }, text: 'Sin materiales propios.' })));
    };
    drawUser();
    wrap.append(h('div', { class: 'card-sec' }, h('h4', { text: `Mis ${label.toLowerCase()}` }), h('table', { class: 't compact' }, h('thead', null, h('tr', null, cols.map(([, l, ty]) => h('th', { class: ty === 'text' ? '' : 'num', text: l })), h('th'))), ut),
      h('div', { style: { height: '8px' } }), btn('Agregar', { icon: 'plus', onClick: () => { user[kind].push(mk(kind)); drawUser(); } })),
      h('div', { class: 'card-sec' }, h('h4', { text: `${label} incluidos (${us.stress})` }), h('div', { style: { maxHeight: '240px', overflow: 'auto' } }, bt)));
    return wrap;
  } })), { cls: 'pill' });
  const m = modal({ title: 'Materiales', icon: 'database', width: 760, cls: 'tall', body: t,
    footer: [btn('Cancelar', { onClick: () => m.close() }), btn('Guardar', { kind: 'primary', icon: 'save', onClick: async () => {
      try { await call('materials_save', { user }); toast('Materiales guardados', 'ok'); m.close(); const c = await call('constants'); S.C = c; } catch (e) { errorBox(e); }
    } })] });
}

// ================================================================================================== plantillas de conexión
export async function openTemplates(E) {
  let list;
  const load = async () => { list = (await call('tpl_list')).templates; draw(); };
  const body = h('div', { class: 'col gap-12' });
  const draw = () => {
    clear(body);
    body.append(h('p', { class: 'hint-text', text: 'Una plantilla guarda los miembros, las operaciones y (opcionalmente) las cargas de la conexión actual para reutilizarlos en otros proyectos.' }));
    body.append(btn('Guardar la conexión actual como plantilla…', { icon: 'save', kind: 'primary', onClick: saveCurrent }));
    if (!list.length) body.append(h('p', { class: 'muted', text: 'Todavía no hay plantillas.' }));
    for (const t of list) body.append(h('div', { class: 'tree-item' }, svg('copy', 16), h('div', { class: 'grow' }, h('div', { class: 'name', text: t.name }), h('div', { class: 'sub', text: t.desc || t.date })),
      btn('Aplicar a esta conexión', { onClick: () => apply(t) }), iconBtn('trash', 'Eliminar', async () => { if (await confirmBox(`¿Eliminar la plantilla «${t.name}»?`, { danger: true, ok: 'Eliminar' })) { await call('tpl_delete', { path: t.file }); load(); } })));
  };
  async function saveCurrent() {
    const name = await promptBox('Nombre de la plantilla', '', { title: 'Nueva plantilla' });
    if (!name) return;
    try { await call('tpl_save', { connection: E.conn(), name, desc: '', loads: true }); toast('Plantilla guardada', 'ok'); load(); } catch (e) { errorBox(e); }
  }
  async function apply(t) {
    if (!(await confirmBox(`¿Reemplazar los miembros y operaciones de esta conexión con la plantilla «${t.name}»?`, { ok: 'Aplicar', detail: 'Puede deshacerlo con Ctrl+Z.' }))) return;
    try {
      const r = await call('tpl_load', { path: t.file });
      E.snap();
      const keep = E.conn();
      for (const k of ['name', 'element', 'author', 'date', 'u_len', 'u_force', 'u_stress', 'u_moment']) r.connection[k] = keep[k];
      E.replaceConn(r.connection); E.changed({ structure: true }); E.refreshTree(); m.close();
    } catch (e) { errorBox(e); }
  }
  const m = modal({ title: 'Plantillas de conexión', icon: 'copy', width: 620, cls: 'tall', body, footer: [btn('Cerrar', { kind: 'primary', onClick: () => m.close() })] });
  load().catch(errorBox);
}
