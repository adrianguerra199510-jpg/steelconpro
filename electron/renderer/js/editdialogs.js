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
          mod.close(true);
        } catch (e) { errorBox(e); }
      } })));
  }
  return new Promise((resolve) => {
    const mod = modal({ title: isMain ? `Miembro principal · ${name}` : `Miembro · ${name}`, icon: 'component', width: 600, cls: 'tall', body,
      footer: [btn('Eliminar', { icon: 'trash', kind: 'danger', disabled: isMain, onClick: async () => {
        const deps = nd.operations.filter((o) => o.member === name || o.parent === name || (o.targets || []).includes(name));
        if (!(await confirmBox(`¿Eliminar el miembro «${name}»?`, { danger: true, ok: 'Eliminar', detail: deps.length ? `También se quitarán ${deps.length} operación(es) que lo usan.` : '' }))) return;
        const idx = nd.members.findIndex((x) => x.name === name);
        nd.members.splice(idx, 1);
        for (const o of deps) { const i = nd.operations.indexOf(o); if (i >= 0) await E.removeOperation(i, { silent: true }); }
        nd.loads = nd.loads.filter((l) => l.member !== name);
        E.changed({ structure: true }); mod.close(true);
      } }), h('span', { class: 'grow' }), btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close(true) })],
      onClose: () => { if (JSON.stringify(nd) === before) E.dropSnap(); E.refreshTree(); resolve(true); } });
  });
}

// ---------------------------------------------------------------------------------------------------- cargas del nudo
export function openLoads(E) {
  const nd = E.conn().node;
  const us = E.us();
  E.snap();
  const before = JSON.stringify(nd.loads);
  const names = [nd.main_name, ...nd.members.map((x) => x.name)];
  const cols = [['N', 'F'], ['Vy', 'F'], ['Vz', 'F'], ['T', 'M'], ['My', 'M'], ['Mz', 'M']];
  const tb = h('tbody');
  const draw = () => {
    tb.replaceChildren();
    nd.loads.forEach((l, i) => {
      const tr = h('tr');
      tr.append(h('td', null, textInput({ value: l.case, onChange: (v) => { l.case = v; E.changed({ loads: true }); } })),
        h('td', null, selectInput({ value: l.member, options: names, onChange: (v) => { l.member = v; E.changed({ loads: true }); } })));
      for (const [k, u] of cols) tr.append(h('td', { class: 'num' }, numInput({ value: us.out(u, l[k]), dec: us.dec(u === 'M' ? 'F' : u), onChange: (v) => { l[k] = us.inn(u, v); E.changed({ loads: true }); } })));
      tr.append(h('td', null, iconBtn('trash', 'Quitar', () => { nd.loads.splice(i, 1); draw(); E.changed({ loads: true }); })));
      tb.append(tr);
    });
    if (!nd.loads.length) tb.append(h('tr', null, h('td', { colspan: 9, class: 'muted', style: { padding: '14px' }, text: 'Sin casos de carga: los resultados de las operaciones de conexión necesitan al menos uno.' })));
  };
  draw();
  const head = h('tr', null, h('th', { text: 'Caso' }), h('th', { text: 'Miembro' }), ...cols.map(([k, u]) => h('th', { class: 'num', text: `${k} (${us.label(u)})` })), h('th'));
  const body = h('div', { class: 'col gap-12' },
    h('p', { class: 'hint-text', text: 'Esfuerzos internos en el extremo de cada miembro junto al nudo, en sus ejes locales: x a lo largo del miembro (N > 0 = tracción), z el peralte y y = z × x.' }),
    h('div', { style: { overflow: 'auto' } }, h('table', { class: 't compact' }, h('thead', null, head), tb)),
    btn('Agregar caso', { icon: 'plus', onClick: () => { nd.loads.push({ case: `Caso ${nd.loads.length + 1}`, member: nd.members[0] ? nd.members[0].name : nd.main_name, N: 0, Vy: 0, Vz: 0, T: 0, My: 0, Mz: 0 }); draw(); E.changed({ loads: true }); } }));
  const mod = modal({ title: 'Cargas del nudo', icon: 'zap', width: 900, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify(nd.loads) === before) E.dropSnap(); E.refreshTree(); } });
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
  const mod = modal({ title: 'Proyecto', icon: 'settings', width: 620, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify([c.name, c.element, c.author, c.date, c.u_len, c.u_force, c.u_stress, c.u_moment]) === before) E.dropSnap(); E.refreshTree(); } });
}
