// Ventanas del editor: miembros, cargas del nudo y datos del proyecto (nombre, unidades).
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, btn, iconBtn, modal, field, selectInput, textInput, numInput, checkInput, errorBox, toast, confirmBox } from './ui.js';
import { renderItems } from './forms.js';
import { sectionPicker } from './sectionpicker.js';

const num = (label, path, uk, lo, hi, step, dec, help) => ({ path, label, type: 'num', uk, lo, hi, step, dec, help });

function formCtx(E, obj, onChange) {
  return { us: E.us(), get: () => obj, onChange, hide: () => false, sectionPicker: (it, val, set) => sectionPicker(val, set) };
}

// Miembros que llegan (directa o indirectamente) al miembro `name`: no pueden ser su apoyo (ciclo).
export function descendantsOf(nd, name) {
  const out = new Set(); const stack = [name];
  while (stack.length) { const cur = stack.pop(); for (const m of nd.members) if (m.attach_to === cur && !out.has(m.name)) { out.add(m.name); stack.push(m.name); } }
  return out;
}
// Al eliminar un miembro, los que llegan a él pasan a llegar al apoyo del eliminado (su posición ya no se mide desde el mismo punto: conviene revisarla).
export function reparentChildren(nd, name) {
  const m = nd.members.find((x) => x.name === name); const up = m ? (m.attach_to || '') : '';
  for (const c of nd.members) if (c.attach_to === name) c.attach_to = up;
}

// Sustituye un nombre de elemento en todas las referencias del nudo (miembros, operaciones, cargas).
// rotaciones liberadas (T, My, Mz) del extremo de un miembro en el nudo: automáticas según su conexión (corte y diagonales articuladas) o las marcadas a mano
export function releasesOf(nd, name) {
  const m = nd.members.find((x) => x.name === name);
  if (!m) return { T: false, My: false, Mz: false };
  if (m.rel_auto === false) return { T: !!m.rel_T, My: !!m.rel_My, Mz: !!m.rel_Mz };
  const K = S.C.op;
  const art = nd.operations.some((o) => o.member === name && [K.TAB, K.DANG, K.SEAT, K.GUSSET, K.GUSSET_W].includes(o.kind));
  return { T: art, My: art, Mz: art };
}

