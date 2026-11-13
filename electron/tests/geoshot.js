// Captura de la pestaña «Geometría» (revisión automática).  Uso: xvfb-run -a node tests/geoshot.js <carpeta> [ejemplo]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-g-'));
  const ex = process.argv[3] || 'CN-01_columna_con_vigas.scp';
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(path.join(__dirname, '..', '..', 'ejemplos', ex), path.join(ws, 'GEO.scp'));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1500, height: 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click('text=GEO'); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.geo))) break; await wait(500); }
  await page.click('.tab[data-id="geo"]'); await wait(800);
  const info = await page.evaluate(() => ({ errors: window.__E.geo.errors, warnings: window.__E.geo.warnings, rows: document.querySelectorAll('.tabpanel .warn-row').length }));
  console.log('geometria', JSON.stringify(info));
  await page.screenshot({ path: path.join(shots, 'geometria_0.png') });
  const row = await page.$('.tabpanel .warn-row');
  if (row) { await row.click(); await wait(800); await page.screenshot({ path: path.join(shots, 'geometria_1.png') }); }
  if (errors.length) console.log('ERRORES DE PAGINA', errors.join(' | '));
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
