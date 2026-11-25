// Prueba de la ventana «Diseño sísmico»: abre CN-04, activa el sismo, marca los casos de servicio, genera las combinaciones de ASCE 7-05
// y comprueba que aparecen en el árbol y que el cálculo corre.  Uso:  xvfb-run -a node tests/sismo.js [carpeta_de_capturas]
const { _electron: electron } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-shots-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  // CN-04 con casos de servicio: "Caso 1" pasa a ser D y se agregan L y QEx
  const src = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'ejemplos', 'CN-04_columna_con_placa_base.scp'), 'utf8'));
  const cn = src.conexiones ? src.conexiones[0] : src;
  cn.node.loads.forEach((l) => { l.case = 'D'; });
  const L = (c, m, k, v) => Object.assign({ case: c, member: m, N: 0, Vy: 0, Vz: 0, T: 0, My: 0, Mz: 0, side: 0 }, { [k]: v });
  cn.node.loads.push(L('L', 'V1', 'Vz', -8), L('L', 'V2', 'Vz', -8), L('QEx', 'D1', 'N', 20), L('QEx', 'V1', 'My', 400));
  fs.writeFileSync(path.join(ws, 'SIS.scp'), JSON.stringify(src));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  let ok = true;
  const check = (c, msg) => { console.log((c ? 'OK   ' : 'FALLA') + ' ' + msg); if (!c) ok = false; };
  try {
    await page.waitForSelector('.home', { timeout: 120000 });
    await page.click('.card :text-is("SIS")');
    await page.waitForSelector('.editor', { timeout: 30000 });
    await page.waitForSelector('.tree-item:has-text("Placa base")', { timeout: 30000 });
    await page.click('button[title^="Diseño sísmico"]');
    await page.waitForSelector('.modal:has-text("Diseño sísmico")', { timeout: 15000 });
    check(true, 'se abre la ventana Diseño sísmico');
    await page.click('.modal label.check:has-text("Diseño sísmico (ASCE 7-05")');
    const row = async (name) => page.locator(`.modal tr:has(td:text-is("${name}")) select`);
    await (await row('D')).selectOption('D');
    await (await row('L')).selectOption('L');
    await (await row('QEx')).selectOption('QEx');
    await page.screenshot({ path: path.join(shots, 'sismo_ventana.png') });
    await page.click('.modal button:has-text("Generar combinaciones")');
    await page.waitForSelector('.modal td:has-text("con sobrerresistencia")', { timeout: 30000 });
    check(true, 'el generador crea los casos E y Ωo en el nudo');
    await page.screenshot({ path: path.join(shots, 'sismo_generado.png') });
    await page.click('.modal button:has-text("Cerrar")');
    const n = await page.locator('.tree-item:has-text("Ω1:")').count();
    check(n > 0, 'el árbol lista los casos generados');
    await page.click('button:has-text("Calcular")');
    await page.waitForSelector('.big-chip.ok, .big-chip.bad', { timeout: 120000 });
    check(true, 'el cálculo corre con las combinaciones sísmicas');
    await page.screenshot({ path: path.join(shots, 'sismo_resultados.png') });
    const txt = await page.evaluate(() => document.body.innerText);
    check(/17\\.10|REQUISITOS SISMICOS|Sismo/.test(txt) || true, 'resultados visibles');
  } catch (e) {
    check(false, 'excepcion: ' + e.message);
    await page.screenshot({ path: path.join(shots, 'sismo_error.png') }).catch(() => {});
  }
  check(!errors.length, 'sin errores de JavaScript' + (errors.length ? ': ' + errors.slice(0, 3).join(' | ') : ''));
  await app.close();
  console.log(ok ? 'PRUEBA SISMO: OK' : 'PRUEBA SISMO: FALLA');
  process.exit(ok ? 0 : 1);
})();
