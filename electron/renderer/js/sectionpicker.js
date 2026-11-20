// Selector de perfil: muestra el perfil actual y abre una ventana con familias del catalogo AISC, secciones propias y libres (Section Designer), con busqueda.
import { call } from './api.js';
import { S } from './state.js';
import { h, svg, modal, btn, selectInput, errorBox, clear, debounce } from './ui.js';

let famCache = null;
export async function families() { if (!famCache) famCache = (await call('catalog_families', { free: true })).families; return famCache; }
export function resetFamilies() { famCache = null; }

export function sectionPicker(value, onPick, { free = true } = {}) {
  const lab = h('span', { class: 'grow', text: value || '—', style: { fontWeight: 600 } });
  const b = h('button', { class: 'input row', type: 'button', style: { cursor: 'pointer', textAlign: 'left', justifyContent: 'space-between' } }, lab, svg('chevron-down', 14));
  b.set = (v) => { lab.textContent = v || '—'; value = v; };
  b.onclick = () => openPicker(value, (v) => { b.set(v); onPick(v); });
  return b;
}

export async function openPicker(current, onPick) {
  let fams;
  try { fams = await families(); } catch (e) { return errorBox(e); }
  let fam = '', q = '', sel = current;
  try { const info = await call('section_info', { label: current }); fam = info.family; } catch (e) { fam = fams[0].id; }
  const list = h('div', { style: { overflow: 'auto', flex: 1, border: '1px solid var(--border)', borderRadius: '9px', minHeight: '260px' } });
  const info = h('div', { class: 'card-sec', style: { fontSize: '12.5px', minHeight: '86px' } });
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Buscar por nombre (por ejemplo W14X90, HSS6)…' });
  const famSel = selectInput({ value: fam, options: [{ value: '', label: 'Todas (buscar)' }, ...fams.map((f) => ({ value: f.id, label: f.label }))], onChange: (v) => { fam = v; load(); } });
  const m = modal({ title: 'Elegir perfil', icon: 'shapes', width: 640, cls: 'tall',
    body: h('div', { class: 'col', style: { height: '100%' } }, h('div', { class: 'row' }, h('div', { style: { width: '220px' } }, famSel), h('div', { class: 'grow' }, search)), list, info),
    footer: [btn('Cancelar', { onClick: () => m.close() }), btn('Usar este perfil', { kind: 'primary', icon: 'check', onClick: () => { if (sel) onPick(sel); m.close(); } })] });
  search.addEventListener('input', debounce(() => { q = search.value; load(); }, 150));
  async function load() {
    clear(list); list.append(h('div', { class: 'muted', style: { padding: '12px' }, text: 'Cargando…' }));
    try {
      const r = q || !fam ? await call('catalog_search', { q: q || current || 'W', limit: 200 }) : await call('catalog_shapes', { family: fam, limit: 800 });
      clear(list);
      const tb = h('table', { class: 't' }, h('thead', null, h('tr', null, h('th', { text: 'Perfil' }), h('th', { class: 'num', text: 'd' }), h('th', { class: 'num', text: 'bf' }), h('th', { class: 'num', text: 'tf' }), h('th', { class: 'num', text: 'tw' }))));
      const body = h('tbody');
      for (const s of r.shapes) {
        const tr = h('tr', { class: s.label === sel ? 'sel' : '', style: { cursor: 'pointer' }, onclick: () => { sel = s.label; body.querySelectorAll('tr').forEach((x) => x.classList.remove('sel')); tr.classList.add('sel'); show(s); }, ondblclick: () => { onPick(s.label); m.close(); } },
          h('td', { text: s.label, style: { fontWeight: 600 } }), ...['d', 'bf', 'tf', 'tw'].map((k) => h('td', { class: 'num', text: s[k] ? (s[k] * S.us.fl ** -1 * 1).toFixed(S.us.dec('L') > 2 ? 2 : 1) : '' })));
        body.append(tr);
        if (s.label === sel) setTimeout(() => tr.scrollIntoView({ block: 'center' }), 0);
      }
      tb.append(body); list.append(tb);
      if (!r.shapes.length) list.append(h('div', { class: 'muted', style: { padding: '14px' }, text: 'Sin resultados.' }));
    } catch (e) { errorBox(e); }
  }
  async function show(s) {
    clear(info);
    try {
      const f = await call('section_info', { label: s.label });
      const u = S.us;
      info.append(h('div', { style: { fontWeight: 700, marginBottom: '4px' }, text: `${f.label}  ·  ${f.family}` }),
        h('div', { class: 'muted', text: `d = ${u.q('L', f.d)}  bf = ${u.q('L', f.bf)}  tf = ${u.q('L', f.tf)}  tw = ${u.q('L', f.tw)}` }),
        h('div', { class: 'muted', text: `A = ${u.q('A', f.A)}   Ix = ${(f.Ix / u.fl ** 4).toPrecision(4)} ${u.length}⁴   Iy = ${(f.Iy / u.fl ** 4).toPrecision(4)} ${u.length}⁴   Zx = ${(f.Zx / u.fl ** 3).toPrecision(4)} ${u.length}³` }));
    } catch (e) { /* */ }
  }
  famSel.value = fam; load(); show({ label: current });
}
