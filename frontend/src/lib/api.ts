import { getAccessToken } from './auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '');

export type FrameworksResult = {
  ok: boolean;
  status: number;
  data?: unknown;
  error?: string;
};

export async function getFrameworks(): Promise<FrameworksResult> {
  if (!API_BASE_URL) {
    return {
      ok: false,
      status: 500,
      error: 'VITE_API_BASE_URL is not configured.',
    };
  }

  const accessToken = await getAccessToken();

  if (!accessToken) {
    return {
      ok: false,
      status: 401,
      error: 'No access token is available. Sign in first.',
    };
  }

  const response = await fetch(`${API_BASE_URL}/frameworks`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    return {
      ok: false,
      status: response.status,
      data: payload,
      error: `Framework request failed with status ${response.status}.`,
    };
  }

  return {
    ok: true,
    status: response.status,
    data: payload,
  };
}
