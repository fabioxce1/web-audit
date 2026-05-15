const BASE_URL = 'http://127.0.0.1:8000/api';
const WS_BASE_URL = 'ws://127.0.0.1:8000/api';

interface Project {
  id: number;
  name: string;
  seed_url: string;
  config: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ProjectListResponse {
  projects: Project[];
  total: number;
}

interface CrawlStartResponse {
  session_id: number;
  status: string;
  message: string;
}

interface DiscoveredURL {
  id: number;
  url: string;
  normalized_url: string;
  status_code: number | null;
  content_type: string | null;
  depth: number;
  parent_url: string | null;
  title: string | null;
  links_count: number;
  crawled_at: string | null;
  is_external: boolean;
  is_duplicate: boolean;
  is_broken: boolean;
  content_hash: string | null;
  redirect_url: string | null;
  error_message: string | null;
  response_time_ms: number | null;
  discovery_method: string;
}

interface UrlListResponse {
  urls: DiscoveredURL[];
  total: number;
  page: number;
  page_size: number;
  total_broken: number;
  total_ok: number;
}

interface CrawlStats {
  session_id: number;
  status: string;
  urls_found: number;
  urls_crawled: number;
  total_broken: number;
  total_ok: number;
  started_at: string | null;
  completed_at: string | null;
}

interface TreeNode {
  id: number;
  url: string;
  normalized_url: string;
  status_code: number | null;
  title: string | null;
  depth: number;
  parent_url: string | null;
  content_type: string | null;
  is_broken: boolean;
  discovery_method: string;
  children: TreeNode[];
}

interface TreeResponse {
  tree: TreeNode[];
  root_url: string;
}

interface SecurityCheck {
  id: number;
  scan_id: number;
  url: string;
  url_id: number | null;
  category: string;
  check_name: string;
  severity: string;
  value_found: string | null;
  value_expected: string | null;
  recommendation: string | null;
  passed: boolean;
}

interface SecurityCheckListResponse {
  checks: SecurityCheck[];
  total: number;
  page: number;
  page_size: number;
}

interface SecurityScanResult {
  id: number;
  project_id: number;
  session_id: number;
  status: string;
  urls_scanned: number;
  total_checks: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  info_count: number;
  score: number;
  started_at: string | null;
  completed_at: string | null;
}

interface SecuritySummary {
  has_scan: boolean;
  scan_id?: number;
  status?: string;
  score?: number;
  urls_scanned?: number;
  total_checks?: number;
  critical_count?: number;
  high_count?: number;
  medium_count?: number;
  low_count?: number;
  info_count?: number;
  category_counts?: Record<string, Record<string, number>>;
  severity_failed?: Record<string, number>;
}

interface SeoCheck {
  id: number;
  scan_id: number;
  url: string;
  url_id: number | null;
  category: string;
  check_name: string;
  severity: string;
  value_found: string | null;
  value_expected: string | null;
  score_impact: number;
  recommendation: string | null;
  passed: boolean;
}

interface SeoCheckListResponse {
  checks: SeoCheck[];
  total: number;
  page: number;
  page_size: number;
}

interface SeoScanResult {
  id: number;
  project_id: number;
  session_id: number;
  status: string;
  urls_scanned: number;
  total_checks: number;
  critical_count: number;
  warning_count: number;
  good_count: number;
  info_count: number;
  score: number;
  started_at: string | null;
  completed_at: string | null;
}

interface SeoSummary {
  has_scan: boolean;
  scan_id?: number;
  status?: string;
  score?: number;
  urls_scanned?: number;
  total_checks?: number;
  critical_count?: number;
  warning_count?: number;
  good_count?: number;
  info_count?: number;
  category_counts?: Record<string, number>;
  severity_failed?: Record<string, number>;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    });

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || `HTTP ${res.status}`);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  createProject: (data: { name: string; seed_url: string; config?: Record<string, unknown> }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),

  listProjects: () =>
    request<ProjectListResponse>('/projects'),

  getProject: (id: number) =>
    request<Project>(`/projects/${id}`),

  deleteProject: (id: number) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  updateProject: (id: number, data: { name: string; seed_url: string; config?: Record<string, unknown> }) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  startCrawl: (projectId: number) =>
    request<CrawlStartResponse>(`/projects/${projectId}/crawl`, { method: 'POST' }),

  stopCrawl: (projectId: number) =>
    request<{ message: string; session_id: number }>(`/projects/${projectId}/crawl/stop`, { method: 'POST' }),

  getUrls: (projectId: number, params?: { page?: number; page_size?: number; status_code?: number; content_type?: string; is_broken?: boolean }) => {
    const search = new URLSearchParams();
    if (params?.page) search.set('page', String(params.page));
    if (params?.page_size) search.set('page_size', String(params.page_size));
    if (params?.status_code) search.set('status_code', String(params.status_code));
    if (params?.content_type) search.set('content_type', params.content_type);
    if (params?.is_broken !== undefined) search.set('is_broken', String(params.is_broken));
    const qs = search.toString();
    return request<UrlListResponse>(`/projects/${projectId}/urls${qs ? `?${qs}` : ''}`);
  },

  getTree: (projectId: number) =>
    request<TreeResponse>(`/projects/${projectId}/tree`),

  getCrawlStats: (projectId: number) =>
    request<CrawlStats>(`/projects/${projectId}/stats`),

  startSecurityScan: (projectId: number) =>
    request<SecurityScanResult>(`/projects/${projectId}/security/scan`, { method: 'POST' }),

  getSecurityScan: (projectId: number) =>
    request<SecurityScanResult>(`/projects/${projectId}/security/scan`),

  getSecurityChecks: (projectId: number, params?: { page?: number; page_size?: number; category?: string; severity?: string; passed?: boolean }) => {
    const search = new URLSearchParams();
    if (params?.page) search.set('page', String(params.page));
    if (params?.page_size) search.set('page_size', String(params.page_size));
    if (params?.category) search.set('category', params.category);
    if (params?.severity) search.set('severity', params.severity);
    if (params?.passed !== undefined) search.set('passed', String(params.passed));
    const qs = search.toString();
    return request<SecurityCheckListResponse>(`/projects/${projectId}/security/checks${qs ? `?${qs}` : ''}`);
  },

  getSecuritySummary: (projectId: number) =>
    request<SecuritySummary>(`/projects/${projectId}/security/summary`),

  startSeoScan: (projectId: number) =>
    request<SeoScanResult>(`/projects/${projectId}/seo/scan`, { method: 'POST' }),

  getSeoScan: (projectId: number) =>
    request<SeoScanResult>(`/projects/${projectId}/seo/scan`),

  getSeoChecks: (projectId: number, params?: { page?: number; page_size?: number; category?: string; severity?: string; passed?: boolean; url?: string }) => {
    const search = new URLSearchParams();
    if (params?.page) search.set('page', String(params.page));
    if (params?.page_size) search.set('page_size', String(params.page_size));
    if (params?.category) search.set('category', params.category);
    if (params?.severity) search.set('severity', params.severity);
    if (params?.passed !== undefined) search.set('passed', String(params.passed));
    if (params?.url) search.set('url', params.url);
    const qs = search.toString();
    return request<SeoCheckListResponse>(`/projects/${projectId}/seo/checks${qs ? `?${qs}` : ''}`);
  },

  getSeoSummary: (projectId: number) =>
    request<SeoSummary>(`/projects/${projectId}/seo/summary`),

  connectWebSocket: (projectId: number, onMessage: (data: unknown) => void, onError?: (e: Event) => void) => {
    const ws = new WebSocket(`${WS_BASE_URL}/projects/ws/${projectId}/crawl`);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch {
        onMessage(event.data);
      }
    };

    ws.onerror = (e) => onError?.(e);
    ws.onclose = () => onMessage({ type: 'ws_closed' });

    return {
      send: (data: unknown) => ws.send(JSON.stringify(data)),
      close: () => ws.close(),
    };
  },
};

export type { Project, DiscoveredURL, UrlListResponse, TreeNode, TreeResponse, CrawlStartResponse, CrawlStats, SecurityCheck, SecurityScanResult, SecuritySummary, SeoCheck, SeoScanResult, SeoSummary };
