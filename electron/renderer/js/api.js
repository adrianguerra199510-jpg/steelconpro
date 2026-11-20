// Cliente del motor (servidor local de Python): POST /api/<funcion> con JSON.
const q = new URLSearchParams(location.search);
const boot = (window.SCP && window.SCP.engine) || { url: q.get('engine') || '', token: q.get('token') || '' };

export const engine = boot;

export class ApiError extends Error {
  constructor(msg, trace) { super(msg); this.trace = trace || ''; }
}

export async function call(fn, args = {}) {
  let res;
  try {
    res = await fetch(`${boot.url}/api/${fn}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-SCP-Token': boot.token },
      body: JSON.stringify(args),
    });
  } catch (e) {
    throw new ApiError('No se pudo comunicar con el motor de cálculo. Cierre y vuelva a abrir SteelConPro.');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* respuesta vacia */ }
  if (!res.ok) throw new ApiError((data && data.error) || `Error ${res.status}`, data && data.trace);
  return data;
}

// Diferencia las llamadas rapidas y repetidas (por ejemplo al escribir): solo se devuelve la ultima.
export function latest(fn) {
  let n = 0;
  return async (...a) => {
    const my = ++n;
    const r = await fn(...a);
    return my === n ? r : undefined;
  };
}

export function b64ToFloat32(s) {
  if (!s) return new Float32Array(0);
  const bin = atob(s);
  const buf = new ArrayBuffer(bin.length);
  const u8 = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Float32Array(buf);
}
