import { useEffect, useState, useRef, useCallback } from 'react';
import { api } from '../lib/api';

interface Props {
  projectId: number;
  sessionId: number | null;
  onStatusChange?: (status: string) => void;
}

interface CrawlEvent {
  type: string;
  url?: string;
  total_found?: number;
  total_crawled?: number;
  stats?: { urls_found: number; urls_crawled: number; errors: number };
}

export default function CrawlProgress({ projectId, sessionId, onStatusChange }: Props) {
  const [found, setFound] = useState(0);
  const [crawled, setCrawled] = useState(0);
  const [status, setStatus] = useState<string>('idle');
  const [recentUrls, setRecentUrls] = useState<string[]>([]);
  const wsRef = useRef<ReturnType<typeof api.connectWebSocket> | null>(null);
  const statusRef = useRef<string>('idle');

  useEffect(() => { statusRef.current = status; }, [status]);

  useEffect(() => {
    loadInitialState();
  }, [projectId]);

  async function loadInitialState() {
    try {
      const project = await api.getProject(projectId);

      if (project.status === 'crawling') {
        setStatus('running');
        onStatusChange?.('running');
      } else if (project.status === 'completed') {
        setStatus('completed');
      } else if (project.status === 'idle') {
        setStatus('idle');
      }

      try {
        const stats = await api.getCrawlStats(projectId);
        if (project.status !== 'crawling') {
          setFound(stats.urls_found);
          setCrawled(stats.urls_crawled);
        }
      } catch {
      }
    } catch {
    }
  }

  const handleMessage = useCallback((data: unknown) => {
    const event = data as CrawlEvent;
    const s = statusRef.current;

    switch (event.type) {
      case 'crawl_started':
        setStatus('running');
        setFound(0);
        setCrawled(0);
        setRecentUrls([]);
        onStatusChange?.('running');
        break;
      case 'url_discovered':
        if (s !== 'completed' && s !== 'stopped' && s !== 'stopping') {
          setStatus('running');
        }
        setFound(event.total_found || 0);
        break;
      case 'url_crawled':
        if (s !== 'completed' && s !== 'stopped' && s !== 'stopping') {
          setStatus('running');
        }
        setCrawled(event.total_crawled || 0);
        setFound(event.total_found || 0);
        if (event.url) {
          setRecentUrls((prev) => [event.url!, ...prev.slice(0, 9)]);
        }
        break;
      case 'crawl_completed': {
        const finalStatus = event.status === 'stopped' ? 'stopped' : 'completed';
        setStatus(finalStatus);
        if (event.stats) {
          setCrawled(event.stats.urls_crawled);
          setFound(event.stats.urls_found);
        }
        onStatusChange?.(finalStatus);
        break;
      }
      case 'crawl_error':
        setStatus('error');
        onStatusChange?.('error');
        break;
      case 'stopped':
        setStatus('stopped');
        break;
      case 'ws_closed':
        if (s === 'running') setStatus('disconnected');
        break;
    }
  }, [projectId, onStatusChange]);

  useEffect(() => {
    const ws = api.connectWebSocket(projectId, handleMessage);
    wsRef.current = ws;

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [projectId, handleMessage]);

  function handleStop() {
    wsRef.current?.send({ action: 'stop' });
    setStatus('stopping');
  }

  const isRunning = status === 'running' || status === 'disconnected';
  const isCompleted = status === 'completed' || status === 'stopped';
  const progress = isCompleted && found > 0 ? 100 : found > 0 ? Math.min(Math.round((crawled / found) * 100), 99) : 0;

  const statusStyles: Record<string, string> = {
    idle: 'text-gray-500',
    running: 'text-blue-400',
    completed: 'text-green-400',
    stopped: 'text-yellow-400',
    stopping: 'text-yellow-400',
    error: 'text-red-400',
    disconnected: 'text-orange-400',
  };

  const statusLabels: Record<string, string> = {
    idle: 'Inactivo',
    running: 'Crawleando',
    completed: 'Completado',
    stopped: 'Detenido',
    stopping: 'Deteniendo...',
    error: 'Error',
    disconnected: 'Reconectando...',
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm">Progreso del Crawling</h3>
        <span className={`text-xs font-medium ${statusStyles[status] || 'text-gray-500'}`}>
          {statusLabels[status] || status}
        </span>
      </div>

      <div className="w-full bg-gray-800 rounded-full h-2 mb-4">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${
            isRunning ? 'bg-blue-500' : isCompleted ? 'bg-green-500' : found > 0 ? 'bg-yellow-500' : 'bg-gray-600'
          }`}
          style={{ width: `${isRunning ? Math.max(progress, 2) : isCompleted && found > 0 ? 100 : found > 0 ? Math.max(progress, 100) : 0}%` }}
        />
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4 text-center">
        <div>
          <div className="text-2xl font-bold text-gray-100">{found}</div>
          <div className="text-xs text-gray-500">Encontradas</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-gray-100">{crawled}</div>
          <div className="text-xs text-gray-500">Crawledas</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-gray-100">{found > 0 ? `${progress}%` : '0%'}</div>
          <div className="text-xs text-gray-500">Progreso</div>
        </div>
      </div>

      {isRunning && (
        <button
          onClick={handleStop}
          className="w-full py-2 bg-red-600/20 hover:bg-red-600/30 border border-red-800 rounded-lg text-sm text-red-300 transition-colors"
        >
          Detener Crawling
        </button>
      )}

      {recentUrls.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-gray-600 mb-2">Últimas URLs procesadas</div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {recentUrls.map((url, i) => (
              <div key={i} className="text-xs text-gray-400 truncate font-mono bg-gray-800/50 rounded px-2 py-1">
                {url}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}