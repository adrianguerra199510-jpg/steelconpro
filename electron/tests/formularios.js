// Revisión de los textos de los formularios de operaciones: abre cada tipo de operación en un ejemplo y detecta (1) elementos que se salen del panel por la
// derecha, (2) etiquetas, botones o textos cortados con puntos suspensivos y (3) botones de un control segmentado con el texto partido en varias líneas.
// Uso: xvfb-run -a node tests/formularios.js [carpeta de capturas]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
const EJ = ['CN-01', 'CN-02', 'CN-03', 'CN-04', 'CN-05', 'CN-06', 'CN-08', 'TP-A02', 'TP-G01', 'TP-G05', 'TP-G06', 'TP-G11', 'TP-G14', 'TP-G22', 'TP-V12', 'TP-V14', 'TP-V39', 'TP-V41', 'TP-V43', 'TP-V44'];
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-form-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  for (const c of [...EJ, 'TP-V45']) { const f = fs.readdirSync(ex).find((x) => x.startsWith(c + '_')); if (f) fs.copyFileSync(path.join(ex, f), path.join(ws, f)); }
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1500, height: 900 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  const wait = (ms) => page.waitForTimeout(ms);
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; }; const seen = new Set(); const problems = [];
  await page.waitForSelector('.home', { timeout: 120000 });
  const scan = () => page.evaluate(() => {
    const panel = document.querySelector('.panel.right');
    if (!panel) return { err: 'sin panel derecho' };
    const pr = panel.getBoundingClientRect(); const out = [];
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && e.offsetParent !== null; };
    for (const e of panel.querySelectorAll('.field, .lbl, .segmented, .segmented button, .input, select, h4, .hint-text, label')) {
      if (!vis(e)) continue;
      const r = e.getBoundingClientRect();
      if (r.right > pr.right + 1.5) out.push(`se sale del panel por la derecha (${Math.round(r.right - pr.right)} px): ${(e.className || e.tagName)} «${(e.textContent || '').trim().slice(0, 50)}»`);
    }
    for (const e of panel.querySelectorAll('.lbl, .segmented button span, .segmented button, h4, label, option')) {
      if (!vis(e)) continue;
      const cs = getComputedStyle(e);
      if (e.scrollWidth > e.clientWidth + 1 && (cs.overflow !== 'visible' || cs.textOverflow === 'ellipsis')) out.push(`texto cortado: «${(e.textContent || '').trim().slice(0, 50)}»`);
    }
    for (const b of panel.querySelectorAll('.segmented button')) {
      if (!vis(b)) continue;
      const sp = b.querySelector('span'); if (!sp) continue;
      const lh = parseFloat(getComputedStyle(sp).lineHeight) || 16;
      if (sp.getBoundingClientRect().height > lh * 1.6) out.push(`texto partido en varias líneas: «${sp.textContent.trim()}»`);
    }
    return { out };
  });
  for (const code of EJ) {
    await page.waitForSelector('.home'); await page.click(`.card :text("${code}")`); await page.waitForSelector('.editor', { timeout: 30000 });
    for (let i = 0; i < 60; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1))) break; await wait(400); }
    await wait(800);
    const n = await page.evaluate(() => window.__E.conn().node.operations.length);
    for (let i = 0; i < n; i++) {
      const kind = await page.evaluate((i) => window.__E.conn().node.operations[i].kind, i);
      if (seen.has(kind)) continue;
      seen.add(kind);
      await page.evaluate((i) => { const rows = [...document.querySelectorAll('.tree-item')].filter((r) => /^\d+\./.test(r.querySelector('.name')?.textContent || '')); rows[i].querySelector('.acts button[title="Editar"]').click(); }, i);
      await wait(1500);
      // recorre el formulario por tramos para que se dibuje todo
      const sc = await scan();
      const bad = (sc.out || []).concat(sc.err ? [sc.err] : []);
      console.log((bad.length ? 'FALLA ' : 'OK    ') + `${code} · ${kind}` + (bad.length ? '\n        ' + [...new Set(bad)].slice(0, 6).join('\n        ') : ''));
      if (bad.length) { fails++; problems.push(kind); }
      await page.screenshot({ path: path.join(shots, `form_${code}_${i + 1}.png`) });
      await page.click('.panel.right button:has-text("Cancelar")').catch(() => {}); await wait(500);
    }
    await page.click('[title="Volver al inicio"]'); await page.waitForSelector('.home', { timeout: 20000 }); await wait(500);
  }
  // sección del Section Designer: la placa se apoya en la cara de un componente
  await page.click('.card :text("TP-V45")'); await page.waitForSelector('.editor', { timeout: 30000 });
  for (let i = 0; i < 60; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 3))) break; await wait(400); }
  await wait(1200);
  await page.screenshot({ path: path.join(shots, 'seccion_personalizada_modelo.png') });
  await page.evaluate(() => { const rows = [...document.querySelectorAll('.tree-item')].filter((r) => /^\d+\./.test(r.querySelector('.name')?.textContent || '')); rows[2].querySelector('.acts button[title="Editar"]').click(); });
  await wait(1500);
  const opts = await page.evaluate(() => [...document.querySelectorAll('.panel.right select')].map((s) => [...s.options].map((o) => o.value)));
  const faces = opts.find((o) => o.includes('Comp. 6 (Rect.) — Cara +X'));
  check(!!faces && faces.length === 30 && faces.includes('Comp. 5 (Rect.) — Cara −X') && faces.includes('Cara +X'), `el desplegable «En la cara» ofrece las caras de los 6 componentes y la envolvente (${faces ? faces.length : 0} caras)`);
  const sel = await page.evaluate(() => { const s = [...document.querySelectorAll('.panel.right select')].find((x) => [...x.options].some((o) => o.value.startsWith('Comp. 5'))); return s ? s.value : null; });
  check(sel === 'Comp. 5 (Rect.) — Cara −X', `la placa PA-a está en la cara exterior del alma izquierda (${sel})`);
  const sc2 = await scan(); const bad2 = (sc2.out || []);
  check(!bad2.length, 'la lista larga de caras no rompe el formulario' + (bad2.length ? ': ' + bad2[0] : ''));
  await page.screenshot({ path: path.join(shots, 'seccion_personalizada_formulario.png') });
  await page.click('.panel.right button:has-text("Cancelar")').catch(() => {}); await wait(500);
  console.log(`tipos de operación revisados: ${seen.size}`);
  if (errs.length) { console.log('errores JS: ' + errs[0]); fails++; }
  await app.close();
  console.log(fails ? `PRUEBA FORMULARIOS: ${fails} FALLAS` : 'PRUEBA FORMULARIOS: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
