// Utilidades de interfaz: creacion de nodos, ventanas modales, menus, avisos y controles de formulario.
import { icon } from './icons.js';

export { icon };

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'html') el.innerHTML = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k === 'value') el.value = v;
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, v);
    }
  }
  add(el, kids);
  return el;
}

function add(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
export function svg(name, size = 18, cls = '') { const t = document.createElement('span'); t.className = 'ic-wrap'; t.innerHTML = icon(name, size, cls); return t; }

export function btn(label, opts = {}) {
  const { icon: ic, kind = '', onClick, title, size = 16, disabled } = opts;
  const b = h('button', { class: `btn ${kind}`.trim(), type: 'button', title, disabled: disabled || null, onclick: onClick });
  if (ic) b.append(svg(ic, size));
  if (label) b.append(h('span', { text: label }));
  return b;
}

export function iconBtn(ic, title, onClick, opts = {}) {
  return h('button', { class: `icon-btn ${opts.kind || ''}`.trim(), type: 'button', title, 'aria-label': title, onclick: onClick, disabled: opts.disabled || null }, svg(ic, opts.size || 17));
}

// ------------------------------------------------------------------ avisos
export function toast(msg, kind = 'info', ms = 4200) {
  let box = $('#toasts');
  if (!box) { box = h('div', { id: 'toasts' }); document.body.append(box); }
  const t = h('div', { class: `toast ${kind}` }, svg(kind === 'error' ? 'circle-alert' : kind === 'ok' ? 'check' : 'info', 16), h('span', { text: msg }));
  box.append(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 250); }, ms);
  return t;
}

export function errorBox(e) {
  console.error(e);
  toast(e && e.message ? e.message : String(e), 'error', 7000);
}

// ------------------------------------------------------------------ ventanas modales
export function modal({ title, icon: ic, width = 560, body, footer, onClose, wide, cls = '', closable = true, floating = false, pos = null }) {
  const root = $('#overlay-root');
  const back = h('div', { class: `modal-back ${floating ? 'float' : ''}` });
  const box = h('div', { class: `modal ${cls} ${floating ? 'floating' : ''}`, style: { width: typeof width === 'number' ? `${width}px` : width }, role: 'dialog', 'aria-modal': 'true' });
  const head = h('div', { class: 'modal-head' }, ic ? svg(ic, 20, 'brand') : null, h('h2', { text: title || '' }),
    closable ? iconBtn('x', 'Cerrar', () => close()) : null);
  const bd = h('div', { class: 'modal-body' }, body);
  const ft = footer ? h('div', { class: 'modal-foot' }, footer) : null;
  box.append(head, bd);
  if (ft) box.append(ft);
  back.append(box);
  root.append(back);
  // la ventana se arrastra por su titulo; las flotantes no tapan ni bloquean el visor
  const place = (x, y) => {
    box.style.position = 'fixed'; box.style.margin = '0'; box.style.transform = 'none';
    box.style.left = `${Math.max(0, Math.min(innerWidth - 120, x))}px`; box.style.top = `${Math.max(0, Math.min(innerHeight - 40, y))}px`;
  };
  if (pos) requestAnimationFrame(() => place(pos.x ?? innerWidth - box.offsetWidth - 20, pos.y ?? 70));
  head.style.cursor = 'move';
  head.addEventListener('pointerdown', (ev) => {
    if (ev.target.closest('button')) return;
    const r = box.getBoundingClientRect();
    const dx = ev.clientX - r.left, dy = ev.clientY - r.top;
    place(r.left, r.top);
    head.setPointerCapture(ev.pointerId);
    const mv = (e) => place(e.clientX - dx, e.clientY - dy);
    const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up); };
    head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
  });
  let closed = false;
  const close = (v) => {
    if (closed) return; closed = true;
    document.removeEventListener('keydown', onKey, true);
    back.classList.add('out'); setTimeout(() => back.remove(), 120);
    if (onClose) onClose(v);
  };
  const onKey = (ev) => {
    const top = root.lastElementChild === back;
    if (ev.key === 'Escape' && closable && top) { ev.stopPropagation(); close(); }
  };
  document.addEventListener('keydown', onKey, true);
  requestAnimationFrame(() => back.classList.add('in'));
  return { el: box, body: bd, foot: ft, close, back };
}

