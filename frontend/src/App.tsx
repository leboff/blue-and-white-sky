import { Link, Route, Routes } from 'react-router-dom'
import Admin from './pages/Admin'
import DevFeed from './pages/DevFeed'

function App() {
  return (
    <div style={{ minHeight: '100vh', background: '#f1f5f9' }}>
      <nav style={{ padding: '1rem 1.5rem', background: '#1e293b', color: '#fff' }}>
        <Link to="/" style={{ color: '#fff', marginRight: '1rem' }}>Admin</Link>
        <Link to="/dev" style={{ color: '#fff' }}>Dev Feed</Link>
      </nav>
      <main style={{ maxWidth: '56rem', margin: '0 auto', padding: '1.5rem' }}>
        <Routes>
          <Route path="/" element={<Admin />} />
          <Route path="/dev" element={<DevFeed />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
