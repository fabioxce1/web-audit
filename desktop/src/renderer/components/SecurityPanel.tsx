import { useEffect, useState, useCallback, Fragment } from 'react';
import { api, SecurityCheck, SecuritySummary, SecurityScanResult } from '../lib/api';

interface Props {
  projectId: number;
}

const severityConfig: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: 'bg-red-900/50', text: 'text-red-400', label: 'Crítico' },
  high: { bg: 'bg-orange-900/50', text: 'text-orange-400', label: 'Alto' },
  medium: { bg: 'bg-yellow-900/50', text: 'text-yellow-400', label: 'Medio' },
  low: { bg: 'bg-blue-900/50', text: 'text-blue-400', label: 'Bajo' },
  info: { bg: 'bg-gray-800', text: 'text-gray-400', label: 'Info' },
};

const categoryLabels: Record<string, string> = {
  headers: 'Headers HTTP',
  ssl: 'SSL/TLS',
  cookies: 'Cookies',
  info_disclosure: 'Info Expuesta',
  tech_detection: 'Tecnologías',
  waf: 'WAF / Firewall',
  cors: 'CORS',
  https: 'HTTPS',
  ports: 'Puertos Abiertos',
  email_security: 'Seguridad Email',
  access: 'Gestión de Accesos',
  injection: 'Inyecciones (SQL/NoSQL/CMD)',
  xss: 'Cross-Site Scripting (XSS)',
  ssrf: 'SSRF',
  authorization: 'Autorización (BOLA)',
  mass_assignment: 'Mass Assignment',
  data_exposure: 'Exposición de Datos',
};

