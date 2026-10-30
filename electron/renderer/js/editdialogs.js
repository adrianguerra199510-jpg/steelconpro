// Ventanas del editor: miembros, cargas del nudo y datos del proyecto (nombre, unidades).
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, btn, iconBtn, modal, field, selectInput, textInput, numInput, errorBox, toast, confirmBox } from './ui.js';
import { renderItems } from './forms.js';
import { sectionPicker } from './sectionpicker.js';

const num = (label, path, uk, lo, hi, step, dec, help) => ({ path, label, type: 'num', uk, lo, hi, step, dec, help });

function formCtx(E, obj, onChange) {
  return { us: E.us(), get: () => obj, onChange, hide: () => false, sectionPicker: (it, val, set) => sectionPicker(val, set) };
}

// Sustituye un nombre de elemento en todas las referencias del nudo (miembros, operaciones, cargas).
export function renameRefs(nd, old, nw) {
  const K = S.C.op;
  if (nd.main_name === old) nd.main_name = nw;
  for (const m of nd.members) if (m.name === old) m.name = nw;
  for (const o of nd.operations) {
    if (o.member === old) o.member = nw;
    if (o.parent === old) o.parent = nw;
    o.targets = (o.targets || []).map((t) => (t === old ? nw : t));
    if (o.kind === K.PLATE && o.name === old) o.name = nw;
  }
  for (const l of nd.loads) if (l.member === old) l.member = nw;
}

// ---------------------------------------------------------------------------------------------------- miembro
export async function openMember(E, name) {
  const conn = E.conn();
  const nd = conn.node;
  const C = S.C;
  const isMain = name === nd.main_name;
  const m = isMain ? null : nd.members.find((x) => x.name === name);
  if (!isMain && !m) return;
  E.snap();
  const before = JSON.stringify(nd);
  const steels = C.steels.map((s) => s.name);
  const body = h('div', { class: 'col gap-12' });
  const nameInp = textInput({ value: name, onChange: (v) => {
    v = v.trim();
    if (!v || v === name || nd.main_name === v || nd.members.some((x) => x.name === v) || nd.operations.some((o) => o.kind === C.op.PLATE && o.name === v)) { nameInp.value = name; return; }
    renameRefs(nd, name, v); name = v; E.changed({ structure: true });
  } });
  const ctxObj = isMain ? nd : m;
  const P = isMain ? { shape: 'main_shape', steel: 'main_steel', az: 'main_az', el: 'main_el', roll: 'main_roll' } : { shape: 'shape', steel: 'steel', az: 'az', el: 'el', roll: 'roll' };
  const ctx = formCtx(E, ctxObj, () => E.changed({ geometry: true }));
  const items = [
    { path: P.shape, label: 'Perfil', type: 'section' },
    { path: P.steel, label: 'Acero', type: 'combo', items: steels },
    num(isMain ? 'Azimut del eje (en planta)' : 'Azimut (en planta)', P.az, null, -360, 360, 5, 1), num(isMain ? 'Inclinación del eje (90° = vertical)' : 'Inclinación sobre la horizontal', P.el, null, -90, 90, 5, 1),
    num('Giro de la sección sobre su eje', P.roll, null, -180, 180, 5, 1)];
  if (isMain) {
    items.push({ path: 'main_end', label: 'Extremo', type: 'combo', items: C.end_labels }, num('Largo del lado − (abajo si es vertical)', 'main_len_neg', 'L', 0, 4000), num('Largo del lado +', 'main_len_pos', 'L', 0, 4000));
  } else {
    items.push(num('Posición sobre el principal', 'pos', 'L', -4000, 4000, null, null, 'Medida desde el nudo, a lo largo del eje del principal.'), num('Desplazamiento (peralte del principal)', 'off', 'L', -400, 400),
      num('Desplazamiento (ancho del principal)', 'off2', 'L', -400, 400), num('Largo dibujado', 'L', 'L', 1, 4000), num('Retranqueo del extremo', 'gap', 'L', 0, 48));
  }
  body.append(h('div', { class: 'card-sec' }, h('h4', { text: isMain ? 'Miembro principal' : 'Miembro conectado' }), h('div', { class: 'form-grid' }, field('Nombre', nameInp)),
    h('div', { style: { height: '10px' } }), renderItems(items, ctx)));
  if (!isMain) {
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Miembro principal' }),
      h('p', { class: 'muted', style: { margin: '0 0 8px' }, text: `El miembro principal es «${nd.main_name}». Puede designar este miembro como principal: el eje del nudo pasa a ser el suyo y los demás llegan a él.` }),
      btn('Designar como miembro principal', { icon: 'star', onClick: async () => {
        try {
          const r = await call('designate_main', { connection: conn, name });
          E.replaceConn(r.connection); E.changed({ structure: true });
          if (r.notes && r.notes.length) toast(r.notes.join(' '), 'info', 7000);
          if (E.panel) E.panel.close('done');
        } catch (e) { errorBox(e); }
      } })));
  }
  return new Promise((resolve) => {
    const panel = E.showPanel({ title: isMain ? `Miembro principal · ${name}` : `Miembro · ${name}`, icon: 'component', body,
      footer: [btn('Eliminar', { icon: 'trash', kind: 'danger', disabled: isMain, onClick: async () => {
        const deps = nd.operations.filter((o) => o.member === name || o.parent === name || (o.targets || []).includes(name));
        if (!(await confirmBox(`¿Eliminar el miembro «${name}»?`, { danger: true, ok: 'Eliminar', detail: deps.length ? `También se quitarán ${deps.length} operación(es) que lo usan.` : '' }))) return;
        const idx = nd.members.findIndex((x) => x.name === name);
        nd.members.splice(idx, 1);
        for (const o of deps) { const i = nd.operations.indexOf(o); if (i >= 0) await E.removeOperation(i, { silent: true }); }
        nd.loads = nd.loads.filter((l) => l.member !== name);
        E.sel = null; E.changed({ structure: true }); panel.close('done');
      } }), h('span', { class: 'grow' }), btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => panel.close('done') })],
      onClose: () => { if (JSON.stringify(nd) === before) E.dropSnap(); E.refreshTree(); resolve(true); } });
  });
}

