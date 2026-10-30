// Capturas de pantalla de los ejemplos y de la pestaña FEM (malla).  Uso:  xvfb-run -a node tests/shots.js <carpeta_de_capturas>
const { _electron: electron } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-shots-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  for (const f of ['CN-01_columna_con_vigas.scp', 'CN-04_columna_con_placa_base.scp', 'CN-05_viga_con_placas_trapezoidales.scp', 'CN-06_diagonal_con_recorte_y_angulo.scp', 'CN-07_placa_base_con_diagonal.scp']) fs.copyFileSync(path.join(ex, f), path.join(ws, f));
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
    await wait(2500);
  };
  const home = async () => { await page.click('[title="Volver al inicio"]'); await page.waitForSelector('.home', { timeout: 20000 }); };
  const step = async (name, fn) => { try { await fn(); console.log('OK   ' + name); } catch (e) { console.log('FALLA ' + name + ': ' + e.message.split('\n')[0]); try { await page.screenshot({ path: path.join(shots, 'error_' + name + '.png') }); } catch (e2) { /* nada */ } } };
  await step('CN-05', async () => { await open('CN-05'); await page.screenshot({ path: path.join(shots, 'ejemplo_CN-05_placas.png') }); await home(); });
  await step('CN-06', async () => { await open('CN-06'); await page.screenshot({ path: path.join(shots, 'ejemplo_CN-06_recorte_angulo.png') }); await home(); });
  await step('CN-07', async () => { await open('CN-07'); await page.screenshot({ path: path.join(shots, 'ejemplo_CN-07_base_diagonal.png') }); await home(); });
  await step('convertir', async () => {
    await open('CN-01');
    await page.dblclick('.tree-item:has-text("Placa extrema")');
    await page.waitForSelector('.pedit', { timeout: 15000 });
    await wait(1200);
    await page.screenshot({ path: path.join(shots, 'editable_1_placa_extrema.png') });
    await page.click('text=Convertir en piezas editables');
    await wait(3500);
    await page.screenshot({ path: path.join(shots, 'editable_2_convertida.png') });
    await page.dblclick('.tree-item:has-text("Pernos en P1")');
    await page.waitForSelector('.pedit', { timeout: 15000 });
    await wait(1500);
    await page.screenshot({ path: path.join(shots, 'editable_3_pernos.png') });
    await home();
  });
  await step('fem', async () => {
    await open('CN-04');
    await page.click('.tabbar >> text=FEM');
    await wait(800);
    await page.click('summary:has-text("Configuración del análisis FEM")');
    await wait(600);
    await page.screenshot({ path: path.join(shots, 'fem_1_configuracion.png') });
    await page.click('text=Ver malla en el visor');
    for (let i = 0; i < 120; i++) { if (await page.evaluate(() => /Malla: /.test(document.body.innerText))) break; await wait(1000); }
    await wait(2500);
    await page.screenshot({ path: path.join(shots, 'fem_2_malla.png') });
  });
  await step('fembase', async () => {
    await home(); await open('CN-04');
    await page.click('.tabbar >> text=FEM');
    await wait(800);
    await page.locator('text=Ver malla en el visor').nth(1).click();
    for (let i = 0; i < 90; i++) { if (await page.evaluate(() => /Malla: /.test(document.body.innerText))) break; await wait(1000); }
    await wait(2500);
    await page.screenshot({ path: path.join(shots, 'fem_3_malla_placa_base.png') });
  });
  console.log(errors.length ? 'Errores: ' + errors.slice(0, 5).join(' | ') : 'sin errores de consola');
  await app.close();
})();
