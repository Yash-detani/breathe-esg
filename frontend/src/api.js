import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: `${BASE}/api`,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to every request
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE}/api/auth/token/refresh/`, { refresh });
          localStorage.setItem('access_token', data.access);
          original.headers.Authorization = `Bearer ${data.access}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = '/login';
        }
      } else {
        localStorage.clear();
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

export const login = async (username, password) => {
  const { data } = await axios.post(`${BASE}/api/auth/token/`, { username, password });
  localStorage.setItem('access_token', data.access);
  localStorage.setItem('refresh_token', data.refresh);
  return data;
};

export const getMe = () => api.get('/me/').then(r => r.data);
export const getClients = () => api.get('/clients/').then(r => r.data);
export const getDashboard = (clientId, year) =>
  api.get('/dashboard/', { params: { client_id: clientId, year } }).then(r => r.data);

export const getBatches = (clientId) =>
  api.get('/batches/', { params: { client_id: clientId } }).then(r => r.data);
export const getBatch = (id) => api.get(`/batches/${id}/`).then(r => r.data);
export const getBatchFailedRows = (id) =>
  api.get(`/batches/${id}/failed_rows/`).then(r => r.data);

export const getRecords = (params) =>
  api.get('/records/', { params }).then(r => r.data);
export const getRecord = (id) => api.get(`/records/${id}/`).then(r => r.data);
export const reviewRecord = (id, action, note) =>
  api.patch(`/records/${id}/review/`, { action, note }).then(r => r.data);
export const bulkReview = (record_ids, action, note) =>
  api.post('/records/bulk_review/', { record_ids, action, note }).then(r => r.data);

export const uploadFile = (formData) =>
  api.post('/upload/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export default api;
