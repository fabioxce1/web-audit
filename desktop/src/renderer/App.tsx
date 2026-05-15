import { HashRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import ProjectDetail from './pages/ProjectDetail';
import UrlTree from './pages/UrlTree';

export default function App() {
  return (
    <HashRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/project/:id" element={<ProjectDetail />} />
          <Route path="/project/:id/tree" element={<UrlTree />} />
        </Routes>
      </div>
    </HashRouter>
  );
}
