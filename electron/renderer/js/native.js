// Puente con el sistema (dialogos de archivo, carpetas): en Electron lo da preload.js; en un navegador (pruebas) se usa un respaldo simple.
const N = (window.SCP && window.SCP.native) || null;

export const native = {
  available: !!N,
  async openFile(filters) {
    if (N) return N.openFile(filters);
    const p = window.prompt('Ruta del archivo a abrir:');
    return p || null;
  },
  async saveFile(defaultName, filters) {
    if (N) return N.saveFile(defaultName, filters);
    const p = window.prompt('Ruta del archivo a guardar:', defaultName);
    return p || null;
  },
  async chooseFolder() {
    if (N) return N.chooseFolder();
    const p = window.prompt('Carpeta de trabajo:');
    return p || null;
  },
  async showItem(path) { if (N) return N.showItem(path); return null; },
  async openExternal(path) { if (N) return N.openExternal(path); return null; },
};
