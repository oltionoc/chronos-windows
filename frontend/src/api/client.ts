// Typed fetch wrapper for the chronos API (BLUEPRINT.md Section 4).
// Base path defaults to /api/v1, overridable via VITE_API_BASE_URL at build time
// (see FRONTEND_NOTES.md — the nginx frontend container is expected to proxy /api
// to the `api` service in Docker Compose, so the default works unmodified in prod).
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api/v1';

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message || `API request failed with status ${status}`);
    this.status = status;
    this.body = body;
  }
}

type QueryValue = string | number | boolean | undefined | null;

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, QueryValue>;
}

function buildQuery(query?: Record<string, QueryValue>): string {
  if (!query) return '';
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

function extractMessage(body: unknown): string | undefined {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === 'string') return b.detail;
    if (typeof b.message === 'string') return b.message;
  }
  return undefined;
}

// All requests send credentials so the httpOnly JWT session cookie set by
// POST /auth/login (BLUEPRINT.md Section 6.1) is included automatically.
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query } = options;
  const res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const data = isJson ? await res.json().catch(() => undefined) : undefined;

  if (!res.ok) {
    throw new ApiError(res.status, data, extractMessage(data));
  }

  return data as T;
}

// For CSV bulk-import uploads (multipart/form-data — no Content-Type header,
// the browser sets the multipart boundary itself).
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  });

  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const data = isJson ? await res.json().catch(() => undefined) : undefined;

  if (!res.ok) {
    throw new ApiError(res.status, data, extractMessage(data));
  }

  return data as T;
}

// For binary downloads (payslip PDFs).
export async function apiDownload(
  path: string,
  query?: Record<string, QueryValue>
): Promise<{ blob: Blob; filename: string | null }> {
  const res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, {
    credentials: 'include',
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = undefined;
    }
    throw new ApiError(res.status, body, extractMessage(body));
  }
  const disposition = res.headers.get('content-disposition');
  const match = disposition?.match(/filename="?([^"]+)"?/);
  const blob = await res.blob();
  return { blob, filename: match ? match[1] : null };
}
