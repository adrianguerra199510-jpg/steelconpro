// Revisión visual: vista en planta, placa alineada a la columna con la viga girada y miembro cortado.  Uso: xvfb-run -a node tests/visual.js <carpeta>
const { _electron: electron } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-vis-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  for (const f of ['CN-01_columna_con_vigas.scp', 'CN-02_viga_con_secundarias.scp']) fs.copyFileSync(path.join(ex, f), path.join(ws, f));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1500, height: 900 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const wait = (ms) => page.waitForTimeout(ms);
  const open = async (name) => {
    await page.waitForSelector('.home', { timeout: 120000 });
    await page.click(`text=${name}`);
    await page.waitForSelector('.editor', { timeout: 30000 });
    for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1))) break; await wait(500); }
    await wait(2000);
  };
  const home = async () => { await page.click('[title="Volver al inicio"]'); await page.waitForSelector('.home', { timeout: 20000 }); };
  const step = async (name, fn) => { try { await fn(); console.log('OK   ' + name); } catch (e) { console.log('FALLA ' + name + ': ' + e.message.split('\n')[0]); try { await page.screenshot({ path: path.join(shots, 'error_' + name + '.png') }); } catch (e2) { /* nada */ } } };
  // acerca la cámara a un punto (en la vista actual)
  const zoomTo = (x, y, z, zoom) => page.evaluate(([x_, y_, z_, k]) => {
    const v = window.__E.viewer;
    const t = v.controls.target.clone(); t.set(x_, y_, z_);
    const off = v.camera.position.clone().sub(v.controls.target);
    v.controls.target.copy(t); v.camera.position.copy(t).add(off);
    if (v.camera.isOrthographicCamera) { v.camera.zoom = k; v.camera.updateProjectionMatrix(); } else { v.camera.position.copy(t).add(off.multiplyScalar(1 / k)); }
    v.camera.lookAt(t); v.controls.update(); v.requestRender();
  }, [x, y, z, zoom]);

  await step('planta', async () => {
    await open('CN-01');
    await page.click('button:has-text("Planta")');
    await wait(1500);
    await page.screenshot({ path: path.join(shots, 'visual_1_planta.png') });
    await page.click('button:has-text("Frontal")'); await wait(1200);
    await page.screenshot({ path: path.join(shots, 'visual_1b_frontal.png') });
    await page.click('button:has-text("Lateral")'); await wait(1200);
    await page.screenshot({ path: path.join(shots, 'visual_1c_lateral.png') });
    await page.click('button:has-text("Iso")'); await wait(1200);
  });
  await step('alineacion', async () => {
    await page.click('button:has-text("Planta")'); await wait(800);
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; n.members[0].az = 10; E.changed({ geometry: true }); });
    await wait(2500);
    await zoomTo(9, 0, 0, 5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_miembro.png') });
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; const o = n.operations.find((x) => x.member === n.members[0].name && x.kind.startsWith('Placa extrema')); o.align_to = n.main_name; E.changed({ geometry: true }); });
    await wait(2500);
    await zoomTo(9, 0, 0, 5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_columna.png') });
    await page.click('button:has-text("Iso")'); await wait(800);
    await zoomTo(10, 0, 0, 2.5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_iso.png') });
    await home();
  });
  await step('corte', async () => {
    await open('CN-02');
    await zoomTo(0, -3, 6, 3.2); await wait(1000);
    await page.screenshot({ path: path.join(shots, 'visual_3_corte.png') });
    await home();
  });
  await step('placa_hasta_alas', async () => {
    await open('CN-02');
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; const o = n.operations.find((x) => x.member === 'S2' && x.kind.startsWith('Placa simple')); o.tab_mode = window.__E.C_TAB || 'Hasta el interior de las alas del principal'; E.changed({ geometry: true }); });
    await wait(3000);
    await page.click('button:has-text("Frontal")'); await wait(700);
    await page.evaluate(() => { const E = window.__E; E.viewer.setView('side'); });
    await wait(900); await zoomTo(0, -4, 3, 3.2); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4_lateral.png') });
    await page.click('button:has-text("Iso")'); await wait(800);
    await zoomTo(0, -4, 3, 2.6); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4_placa_hasta_alas.png') });
    await page.click('button:has-text("Planta")'); await wait(900);
    await zoomTo(0, -6, 0, 3); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4b_placa_hasta_alas_planta.png') });
    await page.click('button:has-text("Frontal")'); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4c_placa_hasta_alas_frontal.png') });
  });
  console.log(errors.length ? 'Errores: ' + errors.slice(0, 5).join(' | ') : 'sin errores de consola');
  await app.close();
})();
