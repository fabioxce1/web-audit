import { DiscoveredURL } from '../lib/api';

interface Props {
  urls: DiscoveredURL[];
  loading: boolean;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  filter: 'all' | 'ok' | 'broken';
  onFilterChange: (filter: 'all' | 'ok' | 'broken') => void;
  brokenCount: number;
  okCount: number;
}

const statusColor = (code: number | null): string => {
  if (!code || code === 0) return 'text-red-400';
  if (code >= 200 && code < 300) return 'text-green-400';
  if (code >= 300 && code < 400) return 'text-yellow-400';
  if (code >= 400 && code < 500) return 'text-orange-400';
  return 'text-red-500';
};

export default function UrlTable({ urls, loading, total, page, pageSize, onPageChange, filter, onFilterChange, brokenCount, okCount }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-800">
        <button
          onClick={() => onFilterChange('all')}
          className={`px-2.5 py-1 text-xs rounded-md transition-colors ${filter === 'all' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          Todas
        </button>
        <button
          onClick={() => onFilterChange('ok')}
          className={`px-2.5 py-1 text-xs rounded-md transition-colors ${filter === 'ok' ? 'bg-green-900/50 text-green-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          OK ({okCount})
        </button>
        <button
          onClick={() => onFilterChange('broken')}
          className={`px-2.5 py-1 text-xs rounded-md transition-colors ${filter === 'broken' ? 'bg-orange-900/50 text-orange-400' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          Rotas ({brokenCount})
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase">
              <th className="text-left px-4 py-3">URL</th>
              <th className="text-center px-3 py-3 w-16">Status</th>
              <th className="text-left px-3 py-3 w-32">Tipo</th>
              <th className="text-center px-3 py-3 w-14">Prof.</th>
              <th className="text-right px-3 py-3 w-20">Tiempo</th>
              <th className="text-center px-2 py-3 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-gray-600">Cargando...</td>
              </tr>
            ) : urls.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-gray-600">Sin URLs descubiertas aún</td>
              </tr>
            ) : (
              urls.map((u) => (
                <tr key={u.id} className={`border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors${u.is_broken ? ' bg-red-950/20' : ''}`}>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-1.5">
                      {u.is_broken && (
                        <span className="shrink-0 w-2 h-2 rounded-full bg-orange-500" title="URL rota" />
                      )}
                      {u.is_duplicate && !u.is_broken && (
                        <span className="shrink-0 w-2 h-2 rounded-full bg-gray-600" title="Contenido duplicado" />
                      )}
                      <div className="min-w-0">
                        <div className="max-w-md truncate font-mono text-xs text-gray-300" title={u.url}>
                          {u.url}
                        </div>
                        {u.discovery_method === 'enumeration' && (
                          <span className="inline-block text-[10px] bg-purple-900/60 text-purple-300 rounded px-1 ml-1 align-middle">enum</span>
                        )}
                        {u.redirect_url && (
                          <div className="text-xs text-blue-400 truncate max-w-md mt-0.5" title={`Redirige a: ${u.redirect_url}`}>
                            &#8594; {u.redirect_url}
                          </div>
                        )}
                        {u.title && !u.is_broken && (
                          <div className="text-xs text-gray-600 truncate max-w-md mt-0.5">{u.title}</div>
                        )}
                        {u.error_message && (
                          <div className="text-xs text-red-400 truncate max-w-md mt-0.5">{u.error_message}</div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className={`text-center px-3 py-2.5 font-mono text-xs font-semibold ${statusColor(u.status_code)}`}>
                    {u.status_code || '-'}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="text-xs bg-gray-800 text-gray-500 rounded px-1.5 py-0.5">
                      {u.content_type?.split('/').pop() || '-'}
                    </span>
                  </td>
                  <td className="text-center px-3 py-2.5 text-xs text-gray-500">{u.depth}</td>
                  <td className="text-right px-3 py-2.5 text-xs text-gray-600 font-mono">
                    {u.response_time_ms ? `${u.response_time_ms}ms` : '-'}
                  </td>
                  <td className="text-center px-2 py-2.5">
                    <a
                      href={u.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-600 hover:text-gray-300 transition-colors"
                      title="Abrir URL en navegador"
                    >
                      <svg className="w-3.5 h-3.5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
          <span className="text-xs text-gray-600">
            {total} URLs &middot; Pág {page} de {totalPages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded transition-colors"
            >
              Anterior
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}