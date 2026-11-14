// Flujo del FEM en el visor: Ejecutar análisis -> botones de malla y cortes -> resultados y deformada.  Uso: xvfb-run -a node tests/femshot.js <carpeta> [archivo.scp] [texto]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2]; const file = process.argv[3] || path.join(__dirname, '..', '..', 'ejemplos', 'CN-02_viga_con_secundarias.scp'); const label = process.argv[4] || 'CN-02';
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(file, path.join(ws, path.basename(file)));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1500, height: 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  const vis = (sel) => page.evaluate((s) => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none'; }, sel);
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click(`text=${label}`); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1))) break; await wait(500); }
  await wait(1500);
  console.log('grupo FEM visible antes de analizar:', await page.evaluate(() => window.__E.ui.femGroup.style.display !== 'none'));
  await page.screenshot({ path: path.join(shots, 'fem_0_inicio.png') });
  await page.click('.tab[data-id="fem"]'); await wait(500);
  await page.click('text=Ejecutar análisis'); await wait(4000);
  console.log('grupo FEM visible tras pulsar:', await page.evaluate(() => window.__E.ui.femGroup.style.display !== 'none'), '· resultados visibles:', await page.evaluate(() => window.__E.ui.femRes.style.display !== 'none'));
  await page.screenshot({ path: path.join(shots, 'fem_1_cortes.png') });
  await page.click('[title^="Ver la malla"]'); await wait(25000);
  await page.screenshot({ path: path.join(shots, 'fem_2_malla.png') });
  await page.click('[title="Volver al modelo"]'); await wait(1500);
  for (let i = 0; i < 120; i++) { if (await page.evaluate(() => window.__E.femDone)) break; await wait(5000); }
  console.log('análisis terminado:', await page.evaluate(() => !!window.__E.femDone));
  await wait(4000);
  await page.screenshot({ path: path.join(shots, 'fem_3_resultados.png') });
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
