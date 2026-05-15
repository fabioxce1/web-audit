import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api, TreeNode } from '../lib/api';

export default function UrlTree() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const projectId = Number(id);

  const [tree, setTree] = useState<TreeNode[]>([]);
  const [rootUrl, setRootUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    loadTree();
  }, [projectId]);

  async function loadTree() {
    try {
      const data = await api.getTree(projectId);
      setTree(data.tree);
      setRootUrl(data.root_url);
      // Auto-expand first two levels
      const expandedIds = new Set<number>();
      for (const node of data.tree) {
        expandLevel(node, 0, expandedIds);
      }
      setExpanded(expandedIds);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  function expandLevel(node: TreeNode, level: number, ids: Set<number>) {
    if (level < 2) ids.add(node.id);
    for (const child of node.children) {
      expandLevel(child, level + 1, ids);
    }
  }

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const statusColor = (code: number | null): string => {
    if (!code || code === 0) return 'bg-red-500';
    if (code >= 200 && code < 300) return 'bg-green-500';
    if (code >= 300 && code < 400) return 'bg-yellow-500';
    if (code >= 400 && code < 500) return 'bg-orange-500';
    return 'bg-red-600';
  };

  function TreeNodeComponent({ node, level = 0 }: { node: TreeNode; level?: number }) {
    const isOpen = expanded.has(node.id);
    const hasChildren = node.children.length > 0;

    return (
      <div>
        <div
          className="flex items-center gap-2 py-1.5 hover:bg-gray-800/50 rounded px-2 cursor-pointer transition-colors group"
          style={{ paddingLeft: `${12 + level * 20}px` }}
          onClick={() => hasChildren && toggleExpand(node.id)}
        >
          {hasChildren ? (
            <svg
              className={`w-3.5 h-3.5 text-gray-600 transition-transform flex-shrink-0 ${isOpen ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          ) : (
            <span className="w-3.5 flex-shrink-0" />
          )}

          <div className={`w-2 h-2 rounded-full flex-shrink-0 ${node.is_broken ? 'bg-orange-500 ring-2 ring-orange-500/30' : statusColor(node.status_code)}`} />

          <div className="min-w-0 flex-1">
            <div className="text-xs font-mono text-gray-400 truncate" title={node.url}>
              {node.normalized_url.replace(rootUrl.replace(/https?:\/\//, ''), '') || '/'}
            </div>
            {node.title && (
              <div className="text-xs text-gray-600 truncate mt-0.5">{node.title}</div>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            {node.status_code && (
              <span className="text-xs text-gray-600 font-mono">{node.status_code}</span>
            )}
            {node.content_type && (
              <span className="text-xs bg-gray-800 text-gray-600 rounded px-1">{node.content_type.split('/').pop()}</span>
            )}
          </div>
        </div>

        {hasChildren && isOpen && (
          <div>
            {node.children.map((child) => (
              <TreeNodeComponent key={child.id} node={child} level={level + 1} />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="flex items-center gap-4 mb-6">
        <button onClick={() => navigate(`/project/${projectId}`)} className="text-gray-600 hover:text-gray-400 transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 className="text-xl font-bold">Árbol de URLs</h1>
          <p className="text-gray-500 text-sm">{rootUrl}</p>
        </div>
        <button onClick={loadTree} className="ml-auto px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
          Refrescar
        </button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        {tree.length === 0 ? (
          <p className="text-gray-600 text-sm text-center py-8">No hay URLs mapeadas aún. Inicia un crawling primero.</p>
        ) : (
          tree.map((node) => (
            <TreeNodeComponent key={node.id} node={node} />
          ))
        )}
      </div>

      <div className="mt-4 flex gap-4 text-xs text-gray-600 flex-wrap">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-green-500" /> 2xx</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-yellow-500" /> 3xx</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-orange-500" /> 4xx</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-600" /> 5xx</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-500" /> Error</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-orange-500 ring-2 ring-orange-500/30" /> Rota</span>
      </div>
    </div>
  );
}
