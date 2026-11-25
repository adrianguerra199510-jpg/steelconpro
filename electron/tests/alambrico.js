// Modo alámbrico del visor: los miembros son su eje (línea), el nudo de análisis es una esfera y se ven las cargas y las resultantes del equilibrio.
// Uso: xvfb-run -a node tests/alambrico.js [carpeta_de_capturas]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-wire-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const ex = path.join(__dirname, '..', '..', 'ejemplos');
  const files = ['CN-02_viga_con_secundarias.scp', 'CN-04_columna_con_placa_base.scp'];
  for (const f of files) fs.copyFileSync(path.join(ex, f), path.join(ws, f));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1300, height: 860 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  for (const f of files) {
    const code = f.split('_')[0];
    await page.waitForSelector('.home', { timeout: 120000 }); await page.click(`text=${code}`); await page.waitForSelector('.editor', { timeout: 30000 });
    for (let i = 0; i < 80; i++) { if (await page.evaluate(() => !!(window.__E && window.__E.viewer && window.__E.viewer.parts.length > 1 && window.__E.nodal))) break; await page.waitForTimeout(500); }
    await page.waitForTimeout(1500);
    const solidAntes = await page.evaluate(() => window.__E.viewer.parts.some((p) => p.objs.some((o) => o.visible)));
    await page.click('[title^="Modo alámbrico"]'); await page.waitForTimeout(1000);
    const r = await page.evaluate(() => {
      const v = window.__E.viewer, w = v.wireData;
      return { solid: v.parts.some((p) => p.objs.some((o) => o.visible)), lines: w ? w.lines.length : 0, meshes: v.wireMeshes.length, node: w && w.node,
        visible: v.wireGroup.visible, loads: v.loadGroup.children.length, labels: v.loadEls.map((l) => l.el.textContent), nodeLabel: v.wireEls.map((l) => l.el.textContent) };
    });
    check(solidAntes && !r.solid, `${code}: las piezas sólidas se ocultan en modo alámbrico`);
    check(r.visible && r.lines >= 2 && r.meshes >= r.lines + 1, `${code}: ${r.lines} ejes (líneas) y la esfera del nudo`);
    check(JSON.stringify(r.node) === '[0,0,0]' && r.nodeLabel.includes('Nudo de análisis'), `${code}: el nudo de análisis está marcado en el origen`);
    check(r.loads > 0 && r.labels.some((t) => /resultante/i.test(t)) && r.labels.some((t) => /reacci/i.test(t)), `${code}: se ven las cargas, la resultante de las cargas y la reacción del equilibrio`);
    await (await page.$('.viewer-wrap')).screenshot({ path: path.join(shots, `alambrico_${code}.png`) });
    // seleccionar un miembro desde su eje
    const name = await page.evaluate(() => { const v = window.__E.viewer; const m = v.wireMeshes.find((x) => x.userData.part.kind === 'wire' && x.userData.part.name !== window.__E.conn().node.main_name); return m && m.userData.part.name; });
    await page.evaluate((n) => window.__E.viewer.onPick && window.__E.viewer.onPick(n, { name: n, kind: 'wire', owner: '' }, {}), name);
    await page.waitForTimeout(400);
    check(await page.evaluate((n) => window.__E.sel === `m:${n}`, name), `${code}: al elegir el eje de «${name}» se selecciona el miembro`);
    await page.click('[title^="Modo alámbrico"]'); await page.waitForTimeout(600);
    check(await page.evaluate(() => window.__E.viewer.parts.some((p) => p.objs.some((o) => o.visible))), `${code}: al apagar el modo vuelven las piezas`);
    await page.click('[title="Volver al inicio"]');
  }
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA ALÁMBRICO: ${fails} FALLAS` : 'PRUEBA ALÁMBRICO: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
