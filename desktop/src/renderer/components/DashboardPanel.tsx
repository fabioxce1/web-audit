import { useEffect, useState, useCallback } from 'react';
import { api, SecuritySummary, SeoSummary } from '../lib/api';

interface Dashboard {
  project: { id: number; name: string; seed_url: string; status: string; created_at: string | null };
  crawl: { urls_found: number; urls_crawled: number; status: string } | null;
  security: { score: number; total_checks: number; critical_count: number; high_count: number; medium_count: number; low_count: number; info_count: number; status: string } | null;
  seo: { score: number; total_checks: number; critical_count: number; warning_count: number; good_count: number; info_count: number; status: string } | null;
  overall_score: number;
}

interface Props {
  projectId: number;
}

const scoreColor = (score: number) => {
  if (score >= 70) return 'text-green-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
};

const scoreBg = (score: number) => {
  if (score >= 70) return 'border-green-500/40 bg-green-500/5';
  if (score >= 40) return 'border-yellow-500/40 bg-yellow-500/5';
  return 'border-red-500/40 bg-red-500/5';
};

export default function DashboardPanel({ projectId }: Props) {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await requestDashboard(projectId);
      setDash(data);
    } catch {
      setDash(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  async function handleExportJson() {
    setExporting(true);
    try {
      const blob = await api.exportJson(projectId);
      downloadBlob(blob, `webaudit-${projectId}.json`);
    } catch (e) {
      console.error(e);
    } finally {
      setExporting(false);
    }
  }

  async function handleExportPdf() {
    setExporting(true);
    try {
      const blob = await api.exportPdf(projectId);
      downloadBlob(blob, `webaudit-report-${projectId}.pdf`);
    } catch (e) {
      console.error(e);
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500 mx-auto" />
      </div>
    );
  }

  if (!dash) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
        <div className="text-gray-500 text-sm">No hay datos disponibles. Realiza un crawling y escaneos primero.</div>
      </div>
    );
  }

  const sec = dash.security;
  const seo = dash.seo;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-400">Exportar: </span>
        <button onClick={handleExportJson} disabled={exporting} className="px-3 py-1.5 text-xs bg-gray-700 hover:bg-gray-600 disabled:opacity-50 rounded-lg transition-colors">
          {exporting ? '...' : '📄 JSON'}
        </button>
        <button onClick={handleExportPdf} disabled={exporting} className="px-3 py-1.5 text-xs bg-blue-700 hover:bg-blue-600 disabled:opacity-50 rounded-lg transition-colors">
          {exporting ? '...' : '📕 PDF'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className={`border rounded-xl p-6 flex flex-col items-center justify-center ${scoreBg(dash.overall_score)}`}>
          <div className={`text-6xl font-bold ${scoreColor(dash.overall_score)}`}>{dash.overall_score}</div>
          <div className="text-xs text-gray-500 mt-2 uppercase tracking-wider">Overall Score</div>
        </div>

        <div className={`border rounded-xl p-6 ${sec ? scoreBg(sec.score) : 'border-gray-800'}`}>
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Security</div>
          <div className={`text-3xl font-bold mb-3 ${sec ? scoreColor(sec.score) : 'text-gray-600'}`}>
            {sec ? `${sec.score}/100` : 'N/A'}
          </div>
          {sec ? (
            <div className="space-y-1">
              <div className="flex justify-between text-xs"><span className="text-red-400">Critical</span><span className="text-red-400 font-mono">{sec.critical_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-orange-400">High</span><span className="text-orange-400 font-mono">{sec.high_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-yellow-400">Medium</span><span className="text-yellow-400 font-mono">{sec.medium_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-blue-400">Low</span><span className="text-blue-400 font-mono">{sec.low_count}</span></div>
            </div>
          ) : (
            <div className="text-xs text-gray-600">No security scan performed</div>
          )}
        </div>

        <div className={`border rounded-xl p-6 ${seo ? scoreBg(seo.score) : 'border-gray-800'}`}>
          <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">SEO</div>
          <div className={`text-3xl font-bold mb-3 ${seo ? scoreColor(seo.score) : 'text-gray-600'}`}>
            {seo ? `${seo.score}/100` : 'N/A'}
          </div>
          {seo ? (
            <div className="space-y-1">
              <div className="flex justify-between text-xs"><span className="text-red-400">Critical</span><span className="text-red-400 font-mono">{seo.critical_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-yellow-400">Warnings</span><span className="text-yellow-400 font-mono">{seo.warning_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-green-400">Good</span><span className="text-green-400 font-mono">{seo.good_count}</span></div>
              <div className="flex justify-between text-xs"><span className="text-gray-400">Info</span><span className="text-gray-400 font-mono">{seo.info_count}</span></div>
            </div>
          ) : (
            <div className="text-xs text-gray-600">No SEO analysis performed</div>
          )}
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold mb-4">Project Summary</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-500">URL</div>
            <div className="text-gray-300 truncate font-mono text-xs" title={dash.project.seed_url}>{dash.project.seed_url}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">URLs Mapped</div>
            <div className="text-gray-300">{dash.crawl?.urls_found ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">URLs Crawled</div>
            <div className="text-gray-300">{dash.crawl?.urls_crawled ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Security Checks</div>
            <div className="text-gray-300">{sec?.total_checks ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">SEO Checks</div>
            <div className="text-gray-300">{seo?.total_checks ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Status</div>
            <div className="text-gray-300 capitalize">{dash.project.status}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Security Status</div>
            <div className="text-gray-300 capitalize">{sec?.status ?? 'Not run'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">SEO Status</div>
            <div className="text-gray-300 capitalize">{seo?.status ?? 'Not run'}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

async function requestDashboard(projectId: number): Promise<Dashboard> {
  const BASE_URL = 'http://127.0.0.1:8000/api';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/dashboard`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: res.statusText }))).detail);
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

function downloadBlob(data: any, filename: string) {
  if (data instanceof Blob) {
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } else if (typeof data === 'string') {
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  } else {
    const text = JSON.stringify(data, null, 2);
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
