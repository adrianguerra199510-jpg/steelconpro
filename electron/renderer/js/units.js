// Conversion entre las unidades que elige el usuario y las internas del motor (in, kip, ksi): igual que steelconpro/units.py.
export class UnitSet {
  constructor(C, len = 'mm', force = 'kN', stress = 'MPa', moment = 'kN·m') {
    this.C = C; this.set(len, force, stress, moment);
  }
  set(len, force, stress, moment) {
    const U = this.C.units;
    this.length = len in U.len ? len : 'in';
    this.force = force in U.force ? force : 'kip';
    this.stress = stress in U.stress ? stress : 'ksi';
    this.moment = moment in U.moment ? moment : null;
    this.fl = U.len[this.length]; this.ff = U.force[this.force]; this.fs = U.stress[this.stress];
    this.fm = this.moment ? U.moment[this.moment] : this.ff * this.fl;
  }
  static of(C, conn) { return new UnitSet(C, conn.u_len, conn.u_force, conn.u_stress, conn.u_moment); }
  label(k) {
    return { L: this.length, F: this.force, M: this.moment || `${this.force}·${this.length}`, S: this.stress, A: `${this.length}²`,
      K: `${this.force}/${this.length}³`, LF: `${this.force}/${this.length}`, '-': '' }[k] ?? '';
  }
  factor(k) {
    switch (k) {
      case 'L': return this.fl; case 'F': return this.ff; case 'M': return this.fm; case 'S': return this.fs;
      case 'A': return this.fl ** 2; case 'K': return this.ff / this.fl ** 3; case 'LF': return this.ff / this.fl;
      default: return 1;
    }
  }
  out(k, v) { const f = this.factor(k); return f ? v / f : v; }   // interno -> mostrado
  inn(k, v) { return v * this.factor(k); }                         // mostrado -> interno
  dec(k) {
    if (k === 'L') return { in: 3, ft: 4, mm: 1, cm: 2, m: 4 }[this.length] ?? 2;
    if (k === 'F') return { kip: 2, lbf: 0, kN: 2, N: 0, tonf: 3, kgf: 0 }[this.force] ?? 2;
    if (k === 'S') return { ksi: 2, psi: 0, MPa: 1, 'kgf/cm2': 0, 'kgf/mm2': 2 }[this.stress] ?? 2;
    return 2;
  }
  step(k) {
    if (k === 'L') return { in: 0.25, ft: 0.05, mm: 5, cm: 0.5, m: 0.005 }[this.length] ?? 1;
    if (k === 'F') return { kip: 5, lbf: 500, kN: 25, N: 5000, tonf: 2.5, kgf: 500 }[this.force] ?? 1;
    if (k === 'S') return { ksi: 1, psi: 100, MPa: 5, 'kgf/cm2': 50, 'kgf/mm2': 0.5 }[this.stress] ?? 1;
    return 0.1;
  }
  fmt(k, v, dec) {
    const x = this.out(k, v);
    if (dec == null) { const a = Math.abs(x); dec = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : 4; }
    return x.toLocaleString('es', { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }
  q(k, v, dec) { return `${this.fmt(k, v, dec)} ${this.label(k)}`.trim(); }
}