export function confirmBox(message, { title = 'Confirmar', ok = 'Aceptar', danger = false, detail = '' } = {}) {
  return new Promise((res) => {
    let m;
    const done = (v) => { m.close(v); };
    m = modal({ title, icon: danger ? 'alert-triangle' : 'circle-help', width: 440, onClose: (v) => res(!!v), closable: true,
      body: h('div', null, h('p', { class: 'lead', text: message }), detail ? h('p', { class: 'muted', text: detail }) : null),
      footer: [btn('Cancelar', { onClick: () => done(false) }), btn(ok, { kind: danger ? 'danger' : 'primary', onClick: () => done(true) })] });
  });
}

export function promptBox(label, value = '', { title = 'Nombre', ok = 'Aceptar', placeholder = '' } = {}) {
  return new Promise((res) => {
    const inp = h('input', { class: 'input', type: 'text', value, placeholder });
    let m;
    const done = (v) => m.close(v);
    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') done(inp.value.trim() || null); });
    m = modal({ title, icon: 'pencil', width: 420, onClose: (v) => res(v == null ? null : v),
      body: h('label', { class: 'field' }, h('span', { class: 'lbl', text: label }), inp),
      footer: [btn('Cancelar', { onClick: () => done(null) }), btn(ok, { kind: 'primary', onClick: () => done(inp.value.trim() || null) })] });
    setTimeout(() => { inp.focus(); inp.select(); }, 30);
  });
}

// ------------------------------------------------------------------ menus emergentes
let openMenu = null;
export function closeMenu() { if (openMenu) { openMenu.remove(); openMenu = null; } }
document.addEventListener('mousedown', (e) => { if (openMenu && !openMenu.contains(e.target)) closeMenu(); }, true);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });

export function menu(anchor, items, { align = 'left', x, y } = {}) {
  closeMenu();
  const m = h('div', { class: 'menu', role: 'menu' });
  for (const it of items) {
    if (it === '-' || it.sep) { m.append(h('div', { class: 'menu-sep' })); continue; }
    if (it.header) { m.append(h('div', { class: 'menu-head', text: it.header })); continue; }
    const row = h('button', { class: `menu-item ${it.danger ? 'danger' : ''} ${it.checked ? 'checked' : ''}`, type: 'button', disabled: it.disabled || null,
      title: it.title || null, onclick: (e) => { closeMenu(); it.onClick && it.onClick(e); } },
      it.icon ? svg(it.icon, 16) : h('span', { class: 'ic-wrap sp' }), h('span', { class: 'grow', text: it.label }), it.hint ? h('span', { class: 'hint', text: it.hint }) : null);
    m.append(row);
  }
  document.body.append(m);
  const r = anchor ? anchor.getBoundingClientRect() : { left: x, bottom: y, right: x, top: y };
  const mw = m.offsetWidth, mh = m.offsetHeight;
  let left = align === 'right' ? r.right - mw : r.left;
  let top = r.bottom + 4;
  if (left + mw > innerWidth - 8) left = innerWidth - mw - 8;
  if (top + mh > innerHeight - 8) top = Math.max(8, r.top - mh - 4);
  m.style.left = `${Math.max(8, left)}px`; m.style.top = `${top}px`;
  openMenu = m;
  return m;
}

// ------------------------------------------------------------------ controles de formulario
export function field(label, control, { hint, help, cls = '' } = {}) {
  const l = h('div', { class: `field ${cls}` }, h('span', { class: 'lbl' }, label, help ? h('span', { class: 'help', title: help }, svg('circle-help', 13)) : null), control);
  if (hint) l.append(h('span', { class: 'hint-text', text: hint }));
  return l;
}

export function numInput({ value = 0, min, max, step = 'any', dec = 3, suffix = '', onChange, cls = '', width }) {
  const inp = h('input', { class: `input num ${cls}`, type: 'number', step: String(step), value: fmtNum(value, dec) });
  if (min != null) inp.min = String(min);
  if (max != null) inp.max = String(max);
  if (width) inp.style.width = width;
  const wrap = h('div', { class: 'input-wrap' }, inp, suffix ? h('span', { class: 'suffix', text: suffix }) : null);
  const commit = () => {
    let v = parseFloat(inp.value.replace(',', '.'));
    if (!isFinite(v)) { inp.value = fmtNum(wrap._value, dec); return; }
    if (min != null) v = Math.max(min, v);
    if (max != null) v = Math.min(max, v);
    wrap._value = v;
    onChange && onChange(v);
  };
  inp.addEventListener('change', commit);
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { commit(); inp.blur(); } });
  wrap._value = value;
  wrap.set = (v) => { wrap._value = v; inp.value = fmtNum(v, dec); };
  wrap.input = inp;
  return wrap;
}
export function fmtNum(v, dec = 3) {
  if (v == null || !isFinite(v)) return '';
  const s = Number(v).toFixed(dec);
  return s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s;
}

