// Captura de la soldadura de un recorte inclinado (CN-06).  Uso: xvfb-run -a node tests/weldshot.js <carpeta>
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-w-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(path.join(__dirname, '..', '..', 'ejemplos', 'CN-01_columna_con_vigas.scp'), path.join(ws, 'CN-01.scp'));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1400, height: 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click('text=CN-01'); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1))) break; await wait(500); }
  const info = '';
  console.log('placas', info);
  await wait(3000);
  const zoom = (x, y, z, k, view) => page.evaluate(([x_, y_, z_, k_, v_]) => { const v = window.__E.viewer; if (v_) v.setView(v_); const t = v.controls.target.clone(); t.set(x_, y_, z_); const off = v.camera.position.clone().sub(v.controls.target); v.controls.target.copy(t); v.camera.position.copy(t).add(off); if (v.camera.isOrthographicCamera) { v.camera.zoom = k_; v.camera.updateProjectionMatrix(); } else v.camera.position.copy(t).add(off.multiplyScalar(1 / k_)); v.camera.lookAt(t); v.controls.update(); v.requestRender(); }, [x, y, z, k, view]);
  await page.evaluate(() => { const E = window.__E; E.showLoadsOn = false; E.showReactionsOn = false; E.viewer.setLoadsVisible(false); });
  await zoom(8, 0, 0, 7, 'iso'); await wait(1500);
  await page.screenshot({ path: path.join(shots, 'placa_extrema_0.png') });
  await zoom(8, 0, 0, 6, 'top'); await wait(1500);
  await page.screenshot({ path: path.join(shots, 'placa_extrema_1.png') });
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
