// Puente seguro entre la interfaz y el sistema: datos del motor local y diálogos de archivos.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('SCP', {
  engine: ipcRenderer.sendSync('scp:engine'),
  native: {
    openFile: (filters) => ipcRenderer.invoke('scp:open-file', filters),
    saveFile: (name, filters) => ipcRenderer.invoke('scp:save-file', name, filters),
    chooseFolder: () => ipcRenderer.invoke('scp:choose-folder'),
    showItem: (p) => ipcRenderer.invoke('scp:show-item', p),
    openExternal: (p) => ipcRenderer.invoke('scp:open-path', p),
  },
});
