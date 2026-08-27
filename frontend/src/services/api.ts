import axios from 'axios';

export const TOKEN_KEY = 'token';
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem(TOKEN_KEY);
      window.location.assign('/login');
    }
    return Promise.reject(error);
  },
);

export const authApi = {
  login: (payload: { email: string; password: string }) => api.post('/api/auth/login', payload),
  register: (payload: { email: string; password: string }) => api.post('/api/auth/register', payload),
  me: () => api.get('/api/auth/me'),
};

export const getData = <T>(url: string) => api.get<T>(url).then((r) => r.data);
