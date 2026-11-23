const API = '/api';
export async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json', ...(options.headers || {})};
  const token = localStorage.getItem('claim_token');
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API}${path}`, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || '请求失败');
  return data;
}
export const get = path => api(path);
export const post = (path, body) => api(path, {method:'POST', body: JSON.stringify(body)});