export function renameRefs(nd, old, nw) {
  const K = S.C.op;
  if (nd.main_name === old) nd.main_name = nw;
  for (const m of nd.members) { if (m.name === old) m.name = nw; if (m.attach_to === old) m.attach_to = nw; }
  for (const o of nd.operations) {
    if (o.member === old) o.member = nw;
    if (o.parent === old) o.parent = nw;
    o.targets = (o.targets || []).map((t) => (t === old ? nw : t));
    if (o.weld_main === old) o.weld_main = nw;
    o.weld_to = (o.weld_to || []).map((t) => [t[0] === old ? nw : t[0], t[1]]);
    if ((o.kind === K.PLATE || o.kind === K.ANGLE) && o.name === old) o.name = nw;
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
    if (!v || v === name || nd.main_name === v || nd.members.some((x) => x.name === v) || nd.operations.some((o) => (o.kind === C.op.PLATE || o.kind === C.op.ANGLE) && o.name === v)) { nameInp.value = name; return; }
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
    items.push({ path: 'main_end', label: 'Extremo', type: 'combo', items: C.end_labels });
  } else {
    const banned = descendantsOf(nd, name); banned.add(name);
    items.push({ type: 'custom', render: () => field('Se une a', selectInput({ value: m.attach_to || '', options: [{ value: '', label: `El principal «${nd.main_name}»` }, ...nd.members.filter((x) => !banned.has(x.name)).map((x) => ({ value: x.name, label: `El miembro «${x.name}»` }))],
      onChange: (v) => { m.attach_to = v; ctx.onChange(); } })) });
    items.push(num('Posición sobre el miembro al que llega', 'pos', 'L', -4000, 4000, null, null, 'Medida desde el nudo (principal) o desde el INICIO del miembro al que llega, a lo largo de su eje.'), num('Desplazamiento (peralte del apoyo)', 'off', 'L', -400, 400),
      num('Desplazamiento (ancho del apoyo)', 'off2', 'L', -400, 400), num('Desplazamiento sobre su eje (+ hacia atrás)', 'gap', 'L', -120, 240));
  }
  body.append(h('div', { class: 'card-sec' }, h('h4', { text: isMain ? 'Miembro principal' : 'Miembro conectado' }), h('div', { class: 'form-grid' }, field('Nombre', nameInp)),
    h('div', { style: { height: '10px' } }), renderItems(items, ctx)));
  if (!isMain) {
    const relBox = h('div');
    const buildRel = () => {
      relBox.replaceChildren();
      const auto = m.rel_auto !== false;
      const cur = releasesOf(nd, name);
      const rf = [{ path: 'rel_auto', label: 'Liberación automática según la conexión', type: 'check', wide: true, help: 'Las conexiones de corte (placa simple, doble ángulo, asiento) y las cartelas de diagonal no transmiten momento; la placa extrema y las alas soldadas sí.' }];
      if (!auto) rf.push({ path: 'rel_T', label: 'Liberar el giro alrededor del eje del miembro (T)', type: 'check', wide: true }, { path: 'rel_My', label: 'Liberar el giro My (flexión por Vz)', type: 'check', wide: true }, { path: 'rel_Mz', label: 'Liberar el giro Mz (flexión por Vy)', type: 'check', wide: true });
      const rctx = formCtx(E, m, () => { E.changed({ geometry: false }); });
      rctx.onChange = (path) => { E.changed({ geometry: false }); if (path === 'rel_auto') buildRel(); };
      relBox.append(h('h4', { text: 'Rotaciones en el extremo del nudo' }), renderItems(rf, rctx),
        h('p', { class: 'hint-text', style: { marginTop: '6px' }, text: `Liberado ahora: ${['T', 'My', 'Mz'].filter((k) => cur[k]).join(', ') || 'ninguna (extremo empotrado)'}. Un giro liberado no transmite momento: queda en 0 en «Cargas» y no entra al equilibrio ni a las verificaciones. Se conserva el momento de la excentricidad del miembro respecto del eje del principal.` }));
    };
    buildRel();
    body.append(h('div', { class: 'card-sec' }, relBox));
    // datos del diseño sísmico de la conexión de la viga (AISC 358 / AISC 341): distancia entre rótulas y cortante de gravedad
    const sctx = formCtx(E, m, () => { E.changed({ geometry: false }); });
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Diseño sísmico de la conexión (pórtico a momento)' }),
      renderItems([{ path: 'sism_Lh', label: 'Distancia entre rótulas plásticas Lh (0 = no se da)', type: 'num', uk: 'L', lo: 0, hi: 2000 },
        { path: 'sism_Vg', label: 'Cortante de gravedad en la rótula (1.2D + 0.5L + 0.2S)', type: 'num', uk: 'F', lo: 0, hi: 10000 }], sctx, { cols: 2 }),
      h('p', { class: 'hint-text', style: { marginTop: '6px' }, text: 'Con el diseño sísmico activo, las combinaciones con sobrerresistencia (Ωo) no exigen a la viga más de 1.1·Ry·Fy·Z en flexión ni, si se da Lh, más de 2·(1.1·Ry·Fy·Z)/Lh + el cortante de gravedad. Estos datos también son los de la conexión precalificada de AISC 358 (Mpr, Vu = 2·Mpr/Lh + Vgravedad).' })));
    // punto de aplicación de las acciones del miembro en el análisis de placas (las flechas del visor y las fórmulas no cambian)
    const lctx = formCtx(E, m, () => { E.changed({ geometry: false }); });
    body.append(h('div', { class: 'card-sec' }, h('h4', { text: 'Punto de aplicación de la carga (análisis)' }),
      renderItems([{ path: 'load_at', label: 'Las acciones del miembro actúan', type: 'combo', items: S.C.load_at || ['Automático', 'En el extremo del elemento', 'En los pernos'], wide: true }], lctx),
      h('p', { class: 'hint-text', style: { marginTop: '6px' }, text: 'Solo cambia el análisis del modelo de placas. «En el extremo del elemento»: las acciones de «Cargas» actúan donde el eje del miembro llega al nudo (los pernos reciben además el momento del cortante por la distancia al nudo). «En los pernos»: actúan en el centro de los pernos del miembro (o de sus cordones, si es soldado). «Automático»: en los pernos para placa simple, doble ángulo, asiento y cartelas; en el extremo para placa extrema, alas soldadas y uniones generales. Las flechas del visor y las verificaciones por fórmulas no cambian.' })));
  }
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
        reparentChildren(nd, name);
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
  const intermediate = () => !nd.main_end || nd.main_end === S.C.end_labels[0];      // el principal pasa por el nudo: no lleva cargas (su acción sale del equilibrio)
  const names = () => [...(intermediate() ? [] : [{ value: nd.main_name, label: `${nd.main_name} (principal)` }]), ...nd.members.map((x) => ({ value: x.name, label: x.name })), { value: NODE, label: 'Carga externa en el nudo (ejes globales)' }];
  const cols = [['N', 'F'], ['Vy', 'F'], ['Vz', 'F'], ['T', 'M'], ['My', 'M'], ['Mz', 'M']];
  const tb = h('tbody');
  const sideLbl = (v) => (v < 0 ? 'Lado −' : v > 0 ? 'Lado +' : 'Auto');
  const off_ = (l) => l.member === nd.main_name && intermediate();
  const draw = () => {
    tb.replaceChildren();
    nd.loads.forEach((l, i) => {
      const tr = h('tr', { title: off_(l) ? 'Nudo intermedio: el miembro principal no lleva cargas; se ignora esta fila' : '' });
      const isMain = l.member === nd.main_name;
      const off = isMain && intermediate();
      tr.append(h('td', null, textInput({ value: l.case, onChange: (v) => { l.case = v; E.changed({ loads: true }); } })),
        h('td', null, selectInput({ value: l.member, options: names(), onChange: (v) => { l.member = v; if (v !== nd.main_name) l.side = 0; draw(); E.changed({ loads: true }); } })),
        h('td', null, isMain ? selectInput({ value: String(l.side || 0), options: [{ value: '0', label: 'Auto (el opuesto)' }, { value: '-1', label: 'Lado −' }, { value: '1', label: 'Lado +' }], onChange: (v) => { l.side = parseInt(v, 10); E.changed({ loads: true }); } }) : null));
      const rel = l.member !== NODE && !isMain ? releasesOf(nd, l.member) : { T: false, My: false, Mz: false };
      for (const [k, u] of cols) {
        const inp = numInput({ value: us.out(u, rel[k] ? 0 : l[k]), dec: us.dec(u === 'M' ? 'F' : u), onChange: (v) => { l[k] = us.inn(u, v); E.changed({ loads: true }); } });
        if (rel[k]) { const i_ = inp.querySelector('input'); if (i_) { i_.disabled = true; i_.title = 'Giro liberado en el extremo del nudo: no transmite momento (se cambia en el miembro)'; } inp.style.opacity = '0.45'; }
        if (off) { const i_ = inp.querySelector('input'); if (i_) { i_.disabled = true; i_.title = 'Nudo intermedio: el miembro principal no lleva cargas'; } inp.style.opacity = '0.45'; }
        tr.append(h('td', { class: 'num' }, inp));
      }
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
      + 'Una carga externa aplicada al nudo se escribe en ejes globales (N = Fx, Vy = Fy, Vz = Fz, T = Mx). En un nudo intermedio (el principal pasa por el nudo) el principal no lleva cargas: su acción sale del equilibrio de fuerzas y momentos. Si el principal termina en el nudo (placa base o nudo superior), se le da la carga de su extremo libre; la del lado que equilibra se calcula '
      + 'y de ella salen las combinaciones de la placa base.' }),
    h('div', { class: 'card-sec' }, h('div', { class: 'form-grid' }, field('Lado del principal que equilibra el nudo', balSel))),
    h('div', { style: { overflow: 'auto' } }, h('table', { class: 't compact' }, h('thead', null, head), tb)),
    btn('Agregar carga', { icon: 'plus', onClick: () => { nd.loads.push({ case: nd.loads.length ? nd.loads[nd.loads.length - 1].case : 'Caso 1', member: nd.members[0] ? nd.members[0].name : nd.main_name, N: 0, Vy: 0, Vz: 0, T: 0, My: 0, Mz: 0, side: 0 }); draw(); E.changed({ loads: true }); } }));
  const mod = modal({ title: 'Cargas del nudo', icon: 'zap', width: 980, floating: true, pos: { x: 340, y: 80 }, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify([nd.loads, nd.balance_end]) === before) E.dropSnap(); E.refreshTree(); } });
}