export function selectInput({ value, options, onChange, cls = '', editable = false }) {
  const sel = h('select', { class: `input select ${cls}` });
  const opts = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o));
  for (const o of opts) sel.append(h('option', { value: o.value, text: o.label, disabled: o.disabled || null }));
  if (value != null && !opts.some((o) => o.value === value)) sel.append(h('option', { value, text: String(value) }));
  sel.value = value ?? '';
  sel.addEventListener('change', () => onChange && onChange(sel.value));
  sel.set = (v) => { if (![...sel.options].some((o) => o.value === v)) sel.append(h('option', { value: v, text: String(v) })); sel.value = v; };
  return sel;
}

export function checkInput({ value, label, onChange }) {
  const c = h('input', { type: 'checkbox' });
  c.checked = !!value;
  c.addEventListener('change', () => onChange && onChange(c.checked));
  const w = h('label', { class: 'check' }, c, h('span', { text: label || '' }));
  w.set = (v) => { c.checked = !!v; };
  return w;
}

export function textInput({ value = '', onChange, placeholder = '', cls = '' }) {
  const i = h('input', { class: `input ${cls}`, type: 'text', value, placeholder });
  i.addEventListener('change', () => onChange && onChange(i.value));
  return i;
}

export function segmented(options, value, onChange) {
  const w = h('div', { class: 'segmented', role: 'tablist' });
  const render = (v) => {
    clear(w);
    for (const o of options) {
      const op = typeof o === 'string' ? { value: o, label: o } : o;
      w.append(h('button', { type: 'button', class: op.value === v ? 'on' : '', title: op.title || null, onclick: () => { render(op.value); onChange && onChange(op.value); } },
        op.icon ? svg(op.icon, 15) : null, op.label ? h('span', { text: op.label }) : null));
    }
  };
  render(value);
  w.set = render;
  return w;
}

export function tabs(items, { active, onChange, cls = '' } = {}) {
  const bar = h('div', { class: 'tabbar' });
  const panel = h('div', { class: 'tabpanel' });
  const root = h('div', { class: `tabs ${cls}` }, bar, panel);
  let cur = null;
  const show = (id) => {
    cur = id;
    for (const b of bar.children) b.classList.toggle('on', b.dataset.id === id);
    clear(panel);
    const it = items.find((x) => x.id === id);
    if (it) { const c = it.render(); panel.append(c instanceof Node ? c : document.createTextNode(c || '')); }
    onChange && onChange(id);
  };
  for (const it of items) bar.append(h('button', { type: 'button', class: 'tab', dataset: { id: it.id }, onclick: () => show(it.id) }, it.icon ? svg(it.icon, 15) : null, h('span', { text: it.label })));
  root.show = show;
  root.current = () => cur;
  show(active || items[0].id);
  return root;
}

export function chip(text, kind = '', title) { return h('span', { class: `chip ${kind}`, title: title || null, text }); }

export function dcBar(ratio, skip = false) {
  if (skip) return h('span', { class: 'dc na', text: '—' });
  const pct = Math.min(ratio, 1.2) / 1.2 * 100;
  const kind = ratio > 1 + 1e-9 ? 'bad' : ratio >= 0.8 ? 'warn' : 'ok';
  return h('div', { class: `dc ${kind}` }, h('div', { class: 'dc-fill', style: { width: `${pct}%` } }), h('span', { class: 'dc-txt', text: ratio.toFixed(3) }));
}

export function spinner(text = '') { return h('div', { class: 'spinner-row' }, h('span', { class: 'spinner' }), text ? h('span', { text }) : null); }

export function debounce(fn, ms = 250) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.flush = (...a) => { clearTimeout(t); fn(...a); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export function fmtDate(ts) {
  const d = new Date(ts * 1000);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'ahora mismo';
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  if (diff < 86400 * 7) return `hace ${Math.floor(diff / 86400)} d`;
  return d.toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
}
