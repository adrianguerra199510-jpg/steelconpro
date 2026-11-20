// Aplicación de escritorio SteelConPro: arranca el motor de cálculo (Python) como proceso local y muestra la interfaz.
const { app, BrowserWindow, ipcMain, dialog, shell, protocol, net, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { pathToFileURL } = require('url');

protocol.registerSchemesAsPrivileged([{ scheme: 'scp', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }]);

const RENDERER = path.join(__dirname, 'renderer');
const ICON = path.join(__dirname, 'assets', 'icon.png');
let win = null;
let engine = null;
let info = null;                       // { port, token }
let pendingOpen = null;

function engineCommand(token) {
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, 'engine', process.platform === 'win32' ? 'SteelConPro-engine.exe' : 'SteelConPro-engine');
    return { cmd: exe, args: ['--serve', '--token', token], cwd: path.dirname(exe) };
  }
  const root = path.join(__dirname, '..');
  return { cmd: process.env.SCP_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'), args: [path.join(root, 'run.py'), '--serve', '--token', token], cwd: root };
}

function startEngine() {
  return new Promise((resolve, reject) => {
    const token = crypto.randomBytes(16).toString('hex');
    const { cmd, args, cwd } = engineCommand(token);
    let done = false;
    let log = '';
    engine = spawn(cmd, args, { cwd, windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' } });
    const timer = setTimeout(() => { if (!done) { done = true; reject(new Error('El motor de cálculo no respondió a tiempo.\n' + log.slice(-800))); } }, 90000);
    const onData = (buf) => {
      const text = buf.toString('utf8');
      log += text;
      for (const line of text.split(/\r?\n/)) {
        if (line.startsWith('SCP_READY ') && !done) {
          done = true; clearTimeout(timer);
          try { info = JSON.parse(line.slice(10)); resolve(info); } catch (e) { reject(e); }
        }
      }
    };
    engine.stdout.on('data', onData);
    engine.stderr.on('data', (b) => { log += b.toString('utf8'); });
    engine.on('error', (e) => { if (!done) { done = true; clearTimeout(timer); reject(new Error(`No se pudo iniciar el motor (${cmd}): ${e.message}`)); } });
    engine.on('exit', (code) => {
      engine = null;
      if (!done) { done = true; clearTimeout(timer); reject(new Error(`El motor de cálculo se cerró (código ${code}).\n${log.slice(-800)}`)); }
      else if (!app.isQuitting && win && !win.isDestroyed()) {
        dialog.showErrorBox('SteelConPro', 'El motor de cálculo se detuvo inesperadamente. Cierre y vuelva a abrir el programa.');
      }
    });
  });
}

function stopEngine() {
  if (engine) { try { engine.kill(); } catch (e) { /* ya cerrado */ } engine = null; }
}

const SPLASH = 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;font:15px Segoe UI,system-ui,sans-serif;background:#f4f5f7;color:#344054">
<div style="font-size:30px;font-weight:800;letter-spacing:-.02em;color:#1f3864">SteelCon<span style="color:#e85d0c">Pro</span></div><div style="margin-top:14px;color:#667085">Iniciando el motor de cálculo…</div>
<div style="margin-top:18px;width:180px;height:4px;border-radius:4px;background:#e2e5ea;overflow:hidden"><div style="width:40%;height:100%;background:#e85d0c;animation:m 1.1s ease-in-out infinite alternate"></div></div>
<style>@keyframes m{from{margin-left:0}to{margin-left:60%}}</style>`);

function openArg(argv) {
  const f = argv.slice(app.isPackaged ? 1 : 2).find((a) => /\.(scp|pbase)$/i.test(a) && fs.existsSync(a));
  return f ? path.resolve(f) : null;
}

async function createWindow() {
  win = new BrowserWindow({ width: 1500, height: 950, minWidth: 1000, minHeight: 640, show: false, backgroundColor: '#f4f5f7', title: 'SteelConPro', icon: ICON,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false } });
  win.once('ready-to-show', () => { win.maximize(); win.show(); });
  win.on('closed', () => { win = null; });
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: 'deny' }; });
  await win.loadURL(SPLASH);
  try {
    await startEngine();
  } catch (e) {
    dialog.showErrorBox('SteelConPro', String(e.message || e));
    app.quit();
    return;
  }
  const q = pendingOpen ? `?open=${encodeURIComponent(pendingOpen)}` : '';
  await win.loadURL(`scp://app/index.html${q}`);
  if (!app.isPackaged && process.env.SCP_DEVTOOLS) win.webContents.openDevTools({ mode: 'detach' });
}

ipcMain.on('scp:engine', (ev) => { ev.returnValue = { url: info ? `http://127.0.0.1:${info.port}` : '', token: info ? info.token : '' }; });
ipcMain.handle('scp:open-file', async (_e, filters) => {
  const r = await dialog.showOpenDialog(win, { properties: ['openFile'], filters: filters || [] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('scp:save-file', async (_e, name, filters) => {
  const r = await dialog.showSaveDialog(win, { defaultPath: name, filters: filters || [] });
  return r.canceled ? null : r.filePath;
});
ipcMain.handle('scp:choose-folder', async () => {
  const r = await dialog.showOpenDialog(win, { properties: ['openDirectory', 'createDirectory'] });
  return r.canceled ? null : r.filePaths[0];
});
ipcMain.handle('scp:show-item', (_e, p) => { if (p) shell.showItemInFolder(p); });
ipcMain.handle('scp:open-path', (_e, p) => { if (p) return shell.openPath(p); return ''; });

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', (_e, argv) => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); const f = openArg(argv); if (f && info) win.loadURL(`scp://app/index.html?open=${encodeURIComponent(f)}`); }
  });
  app.whenReady().then(async () => {
    protocol.handle('scp', (req) => {
      const u = new URL(req.url);
      const rel = decodeURIComponent(u.pathname).replace(/^\/+/, '') || 'index.html';
      const file = path.normalize(path.join(RENDERER, rel));
      if (!file.startsWith(RENDERER)) return new Response('prohibido', { status: 403 });
      return net.fetch(pathToFileURL(file).toString());
    });
    if (!process.env.SCP_DEVTOOLS) Menu.setApplicationMenu(null);
    pendingOpen = openArg(process.argv);
    await createWindow();
  });
  app.on('window-all-closed', () => { app.quit(); });
  app.on('before-quit', () => { app.isQuitting = true; stopEngine(); });
  process.on('exit', stopEngine);
}
