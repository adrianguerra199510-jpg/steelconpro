// Plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)»: no está en «Nueva conexión», está como proyecto en Favoritos, abre la 8ES
// del ejemplo 4.4 y las verificaciones del nudo (AISC 341-22) llegan al resumen.  Uso: xvfb-run -a node tests/plantilla_smf.js [carpeta]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-smf-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1500, height: 900 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  const wait = (ms) => page.waitForTimeout(ms);
  await page.waitForSelector('.home', { timeout: 120000 }); await wait(1500);
  // no está en el diálogo «Nueva conexión»
  await page.click('button:has-text("Nuevo proyecto")'); await wait(500);
  await page.fill('.modal input', 'Prueba');
  await page.click('.modal button:has-text("Crear proyecto")');
  await page.waitForSelector('.tpl-card', { timeout: 15000 });
  check(await page.locator('.tpl-card:has-text("Pórtico especial")').count() === 0, 'la plantilla no está en el diálogo «Nueva conexión»');
  await page.click('.modal button:has-text("Cancelar")'); await wait(500);
  // sí está en Favoritos
  await page.click('.side :text("Favoritos")'); await wait(1200);
  const card = page.locator('.card:has-text("Pórtico especial")');
  check(await card.count() === 1, 'la plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)» está en Favoritos');
  await page.screenshot({ path: path.join(shots, 'smf_favoritos.png') });
  await card.click();
  await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 4))) break; await wait(500); }
  await wait(2500);
  const parts = await page.evaluate(() => window.__E.viewer.parts.filter((p) => p.kind !== 'weld').map((p) => p.name));
  check(parts.includes('V1') && parts.filter((n) => n.startsWith('Rigidizador')).length === 2, `el visor dibuja la viga con su placa 8ES y rigidizadores (${parts.length} piezas)`);
  await page.screenshot({ path: path.join(shots, 'smf_plantilla_modelo.png') });
  await page.click('.calc-big'); await wait(1000);                 // «Calcular» verifica enseguida (el análisis de placas sigue aparte)
  for (let i = 0; i < 60; i++) { if (await page.evaluate(() => !!(window.__E.res && window.__E.res.checks.some((c) => /Zona del panel/.test(c.title))))) break; await wait(500); }
  const res = await page.evaluate(() => (window.__E.res ? window.__E.res.checks.map((c) => c.title) : []));
  check(res.some((t) => /Columna fuerte–viga débil/.test(t)) && res.some((t) => /Zona del panel/.test(t)) && res.some((t) => /Placas de continuidad — espesor/.test(t)),
    'las verificaciones del nudo (columna fuerte–viga débil, zona del panel, placas de continuidad) están en los resultados');
  await page.click('.tab[data-id="res"]').catch(() => {}); await wait(800);
  await page.evaluate(() => { for (const g of document.querySelectorAll('.res-group')) g.classList.remove('closed'); });
  await wait(500);
  await page.screenshot({ path: path.join(shots, 'smf_plantilla_resumen.png') });
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA PLANTILLA SMF: ${fails} FALLAS` : 'PRUEBA PLANTILLA SMF: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
