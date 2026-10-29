// Visor 3D (three.js): mallas por pieza con sombreado plano de dos caras, aristas, etiquetas, cotas, seleccion y vistas Iso / Planta / Frontal / Lateral.
import * as THREE from '../vendor/three.module.js';
import { OrbitControls } from '../vendor/OrbitControls.js';
import { b64ToFloat32 } from './api.js';

const STRIDE = 10;

const VERT = `
attribute vec4 aCol; attribute vec3 aNor;
uniform vec3 uCam; uniform vec3 uL; uniform vec4 uTint;
varying vec4 vCol;
void main(){
  float k = 1.0;
  float l = length(aNor);
  if (l > 0.5) {
    vec3 n = aNor / l;
    if (dot(n, uCam) < 0.0) n = -n;
    k = 0.45 + 0.35 * max(dot(n, uL), 0.0) + 0.25 * max(dot(n, uCam), 0.0);
  }
  vec3 c = aCol.rgb * min(k, 1.0);
  c = mix(c, uTint.rgb, uTint.a);
  vCol = vec4(c, aCol.a);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
const FRAG = `varying vec4 vCol; uniform float uDim; void main(){ gl_FragColor = vec4(vCol.rgb, vCol.a * uDim); }`;

function makeGeometry(arr) {
  const n = arr.length / STRIDE;
  const g = new THREE.BufferGeometry();
  const buf = new THREE.InterleavedBuffer(arr, STRIDE);
  g.setAttribute('position', new THREE.InterleavedBufferAttribute(buf, 3, 0));
  g.setAttribute('aNor', new THREE.InterleavedBufferAttribute(buf, 3, 3));
  g.setAttribute('aCol', new THREE.InterleavedBufferAttribute(buf, 4, 6));
  g.computeBoundingSphere();
  g.userData.count = n;
  return g;
}

export class Viewer {
  constructor(container, { onPick, onHover } = {}) {
    this.el = container;
    this.onPick = onPick; this.onHover = onHover;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    container.append(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.root = new THREE.Group(); this.scene.add(this.root);
    this.persp = new THREE.PerspectiveCamera(32, 1, 0.1, 100000);
    this.ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, -100000, 100000);
    this.persp.up.set(0, 0, 1); this.ortho.up.set(0, 0, 1);
    this.camera = this.persp;
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.screenSpacePanning = true;
    this.controls.addEventListener('change', () => this.requestRender());
    this.parts = [];            // { name, kind, label, meshes: [..], lines, tint, visible }
    this.dims = []; this.labels = [];
    this.showDims = false; this.showLabels = true;
    this.view = 'iso';
    this.bounds = new THREE.Box3(new THREE.Vector3(-1, -1, -1), new THREE.Vector3(1, 1, 1));
    this.selected = new Set();
    this.hidden = new Set();
    this.dimGroup = new THREE.Group(); this.scene.add(this.dimGroup);
    this.overlay = document.createElement('div'); this.overlay.className = 'vlabels'; container.append(this.overlay);
    this.uniforms = { uCam: { value: new THREE.Vector3(0, 0, 1) }, uL: { value: new THREE.Vector3(0.4, -0.5, 0.75).normalize() } };
    this._raf = 0;
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(container);
    this.renderer.domElement.addEventListener('pointerdown', (e) => { this._down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
    this.renderer.domElement.addEventListener('pointerup', (e) => {
      if (!this._down) return;
      const d = Math.hypot(e.clientX - this._down.x, e.clientY - this._down.y);
      if (d < 4 && performance.now() - this._down.t < 500) this.pick(e);
      this._down = null;
    });
    this.renderer.domElement.addEventListener('pointermove', (e) => { if (this.onHover && !e.buttons) this._hoverMove(e); });
    this.resize();
  }

  dispose() { this.ro.disconnect(); this.clear(); this.renderer.dispose(); this.renderer.domElement.remove(); this.overlay.remove(); cancelAnimationFrame(this._raf); }

  clear() {
    for (const p of this.parts) for (const m of p.objs) { m.geometry.dispose(); m.material.dispose(); this.root.remove(m); }
    this.parts = [];
    this.dimGroup.clear();
    this.overlay.replaceChildren();
  }

  _mat(transparent) {
    return new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, transparent, depthWrite: !transparent, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      uniforms: { uCam: this.uniforms.uCam, uL: this.uniforms.uL, uTint: { value: new THREE.Vector4(1, 0.45, 0.05, 0) }, uDim: { value: 1 } } });
  }

  // data = respuesta de api.mesh (o fem_scene): { parts: [{name, kind, label, o, t, l}], dims, labels, bounds }
  setModel(data, { keepView = true } = {}) {
    this.clear();
    for (const pd of data.parts) {
      const part = { name: pd.name, kind: pd.kind, label: pd.label, objs: [], mats: [] };
      for (const [key, transparent] of [['o', false], ['t', true]]) {
        const arr = b64ToFloat32(pd[key]);
        if (!arr.length) continue;
        const mesh = new THREE.Mesh(makeGeometry(arr), this._mat(transparent));
        mesh.userData.part = part; mesh.renderOrder = transparent ? 2 : 0;
        if (transparent) mesh.raycast = () => {};            // el pedestal translucido no intercepta la seleccion
        this.root.add(mesh); part.objs.push(mesh); part.mats.push(mesh.material);
      }
      const la = b64ToFloat32(pd.l);
      if (la.length) {
        const g = new THREE.BufferGeometry();
        const buf = new THREE.InterleavedBuffer(la, STRIDE);
        g.setAttribute('position', new THREE.InterleavedBufferAttribute(buf, 3, 0));
        g.setAttribute('color', new THREE.InterleavedBufferAttribute(buf, 3, 6));
        const lm = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.8 });
        const ls = new THREE.LineSegments(g, lm);
        ls.raycast = () => {}; ls.renderOrder = 1;
        this.root.add(ls); part.objs.push(ls); part.mats.push(lm); part.lines = ls;
      }
      this.parts.push(part);
    }
    const [lo, hi] = data.bounds || [[-1, -1, -1], [1, 1, 1]];
    this.bounds = new THREE.Box3(new THREE.Vector3(...lo), new THREE.Vector3(...hi));
    this.dimData = data.dims || []; this.labelData = data.labels || [];
    this._buildDims(); this._buildLabels();
    this._applyVisibility(); this._applySelection();
    if (!keepView || !this._fitted) { this.setView(this.view, true); this._fitted = true; }
    this.requestRender();
  }

  _buildDims() {
    this.dimGroup.clear();
    this.dimLabels = [];
    const pos = [];
    const lo = this.bounds.min, hi = this.bounds.max;
    const arrow = 0.012 * Math.max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, 1);
    for (const d of this.dimData || []) {
      const a = new THREE.Vector3(...d.a), b = new THREE.Vector3(...d.b), off = new THREE.Vector3(...d.off);
      if (off.length() < 1e-9 || a.distanceTo(b) < 1e-9) continue;
      const q1 = a.clone().add(off), q2 = b.clone().add(off);
      const o = off.clone().normalize(), t = q2.clone().sub(q1).normalize();
      const seg = (p, q) => pos.push(p.x, p.y, p.z, q.x, q.y, q.z);
      seg(a.clone().addScaledVector(off, 0.12), q1.clone().addScaledVector(o, arrow));
      seg(b.clone().addScaledVector(off, 0.12), q2.clone().addScaledVector(o, arrow));
      seg(q1, q2);
      for (const [tip, sg] of [[q1, 1], [q2, -1]]) {
        seg(tip, tip.clone().addScaledVector(t, sg * arrow).addScaledVector(o, 0.35 * arrow));
        seg(tip, tip.clone().addScaledVector(t, sg * arrow).addScaledVector(o, -0.35 * arrow));
      }
      this.dimLabels.push({ p: q1.clone().add(q2).multiplyScalar(0.5), text: d.text ?? d.value, views: d.views });
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    this._dimLines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x3b4452 }));
    this.dimGroup.add(this._dimLines);
    this.dimGroup.visible = this.showDims;
  }

  _buildLabels() {
    this.overlay.replaceChildren();
    this.labelEls = [];
    for (const l of this.labelData || []) {
      const e = document.createElement('div'); e.className = 'vlabel'; e.textContent = l.text; this.overlay.append(e);
      this.labelEls.push({ el: e, p: new THREE.Vector3(...l.pos), kind: 'tag' });
    }
    this.dimEls = [];
    for (const d of this.dimLabels || []) {
      const e = document.createElement('div'); e.className = 'vlabel dim'; e.textContent = typeof d.text === 'number' ? d.text.toFixed(2) : d.text; this.overlay.append(e);
      this.dimEls.push({ el: e, p: d.p, views: d.views });
    }
  }

  setDimFormatter(fn) { this._fmt = fn; }
  setDimTexts(fn) { (this.dimLabels || []).forEach((d, i) => { if (this.dimEls[i] && typeof d.text === 'number') this.dimEls[i].el.textContent = fn(d.text); }); }

  setDims(on) { this.showDims = on; if (this.dimGroup) this.dimGroup.visible = on; this.requestRender(); }
  setLabels(on) { this.showLabels = on; this.requestRender(); }

  setHidden(names) { this.hidden = new Set(names); this._applyVisibility(); this.requestRender(); }
  _applyVisibility() { for (const p of this.parts) for (const o of p.objs) o.visible = !this.hidden.has(p.kind) && !this.hidden.has(p.name); }

  select(names) { this.selected = new Set(names || []); this._applySelection(); this.requestRender(); }
  _applySelection() {
    const any = this.selected.size > 0;
    for (const p of this.parts) {
      const on = this.selected.has(p.name);
      for (const m of p.mats) {
        if (m.uniforms) { m.uniforms.uTint.value.w = on ? 0.45 : 0; m.uniforms.uDim.value = any && !on ? 0.55 : 1; }
      }
    }
  }

  // ---------------------------------------------------------------- camara
  fit() {
    const b = this.bounds;
    const c = b.getCenter(new THREE.Vector3());
    const size = b.getSize(new THREE.Vector3());
    const r = Math.max(size.length() / 2, 1e-3);
    this._center = c; this._r = r;
    const dir = this._viewDir(this.view);
    const dist = r / Math.sin((this.persp.fov * Math.PI / 180) / 2) * 1.05;
    this.persp.position.copy(c).addScaledVector(dir, dist);
    this.persp.near = dist / 100; this.persp.far = dist * 20; this.persp.updateProjectionMatrix();
    this.ortho.position.copy(c).addScaledVector(dir, dist);
    const asp = this._w / Math.max(this._h, 1);
    const half = r * 1.15;
    this.ortho.left = -half * Math.max(asp, 1); this.ortho.right = half * Math.max(asp, 1);
    this.ortho.top = half / Math.min(asp, 1); this.ortho.bottom = -half / Math.min(asp, 1);
    this.ortho.near = -dist * 20; this.ortho.far = dist * 20; this.ortho.updateProjectionMatrix();
    this.controls.target.copy(c);
    this.camera.lookAt(c);
    this.controls.update();
    this.requestRender();
  }

  _viewDir(v) {
    return { iso: new THREE.Vector3(0.62, -0.78, 0.55), plan: new THREE.Vector3(0, 0.0001, 1), front: new THREE.Vector3(0, -1, 0), side: new THREE.Vector3(1, 0, 0) }[v] || new THREE.Vector3(0.62, -0.78, 0.55);
  }

  setView(v, noRender) {
    this.view = v;
    const ortho = v !== 'iso';
    this.camera = ortho ? this.ortho : this.persp;
    this.controls.object = this.camera;
    this.controls.enableRotate = !ortho;
    this.fit();
    if (this.onView) this.onView(v);
  }

  togglePerspective() { /* reservado */ }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this._w = w; this._h = h;
    this.renderer.setSize(w, h, false);
    this.persp.aspect = w / h; this.persp.updateProjectionMatrix();
    if (this._center) this.fit();
    this.requestRender();
  }

  requestRender() { if (!this._raf) this._raf = requestAnimationFrame(() => { this._raf = 0; this.render(); }); }

  render() {
    const cam = this.camera;
    const dir = new THREE.Vector3(); dir.copy(cam.position).sub(this.controls.target).normalize();
    this.uniforms.uCam.value.copy(dir);
    this.renderer.render(this.scene, cam);
    this._placeLabels();
  }

  _proj(p) {
    const v = p.clone().project(this.camera);
    return { x: (v.x * 0.5 + 0.5) * this._w, y: (-v.y * 0.5 + 0.5) * this._h, z: v.z };
  }

  _placeLabels() {
    for (const l of this.labelEls || []) {
      const q = this._proj(l.p);
      l.el.style.display = this.showLabels && q.z < 1 ? 'block' : 'none';
      l.el.style.left = `${q.x}px`; l.el.style.top = `${q.y}px`;
    }
    for (const l of this.dimEls || []) {
      const q = this._proj(l.p);
      const vis = this.showDims && q.z < 1 && (this.view === 'iso' || !l.views || l.views.includes(this.view));
      l.el.style.display = vis ? 'block' : 'none';
      l.el.style.left = `${q.x}px`; l.el.style.top = `${q.y}px`;
    }
  }

  // ---------------------------------------------------------------- seleccion
  _ray(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const rc = new THREE.Raycaster();
    rc.setFromCamera(ndc, this.camera);
    const objs = [];
    for (const p of this.parts) for (const o of p.objs) if (o.visible && o.isMesh) objs.push(o);
    const hit = rc.intersectObjects(objs, false)[0];
    return hit ? hit.object.userData.part : null;
  }

  pick(e) { const p = this._ray(e); if (this.onPick) this.onPick(p ? p.name : null, p, e); }
  _hoverMove(e) { const p = this._ray(e); this.renderer.domElement.style.cursor = p ? 'pointer' : 'default'; this.onHover(p ? p.name : null, p); }

  screenshot() { this.render(); return this.renderer.domElement.toDataURL('image/png'); }
}
