import { getAccessToken } from './auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '');

type ApiResult<T> = {
  ok: boolean;
  status: number;
  data?: T;
  error?: string;
};

export type UserSummary = {
  sub: string;
  email: string;
};

export type OrganisationSummary = {
  organisationId: string;
  name: string;
  sector: string;
  size: string;
  country: string;
  primaryContactName: string;
  primaryContactEmail: string;
  createdBy: string;
  createdAt: string;
};

export type FrameworkSummary = {
  frameworkId: string;
  name: string;
  version: string;
  description: string;
  sections: Array<{
    sectionId: string;
    name: string;
  }>;
};

export type BootstrapResponse = {
  user: UserSummary;
  hasOrganisation: boolean;
  organisation: OrganisationSummary | null;
  frameworks: FrameworkSummary[];
};

export type CreateOrganisationInput = {
  name: string;
  sector: string;
  size: string;
  country: string;
  primaryContactName: string;
  primaryContactEmail: string;
};

export async function getBootstrap(): Promise<ApiResult<BootstrapResponse>> {
  return request<BootstrapResponse>('/app/bootstrap', {
    method: 'GET',
  });
}

export async function getFrameworks(): Promise<ApiResult<FrameworkSummary[]>> {
  return request<FrameworkSummary[]>('/frameworks', {
    method: 'GET',
  });
}

export async function createOrganisation(
  payload: CreateOrganisationInput,
): Promise<ApiResult<OrganisationSummary>> {
  return request<OrganisationSummary>('/organisations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

async function request<T>(path: string, init: RequestInit): Promise<ApiResult<T>> {
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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload !== null && 'message' in payload
        ? String(payload.message)
        : `Request failed with status ${response.status}.`;

    return {
      ok: false,
      status: response.status,
      data: payload as T,
      error: message,
    };
  }

  return {
    ok: true,
    status: response.status,
    data: payload as T,
  };
}
