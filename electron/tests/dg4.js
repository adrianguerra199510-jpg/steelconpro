// Placa extrema precalificada (AISC Design Guide 4): abre TP-V39 (8ES, ejemplo 4.4 de la guía), comprueba el formulario de la operación, las
// verificaciones DG4 en el resumen y el análisis del modelo de placas.  Uso: xvfb-run -a node tests/dg4.js [carpeta]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-dg4-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  const f = fs.readdirSync(ex).find((x) => x.startsWith('TP-V39_'));
  fs.copyFileSync(path.join(ex, f), path.join(ws, f));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1500, height: 900 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 }); await page.click('.card :text("TP-V39")'); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1 && window.__E.nodal))) break; await wait(500); }
  await wait(1500);
  const parts = await page.evaluate(() => window.__E.viewer.parts.filter((p) => p.kind !== 'weld').map((p) => p.name));
  check(parts.filter((n) => n.startsWith('Rigidizador V1')).length === 2, `el visor dibuja los 2 rigidizadores de la 8ES (${parts.filter((n) => n.startsWith('Rigidizador')).join(', ')})`);
  await page.screenshot({ path: path.join(shots, 'dg4_modelo.png') });
  await page.dblclick('.tree-item:has-text("Placa extrema extendida")'); await wait(1200);
  const sel = await page.evaluate(() => { const s = [...document.querySelectorAll('select')].find((x) => [...x.options].some((o) => o.value === '8ES')); return s ? s.value : null; });
  check(sel === '8ES', `el formulario de la placa extrema muestra «Precalificada (AISC Design Guide 4)» = ${sel}`);
  await page.screenshot({ path: path.join(shots, 'dg4_formulario.png') });
  await page.click('button:has-text("Aceptar")'); await wait(1200);
  await page.click('.calc-big'); await wait(1500);
  for (let i = 0; i < 120; i++) { if (await page.evaluate(() => !!window.__E.femDone && !window.__E.femRunning)) break; await wait(5000); }
  await wait(3000);
  const res = await page.evaluate(() => (window.__E.res ? window.__E.res.checks.map((c) => c.title) : []));
  check(res.some((t) => /líneas de fluencia — tp,req/.test(t)) && res.some((t) => /Pernos sin palanca/.test(t)), 'las verificaciones DG4 están en los resultados');
  check(await page.evaluate(() => !!window.__E.femDone), 'el análisis del modelo de placas termina con la 8ES y sus rigidizadores');
  await page.screenshot({ path: path.join(shots, 'dg4_analisis.png') });
  await page.click('.tab[data-id="res"]').catch(() => {}); await wait(800);
  await page.evaluate(() => { for (const g of document.querySelectorAll('.res-group.cat')) g.classList.remove('closed'); });
  await wait(500);
  await page.screenshot({ path: path.join(shots, 'dg4_resumen.png') });
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA DG4: ${fails} FALLAS` : 'PRUEBA DG4: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
