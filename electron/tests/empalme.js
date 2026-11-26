// Empalme de viga con cubreplacas: abre TP-V41 (atornillado), comprueba el dibujo, el formulario (alas y alma atornilladas o soldadas, campos que se
// muestran según la unión), las verificaciones en el resumen y el análisis del modelo de placas.  Uso: xvfb-run -a node tests/empalme.js [carpeta]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-emp-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  const f = fs.readdirSync(ex).find((x) => x.startsWith('TP-V41_'));
  fs.copyFileSync(path.join(ex, f), path.join(ws, f));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1500, height: 900 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 }); await page.click('.card :text("TP-V41")'); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1 && window.__E.nodal))) break; await wait(500); }
  await wait(1500);
  const parts = await page.evaluate(() => window.__E.viewer.parts.filter((p) => p.kind !== 'weld').map((p) => p.name));
  check(parts.filter((n) => n.startsWith('Cubreplaca')).length === 2 && parts.filter((n) => n.startsWith('Placa alma')).length === 2, `el visor dibuja las 2 cubreplacas y las 2 placas del alma (${parts.join(', ')})`);
  await page.screenshot({ path: path.join(shots, 'empalme_atornillado.png') });
  await page.dblclick('.tree-item:has-text("Empalme de viga")'); await wait(1200);
  const vis = () => page.evaluate(() => [...document.querySelectorAll('.field')].filter((f) => !f.classList.contains('hidden') && f.offsetParent).map((f) => f.textContent));
  let v = await vis();
  check(v.some((t) => /Pernos por línea en cada ala/.test(t)) && !v.some((t) => /Largo de los filetes de las alas/.test(t)), 'atornillado: el formulario muestra los pernos de las alas y no los filetes');
  await page.screenshot({ path: path.join(shots, 'empalme_formulario.png') });
  const sel = page.locator('.field:has-text("Cubreplacas de las alas") select');
  await sel.selectOption('Soldada'); await wait(1500);
  v = await vis();
  check(v.some((t) => /Largo de los filetes de las alas/.test(t)) && !v.some((t) => /Pernos por línea en cada ala/.test(t)), 'al elegir «Soldada» aparecen los filetes y se ocultan los pernos de las alas');
  const nw = await page.evaluate(() => window.__E.viewer.parts.filter((p) => p.kind === 'weld').length);
  check(nw > 0, `el visor dibuja los filetes de las cubreplacas (${nw})`);
  await page.screenshot({ path: path.join(shots, 'empalme_soldado.png') });
  await page.click('button:has-text("Cancelar")'); await wait(1200);
  await page.click('.calc-big'); await wait(1500);
  for (let i = 0; i < 120; i++) { if (await page.evaluate(() => !!window.__E.femDone && !window.__E.femRunning)) break; await wait(5000); }
  await wait(3000);
  const res = await page.evaluate(() => (window.__E.res ? window.__E.res.checks.map((c) => c.title) : []));
  check(res.some((t) => /Alas — cortante de los pernos/.test(t)) && res.some((t) => /F13|agujeros del ala/.test(t)), 'las verificaciones del empalme están en los resultados');
  check(await page.evaluate(() => !!window.__E.femDone), 'el análisis del modelo de placas termina con el empalme');
  await page.screenshot({ path: path.join(shots, 'empalme_analisis.png') });
  await page.click('.tab[data-id="res"]').catch(() => {}); await wait(800);
  await page.evaluate(() => { for (const g of document.querySelectorAll('.res-group.cat')) g.classList.remove('closed'); });
  await wait(500);
  await page.screenshot({ path: path.join(shots, 'empalme_resumen.png') });
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA EMPALME: ${fails} FALLAS` : 'PRUEBA EMPALME: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
