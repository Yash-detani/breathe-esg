import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getMe } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [clients, setClients] = useState([]);
  const [activeClient, setActiveClient] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('access_token');
    if (!token) { setLoading(false); return; }
    try {
      const me = await getMe();
      setUser(me.user);
      setClients(me.clients);
      const saved = localStorage.getItem('active_client');
      const first = me.clients[0];
      if (saved) {
        const found = me.clients.find(c => c.id === saved);
        setActiveClient(found || first || null);
      } else {
        setActiveClient(first || null);
      }
    } catch {
      localStorage.clear();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUser(); }, [loadUser]);

  const logout = () => {
    localStorage.clear();
    setUser(null);
    setClients([]);
    setActiveClient(null);
  };

  const switchClient = (c) => {
    setActiveClient(c);
    localStorage.setItem('active_client', c.id);
  };

  return (
    <AuthContext.Provider value={{ user, clients, activeClient, loading, loadUser, logout, switchClient }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
