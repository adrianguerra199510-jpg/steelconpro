// Captura de un proyecto .scp cualquiera.  Uso: xvfb-run -a node tests/placashot.js <carpeta> <archivo.scp> <texto a pulsar> [vista]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const [shots, file, label, view] = process.argv.slice(2);
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(file, path.join(ws, path.basename(file)));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1400, height: 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click(`text=${label}`); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1))) break; await wait(500); }
  await page.evaluate(() => { const E = window.__E; E.showLoadsOn = false; E.showReactionsOn = false; E.viewer.setLoadsVisible(false); });
  await wait(1500);
  await page.screenshot({ path: path.join(shots, 'placa_0.png') });
  if (view) { await page.evaluate((v) => window.__E.viewer.setView(v), view); await wait(1200); await page.screenshot({ path: path.join(shots, 'placa_1.png') }); }
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
