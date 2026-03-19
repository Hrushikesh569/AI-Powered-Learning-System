// Centralized API client for backend integration
const _envBase = (import.meta.env.VITE_API_URL || '').trim();
const _normalizedBase = (() => {
  if (!_envBase) return 'http://localhost:8000/api/v1';
  // Accept either a root URL (http://localhost:8000) or full API prefix.
  return /\/api\/v1\/?$/.test(_envBase)
    ? _envBase.replace(/\/$/, '')
    : `${_envBase.replace(/\/$/, '')}/api/v1`;
})();
const BASE_URL = _normalizedBase;
const TOKEN_KEY = 'authToken';

export function getAuthToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch (_err) {
    return null;
  }
}

export function setAuthToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
  } catch (_err) {
    // Ignore storage errors in restricted environments.
  }
}

export function clearAuthToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch (_err) {
    // Ignore storage errors in restricted environments.
  }
}

export async function apiRequest(endpoint, method = 'GET', body = null, token = null) {
  const headers = { 'Content-Type': 'application/json' };
  const resolvedToken = token ?? getAuthToken();
  if (resolvedToken) headers['Authorization'] = `Bearer ${resolvedToken}`;
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiUpload(endpoint, formData, token = null) {
  const headers = {};
  const resolvedToken = token ?? getAuthToken();
  if (resolvedToken) headers['Authorization'] = `Bearer ${resolvedToken}`;
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// AGENT ENDPOINTS
export const agentAPI = {
  // User Profiling
  getProfileLabel: (token) => apiRequest('/profiling/label', 'GET', null, token),

  // Learning Schedule Generator
  generateSchedule: (data, token) => apiRequest('/schedule/generate', 'POST', data, token),

  // Progress Monitoring
  logProgress: (data, token) => apiRequest('/progress/log', 'POST', data, token),
  predictProgress: (data, token) => apiRequest('/progress/predict', 'POST', data, token),

  // Stress Logging
  logStress: (data, token) => apiRequest('/stress/log', 'POST', data, token),

  // Motivation
  logMotivation: (data, token) => apiRequest('/motivation/log', 'POST', data, token),
  classifyMotivation: (data, token) => apiRequest('/motivation/classify', 'POST', data, token),
  getMotivationTips: (token) => apiRequest('/motivation/tips', 'GET', null, token),

  // Community
  getPeerCompatibility: (token) => apiRequest('/community/peers', 'GET', null, token),
  listStudyGroups: (token) => apiRequest('/community/groups', 'GET', null, token),

  // Group Matching
  matchGroup: (data, token) => apiRequest('/group/match', 'POST', data, token),
  getMyGroup: (token) => apiRequest('/group/my-group', 'GET', null, token),

  // Profiling
  classifyProfile: (data, token) => apiRequest('/profiling/classify', 'POST', data, token),

  // Progress dashboard
  getProgressDashboard: (token) => apiRequest('/progress/dashboard', 'GET', null, token),

  // Content / uploads
  uploadScheduleDoc: (formData, token) => apiUpload('/content/upload-schedule', formData, token),
  uploadStudyMaterial: (formData, token) => apiUpload('/content/upload-material', formData, token),

  // Auth
  login: (data) => apiRequest('/auth/login', 'POST', data),
  register: (data) => apiRequest('/auth/register', 'POST', data),
  updateProfile: (data, token) => apiRequest('/auth/profile', 'PATCH', data, token),

  // User
  getMe: (token) => apiRequest('/users/me', 'GET', null, token),
  updateMe: (data, token) => apiRequest('/users/me', 'PATCH', data, token),

  // Stress
  logStressAnalysis: (token) => apiRequest('/stress/analysis', 'GET', null, token),

  // Alerts
  listAlerts: (token) => apiRequest('/alerts', 'GET', null, token),

  // ── Community feed ──────────────────────────────────────────────────────
  getGroupFeed: (groupId, limit = 30, offset = 0, token) =>
    apiRequest(`/community/groups/${groupId}/feed?limit=${limit}&offset=${offset}`, 'GET', null, token),
  createPost: (groupId, data, token) =>
    apiRequest(`/community/groups/${groupId}/posts`, 'POST', data, token),
  likePost: (postId, token) =>
    apiRequest(`/community/posts/${postId}/like`, 'POST', null, token),
  getComments: (postId, token) =>
    apiRequest(`/community/posts/${postId}/comments`, 'GET', null, token),
  addComment: (postId, data, token) =>
    apiRequest(`/community/posts/${postId}/comments`, 'POST', data, token),
  deletePost: (postId, token) =>
    apiRequest(`/community/posts/${postId}`, 'DELETE', null, token),
  deleteComment: (commentId, token) =>
    apiRequest(`/community/comments/${commentId}`, 'DELETE', null, token),

  // ── File / Subject management ───────────────────────────────────────────
  listSubjects: (token) => apiRequest('/content/subjects', 'GET', null, token),
  listFiles: (subject, token) =>
    apiRequest(`/content/files${subject ? `?subject=${encodeURIComponent(subject)}` : ''}`, 'GET', null, token),
  getFileTopics: (materialId, token) =>
    apiRequest(`/content/files/${materialId}/topics`, 'GET', null, token),
  deleteFile: (materialId, token) =>
    apiRequest(`/content/files/${materialId}`, 'DELETE', null, token),
  openFile: async (materialId, filename) => {
    const token = getAuthToken();
    const resp = await fetch(`${BASE_URL}/content/files/${materialId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) throw new Error('Could not open file');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const win = window.open(url, '_blank');
    // Clean up the object URL once the new tab has loaded
    if (win) win.addEventListener('load', () => URL.revokeObjectURL(url), { once: true });
    else setTimeout(() => URL.revokeObjectURL(url), 60000);
  },

  // ── AI Study Chatbot ────────────────────────────────────────────────────
  chatWithBot: (data, token) => apiRequest('/content/chat', 'POST', data, token),

  // ── Intelligent Scheduling (LLM-powered) ───────────────────────────────
  getIntelligentSchedule: (data, token) =>
    apiRequest('/schedule/intelligent', 'POST', data, token),
  getAdaptiveSchedule: (data, token) =>
    apiRequest('/schedule/adaptive', 'POST', data, token),
  // Subject→Unit→Topic hierarchy for the topic picker
  getSubjectHierarchy: (token) =>
    apiRequest('/schedule/subject-hierarchy', 'GET', null, token),
  getFileAnalysis: (materialId, token) =>
    apiRequest(`/content/files/${materialId}/analysis`, 'GET', null, token),
  triggerFileAnalysis: (materialId, token) =>
    apiRequest(`/content/files/${materialId}/analyze`, 'POST', null, token),
  // Hierarchical topics: subject → unit → topic with scheduling metadata
  getFileTopicsHierarchical: (materialId, token) =>
    apiRequest(`/content/files/${materialId}/topics-hierarchical`, 'GET', null, token),
  // Mark a topic as completed
  markTopicComplete: (topicId, notes = '', token) =>
    apiRequest(`/content/scheduled-topics/${topicId}/complete`, 'PATCH', { completion_notes: notes }, token),
  // Reschedule a topic to a new date
  rescheduleTopics: (topicId, newDate, reason = '', token) =>
    apiRequest(`/content/scheduled-topics/${topicId}/reschedule`, 'PATCH', { new_scheduled_date: newDate, reason }, token),
  // Query scheduled topics by status/material/subject
  queryScheduledTopics: (filters = {}, token) => {
    const params = new URLSearchParams();
    if (filters.material_id) params.append('material_id', filters.material_id);
    if (filters.subject) params.append('subject', filters.subject);
    if (filters.status) params.append('status', filters.status);
    return apiRequest(`/content/scheduled-topics?${params}`, 'GET', null, token);
  },
  // Topic-page lookup — find PDFs that cover a topic + what page
  getTopicPages: (topic, subject = '', token) => {
    const params = new URLSearchParams({ topic });
    if (subject) params.append('subject', subject);
    return apiRequest(`/content/topic-pages?${params}`, 'GET', null, token);
  },
  getTopicResources: (topic, subject = '', limit = 6, token) => {
    const params = new URLSearchParams({ topic, limit: String(limit) });
    if (subject) params.append('subject', subject);
    return apiRequest(`/content/topic-resources?${params}`, 'GET', null, token);
  },
  updateTopicFeedback: (data, token) =>
    apiRequest('/schedule/topic-feedback', 'POST', data, token),

  // ── SHAP Explanations ───────────────────────────────────────────────────
  getProgressExplanation: (token) => apiRequest('/explain/progress', 'GET', null, token),
  getProfileExplanation:  (token) => apiRequest('/explain/profile',  'GET', null, token),
};
