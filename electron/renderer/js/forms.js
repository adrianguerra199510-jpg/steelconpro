// Formularios a partir de una lista de campos: { path, label, type: num|int|combo|check|text|note, uk, lo, hi, step, dec, items, help }.
// Los valores viven en un objeto JSON (la conexion); las magnitudes con `uk` se muestran en las unidades del proyecto.
import { h, field, numInput, selectInput, checkInput, textInput, svg } from './ui.js';

export function getPath(o, path) { return path.split('.').reduce((a, k) => (a == null ? a : a[k]), o); }
export function setPath(o, path, v) {
  const ks = path.split('.'); const last = ks.pop();
  const t = ks.reduce((a, k) => a[k], o);
  t[last] = v;
}

// ctx: { us: UnitSet, get(): objeto raiz, onChange(path, valor), hide(path) -> bool, sectionPicker(item) -> Node }
export function renderItems(items, ctx, { cols = 2 } = {}) {
  const grid = h('div', { class: `form-grid ${cols === 3 ? 'c3' : cols === 1 ? 'c1' : ''}` });
  const refreshers = [];
  for (const it of items) {
    if (it.type === 'note') { grid.append(h('p', { class: 'muted span3', style: { fontSize: '12px', margin: 0 }, text: it.text })); continue; }
    if (it.type === 'custom') { if (it.render) { const n = it.render(ctx); if (n) grid.append(n); } continue; }
    const el = renderField(it, ctx);
    if (!el) continue;
    el.classList.add(it.wide ? 'span2' : 'x');
    grid.append(el);
    refreshers.push(() => {
      const hidden = ctx.hide ? ctx.hide(it.path) : false;
      el.classList.toggle('hidden', !!hidden);
      if (el._refresh) el._refresh();
    });
  }
  const refresh = () => refreshers.forEach((f) => f());
  refresh();
  grid.refresh = refresh;
  return grid;
}

export function renderField(it, ctx) {
  const root = ctx.get();
  const us = ctx.us;
  const val = getPath(root, it.path);
  let control, wrap;
  const set = (v) => { setPath(ctx.get(), it.path, v); ctx.onChange && ctx.onChange(it.path, v); };
  if (it.type === 'num') {
    const uk = it.uk && it.uk !== '-' ? it.uk : null;
    const disp = (v) => (uk ? us.out(uk, v) : v);
    const dec = it.dec ?? (uk ? us.dec(uk) : 3);
    const lo = it.lo != null ? (uk ? Math.min(us.out(uk, it.lo), us.out(uk, it.hi ?? 1e9)) : it.lo) : null;
    const hi = it.hi != null ? (uk ? Math.max(us.out(uk, it.lo ?? 0), us.out(uk, it.hi)) : it.hi) : null;
    control = numInput({ value: disp(val ?? 0), min: lo, max: hi, dec, step: it.step ? (uk ? us.step(uk) : it.step) : 'any', suffix: uk ? us.label(uk) : (it.suffix || ''),
      onChange: (v) => set(uk ? us.inn(uk, v) : v) });
    wrap = field(it.label, control, { help: it.help });
    wrap._refresh = () => { const v = getPath(ctx.get(), it.path); control.set(disp(v ?? 0)); control.querySelector('.suffix') && uk && (control.querySelector('.suffix').textContent = us.label(uk)); };
  } else if (it.type === 'int') {
    control = numInput({ value: val ?? 0, min: it.lo, max: it.hi, dec: 0, step: 1, onChange: (v) => set(Math.round(v)) });
    wrap = field(it.label, control, { help: it.help });
    wrap._refresh = () => control.set(getPath(ctx.get(), it.path) ?? 0);
  } else if (it.type === 'combo') {
    const items2 = typeof it.items === 'function' ? it.items(ctx) : it.items;
    control = selectInput({ value: val, options: items2, onChange: set });
    wrap = field(it.label, control, { help: it.help });
    wrap._refresh = () => {
      const cur = typeof it.items === 'function' ? it.items(ctx) : it.items;
      const want = cur.map((o) => (typeof o === 'string' ? o : o.value)).join('|');
      if (control._opts !== want) {
        const v = getPath(ctx.get(), it.path);
        control.replaceChildren(...cur.map((o) => { const op = typeof o === 'string' ? { value: o, label: o } : o; return h('option', { value: op.value, text: op.label }); }));
        control._opts = want; control.set(v);
      } else control.set(getPath(ctx.get(), it.path));
    };
    control._opts = items2.map((o) => (typeof o === 'string' ? o : o.value)).join('|');
  } else if (it.type === 'check') {
    control = checkInput({ value: val, label: it.label, onChange: set });
    wrap = h('div', { class: 'field' }, h('span', { class: 'lbl', html: '&nbsp;' }), control);
    if (it.help) control.title = it.help;
    wrap._refresh = () => control.set(getPath(ctx.get(), it.path));
  } else if (it.type === 'text') {
    control = textInput({ value: val ?? '', onChange: set });
    wrap = field(it.label, control, { help: it.help });
    wrap._refresh = () => { control.value = getPath(ctx.get(), it.path) ?? ''; };
  } else if (it.type === 'section') {
    control = ctx.sectionPicker ? ctx.sectionPicker(it, val, set) : textInput({ value: val, onChange: set });
    wrap = field(it.label, control, { help: it.help });
    wrap._refresh = () => control.set && control.set(getPath(ctx.get(), it.path));
  } else return null;
  return wrap;
}