const REFERENCE_LINKS: Record<string, Array<{ label: string; url: string }>> = {
  'Content-Security-Policy': [
    { label: 'MDN: CSP', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP' },
    { label: 'CSP Evaluator', url: 'https://csp-evaluator.withgoogle.com/' },
  ],
  'HSTS': [
    { label: 'MDN: Strict-Transport-Security', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security' },
    { label: 'HSTS Preload', url: 'https://hstspreload.org/' },
  ],
  'X-Frame-Options': [
    { label: 'MDN: X-Frame-Options', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options' },
    { label: 'OWASP: Clickjacking', url: 'https://cheatsheetseries.owasp.org/cheatsheets/Clickjacking_Defense_Cheat_Sheet.html' },
  ],
  'X-Content-Type-Options': [
    { label: 'MDN: X-Content-Type-Options', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options' },
  ],
  'Referrer-Policy': [
    { label: 'MDN: Referrer-Policy', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy' },
  ],
  'Permissions-Policy': [
    { label: 'MDN: Permissions-Policy', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy' },
  ],
  'CORS': [
    { label: 'MDN: CORS', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS' },
    { label: 'OWASP: CORS', url: 'https://cheatsheetseries.owasp.org/cheatsheets/CORS_Cheat_Sheet.html' },
  ],
  'SSL': [
    { label: 'SSL Labs', url: 'https://www.ssllabs.com/ssltest/' },
    { label: 'Mozilla SSL Config', url: 'https://ssl-config.mozilla.org/' },
  ],
  'Cookie': [
    { label: 'MDN: Set-Cookie', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie' },
    { label: 'OWASP: Session Management', url: 'https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html' },
  ],
  'SPF': [
    { label: 'dmarcian: SPF Guide', url: 'https://dmarcian.com/spf-syntax-table/' },
    { label: 'MXToolbox SPF', url: 'https://mxtoolbox.com/spf.aspx' },
  ],
  'DMARC': [
    { label: 'dmarcian: DMARC Guide', url: 'https://dmarcian.com/dmarc-record/' },
    { label: 'MXToolbox DMARC', url: 'https://mxtoolbox.com/dmarc.aspx' },
  ],
  'Server Header': [
    { label: 'OWASP: Fingerprinting', url: 'https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html' },
  ],
  'WAF': [
    { label: 'Cloudflare WAF', url: 'https://www.cloudflare.com/waf/' },
    { label: 'OWASP: ModSecurity', url: 'https://owasp.org/www-project-modsecurity-core-rule-set/' },
  ],
  'Rate Limiting': [
    { label: 'OWASP: Rate Limiting', url: 'https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html' },
  ],
  'Password': [
    { label: 'OWASP: Password Storage', url: 'https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html' },
  ],
  'Puertos': [
    { label: 'NIST: Port Security', url: 'https://csrc.nist.gov/glossary/term/port_security' },
  ],
  'SQL': [
    { label: 'OWASP: SQL Injection', url: 'https://owasp.org/www-community/attacks/SQL_Injection' },
    { label: 'PortSwigger: SQLi', url: 'https://portswigger.net/web-security/sql-injection' },
  ],
  'NoSQL': [
    { label: 'OWASP: NoSQL Injection', url: 'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/07-Input_Validation_Testing/05.6-Testing_for_NoSQL_Injection' },
  ],
  'Command': [
    { label: 'OWASP: Command Injection', url: 'https://owasp.org/www-community/attacks/Command_Injection' },
  ],
  'XSS': [
    { label: 'OWASP: XSS', url: 'https://owasp.org/www-community/attacks/xss/' },
    { label: 'PortSwigger: XSS', url: 'https://portswigger.net/web-security/cross-site-scripting' },
  ],
  'SSRF': [
    { label: 'OWASP: SSRF', url: 'https://owasp.org/www-community/attacks/Server_Side_Request_Forgery' },
    { label: 'PortSwigger: SSRF', url: 'https://portswigger.net/web-security/ssrf' },
  ],
  'BOLA': [
    { label: 'OWASP: BOLA/IDOR', url: 'https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References' },
  ],
  'Mass Assignment': [
    { label: 'OWASP: Mass Assignment', url: 'https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html' },
  ],
  'Data': [
    { label: 'OWASP: Sensitive Data Exposure', url: 'https://owasp.org/www-project-top-ten/2017/A3_2017-Sensitive_Data_Exposure' },
  ],
};

function getReferenceLinks(checkName: string): Array<{ label: string; url: string }> {
  for (const [key, links] of Object.entries(REFERENCE_LINKS)) {
    if (checkName.toLowerCase().includes(key.toLowerCase())) {
      return links;
    }
  }

  const genericLinks = [];
  if (checkName.toLowerCase().includes('header') || checkName.toLowerCase().includes('policy')) {
    genericLinks.push({ label: 'MDN: HTTP Headers', url: 'https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers' });
    genericLinks.push({ label: 'OWASP: Headers Cheatsheet', url: 'https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html' });
  }
  if (genericLinks.length > 0) return genericLinks;

  return [
    { label: 'NIST Cybersecurity', url: 'https://www.nist.gov/cybersecurity' },
    { label: 'OWASP Cheat Sheets', url: 'https://cheatsheetseries.owasp.org/' },
  ];
}

export default function SecurityPanel({ projectId }: Props) {
  const [scan, setScan] = useState<SecurityScanResult | null>(null);
  const [summary, setSummary] = useState<SecuritySummary | null>(null);
  const [checks, setChecks] = useState<SecurityCheck[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState<string>('');
  const [category, setCategory] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [showFailed, setShowFailed] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      const data = await api.getSecuritySummary(projectId);
      setSummary(data);
    } catch {
      setSummary(null);
    }
  }, [projectId]);

  const loadScan = useCallback(async () => {
    try {
      const data = await api.getSecurityScan(projectId);
      setScan(data);
    } catch {
      setScan(null);
    }
  }, [projectId]);

  const loadChecks = useCallback(async () => {
    try {
      const params: Record<string, unknown> = { page, page_size: 50 };
      if (severity) params.severity = severity;
      if (category) params.category = category;
      if (showFailed) params.passed = false;
      const data = await api.getSecurityChecks(projectId, params as { page?: number; page_size?: number; category?: string; severity?: string; passed?: boolean });
      setChecks(data.checks);
      setTotal(data.total);
    } catch {
      setChecks([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, page, severity, category, showFailed]);

  useEffect(() => {
    loadSummary();
    loadScan();
  }, [projectId]);

  useEffect(() => {
    loadChecks();
  }, [loadChecks]);

  const isScanning = scanning || scan?.status === 'pending' || scan?.status === 'running';

  useEffect(() => {
    if (!isScanning) return;

    const interval = setInterval(async () => {
      try {
        const data = await api.getSecurityScan(projectId);
        setScan(data);
        if (data.status === 'completed' || data.status === 'failed') {
          setScanning(false);
          setSummary(await api.getSecuritySummary(projectId));
          await loadChecks();
        }
      } catch {
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [projectId, isScanning]);

  async function handleStartScan() {
    setScanning(true);
    try {
      await api.startSecurityScan(projectId);
      await loadScan();
    } catch (e) {
      console.error(e);
      setScanning(false);
    }
  }

  const scoreColor = (score: number) => {
    if (score >= 80) return 'text-green-400';
    if (score >= 60) return 'text-yellow-400';
    if (score >= 40) return 'text-orange-400';
    return 'text-red-400';
  };

  const scoreBg = (score: number) => {
    if (score >= 80) return 'border-green-500/30';
    if (score >= 60) return 'border-yellow-500/30';
    if (score >= 40) return 'border-orange-500/30';
    return 'border-red-500/30';
  };

  if (!summary || !summary.has_scan) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
        <div className="text-gray-500 text-sm mb-4">No se ha realizado un escaneo de seguridad</div>
        <button
          onClick={handleStartScan}
          disabled={isScanning}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm font-medium transition-colors"
        >
          {isScanning ? (
            <span className="flex items-center gap-2">
              <span className="animate-spin rounded-full h-3.5 w-3.5 border-2 border-blue-300 border-t-transparent" />
              Escaneando...
            </span>
          ) : 'Iniciar Escaneo de Seguridad'}
        </button>
      </div>
    );
  }

  const s = summary;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 mb-2">
        <button
          onClick={handleStartScan}
          disabled={isScanning}
          className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors"
        >
          {isScanning ? 'Escaneando...' : 'Re-escanear'}
        </button>
        {scan?.status && (
          <span className="text-xs text-gray-500">
            {scan.status === 'completed' ? 'Completado' : scan.status === 'running' ? 'En progreso' : scan.status}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className={`bg-gray-900 border ${scoreBg(s.score || 0)} rounded-xl p-4 flex flex-col items-center justify-center`}>
          <div className={`text-4xl font-bold ${scoreColor(s.score || 0)}`}>
            {s.score ?? 0}
          </div>
          <div className="text-xs text-gray-500 mt-1">Score de Seguridad</div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="text-xs text-gray-500 mb-2">Por Severidad</div>
          <div className="space-y-1">
            {['critical', 'high', 'medium', 'low', 'info'].map((sev) => {
              const cfg = severityConfig[sev];
              const count = (s.severity_failed?.[sev] ?? 0);
              return (
                <div key={sev} className="flex items-center justify-between">
                  <span className={`text-xs ${cfg.text}`}>{cfg.label}</span>
                  <span className={`text-xs font-mono ${count > 0 ? cfg.text : 'text-gray-600'}`}>{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 col-span-2">
          <div className="text-xs text-gray-500 mb-2">Por Categoría</div>
          <div className="space-y-1">
            {Object.entries(s.category_counts || {}).map(([cat, sevs]) => {
              const total = Object.values(sevs).reduce((a: number, b) => a + b, 0);
              const failed = Object.entries(sevs)
                .filter(([sev]) => sev !== 'info')
                .reduce((a, [, v]) => a + v, 0);
              return (
                <div key={cat} className="flex items-center justify-between">
                  <span className="text-xs text-gray-400">{categoryLabels[cat] || cat}</span>
                  <span className="text-xs text-gray-600">{total} checks ({failed} fallidos)</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setSeverity('')}
          className={`px-2.5 py-1 text-xs rounded-md transition-colors ${!severity ? 'bg-gray-700 text-white' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          Todas
        </button>
        {Object.entries(severityConfig).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setSeverity(severity === key ? '' : key)}
            className={`px-2.5 py-1 text-xs rounded-md transition-colors ${severity === key ? `${cfg.bg} ${cfg.text}` : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
          >
            {cfg.label}
          </button>
        ))}
        <div className="w-px h-4 bg-gray-700 mx-1" />
        {Object.entries(categoryLabels).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setCategory(category === key ? '' : key)}
            className={`px-2.5 py-1 text-xs rounded-md transition-colors ${category === key ? 'bg-purple-900/50 text-purple-300' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
          >
            {label}
          </button>
        ))}
        <div className="w-px h-4 bg-gray-700 mx-1" />
        <button
          onClick={() => setShowFailed(!showFailed)}
          className={`px-2.5 py-1 text-xs rounded-md transition-colors ${showFailed ? 'bg-red-900/50 text-red-300' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
        >
          {showFailed ? 'Solo fallidos' : 'Todos'}
        </button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-500 text-xs uppercase">
                <th className="text-left px-4 py-3">Check</th>
                <th className="text-center px-3 py-3 w-20">Severidad</th>
                <th className="text-left px-3 py-3 w-48">URL</th>
                <th className="text-left px-3 py-3">Detalle</th>
                <th className="text-left px-3 py-3 w-28">Categoría</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5} className="text-center py-8 text-gray-600">Cargando...</td></tr>
              ) : checks.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-8 text-gray-600">Sin hallazgos</td></tr>
              ) : (
                checks.map((c) => {
                  const sev = severityConfig[c.severity] || severityConfig.info;
                  const isExpanded = expandedId === c.id;
                  const refLinks = getReferenceLinks(c.check_name);
                  return (
                    <Fragment key={c.id}>
                      <tr
                        onClick={() => setExpandedId(isExpanded ? null : c.id)}
                        className={`border-b border-gray-800/50 hover:bg-gray-800/50 transition-colors cursor-pointer ${isExpanded ? 'bg-gray-800/70' : ''}`}
                      >
                        <td className="px-4 py-2.5">
                          <div className="flex items-center gap-2">
                            <svg
                              className={`w-3 h-3 text-gray-600 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
                              fill="none" stroke="currentColor" viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                            </svg>
                            <div>
                              <div className="font-medium text-xs text-gray-300">{c.check_name}</div>
                              {!isExpanded && (
                                <div className="text-xs text-gray-600 mt-0.5 line-clamp-1 max-w-sm">
                                  {c.value_found || 'Fallo'}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="text-center px-3 py-2.5">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${sev.bg} ${sev.text}`}>
                            {sev.label}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="text-xs font-mono text-gray-500 truncate max-w-[180px]" title={c.url}>
                            {c.url.replace(/^https?:\/\/(www\.)?/, '')}
                          </div>
                        </td>
                        <td className="px-3 py-2.5">
                          {c.passed ? (
                            <span className="text-green-500 text-xs">OK</span>
                          ) : (
                            <span className={`text-xs ${sev.text}`}>{c.value_found || 'Fallo'}</span>
                          )}
                        </td>
                        <td className="text-center px-2 py-2.5">
                          <span className="text-gray-600 text-[10px]">{categoryLabels[c.category] || c.category}</span>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr className="bg-gray-800/30">
                          <td colSpan={5} className="px-6 py-4">
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
                              <div className="space-y-3">
                                {c.url && (
                                  <div>
                                    <div className="text-gray-500 font-medium mb-0.5">URL</div>
                                    <a href={c.url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 font-mono break-all">
                                      {c.url}
                                      <svg className="w-3 h-3 inline ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                      </svg>
                                    </a>
                                  </div>
                                )}
                                <div>
                                  <div className="text-gray-500 font-medium mb-0.5">Valor encontrado</div>
                                  <div className={`text-gray-300 break-all font-mono bg-gray-900/70 rounded px-2 py-1.5 ${c.passed ? 'text-green-400' : 'text-red-300'}`}>
                                    {c.value_found || (c.passed ? 'Correcto' : 'No detectado')}
                                  </div>
                                </div>
                              </div>

                              <div className="space-y-3">
                                {c.value_expected && (
                                  <div>
                                    <div className="text-gray-500 font-medium mb-0.5">Valor esperado</div>
                                    <div className="text-green-400 break-all font-mono bg-gray-900/70 rounded px-2 py-1.5">
                                      {c.value_expected}
                                    </div>
                                  </div>
                                )}
                                {c.recommendation && (
                                  <div>
                                    <div className="text-gray-500 font-medium mb-0.5">{c.passed ? 'Nota' : 'Recomendación'}</div>
                                    <div className={`${c.passed ? 'text-gray-400' : 'text-yellow-300'} leading-relaxed`}>
                                      {c.recommendation}
                                    </div>
                                  </div>
                                )}
                              </div>

                              <div className="lg:col-span-2">
                                <div className="flex flex-wrap gap-2 items-center">
                                  <span className="text-gray-500">Severidad:</span>
                                  <span className={`text-xs px-1.5 py-0.5 rounded ${sev.bg} ${sev.text}`}>
                                    {sev.label}
                                  </span>
                                  <span className="text-gray-700 mx-1">|</span>
                                  <span className="text-gray-500">Categoría:</span>
                                  <span className="text-gray-400">{categoryLabels[c.category] || c.category}</span>
                                  <span className="text-gray-700 mx-1">|</span>
                                  <span className="text-gray-500">Estado:</span>
                                  <span className={c.passed ? 'text-green-400' : sev.text}>
                                    {c.passed ? 'Pasó' : 'Falló'}
                                  </span>
                                </div>
                              </div>

                              {refLinks.length > 0 && (
                                <div className="lg:col-span-2 pt-2 border-t border-gray-700/50">
                                  <div className="text-gray-500 font-medium mb-1.5">Más información</div>
                                  <div className="flex flex-wrap gap-2">
                                    {refLinks.map((link) => (
                                      <a
                                        key={link.url}
                                        href={link.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-xs bg-gray-700/50 hover:bg-gray-600/50 text-blue-300 hover:text-blue-200 rounded px-2 py-1 transition-colors"
                                      >
                                        {link.label}
                                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                        </svg>
                                      </a>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })
              )}
            </tbody>
            {total > 50 && (
            <tfoot>
              <tr className="border-t border-gray-800">
                <td colSpan={5} className="text-center py-3">
                  <span className="text-xs text-gray-600">
                    {total} hallazgos &middot; Pág {page} de {Math.ceil(total / 50)}
                  </span>
                </td>
              </tr>
            </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}