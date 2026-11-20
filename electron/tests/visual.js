// Revisión visual: vista en planta, placa alineada a la columna con la viga girada y miembro cortado.  Uso: xvfb-run -a node tests/visual.js <carpeta>
const { _electron: electron } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-vis-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  for (const f of ['CN-01_columna_con_vigas.scp', 'CN-02_viga_con_secundarias.scp', 'CN-06_diagonal_con_recorte_y_angulo.scp']) fs.copyFileSync(path.join(ex, f), path.join(ws, f));
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
    await page.evaluate(() => window.__E.viewer.setView('top'));
    await wait(1500);
    await page.screenshot({ path: path.join(shots, 'visual_1_planta.png') });
    await page.evaluate(() => window.__E.viewer.setView('front')); await wait(1200);
    await page.screenshot({ path: path.join(shots, 'visual_1b_frontal.png') });
    await page.evaluate(() => window.__E.viewer.setView('side')); await wait(1200);
    await page.screenshot({ path: path.join(shots, 'visual_1c_lateral.png') });
    await page.evaluate(() => window.__E.viewer.setView('iso')); await wait(1200);
  });
  await step('alineacion', async () => {
    await page.evaluate(() => window.__E.viewer.setView('top')); await wait(800);
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; n.members[0].az = 10; E.changed({ geometry: true }); });
    await wait(2500);
    await zoomTo(9, 0, 0, 5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_miembro.png') });
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; const o = n.operations.find((x) => x.member === n.members[0].name && x.kind.startsWith('Placa extrema')); o.align_to = n.main_name; E.changed({ geometry: true }); });
    await wait(2500);
    await zoomTo(9, 0, 0, 5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_columna.png') });
    await page.evaluate(() => window.__E.viewer.setView('iso')); await wait(800);
    await zoomTo(10, 0, 0, 2.5); await wait(800);
    await page.screenshot({ path: path.join(shots, 'visual_2_alineada_iso.png') });
    await home();
  });
  await step('cubo', async () => {
    await open('CN-01');
    await wait(500);
    await page.screenshot({ path: path.join(shots, 'cubo_1_iso.png'), clip: { x: 1010, y: 40, width: 190, height: 150 } }).catch(() => {});
    const box = await page.locator('.viewcube').boundingBox();
    const clickAt = async (fx, fy) => { await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy); await wait(900); };
    await clickAt(0.5, 0.18);                                   // cara superior
    console.log('vista tras clic arriba:', await page.evaluate(() => window.__E.viewer.view));
    await page.screenshot({ path: path.join(shots, 'cubo_2_superior.png') });
    await page.evaluate(() => window.__E.viewer.setView('iso')); await wait(600);
    await clickAt(0.35, 0.62);                                  // cara frontal (hacia -Y)
    console.log('vista tras clic frontal:', await page.evaluate(() => window.__E.viewer.view));
    await page.evaluate(() => window.__E.viewer.setViewDir([1, -1, 1])); await wait(800);
    console.log('esquina:', await page.evaluate(() => window.__E.viewer.view));
    await page.screenshot({ path: path.join(shots, 'cubo_3_esquina.png') });
    await home();
  });
  await step('raton', async () => {
    await open('CN-01');
    const st = () => page.evaluate(() => { const v = window.__E.viewer; return { t: v.controls.target.toArray().map((x) => +x.toFixed(2)), q: v.camera.quaternion.toArray().map((x) => +x.toFixed(3)), p: v.camera.position.length() }; });
    const a = await st();
    await page.mouse.move(700, 700); await page.mouse.down(); await page.mouse.move(760, 720, { steps: 6 }); await page.mouse.up(); await wait(400);
    const b = await st();
    console.log('izquierdo mueve:', JSON.stringify(a.t) + ' -> ' + JSON.stringify(b.t), 'giro igual:', JSON.stringify(a.q) === JSON.stringify(b.q));
    await page.mouse.move(700, 700); await page.mouse.down({ button: 'middle' }); await page.mouse.move(760, 690, { steps: 6 }); await page.mouse.up({ button: 'middle' }); await wait(400);
    const c = await st();
    console.log('rueda apretada gira:', JSON.stringify(b.q) !== JSON.stringify(c.q));
    await page.mouse.wheel(0, -400); await wait(400);
    const d = await st();
    console.log('rueda hace zoom:', c.p.toFixed(1) + ' -> ' + d.p.toFixed(1));
    await page.evaluate(() => window.__E.viewer.setView('iso')); await wait(800);
    const pt = await page.evaluate(() => { const v = window.__E.viewer; const V = v.camera.position.constructor; const q = new V(0, 0, 40).project(v.camera); const r = v.renderer.domElement.getBoundingClientRect(); return { x: r.left + (q.x * 0.5 + 0.5) * r.width, y: r.top + (-q.y * 0.5 + 0.5) * r.height }; });
    await page.mouse.click(pt.x, pt.y, { button: 'right' }); await wait(600);
    await page.screenshot({ path: path.join(shots, 'raton_menu_miembro.png') });
    await page.keyboard.press('Escape'); await wait(200);
    const pt2 = await page.evaluate(() => { const v = window.__E.viewer; const V = v.camera.position.constructor; const q = new V(8.5, 0, 0).project(v.camera); const r = v.renderer.domElement.getBoundingClientRect(); return { x: r.left + (q.x * 0.5 + 0.5) * r.width, y: r.top + (-q.y * 0.5 + 0.5) * r.height }; });
    await page.evaluate(() => window.__E.contextMenu('Placa extrema V1', { owner: 'V1', name: 'Placa extrema V1' }, { clientX: 760, clientY: 330 })); await wait(600);
    await page.screenshot({ path: path.join(shots, 'raton_menu_operacion.png') });
    await page.keyboard.press('Escape'); await wait(200);
    await page.mouse.click(900, 200, { button: 'right' }); await wait(600);
    await page.screenshot({ path: path.join(shots, 'raton_menu_vacio.png') });
    await page.keyboard.press('Escape');
    await home();
  });
  await step('recorte', async () => {
    await open('CN-06');
    await zoomTo(8, 0, 16, 3.2); await wait(900);
    await page.screenshot({ path: path.join(shots, 'recorte_1.png') });
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; n.members[0].gap = 4; E.changed({ geometry: true }); });
    await wait(2500); await zoomTo(8, 0, 16, 3.2); await wait(900);
    await page.screenshot({ path: path.join(shots, 'recorte_2_desplazada.png') });
    await home();
  });
  await step('placa_soldada', async () => {
    await open('CN-02');
    await page.evaluate(() => { const E = window.__E; const n = E.conn().node; const o = n.operations.find((x) => x.member === 'S2' && x.kind.startsWith('Placa simple')); o.beam_conn = 'Soldada'; E.changed({ geometry: true }); });
    await wait(3000);
    await zoomTo(0, -3, 3, 3.2); await wait(900);
    await page.screenshot({ path: path.join(shots, 'placa_soldada_viga.png') });
    await home();
  });
  await step('alinear', async () => {
    await open('CN-01');
    await page.evaluate(() => { window.__E.createOperation('Plano de trabajo'); });
    await page.waitForSelector('.pfoot >> text=Agregar', { timeout: 20000 });
    await page.evaluate(() => { const o = window.__E.conn().node.operations.slice(-1)[0]; o.wp_x = 35; o.wp_el = 0; o.wp_az = 0; window.__E.changed({ geometry: true }); });
    await wait(1500);
    await page.screenshot({ path: path.join(shots, 'alinear_1_plano.png') });
    await page.click('.pfoot >> text=Agregar'); await wait(800);
    await page.evaluate(() => { window.__E.sel = 'm:V1'; });
    await page.evaluate(() => { window.__E.createOperation('Alinear cara'); });
    await page.waitForSelector('.pfoot >> text=Agregar', { timeout: 20000 });
    await page.evaluate(() => { const o = window.__E.conn().node.operations.slice(-1)[0]; o.parent = 'PT1'; o.ref_face = 'Plano'; window.__E.changed({ geometry: true }); });
    await wait(2500);
    await page.screenshot({ path: path.join(shots, 'alinear_2_operacion.png') });
    await page.click('.pfoot >> text=Agregar'); await wait(800);
    await page.evaluate(() => window.__E.viewer.setView('top')); await wait(1200);
    await page.screenshot({ path: path.join(shots, 'alinear_3_planta.png') });
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
    await page.evaluate(() => window.__E.viewer.setView('front')); await wait(700);
    await page.evaluate(() => { const E = window.__E; E.viewer.setView('side'); });
    await wait(900); await zoomTo(0, -4, 3, 3.2); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4_lateral.png') });
    await page.evaluate(() => window.__E.viewer.setView('iso')); await wait(800);
    await zoomTo(0, -4, 3, 2.6); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4_placa_hasta_alas.png') });
    await page.evaluate(() => window.__E.viewer.setView('top')); await wait(900);
    await zoomTo(0, -6, 0, 3); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4b_placa_hasta_alas_planta.png') });
    await page.evaluate(() => window.__E.viewer.setView('front')); await wait(900);
    await page.screenshot({ path: path.join(shots, 'visual_4c_placa_hasta_alas_frontal.png') });
  });
  console.log(errors.length ? 'Errores: ' + errors.slice(0, 5).join(' | ') : 'sin errores de consola');
  await app.close();
})();
