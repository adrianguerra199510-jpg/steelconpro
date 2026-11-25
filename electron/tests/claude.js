// «Conectar con Claude Desktop» (inicio): el diálogo explica la conexión y, al conectar, agrega el servidor MCP de SteelConPro a la configuración de
// Claude Desktop con la carpeta de trabajo de la aplicación, sin tocar lo demás.  Uso: xvfb-run -a node tests/claude.js [carpeta]
const { _electron: electron } = require('playwright');
const path = require('path'), fs = require('fs'), os = require('os');
(async () => {
  const shots = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'scp-cl-'));
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-ws-'));
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'scp-home-'));
  const cfgDir = process.platform === 'win32' ? path.join(home, 'AppData', 'Roaming', 'Claude') : process.platform === 'darwin' ? path.join(home, 'Library', 'Application Support', 'Claude') : path.join(home, '.config', 'Claude');
  fs.mkdirSync(cfgDir, { recursive: true });
  const cfg = path.join(cfgDir, 'claude_desktop_config.json');
  fs.writeFileSync(cfg, JSON.stringify({ mcpServers: { otro: { command: 'x' } } }));
  const app = await electron.launch({ executablePath: require('electron'), args: [path.join(__dirname, '..'), '--no-sandbox', '--disable-gpu-sandbox', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
    env: { ...process.env, SCP_WORKSPACE: ws, HOME: home, APPDATA: path.join(home, 'AppData', 'Roaming') } });
  const page = await app.firstWindow(); await page.setViewportSize({ width: 1300, height: 860 });
  const errs = []; page.on('pageerror', (e) => errs.push(e.message));
  let fails = 0; const check = (c, m) => { console.log((c ? 'OK    ' : 'FALLA ') + m); if (!c) fails++; };
  await page.waitForSelector('.home', { timeout: 120000 });
  await page.click('text=Conectar con Claude Desktop'); await page.waitForTimeout(1500);
  check(await page.isVisible('text=todavía no está en la configuración'), 'el diálogo dice que SteelConPro aún no está en Claude Desktop');
  await page.screenshot({ path: path.join(shots, 'claude_1.png') });
  await page.click('.modal button:has-text("Conectar")'); await page.waitForTimeout(2000);
  const d = JSON.parse(fs.readFileSync(cfg, 'utf-8'));
  const e = d.mcpServers.steelconpro;
  check(e && e.args.includes('--mcp') && e.args.includes(ws) && d.mcpServers.otro, `la configuración tiene «steelconpro» con --mcp y la carpeta de trabajo, y conserva los otros servidores (${JSON.stringify(e)})`);
  check(await page.isVisible('text=ya está en la configuración'), 'el diálogo confirma la conexión');
  await page.screenshot({ path: path.join(shots, 'claude_2.png') });
  check(!errs.length, 'sin errores de JavaScript' + (errs.length ? ': ' + errs[0] : ''));
  await app.close();
  console.log(fails ? `PRUEBA CLAUDE DESKTOP: ${fails} FALLAS` : 'PRUEBA CLAUDE DESKTOP: OK');
  process.exit(fails ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