// ---------------------------------------------------------------------------------------------------- diseño sísmico
// ASCE 7-05 / AISC 341-22 / ACI 318-19 17.10: datos de la conexión, tipo de cada caso de carga del nudo y generación de las combinaciones.
export function openSeismic(E) {
  const c = E.conn();
  const nd = c.node;
  const us = E.us();
  const C = (S.C && S.C.seismic) || { systems: [], sdc: ['A', 'B', 'C', 'D', 'E', 'F'], omega0: {} };
  E.snap();
  if (!nd.case_kind) nd.case_kind = {};
  const sd = c.seis;
  const before = JSON.stringify([sd, nd.case_kind, nd.loads]);
  const GEN = ['G', 'E', 'Ωo'];
  const set = (k, v) => { sd[k] = v; E.changed({ geometry: false }); };
  const chk = (k, label) => checkInput({ value: sd[k], label, onChange: (v) => { set(k, v); sync(); } });
  const num = (k, dec, kind) => numInput({ value: kind ? us.out(kind, sd[k]) : sd[k], dec, onChange: (v) => set(k, kind ? us.inn(kind, v) : v) });
  const omegaI = num('Omega0', 2);
  const sysSel = selectInput({ value: sd.system, options: C.systems, onChange: (v) => {
    sd.system = v; if (C.omega0[v] != null) { sd.Omega0 = C.omega0[v]; omegaI.querySelector('input').value = String(sd.Omega0); } E.changed({ geometry: false }); refreshInfo(); } });
  const info = h('p', { class: 'hint-text', text: '' });
  const refreshInfo = async () => {
    try {
      const r = await call('seismic_info', { connection: E.conn() });
      const L = r.limits;
      info.textContent = `Miembro de la placa base: ${r.member}, Ry = ${r.Ry}.  Límites de la resistencia requerida (AISC 341-22 D2.6): 1.1·Ry·Fy·Zx = ${us.fmt('M', L.Mx)}, `
        + `1.1·Ry·Fy·Zy = ${us.fmt('M', L.My)}, 2·Ry·Fy·Zx/H = ${us.fmt('F', L.Vy)}, 2·Ry·Fy·Zy/H = ${us.fmt('F', L.Vx)}.`;
    } catch (e) { info.textContent = ''; }
  };
  // ---- tipo de cada caso de carga
  const tb = h('tbody');
  const drawCases = () => {
    tb.replaceChildren();
    const names = [...new Set(nd.loads.map((l) => l.case))];
    const opts = [{ value: '', label: 'Combinación factorizada' }, { value: 'D', label: 'D — muerta (servicio)' }, { value: 'L', label: 'L — viva (servicio)' },
      { value: 'S', label: 'S — nieve (servicio)' }, { value: 'QEx', label: 'QEx — sismo en X (servicio)' }, { value: 'QEy', label: 'QEy — sismo en Y (servicio)' }];
    const gen = { G: 0, E: 0, 'Ωo': 0 };
    for (const n of names) {
      const k = nd.case_kind[n] || '';
      if (GEN.includes(k)) { gen[k] += 1; continue; }
      const cell = selectInput({ value: k, options: opts, onChange: (v) => { if (v) nd.case_kind[n] = v; else delete nd.case_kind[n]; E.changed({ loads: true }); } });
      tb.append(h('tr', null, h('td', { text: n }), h('td', null, cell)));
    }
    if (gen.G + gen.E + gen['Ωo']) {
      tb.append(h('tr', null, h('td', { class: 'muted', text: 'Generadas' }),
        h('td', { class: 'muted', text: `${gen.G} de gravedad, ${gen.E} sísmicas (ρ·QE), ${gen['Ωo']} con sobrerresistencia (Ωo·QE)` })));
    }
    if (!names.length) tb.append(h('tr', null, h('td', { colspan: 2, class: 'muted', text: 'Sin casos de carga: escríbalos en Cargas (D, L, S, QEx, QEy sin factorar, por miembro).' })));
  };
  const genBtn = btn('Generar combinaciones', { icon: 'zap', kind: 'primary', onClick: async () => {
    try {
      const r = await call('seismic_generate', { connection: E.conn() });
      E.replaceConn(r.connection); E.changed({ loads: true });
      Object.assign(c, E.conn());
      toast(r.count ? `${r.count} combinaciones de ASCE 7-05 generadas en el nudo` : 'No hay casos de servicio con cargas: marque D, L, S, QEx o QEy', r.count ? 'ok' : 'warn', 6000);
      mod.close();
      openSeismic(E);
    } catch (e) { errorBox(e); }
  } });
  const grp = h('div', { class: 'col gap-12' });
  const sync = () => { grp.style.display = sd.enabled ? '' : 'none'; };
  grp.append(
    h('div', { class: 'card-sec' }, h('h4', { text: 'Sitio y sistema' }), h('div', { class: 'form-grid' },
      field('Categoría de diseño sísmico (SDC)', selectInput({ value: sd.sdc, options: C.sdc, onChange: (v) => set('sdc', v) }), { help: 'ASCE 7-05 11.6. ACI 318-19 17.10 solo aplica en SDC C a F.' }),
      field('Sistema sismorresistente', sysSel, { help: 'Define Ωo por defecto (ASCE 7-05 Tabla 12.2-1), si las soldaduras columna-placa son de demanda crítica (AISC 341-22 A3.4b) y los avisos de riostras.' }),
      field('Ωo (sobrerresistencia)', omegaI), field('ρ (redundancia)', num('rho', 2)), field('SDS', num('SDS', 3), { help: 'Ev = 0.2·SDS·D (12.4.2.2).' }),
      field('f1 (factor de L con sismo)', num('f1', 2), { help: 'ASCE 7-05 2.3.2 excepción 1: 0.5 si L0 ≤ 100 psf (salvo garajes y reunión pública); si no, 1.0.' }),
      field('Ry (0 = automático)', num('Ry', 2), { help: 'AISC 341-22 Tabla A3.2 según el acero del miembro de la placa base.' }),
      field(`H, altura del piso (${us.label('L')})`, num('H', us.dec('L'), 'L')),
      field('', chk('base_moment', 'La base transmite momento (empotrada)'))), info),
    h('div', { class: 'card-sec' }, h('h4', { text: 'Tipo de cada caso de carga del nudo' }),
      h('p', { class: 'hint-text', text: 'Escriba en Cargas los casos de SERVICIO (sin factorar) y márquelos aquí. Los casos de servicio no se diseñan: el generador arma con ellos los casos factorizados de ASCE 7-05 para todos los miembros del nudo.' }),
      h('table', { class: 't compact' }, h('thead', null, h('tr', null, h('th', { text: 'Caso' }), h('th', { text: 'Tipo' }))), tb)),
    h('div', { class: 'card-sec' }, h('h4', { text: 'Combinaciones (ASCE 7-05)' }), h('div', { class: 'form-grid' },
      field('', chk('gravity', 'Incluir gravedad: 1.4D ; 1.2D + 1.6L + 0.5S ; 1.2D + 1.6S + f1·L')),
      field('', chk('ortho', 'Direcciones ortogonales 100 % + 30 % (12.5)')),
      field('', chk('cap_limit', 'Limitar Ωo·QE de la placa base por la capacidad de la columna (AISC 341-22 D2.6)'))),
      h('p', { class: 'hint-text', text: '(1.2 + 0.2·SDS)·D + ρ·QE + f1·L + 0.2·S ; (0.9 − 0.2·SDS)·D + ρ·QE (12.4.2.3) y las mismas con Ωo·QE (12.4.3.2), con ±QE en cada dirección. Reemplaza los casos generados antes; los escritos a mano se conservan.' }),
      genBtn),
    h('div', { class: 'card-sec' }, h('h4', { text: 'Placa base: anclaje dúctil (ACI 318-19 17.10.5.3(a))' }), h('div', { class: 'form-grid' },
      field('', chk('ductile', 'Verificar anclaje dúctil')),
      field(`Longitud desadherida en el concreto (${us.label('L')})`, num('sleeve', us.dec('L'), 'L'), { help: 'Estiramiento = camisa + mortero + stand-off + tp ≥ 8·da.' }),
      field('', chk('upset', 'Rosca recalcada (upset): no se exige futa/fya ≥ 1.3')))));
  drawCases();
  sync();
  refreshInfo();
  const body = h('div', { class: 'col gap-12' },
    h('div', { class: 'card-sec' }, checkInput({ value: sd.enabled, label: 'Diseño sísmico (ASCE 7-05 / AISC 341-22 / ACI 318-19 17.10)', onChange: (v) => { set('enabled', v); sync(); } })),
    grp);
  const mod = modal({ title: 'Diseño sísmico', icon: 'activity', width: 820, cls: 'tall', floating: true, pos: { x: 340, y: 40 }, body, footer: [btn('Cerrar', { kind: 'primary', icon: 'check', onClick: () => mod.close() })],
    onClose: () => { if (JSON.stringify([sd, nd.case_kind, nd.loads]) === before) E.dropSnap(); E.refreshTree(); } });
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