// ---------------------------------------------------------------------------------------------------- cargas del nudo (análisis nodal)
export function openLoads(E) {
  const nd = E.conn().node;
  const us = E.us();
  E.snap();
  const before = JSON.stringify([nd.loads, nd.balance_end]);
  const NODE = '@nudo';
  const names = () => [{ value: nd.main_name, label: `${nd.main_name} (principal)` }, ...nd.members.map((x) => ({ value: x.name, label: x.name })), { value: NODE, label: 'Carga externa en el nudo (ejes globales)' }];
  const cols = [['N', 'F'], ['Vy', 'F'], ['Vz', 'F'], ['T', 'M'], ['My', 'M'], ['Mz', 'M']];
  const tb = h('tbody');
  const sideLbl = (v) => (v < 0 ? 'Lado −' : v > 0 ? 'Lado +' : 'Auto');
  const draw = () => {
    tb.replaceChildren();
    nd.loads.forEach((l, i) => {
      const tr = h('tr');
      const isMain = l.member === nd.main_name;
      tr.append(h('td', null, textInput({ value: l.case, onChange: (v) => { l.case = v; E.changed({ loads: true }); } })),
        h('td', null, selectInput({ value: l.member, options: names(), onChange: (v) => { l.member = v; if (v !== nd.main_name) l.side = 0; draw(); E.changed({ loads: true }); } })),
        h('td', null, isMain ? selectInput({ value: String(l.side || 0), options: [{ value: '0', label: 'Auto (el opuesto)' }, { value: '-1', label: 'Lado −' }, { value: '1', label: 'Lado +' }], onChange: (v) => { l.side = parseInt(v, 10); E.changed({ loads: true }); } }) : null));
      for (const [k, u] of cols) tr.append(h('td', { class: 'num' }, numInput({ value: us.out(u, l[k]), dec: us.dec(u === 'M' ? 'F' : u), onChange: (v) => { l[k] = us.inn(u, v); E.changed({ loads: true }); } })));
      tr.append(h('td', null, iconBtn('trash', 'Quitar', () => { nd.loads.splice(i, 1); draw(); E.changed({ loads: true }); })));
      tb.append(tr);
    });
    if (!nd.loads.length) tb.append(h('tr', null, h('td', { colspan: 10, class: 'muted', style: { padding: '14px' }, text: 'Sin casos de carga: escriba las acciones de los miembros que llegan al nudo.' })));
  };
  draw();
  const head = h('tr', null, h('th', { text: 'Caso' }), h('th', { text: 'Miembro' }), h('th', { text: 'Lado' }), ...cols.map(([k, u]) => h('th', { class: 'num', text: `${k} (${us.label(u)})` })), h('th'));
  const balSel = selectInput({ value: String(nd.balance_end ?? -1), options: [{ value: '-1', label: `Lado − de «${nd.main_name}»` }, { value: '1', label: `Lado + de «${nd.main_name}»` }], onChange: (v) => { nd.balance_end = parseInt(v, 10); E.changed({ loads: true }); } });
  const body = h('div', { class: 'col gap-12' },
    h('p', { class: 'hint-text', text: 'Análisis nodal: escriba la ACCIÓN DE CADA MIEMBRO SOBRE EL NUDO en su extremo junto al nudo, en sus ejes locales (x a lo largo del miembro hacia afuera del nudo, N > 0 = tracción; z el peralte; y = z × x). '
      + 'Una carga externa aplicada al nudo se escribe en ejes globales (N = Fx, Vy = Fy, Vz = Fz, T = Mx). El miembro principal da sus cargas en un lado; la acción en el otro lado (el que equilibra) se calcula por equilibrio de fuerzas y momentos del nudo '
      + 'y de ella salen las combinaciones de la placa base.' }),
    h('div', { class: 'card-sec' }, h('div', { class: 'form-grid' }, field('Lado del principal que equilibra el nudo', balSel))),
    h('div', { style: { overflow: 'auto' } }, h('table', { class: 't compact' }, h('thead', null, head), tb)),
    btn('Agregar carga', { icon: 'plus', onClick: () => { nd.loads.push({ case: nd.loads.length ? nd.loads[nd.loads.length - 1].case : 'Caso 1', member: nd.members[0] ? nd.members[0].name : nd.main_name, N: 0, Vy: 0, Vz: 0, T: 0, My: 0, Mz: 0, side: 0 }); draw(); E.changed({ loads: true }); } }));
  const mod = modal({ title: 'Cargas del nudo', icon: 'zap', width: 980, floating: true, pos: { x: 340, y: 80 }, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify([nd.loads, nd.balance_end]) === before) E.dropSnap(); E.refreshTree(); } });
}

