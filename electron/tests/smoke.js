// Prueba de humo de la aplicación Electron: arranca la ventana real, abre un proyecto de ejemplo y comprueba que el motor responde y que el visor 3D dibuja.
// Uso:  node tests/smoke.js [carpeta_de_capturas]      (en Linux sin pantalla:  xvfb-run -a node tests/smoke.js)
const { _electron: electron } = require('playwright');
const path = require('path');
const fs = require('fs');
const os = require('os');

(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-shots-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  fs.copyFileSync(path.join(__dirname, '..', '..', 'ejemplos', 'CN-04_columna_con_placa_base.scp'), path.join(ws, 'CN-04.scp'));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'], env: { ...process.env, SCP_WORKSPACE: ws } });
  const page = await app.firstWindow();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  let ok = true;
  const check = (c, msg) => { console.log((c ? 'OK   ' : 'FALLA') + ' ' + msg); if (!c) ok = false; };
  try {
    await page.waitForSelector('.home', { timeout: 120000 });
    check(true, 'la pantalla de inicio carga (motor local activo)');
    await page.waitForSelector('.card, .proj-card, [class*="card"]', { timeout: 20000 }).catch(() => {});
    await page.screenshot({ path: path.join(shots, 'electron_home.png') });
    await page.click('text=CN-04');
    await page.waitForSelector('.editor', { timeout: 30000 });
    await page.waitForSelector('.tree-item:has-text("Placa base")', { timeout: 30000 });
    check(true, 'el editor abre el proyecto y lista las operaciones');
    await page.waitForFunction(() => window.__E && window.__E.viewer && window.__E.viewer.parts.length > 3, null, { timeout: 30000 });
    check(true, 'el visor 3D recibe las piezas del modelo');
    await page.waitForSelector('.big-chip.ok, .big-chip.bad', { timeout: 60000 });
    check(true, 'se calculan los resultados por operación');
    await page.screenshot({ path: path.join(shots, 'electron_editor.png') });
    await page.dblclick('.tree-item:has-text("Placa base")');
    await page.waitForSelector('.modal .tabbar', { timeout: 15000 });
    check(true, 'la operación abre su ventana de edición');
    await page.screenshot({ path: path.join(shots, 'electron_operacion.png') });
  } catch (e) {
    ok = false; console.log('ERROR: ' + e.message);
    try { await page.screenshot({ path: path.join(shots, 'electron_error.png') }); } catch (e2) { /* sin captura */ }
  }
  if (errors.length) console.log('Errores de consola:\n  ' + errors.slice(0, 8).join('\n  '));
  await app.close();
  console.log(ok ? 'PRUEBA DE HUMO: OK' : 'PRUEBA DE HUMO: FALLÓ');
  process.exit(ok ? 0 : 1);
})();
