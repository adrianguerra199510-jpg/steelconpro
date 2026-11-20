// Una captura del visor por cada proyecto .scp dado (para revisar los ejemplos de un vistazo).
// Uso:  xvfb-run -a node tests/tablero.js <carpeta_salida> <a.scp> <b.scp> ...     (lo usa tools/capturas_ejemplos.py)
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const [out, ...files] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  for (const f of files) fs.copyFileSync(f, path.join(ws, path.basename(f)));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--user-data-dir=' + fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ud-')), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  await page.setViewportSize({ width: 1400, height: 900 });
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 });
  for (const f of files) {
    const stem = path.basename(f, '.scp');
    try {
      await page.click(`text=${stem}`, { timeout: 20000 });
      await page.waitForSelector('.editor', { timeout: 30000 });
      for (let i = 0; i < 60; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 0))) break; await wait(500); }
      await page.evaluate(() => { const E = window.__E; E.showLoadsOn = false; E.showReactionsOn = false; E.viewer.setLoadsVisible(false); E.viewer.setView('iso'); });
      await wait(1500);
      const box = await (await page.$('.viewer')).boundingBox();
      await page.screenshot({ path: path.join(out, stem + '.png'), clip: box });
      console.log('OK   ' + stem);
      await page.click('[title="Volver al inicio"]');
      await page.waitForSelector('.home', { timeout: 30000 });
      await wait(500);
    } catch (e) {
      console.log('FALLA ' + stem + ': ' + e.message.split('\n')[0]);
      try { await page.screenshot({ path: path.join(out, stem + '_error.png') }); await page.click('[title="Volver al inicio"]', { timeout: 3000 }); await page.waitForSelector('.home', { timeout: 10000 }); } catch (e2) { /* sigue */ }
    }
  }
  await app.close();
})().catch((e) => { console.error(e); process.exit(1); });
