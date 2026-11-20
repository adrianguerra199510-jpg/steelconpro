// Formulario de la operación «Placa base»: se genera a partir del esquema de campos del motor (schema_baseplate.json).
// Los valores viven en la conexión (conn.plate, conn.bolts, conn.lug…); el perfil es el del miembro que lleva la placa.
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, btn, iconBtn, tabs, numInput, textInput, selectInput, segmented } from './ui.js';
import { renderItems, getPath } from './forms.js';
import { sectionPicker } from './sectionpicker.js';

const TABS = [
  ['Cargas', 'zap'], ['Orientación', 'rotate'], ['Placa', 'square'], ['Pernos', 'nut'], ['Llave de corte', 'key'], ['Rigidizadores', 'layers'],
  ['Soldadura', 'zap'], ['Concreto', 'box'], ['Elementos finitos', 'cpu'],
];

// Campos de la pestaña «Perfil» que sí se editan aquí (el perfil y el acero son los del miembro).
const ORIENT_PATHS = new Set(['section.rotation', 'section.cx', 'section.cy', 'loads.tilt_x', 'loads.tilt_y', 'section.double', 'section.gap']);

function baseShape(nd) {
  const op = nd.operations.find((o) => o.kind === S.C.ops.base);
  const name = op && op.member ? op.member : nd.main_name;
  if (name === nd.main_name) return nd.main_shape;
  const m = nd.members.find((x) => x.name === name);
  return m ? m.shape : nd.main_shape;
}

