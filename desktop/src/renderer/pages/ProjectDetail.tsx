import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api, Project, DiscoveredURL } from '../lib/api';
import CrawlProgress from '../components/CrawlProgress';
import UrlTable from '../components/UrlTable';
import SecurityPanel from '../components/SecurityPanel';
import SeoPanel from '../components/SeoPanel';

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = Number(id);

  const [project, setProject] = useState<Project | null>(null);
  const [urls, setUrls] = useState<DiscoveredURL[]>([]);
  const [totalUrls, setTotalUrls] = useState(0);
  const [totalBroken, setTotalBroken] = useState(0);
  const [totalOk, setTotalOk] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [urlsLoading, setUrlsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crawling, setCrawling] = useState(false);
  const [startingCrawl, setStartingCrawl] = useState(false);
  const [filter, setFilter] = useState<'all' | 'ok' | 'broken'>('all');
  const [activeTab, setActiveTab] = useState<'urls' | 'security' | 'seo'>('urls');

  useEffect(() => {
    if (!id || isNaN(projectId)) {
      navigate('/');
      return;
    }
    loadProject();
  }, [projectId]);

  const loadUrls = useCallback(async () => {
    try {
      setUrlsLoading(true);
      const params: { page: number; page_size: number; is_broken?: boolean } = { page, page_size: 50 };
      if (filter === 'broken') params.is_broken = true;
      else if (filter === 'ok') params.is_broken = false;
      const data = await api.getUrls(projectId, params);
      setUrls(data.urls);
      setTotalUrls(data.total);
      setTotalBroken(data.total_broken);
      setTotalOk(data.total_ok);
    } catch {
    } finally {
      setUrlsLoading(false);
    }
  }, [projectId, page, filter]);

  useEffect(() => {
    loadUrls();

    if (!crawling) {
      return;
    }

    const interval = setInterval(() => {
      loadUrls();
      checkProjectStatus();
    }, 3000);

    return () => clearInterval(interval);
  }, [projectId, page, crawling, loadUrls]);

  async function checkProjectStatus() {
    try {
      const data = await api.getProject(projectId);
      if (data.status !== 'crawling') {
        setCrawling(false);
        setProject(data);
      }
    } catch {
    }
  }

  async function loadProject() {
    try {
      const data = await api.getProject(projectId);
      setProject(data);
      setCrawling(data.status === 'crawling');
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleStartCrawl() {
    setStartingCrawl(true);
    try {
      await api.startCrawl(projectId);
      setCrawling(true);
      await loadProject();
      setPage(1);
      setFilter('all');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStartingCrawl(false);
    }
  }

  function handleCrawlEnd(_status: string) {
    setCrawling(false);
    loadProject();
    loadUrls();
  }

  function handleFilterChange(newFilter: 'all' | 'ok' | 'broken') {
    setFilter(newFilter);
    setPage(1);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-red-400">{error || 'Proyecto no encontrado'}</p>
      </div>
    );
  }

  const statusCodes = urls.reduce((acc, u) => {
    const code = u.status_code || 0;
    const bucket = code === 0 ? 'error' : `${Math.floor(code / 100)}xx`;
    acc[bucket] = (acc[bucket] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate('/')} className="text-gray-600 hover:text-gray-400 transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-xl font-bold">{project.name}</h1>
          <p className="text-gray-500 text-sm">{project.seed_url}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Link
            to={`/project/${projectId}/tree`}
            className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg transition-colors"
          >
            Ver Árbol
          </Link>
          {!crawling && !startingCrawl && (
            <button
              onClick={handleStartCrawl}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors"
            >
              Iniciar Crawling
            </button>
          )}
          {startingCrawl && (
            <span className="flex items-center gap-2 px-4 py-2 bg-blue-600/50 rounded-lg text-sm text-blue-200 cursor-wait">
              <span className="animate-spin rounded-full h-3.5 w-3.5 border-2 border-blue-300 border-t-transparent" />
              Ejecutando Crawling...
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-6 text-sm">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2">
          <CrawlProgress projectId={projectId} sessionId={null} onStatusChange={handleCrawlEnd} />
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="font-semibold text-sm mb-4">Distribución de Códigos</h3>
          {totalUrls === 0 ? (
            <p className="text-gray-600 text-sm">Sin datos aún</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(statusCodes).map(([code, count]) => (
                <div key={code} className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">{code}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-32 bg-gray-800 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
                          code === '2xx' ? 'bg-green-500' : code === '3xx' ? 'bg-yellow-500' : code === '4xx' ? 'bg-orange-500' : code === '5xx' ? 'bg-red-500' : 'bg-gray-600'
                        }`}
                        style={{ width: `${(count / totalUrls) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-600 w-8 text-right">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setActiveTab('urls')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${activeTab === 'urls' ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          URLs
        </button>
        <button
          onClick={() => setActiveTab('security')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${activeTab === 'security' ? 'bg-purple-900/50 text-purple-300' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          Ciberseguridad
        </button>
        <button
          onClick={() => setActiveTab('seo')}
          className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${activeTab === 'seo' ? 'bg-green-900/50 text-green-300' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          SEO
        </button>
      </div>

      {activeTab === 'urls' && (
        <UrlTable
          urls={urls}
          loading={urlsLoading}
          total={totalUrls}
          page={page}
          pageSize={50}
          onPageChange={setPage}
          filter={filter}
          onFilterChange={handleFilterChange}
          brokenCount={totalBroken}
          okCount={totalOk}
        />
      )}

      {activeTab === 'security' && (
        <SecurityPanel projectId={projectId} />
      )}

      {activeTab === 'seo' && (
        <SeoPanel projectId={projectId} />
      )}
    </div>
  );
}