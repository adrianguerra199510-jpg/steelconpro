// Capturas del visor 3D (solo el recuadro del visor) con cámara, zoom y preparación del modelo a gusto.
// Uso:  xvfb-run -a node tests/mallashot.js <carpeta> <archivo.scp> <texto de la tarjeta> <spec.json>
// spec.json: { "prep": "js que se evalua en la pagina (p. ej. cambiar la conexion desde window.__E y llamar a window.__E.changed({geometry:true}))",
//              "shots": [ { "name": "iso", "view": "iso", "dir": [x,y,z], "target": [x,y,z], "zoom": 1, "cotas": false, "etiquetas": false } ] }
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const [shots, file, label, specFile] = process.argv.slice(2);
  const spec = JSON.parse(fs.readFileSync(specFile, 'utf8'));
  fs.mkdirSync(shots, { recursive: true });
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(file, path.join(ws, path.basename(file)));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: spec.width || 1400, height: spec.height || 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click(`text=${label}`); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 0))) break; await wait(500); }
  await page.evaluate(() => { const E = window.__E; E.showLoadsOn = false; E.showReactionsOn = false; E.viewer.setLoadsVisible(false); });
  if (spec.prep) {
    await page.evaluate(spec.prep);
    await wait(3500);
  }
  for (const s of spec.shots) {
    await page.evaluate((s_) => {
      const v = window.__E.viewer;
      v.setDims(!!s_.cotas); v.setLabels(!!s_.etiquetas);
      v.setView(s_.view || 'iso');
      const dist = v.camera.position.distanceTo(v.controls.target);
      const t = s_.target ? v.controls.target.clone().set(s_.target[0], s_.target[1], s_.target[2]) : v.controls.target.clone();
      const off = v.camera.position.clone().sub(v.controls.target);
      if (s_.dir) off.set(s_.dir[0], s_.dir[1], s_.dir[2]).normalize().multiplyScalar(dist);
      const z = s_.zoom || 1;
      v.controls.target.copy(t);
      if (v.camera.isOrthographicCamera) { v.camera.position.copy(t).add(off); v.camera.zoom = z; v.camera.updateProjectionMatrix(); }
      else v.camera.position.copy(t).add(off.multiplyScalar(1 / z));
      v.camera.lookAt(t); v.controls.update(); v.requestRender();
    }, s);
    await wait(900);
    const box = await (await page.$('.viewer')).boundingBox();
    await page.screenshot({ path: path.join(shots, `${s.name}.png`), clip: box });
  }
  if (errors.length) console.log('ERRORES DE PAGINA: ' + errors.slice(0, 5).join(' | '));
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
