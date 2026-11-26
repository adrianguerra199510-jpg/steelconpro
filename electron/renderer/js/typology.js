// Diálogo «Nueva conexión»: en blanco o a partir de una tipología de nudo (plato base, columna intermedia o superior, nodo de vigas) o de la plantilla
// fija del pórtico especial con placa extrema precalificada (AISC DG4).
import { call } from './api.js';
import { S } from './state.js';
import { h, btn, modal, field, numInput, checkInput, selectInput, errorBox, clear } from './ui.js';
import { sectionPicker } from './sectionpicker.js';

// esquemas de cada nudo (líneas que salen del nodo), como en los diagramas de referencia
const ICON = {
  base: '<line x1="50" y1="12" x2="50" y2="78"/><line x1="50" y1="78" x2="84" y2="48"/><line x1="50" y1="78" x2="16" y2="48"/><rect x="34" y="78" width="32" height="6" rx="1" fill="currentColor"/>',
  col: '<line x1="50" y1="6" x2="50" y2="94"/><line x1="50" y1="50" x2="84" y2="24"/><line x1="50" y1="50" x2="16" y2="24"/><line x1="50" y1="50" x2="84" y2="76"/><line x1="50" y1="50" x2="16" y2="76"/><circle cx="50" cy="50" r="5" fill="currentColor"/>',
  vigas: '<line x1="14" y1="78" x2="86" y2="22"/><line x1="14" y1="22" x2="86" y2="78"/><circle cx="50" cy="50" r="5" fill="currentColor"/>',
  smf: '<line x1="50" y1="6" x2="50" y2="94"/><line x1="54" y1="44" x2="94" y2="44"/><line x1="54" y1="56" x2="94" y2="56"/><rect x="52" y="34" width="5" height="32" fill="currentColor"/><line x1="46" y1="44" x2="6" y2="44" stroke-dasharray="6 5"/><line x1="46" y1="56" x2="6" y2="56" stroke-dasharray="6 5"/>',
  blank: '<circle cx="50" cy="50" r="6" fill="currentColor"/>',
};
const icon = (k) => { const w = document.createElement('span'); w.style.cssText = 'width:52px;height:52px;flex:none;color:var(--brand,#e8731a)'; w.innerHTML = `<svg viewBox="0 0 100 100" width="52" height="52" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round">${ICON[k] || ICON.blank}</svg>`; return w; };

// Devuelve {typology, params} (typology '' = en blanco) o null si se cancela.  `us` = unidades del proyecto (desde el inicio aún no hay editor abierto).
export async function pickTypology(us = S.us) {
  let d;
  try { d = await call('typologies'); } catch (e) { errorBox(e); return null; }
  return new Promise((resolve) => {
    let sel = '';
    const vals = {};
    const cards = h('div', { class: 'col gap-8' });
    const form = h('div', { class: 'form-grid', style: { marginTop: '6px' } });
    const draw = () => {
      clear(cards); clear(form);
      const items = [{ id: '', name: 'En blanco', sub: 'Solo el miembro principal; agregue miembros y operaciones a mano.' }, ...d.types.map((t) => ({ id: t.id, name: t.name, sub: ({ base: 'Columna sobre placa base con diagonales y cartelas.', col: 'Columna que continúa o termina en el nudo, con diagonales y cartelas.', vigas: 'Dos miembros que se cruzan; uno pasa por el nudo y el otro llega a él.', smf: 'Plantilla fija: columna W con una o dos vigas con placa extrema 4E, 4ES u 8ES, placas de continuidad y verificación del nudo (AISC 341-22).' })[t.id] }))];
      for (const it of items) {
        cards.append(h('button', { type: 'button', class: `tpl-card ${sel === it.id ? 'on' : ''}`, style: { display: 'flex', gap: '12px', alignItems: 'center', textAlign: 'left', padding: '10px 12px', border: `1px solid ${sel === it.id ? 'var(--brand)' : 'var(--border)'}`, borderRadius: '10px', background: sel === it.id ? 'var(--brand-soft, #fff3ea)' : 'var(--surface)', cursor: 'pointer' }, onclick: () => { sel = it.id; draw(); } },
          icon(it.id || 'blank'), h('div', null, h('div', { style: { fontWeight: 700 }, text: it.name }), h('div', { class: 'muted', style: { fontSize: '12.5px' }, text: it.sub }))));
      }
      const t = d.types.find((x) => x.id === sel);
      if (!t) return;
      for (const f of t.fields) {
        const u = f.unit || (f.length ? 'L' : '');
        if (!(f.key in vals) || vals._k !== sel) vals[f.key] = u ? us.out(u, f.default) : f.default;
        let ctl;
        if (f.type === 'shape') ctl = sectionPicker(vals[f.key], (v) => { vals[f.key] = v; });
        else if (f.type === 'choice') ctl = selectInput({ value: vals[f.key], options: f.items, onChange: (v) => { vals[f.key] = v; } });
        else if (f.type === 'bool') ctl = checkInput({ value: !!vals[f.key], label: '', onChange: (v) => { vals[f.key] = v; } });
        else ctl = numInput({ value: vals[f.key], min: u && f.lo != null ? us.out(u, f.lo) : f.lo, max: u && f.hi != null ? us.out(u, f.hi) : f.hi, dec: f.type === 'int' ? 0 : (u === 'L' && us.label('L') === 'in' ? (f.dec || 1) : 1), onChange: (v) => { vals[f.key] = f.type === 'int' ? Math.round(v) : v; }, suffix: u ? us.label(u) : '' });
        form.append(field(f.label, ctl));
      }
      vals._k = sel;
    };
    draw();
    const m = modal({ title: 'Nueva conexión', icon: 'component', width: 600, body: h('div', { class: 'col gap-12' }, cards, form),
      footer: [btn('Cancelar', { onClick: () => { resolve(null); m.close(); } }), btn('Crear', { kind: 'primary', icon: 'check', onClick: () => {
        const params = {}; const t = d.types.find((x) => x.id === sel);
        if (t) for (const f of t.fields) { const u = f.unit || (f.length ? 'L' : ''); params[f.key] = u ? us.inn(u, vals[f.key]) : vals[f.key]; }
        resolve({ typology: sel, params }); m.close();
      } })],
      onClose: () => resolve(null) });
  });
}
