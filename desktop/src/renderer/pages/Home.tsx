import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, Project } from '../lib/api';
import NewProjectForm from '../components/NewProjectForm';

export default function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const navigate = useNavigate();

  useEffect(() => {
    checkBackend();
  }, []);

  async function checkBackend() {
    try {
      const res = await fetch('http://127.0.0.1:8000/health');
      if (res.ok) {
        setBackendStatus('online');
        loadProjects();
      } else {
        setBackendStatus('offline');
      }
    } catch {
      setBackendStatus('offline');
      setTimeout(checkBackend, 2000);
    }
  }

  async function loadProjects() {
    try {
      setLoading(true);
      const data = await api.listProjects();
      setProjects(data.projects);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('¿Eliminar este proyecto y todos sus datos?')) return;
    try {
      await api.deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function handleCreated() {
    setShowForm(false);
    loadProjects();
  }

  const statusColors: Record<string, string> = {
    idle: 'bg-gray-600',
    crawling: 'bg-blue-500 animate-pulse',
    paused: 'bg-yellow-500',
    completed: 'bg-green-500',
    failed: 'bg-red-500',
  };

  const statusLabels: Record<string, string> = {
    idle: 'En espera',
    crawling: 'Crawleando',
    paused: 'Pausado',
    completed: 'Completado',
    failed: 'Fallido',
  };

  if (backendStatus === 'checking') {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4" />
          <p className="text-gray-400">Conectando con el backend...</p>
        </div>
      </div>
    );
  }

  if (backendStatus === 'offline') {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-center">
          <div className="text-red-500 text-4xl mb-4">&#x26A0;</div>
          <p className="text-red-400 text-lg mb-2">Backend no disponible</p>
          <p className="text-gray-500">Esperando conexión con el servidor Python...</p>
          <button
            onClick={checkBackend}
            className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm transition-colors"
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">WebAudit</h1>
          <p className="text-gray-500 text-sm mt-1">Auditoría integral de sitios web</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors"
        >
          + Nuevo Proyecto
        </button>
      </header>

      {showForm && (
        <NewProjectForm
          onCreate={handleCreated}
          onCancel={() => setShowForm(false)}
        />
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 rounded-lg px-4 py-3 mb-6 text-sm">
          {error}
          <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-gray-500">Cargando proyectos...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-gray-600 text-5xl mb-4">&#x1F50D;</div>
          <p className="text-gray-500 text-lg mb-2">No hay proyectos aún</p>
          <p className="text-gray-600 text-sm">Crea tu primer proyecto para empezar a auditar sitios web</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {projects.map((project) => (
            <div
              key={project.id}
              onClick={() => navigate(`/project/${project.id}`)}
              className="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-xl p-5 cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${statusColors[project.status] || 'bg-gray-600'}`} />
                  <div>
                    <h3 className="font-semibold text-gray-100">{project.name}</h3>
                    <p className="text-gray-500 text-sm mt-0.5">{project.seed_url}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
                    {statusLabels[project.status] || project.status}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(project.id); }}
                    className="text-gray-600 hover:text-red-400 transition-colors"
                    title="Eliminar proyecto"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="text-xs text-gray-600 mt-3">
                Creado: {new Date(project.created_at).toLocaleDateString('es-CO', {
                  year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
