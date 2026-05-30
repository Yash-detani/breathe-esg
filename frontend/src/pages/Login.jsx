import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api';
import { useAuth } from '../AuthContext';
import { Leaf, Lock } from 'lucide-react';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const navigate = useNavigate();
  const { loadUser } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      await loadUser();
      navigate('/dashboard');
    } catch (err) {
      setError('Invalid username or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="gap-4" style={{ marginBottom: 4 }}>
          <Leaf size={18} color="var(--green)" />
          <div className="login-logo">Breathe ESG</div>
        </div>
        <div className="login-tagline">Emissions ingestion & review platform</div>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input
              className="form-input"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              required
              autoComplete="username"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              className="form-input"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', marginTop: 8 }}
          >
            <Lock size={14} />
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="login-hint">
          <div style={{ color: 'var(--text-dim)', marginBottom: 6, fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Demo credentials</div>
          <div>admin / <span style={{ color: 'var(--green)' }}>demo1234</span></div>
          <div>analyst / <span style={{ color: 'var(--green)' }}>demo1234</span></div>
        </div>
      </div>
    </div>
  );
}
