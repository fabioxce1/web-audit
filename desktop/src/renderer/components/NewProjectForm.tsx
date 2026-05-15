import { useState } from 'react';
import { api } from '../lib/api';

interface Props {
  onCreate: () => void;
  onCancel: () => void;
}

const defaultConfig = {
  user_agent: 'WebAudit/1.0',
  max_workers: 5,
  crawl_delay: 1.0,
  respect_robots_txt: true,
  use_playwright: true,
  follow_redirects: true,
  max_redirects: 5,
  timeout: 30,
  max_urls: 0,
  save_html_snapshots: true,
  headless: true,
};

export default function NewProjectForm({ onCreate, onCancel }: Props) {
  const [name, setName] = useState('');
  const [seedUrl, setSeedUrl] = useState('');
  const [config, setConfig] = useState(defaultConfig);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !seedUrl.trim()) return;

    try {
      setLoading(true);
      setError(null);
      await api.createProject({ name: name.trim(), seed_url: seedUrl.trim(), config });
      onCreate();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onCancel}>
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold mb-4">Nuevo Proyecto</h2>

        {error && (
          <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg px-3 py-2 mb-4 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Nombre del proyecto</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Mi sitio web"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                required
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">URL semilla</label>
              <input
                type="url"
                value={seedUrl}
                onChange={(e) => setSeedUrl(e.target.value)}
                placeholder="https://ejemplo.com"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
                required
              />
            </div>

            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showAdvanced ? 'Ocultar' : 'Mostrar'} configuración avanzada
            </button>

            {showAdvanced && (
              <div className="space-y-3 bg-gray-800/50 rounded-lg p-3 border border-gray-700/50">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Workers</label>
                    <input
                      type="number"
                      value={config.max_workers}
                      onChange={(e) => setConfig({ ...config, max_workers: Number(e.target.value) })}
                      min={1} max={20}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Delay (seg)</label>
                    <input
                      type="number"
                      value={config.crawl_delay}
                      onChange={(e) => setConfig({ ...config, crawl_delay: Number(e.target.value) })}
                      min={0} max={10} step={0.1}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Timeout (seg)</label>
                    <input
                      type="number"
                      value={config.timeout}
                      onChange={(e) => setConfig({ ...config, timeout: Number(e.target.value) })}
                      min={5} max={120}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Máx URLs (0=sin límite)</label>
                    <input
                      type="number"
                      value={config.max_urls}
                      onChange={(e) => setConfig({ ...config, max_urls: Number(e.target.value) })}
                      min={0}
                      className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  {(['respect_robots_txt', 'use_playwright', 'follow_redirects', 'save_html_snapshots', 'headless'] as const).map((key) => (
                    <label key={key} className="flex items-center gap-2 text-sm text-gray-400">
                      <input
                        type="checkbox"
                        checked={config[key]}
                        onChange={(e) => setConfig({ ...config, [key]: e.target.checked })}
                        className="rounded bg-gray-700 border-gray-600"
                      />
                      {key.replace(/_/g, ' ')}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 mt-6">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim() || !seedUrl.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
            >
              {loading ? 'Creando...' : 'Crear Proyecto'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
