// «Calcular» verifica y analiza el modelo de placas con CalculiX; al terminar el visor pasa a la malla con los esfuerzos sobre la deformada,
// y la barra del visor deja elegir el campo, el caso, la pieza y la escala.  Uso: xvfb-run -a node tests/analisis.js [carpeta] [archivo.scp] [código]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-an-'));
  const file = process.argv[3] || path.join(__dirname, '..', '..', 'ejemplos', 'CN-02_viga_con_secundarias.scp');
  const code = process.argv[4] || path.basename(file).split('_')[0];
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(file, path.join(ws, path.basename(file)));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1500, height: 900 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 }); await page.click(`text=${code}`); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1 && window.__E.nodal))) break; await wait(500); }
  await wait(1200);
  // punto de aplicación de la carga (análisis): está en la ficha del miembro y no mueve las flechas del visor
  const arrows0 = await page.evaluate(() => window.__E.viewer.loadEls.map((l) => l.p.toArray().map((x) => +x.toFixed(3)).join(',')).sort().join(';'));
  await page.dblclick('.tree-item:has-text("S2")'); await wait(900);
  check(await page.isVisible('text=Punto de aplicación de la carga (análisis)'), `${code}: la ficha del miembro tiene el punto de aplicación de la carga`);
  const sel = page.locator('select').filter({ has: page.locator('option', { hasText: 'En los pernos' }) }).first();
  await sel.selectOption('En el extremo del elemento'); await wait(800);
  await page.screenshot({ path: path.join(shots, `analisis_${code}_punto_carga.png`) });
  await sel.selectOption('Automático'); await wait(500);
  await page.click('button:has-text("Cerrar")'); await wait(800);
  const arrows1 = await page.evaluate(() => window.__E.viewer.loadEls.map((l) => l.p.toArray().map((x) => +x.toFixed(3)).join(',')).sort().join(';'));
  check(arrows0 === arrows1, `${code}: las flechas del visor no cambian con el punto de aplicación`);
  await page.click('.calc-big');
  await wait(1500);
  check(await page.evaluate(() => !!window.__E.femRunning || !!window.__E.femDone), `${code}: «Calcular» lanza el análisis del modelo de placas`);
  for (let i = 0; i < 180; i++) { if (await page.evaluate(() => !!window.__E.femDone && !window.__E.femRunning)) break; await wait(5000); }
  await wait(3000);
  const r = await page.evaluate(() => { const E = window.__E; const fp = E.viewer.parts.find((p) => p.kind === 'fem'); return { done: !!E.femDone, view: !!E.femView, fem: !!fp, res: E.ui.femRes.style.display !== 'none',
    scale: E.ui.femScale.value, field: E.ui.femField.value, fields: [...E.ui.femField.options].map((o) => o.value), bar: E.ui.fembar.textContent, status: document.querySelector('.statusbar') ? document.querySelector('.statusbar').textContent : '' }; });
  check(r.done && r.view && r.fem, `${code}: al terminar el visor muestra la malla con resultados`);
  check(r.res && r.scale === '-1' && r.field === 'vm', `${code}: von Mises sobre la deformada automática (${r.field}, escala ${r.scale})`);
  check(['vm', 'peeq', 'u'].every((f) => r.fields.includes(f)), `${code}: campos von Mises, deformación plástica y desplazamiento`);
  check(/Mises/.test(r.bar), `${code}: barra de colores del campo`);
  await page.screenshot({ path: path.join(shots, `analisis_${code}_vm.png`) });
  await page.selectOption('select[title="Resultado"]', 'peeq'); await wait(2500);
  check(await page.evaluate(() => /plástica/.test(window.__E.ui.fembar.textContent)), `${code}: campo de deformación plástica`);
  await page.screenshot({ path: path.join(shots, `analisis_${code}_peeq.png`) });
  await page.selectOption('select[title="Resultado"]', 'u'); await wait(2500);
  await page.screenshot({ path: path.join(shots, `analisis_${code}_u.png`) });
  const res = await page.evaluate(() => (window.__E.res && window.__E.res.checks) ? window.__E.res.checks.filter((c) => c.cat).map((c) => c.cat) : []);
  check(['Miembros', 'Placas', 'Pernos'].every((c) => res.includes(c)), `${code}: las verificaciones del análisis tienen categoría (${[...new Set(res)].join(', ')})`);
  // resumen estándar por componentes en la pestaña Resultados
  await page.click('.tab[data-id="res"]').catch(() => {}); await wait(800);
  const sum = await page.evaluate(() => ({ cats: [...document.querySelectorAll('.res-group.cat')].map((g) => g.dataset.cat), on: (document.querySelector('.seg-btn.on') || {}).textContent || '' }));
  check(sum.on.includes('Resumen') && ['Miembros', 'Placas', 'Pernos', 'Soldaduras'].every((c) => sum.cats.includes(c)), `${code}: el resumen por componentes es la vista estándar (${sum.cats.join(', ')})`);
  await page.evaluate(() => { const g = document.querySelector('.res-group.cat[data-cat="Pernos"]'); if (g) g.classList.remove('closed'); });
  await wait(400);
  await page.screenshot({ path: path.join(shots, `analisis_${code}_resumen.png`) });
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA ANÁLISIS: ${fails} FALLAS` : 'PRUEBA ANÁLISIS: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
