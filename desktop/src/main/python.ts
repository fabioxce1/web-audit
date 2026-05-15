import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import http from 'http';
import { app } from 'electron';

let pythonProcess: ChildProcess | null = null;

function getBackendPath(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }
  return path.join(__dirname, '..', '..', '..', 'backend');
}

export function startPythonBackend(): void {
  const backendPath = getBackendPath();
  const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';

  try {
    pythonProcess = spawn(pythonCommand, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], {
      cwd: backendPath,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        WEB_AUDIT_DB_PATH: path.join(app.getPath('userData'), 'web_audit.db'),
        WEB_AUDIT_SNAPSHOT_DIR: path.join(app.getPath('userData'), 'snapshots'),
      },
    });

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      console.log(`[Python] ${data.toString().trim()}`);
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      console.error(`[Python] ${data.toString().trim()}`);
    });

    pythonProcess.on('error', (err: Error) => {
      console.error('Error al iniciar backend Python:', err.message);
    });

    pythonProcess.on('close', (code: number | null) => {
      console.log(`Backend Python terminado con código ${code}`);
      pythonProcess = null;
    });
  } catch (err) {
    console.error('No se pudo iniciar el backend Python:', err);
  }
}

export function stopPythonBackend(): void {
  if (pythonProcess) {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pythonProcess.pid), '/f', '/t']);
    } else {
      pythonProcess.kill('SIGTERM');
    }
    pythonProcess = null;
  }
}

export function waitForBackend(maxRetries: number = 30, delayMs: number = 1000): Promise<void> {
  return new Promise((resolve, reject) => {
    let retries = 0;

    const check = () => {
      const req = http.get('http://127.0.0.1:8000/health', (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });

      req.on('error', () => {
        retry();
      });

      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      retries++;
      if (retries >= maxRetries) {
        reject(new Error(`Backend no disponible después de ${maxRetries} intentos`));
        return;
      }
      setTimeout(check, delayMs);
    };

    check();
  });
}
