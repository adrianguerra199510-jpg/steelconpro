// Plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)» en Nuevo proyecto: la tarjeta aparece en el diálogo, arma el nudo con
// vigas a los dos lados y las verificaciones del nudo (AISC 341-22) llegan al resumen.  Uso: xvfb-run -a node tests/plantilla_smf.js [carpeta]
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
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click('button:has-text("Nuevo proyecto")'); await wait(500);
  await page.fill('.modal input', 'Pórtico especial N1');
  await page.click('.modal button:has-text("Crear proyecto")');
  await page.waitForSelector('.tpl-card', { timeout: 15000 });
  const card = page.locator('.tpl-card:has-text("Pórtico especial")');
  check(await card.count() === 1, 'la plantilla fija «Pórtico especial: placa extrema precalificada (AISC DG4)» está en el diálogo');
  await card.click(); await wait(500);
  const opts = await page.evaluate(() => [...document.querySelectorAll('.modal select')].map((s) => [...s.options].map((o) => o.value).join(',')));
  check(opts.some((o) => o === '4E,4ES,8ES'), `el formulario ofrece 4E, 4ES y 8ES (${opts.join(' | ')})`);
  const two = page.locator('.modal .field:has-text("Vigas a los dos lados") input[type=checkbox]');
  await two.check();
  await page.screenshot({ path: path.join(shots, 'smf_plantilla_dialogo.png') });
  await page.click('.modal button:has-text("Crear")');
  await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 4 && window.__E.res))) break; await wait(500); }
  await wait(2500);
  const parts = await page.evaluate(() => window.__E.viewer.parts.filter((p) => p.kind !== 'weld').map((p) => p.name));
  check(parts.includes('V1') && parts.includes('V2') && parts.filter((n) => n.startsWith('Rigidizador')).length === 4, `el visor dibuja las dos vigas con sus placas 8ES y rigidizadores (${parts.length} piezas)`);
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
