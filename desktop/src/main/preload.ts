import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,
  isPackaged: process.env.NODE_ENV !== 'development',
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
});