// ---------------------------------------------------------------------------------------------------- proyecto y unidades
export function openProject(E) {
  const c = E.conn();
  const C = S.C;
  E.snap();
  const before = JSON.stringify([c.name, c.element, c.author, c.date, c.u_len, c.u_force, c.u_stress, c.u_moment]);
  const sets = C.units.sets;
  const setSel = selectInput({ value: '', options: [{ value: '', label: 'Personalizado…' }, ...Object.keys(sets).map((k) => ({ value: k, label: k }))], onChange: (v) => {
    if (!v) return; const [l, f, s, m] = sets[v]; c.u_len = l; c.u_force = f; c.u_stress = s; c.u_moment = m; sync(); } });
  const sel = (key, list) => selectInput({ value: c[key], options: list, onChange: (v) => { c[key] = v; sync(false); } });
  const sl = sel('u_len', Object.keys(C.units.len)), sf = sel('u_force', Object.keys(C.units.force)), ss = sel('u_stress', Object.keys(C.units.stress)), sm = sel('u_moment', Object.keys(C.units.moment));
  function sync(upd = true) {
    if (upd) { sl.set(c.u_len); sf.set(c.u_force); ss.set(c.u_stress); sm.set(c.u_moment); }
    E.applyUnits();
  }
  const text = (key, label) => field(label, textInput({ value: c[key] || '', onChange: (v) => { c[key] = v; E.changed({ meta: true }); } }));
  const body = h('div', { class: 'col gap-12' },
    h('div', { class: 'card-sec' }, h('h4', { text: 'Conexión' }), h('div', { class: 'form-grid' }, text('name', 'Nombre del proyecto'), text('element', 'Identificador del elemento'), text('author', 'Autor'), text('date', 'Fecha'))),
    h('div', { class: 'card-sec' }, h('h4', { text: 'Unidades' }), h('div', { class: 'form-grid' }, field('Conjunto', setSel), field('Longitud', sl), field('Fuerza', sf), field('Esfuerzo', ss), field('Momento', sm)),
      h('p', { class: 'hint-text', style: { marginTop: '8px' }, text: 'Los datos se guardan en pulgadas, kip y ksi; las unidades solo cambian cómo se muestran y se escriben.' })));
  const mod = modal({ title: 'Proyecto', icon: 'settings', width: 620, floating: true, pos: { x: 340, y: 80 }, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify([c.name, c.element, c.author, c.date, c.u_len, c.u_force, c.u_stress, c.u_moment]) === before) E.dropSnap(); E.refreshTree(); } });
}