export async function baseplateForm(E, parentCtx) {
  const conn = () => E.conn();
  const us = E.us();
  const nd = conn().node;
  let info = { hollow: false, round: false };
  try { info = await call('section_info', { label: baseShape(nd) }); } catch (e) { /* perfil desconocido */ }
  const C = S.C;
  const schema = C.schema_baseplate;
  const lists = [];                                    // formularios para volver a evaluar la visibilidad

  const vis = (path) => {
    const c = conn();
    const pl = c.plate, b = c.bolts, lg = c.lug, st = c.stiff, fe = c.fea, cn = c.conc, sc = c.section;
    const circ = pl.shape === 'Circular';
    const recto = b.atype.startsWith('Recto'), gancho = b.atype.includes('Gancho');
    const adh = recto && b.install.startsWith('Postinstalado');
    const manual = b.pattern.startsWith('Coordenadas');
    const circp = b.pattern === 'Circular' || circ;
    const sec = lg.enabled && lg.ltype.startsWith('Perfil');
    const stOn = st.enabled && !(Math.abs(c.loads.tilt_x) > 1e-9 || Math.abs(c.loads.tilt_y) > 1e-9);
    const conectores = String(fe.weld_model).startsWith('Conectores');
    const plast = String(fe.weld_criterion).startsWith('Plastico');
    switch (path) {
      case 'plate.N': case 'plate.B': return circ;
      case 'plate.Dp': return !circ;
      case 'section.gap': return !sc.double;
      case 'bolts.install': return !recto;
      case 'bolts.eh': return !gancho;
      case 'bolts.Abrg_user': return !b.atype.startsWith('Con cabeza');
      case 'bolts.fixity': return !(b.standoff > 1e-9);
      case 'bolts.n_major': case 'bolts.n_minor': return manual || circp;
      case 'bolts.n_circ': return manual || !circp;
      case 'bolts.ex': return manual;
      case 'bolts.ey': return manual || circp;
      case 'lug.ltype': case 'lug.H': case 'lug.steel': case 'lug.weld_size': case 'lug.electrode': return !lg.enabled;
      case 'lug.label': case 'lug.rotation': return !sec;
      case 'lug.direction': case 'lug.W': case 'lug.t': return !lg.enabled || sec;
      case 'stiff.spacing': return !(stOn && st.spacing_mode === 'Separacion fija');
      case 'stiff.offset_angle': return !(stOn && info.round);
      case 'stiff.clip_h': case 'stiff.clip_v': return !(stOn && st.shape.startsWith('Rectangular con'));
      case 'conc.u_type': case 'conc.u_size': case 'conc.u_n': case 'conc.u_fy': case 'conc.u_depth': case 'conc.u_leg': return !cn.u_on;
      case 'fea.ks_manual': return fe.ks_mode !== 'manual';
      case 'fea.plastic_limit': return !fe.plastic;
      case 'fea.weld_criterion': return !conectores;
      case 'fea.weld_plastic_limit': return !(conectores && plast);
      case 'fea.weld_peak_factor': return !(conectores && !plast);
      default:
        if (path && path.startsWith('stiff.') && path !== 'stiff.enabled') return !stOn;
        return false;
    }
  };

  const ctx = {
    us, get: conn,
    onChange: (path) => { lists.forEach((g) => g.refresh && g.refresh()); groupVis(); parentCtx.onChange && parentCtx.onChange(path); },
    hide: vis,
    sectionPicker: (it, val, set) => sectionPicker(val, set),
  };

  // ---- grupos que se muestran u ocultan completos
  const groupEls = [];
  const groupVisible = (title) => {
    const c = conn();
    const b = c.bolts;
    const stOn = c.stiff.enabled && !(Math.abs(c.loads.tilt_x) > 1e-9 || Math.abs(c.loads.tilt_y) > 1e-9);
    switch (title) {
      case 'Anclaje adhesivo (postinstalado)': return b.atype.startsWith('Recto') && b.install.startsWith('Postinstalado');
      case 'Coordenadas manuales': return b.pattern.startsWith('Coordenadas');
      case 'Ubicacion a lo largo de la cara': case 'Forma de la pletina': return stOn;
      case 'Soldadura': return stOn || false;
      case 'Alas (perfiles W)': case 'Alma (perfiles W)': return !info.hollow;
      case 'Perimetral (HSS / Pipe)': return info.hollow;
      default: return true;
    }
  };
  const groupVis = () => groupEls.forEach(([el, , title]) => {
    const show = groupVisible(title);
    el.classList.toggle('hidden', !show);
  });

  const units = {
    F: () => us.label('F'), M: () => us.label('M'),
  };

  // ---- tabla de combinaciones
  const comboTable = () => {
    const wrap = h('div', { class: 'col gap-8' });
    if (conn().node.loads.length) {                        // con casos de carga del nudo, las combinaciones salen del analisis nodal
      const box = h('div', { class: 'col gap-8' }, h('p', { class: 'hint-text', text: 'Las cargas de la placa base salen del ANÁLISIS NODAL: el nudo tiene casos de carga y la placa recibe la acción del miembro que la lleva, trasladada del nudo al centro de la placa. Se editan en «Cargas» del árbol.' }));
      call('nodal', { connection: conn() }).then((a) => {
        const tb = h('table', { class: 't compact' }, h('thead', null, h('tr', null, h('th', { text: 'Caso' }), ...[['Pu', 'F'], ['Mux', 'M'], ['Muy', 'M'], ['Vux', 'F'], ['Vuy', 'F']].map(([n, k]) => h('th', { class: 'num', text: `${n} (${us.label(k)})` })))),
          h('tbody', null, a.cases.filter((c) => c.base).map((c) => h('tr', null, h('td', { text: c.case }), ...[['Pu', 'F'], ['Mux', 'M'], ['Muy', 'M'], ['Vux', 'F'], ['Vuy', 'F']].map(([n, k]) => h('td', { class: 'num', text: us.fmt(k, c.base[n], 2) }))))));
        box.append(tb);
      }).catch(() => {});
      return box;
    }
    const tb = h('table', { class: 't compact' });
    const head = h('tr', null, h('th', { text: 'Nombre' }), ...[['Pu', 'F'], ['Mux', 'M'], ['Muy', 'M'], ['Vux', 'F'], ['Vuy', 'F']].map(([n, k]) => h('th', { class: 'num', text: `${n} (${us.label(k)})` })), h('th'));
    const body = h('tbody');
    tb.append(h('thead', null, head), body);
    const draw = () => {
      body.replaceChildren();
      conn().combos.forEach((cb, i) => {
        const tr = h('tr', { class: i === conn().combo_idx ? 'sel' : '' });
        const nameI = textInput({ value: cb.name, onChange: (v) => { cb.name = v; ctx.onChange('combos'); } });
        tr.append(h('td', null, nameI));
        for (const [k, u] of [['Pu', 'F'], ['Mux', 'M'], ['Muy', 'M'], ['Vux', 'F'], ['Vuy', 'F']]) {
          tr.append(h('td', { class: 'num' }, numInput({ value: us.out(u, cb[k]), dec: us.dec(u === 'M' ? 'F' : u), onChange: (v) => { cb[k] = us.inn(u, v); ctx.onChange('combos'); } })));
        }
        tr.append(h('td', null, h('div', { class: 'row gap-4' },
          iconBtn('eye', 'Dibujar y detallar esta combinación', () => { conn().combo_idx = i; draw(); ctx.onChange('combo_idx'); }),
          iconBtn('trash', 'Quitar', () => { if (conn().combos.length > 1) { conn().combos.splice(i, 1); conn().combo_idx = Math.min(conn().combo_idx, conn().combos.length - 1); draw(); ctx.onChange('combos'); } }, { disabled: conn().combos.length < 2 }))));
        body.append(tr);
      });
    };
    draw();
    wrap.append(h('div', { style: { overflow: 'auto' } }, tb),
      h('div', { class: 'row' }, btn('Agregar combinación', { icon: 'plus', onClick: () => {
        const cs = conn().combos; const last = cs[cs.length - 1] || { Pu: 0, Mux: 0, Muy: 0, Vux: 0, Vuy: 0 };
        cs.push({ name: `Comb ${cs.length + 1}`, Pu: last.Pu, Mux: last.Mux, Muy: last.Muy, Vux: last.Vux, Vuy: last.Vuy }); draw(); ctx.onChange('combos');
      } })));
    return wrap;
  };

  // ---- tabla de coordenadas de pernos
  const coordTable = () => {
    const wrap = h('div', { class: 'col gap-8' });
    const body = h('tbody');
    const tb = h('table', { class: 't compact' }, h('thead', null, h('tr', null, h('th', { text: '#' }), h('th', { class: 'num', text: `x (${us.label('L')})` }), h('th', { class: 'num', text: `y (${us.label('L')})` }), h('th'))), body);
    const draw = () => {
      body.replaceChildren();
      conn().bolts.coords.forEach((p, i) => {
        body.append(h('tr', null, h('td', { text: `P${i + 1}` }),
          ...[0, 1].map((k) => h('td', { class: 'num' }, numInput({ value: us.out('L', p[k]), dec: us.dec('L'), onChange: (v) => { p[k] = us.inn('L', v); ctx.onChange('bolts.coords'); } }))),
          h('td', null, iconBtn('trash', 'Quitar', () => { if (conn().bolts.coords.length > 1) { conn().bolts.coords.splice(i, 1); draw(); ctx.onChange('bolts.coords'); } }))));
      });
    };
    draw();
    const paste = async () => {
      let text = '';
      try { text = await navigator.clipboard.readText(); } catch (e) { text = window.prompt('Pegue aquí dos columnas (x, y):') || ''; }
      const rows = text.split(/\r?\n/).map((l) => l.trim().split(/[\t;]+|\s{2,}|\s+/).map((x) => parseFloat(x.replace(',', '.')))).filter((r) => r.length >= 2 && isFinite(r[0]) && isFinite(r[1]));
      if (!rows.length) return;
      conn().bolts.coords = rows.map((r) => [us.inn('L', r[0]), us.inn('L', r[1])]);
      draw(); ctx.onChange('bolts.coords');
    };
    wrap.append(h('div', { style: { maxHeight: '260px', overflow: 'auto' } }, tb),
      h('div', { class: 'row' }, btn('Agregar punto', { icon: 'plus', onClick: () => { conn().bolts.coords.push([0, 0]); draw(); ctx.onChange('bolts.coords'); } }), btn('Pegar desde Excel', { icon: 'clipboard', onClick: paste })));
    return wrap;
  };

  const customs = { tbl_cb: comboTable, tbl_xy: coordTable };

  const fixNote = (t) => t.replace('pestaña Perfil', 'pestaña Orientación').replace(/El boton CALCULAR corre el analisis 3D de TODAS las combinaciones y el veredicto es el de la mas desfavorable; el combo 'Combinacion' de la barra superior elige cual se dibuja y se detalla\./, "El veredicto es el de la combinación más desfavorable; el ojo de cada fila elige cuál se dibuja y se detalla.");
  const mkItems = (items) => items.filter((it) => {
    if (it.type === 'custom') return !!customs[it.id];
    return true;
  }).map((it) => (it.type === 'custom' ? { type: 'custom', render: () => { const n = customs[it.id](); n.classList.add('span3'); return n; } } : { ...it, text: it.type === 'note' ? fixNote(it.text) : it.text, wide: it.type === 'text' || undefined }));

  // ---- armado de pestañas
  const groupsOf = (tabTitle) => {
    const out = [];
    const sources = tabTitle === 'Orientación' ? schema.filter((t) => t.title === 'Perfil') : schema.filter((t) => t.title === tabTitle);
    for (const t of sources) {
      for (const g of t.groups) {
        let items = g.items;
        if (tabTitle === 'Orientación') items = items.filter((it) => ORIENT_PATHS.has(it.path) || it.type === 'note');
        else if (tabTitle === 'Cargas') items = items.filter((it) => it.id !== 'lbl_si');
        if (!items.length) continue;
        out.push({ ...g, items });
      }
    }
    return out;
  };

  const panelFor = (tabTitle) => {
    const root = h('div', { class: 'col gap-12' });
    for (const g of groupsOf(tabTitle)) {
      const items = mkItems(g.items);
      if (!items.length) continue;
      const form = renderItems(items, ctx, { cols: tabTitle === 'Cargas' ? 1 : 2 });
      lists.push(form);
      const card = h('div', { class: 'card-sec' }, g.title ? h('h4', { text: g.title }) : null, form);
      groupEls.push([card, tabTitle, g.title]);
      root.append(card);
    }
    if (tabTitle === 'Orientación') root.prepend(h('p', { class: 'hint-text', text: `El perfil de la placa base es el del miembro (${baseShape(nd)}); se cambia en «Miembros». Aquí se define cómo se coloca respecto de la placa.` }));
    groupVis();
    return root;
  };

  const t = tabs(TABS.map(([title, ic]) => ({ id: title, label: title, icon: ic, render: () => panelFor(title) })), { active: 'Placa', cls: 'pill' });
  t.refresh = () => { lists.forEach((g) => g.refresh && g.refresh()); groupVis(); };
  t.style.minHeight = '360px';
  return h('div', { class: 'card-sec' }, h('h4', { text: 'Parámetros de la placa base' }), t);
}
