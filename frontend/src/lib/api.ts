import { getAccessToken } from './auth';

const API_BASE_URL = normaliseApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

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

export type AssessmentSummary = {
  assessmentId: string;
  frameworkId: string;
  organisationId: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  score: number;
  completedAt: string | null;
  reportS3Key: string | null;
  currentSectionId: string;
  previousAssessmentId?: string | null;
  sectionScores?: Array<{ sectionId: string; score: number }>;
  maturityLevel?: string;
  previousScore?: number | null;
  scoreImprovement?: number | null;
  improvementPercent?: number | null;
  remediationActions?: RemediationAction[];
  remediationProgress?: RemediationProgress;
};

export type RemediationActionStatus = 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

export type RemediationAction = {
  actionId: string;
  sectionId: string;
  questionId: string;
  gapId: string;
  gapTitle: string;
  priority: 'HIGH' | 'MEDIUM';
  actionText: string;
  status: RemediationActionStatus;
  owner?: string | null;
  dueDate?: string | null;
};

export type RemediationProgress = {
  actionsCompletedPercent: number;
  gapsResolvedPercent: number;
  totalActions: number;
  completedActions: number;
  totalGaps: number;
  resolvedGaps: number;
  overallPercent: number;
};

export type AssessmentDetail = AssessmentSummary & {
  sections: Array<{
    sectionId: string;
    name: string;
    description?: string;
    questions?: Array<{
      questionId: string;
      text: string;
      helpText?: string;
      guidance?: {
        title?: string;
        risk?: string;
        action?: string;
        actions?: string[];
        evidence?: string[];
      };
    }>;
  }>;
  currentSection: {
    sectionId: string;
    name: string;
    description?: string;
    questions?: Array<{
      questionId: string;
      text: string;
      helpText?: string;
      guidance?: {
        title?: string;
        risk?: string;
        action?: string;
        actions?: string[];
        evidence?: string[];
      };
    }>;
  } | null;
  framework: {
    frameworkId: string;
    name: string;
    version: string;
    description: string;
    sections: Array<{
      id: string;
      title: string;
      summary?: string;
      questions?: Array<{
        id: string;
        text: string;
        helpText?: string;
      }>;
    }>;
  };
  responses: Record<string, Array<{ questionId: string; value: number | string }>>;
  remediationActions?: RemediationAction[];
  remediationProgress?: RemediationProgress;
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

export async function getBootstrap(frameworkId?: string): Promise<ApiResult<BootstrapResponse>> {
  const query = frameworkId ? `?framework_id=${encodeURIComponent(frameworkId)}` : '';
  return request<BootstrapResponse>(`/app/bootstrap${query}`, {
    method: 'GET',
  });
}

export async function getFrameworks(): Promise<ApiResult<FrameworkSummary[]>> {
  return request<FrameworkSummary[]>('/frameworks', {
    method: 'GET',
  });
}

export async function getHealth(): Promise<ApiResult<{ ok: boolean; service: string }>> {
  return request<{ ok: boolean; service: string }>(
    '/health',
    {
      method: 'GET',
    },
    {
      requiresAuth: false,
    },
  );
}

export async function createOrganisation(
  payload: CreateOrganisationInput,
): Promise<ApiResult<OrganisationSummary>> {
  return request<OrganisationSummary>('/organisations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function createAssessment(
  frameworkId: string,
): Promise<ApiResult<AssessmentSummary>> {
  return request<AssessmentSummary>('/assessments', {
    method: 'POST',
    body: JSON.stringify({ frameworkId }),
  });
}

export async function getAssessments(
  frameworkId?: string,
): Promise<ApiResult<AssessmentSummary[]>> {
  const query = frameworkId ? `?framework_id=${encodeURIComponent(frameworkId)}` : '';
  return request<AssessmentSummary[]>(`/assessments${query}`, {
    method: 'GET',
  });
}

export async function getAssessmentReportUrl(
  assessmentId: string,
): Promise<ApiResult<{ url: string }>> {
  const response = await request<{ url?: string; reportUrl?: string; signedUrl?: string }>(
    `/assessments/${assessmentId}/report`,
    {
      method: 'GET',
    },
  );

  if (!response.ok) {
    return response as ApiResult<{ url: string }>;
  }

  const normalizedUrl = response.data?.url ?? response.data?.reportUrl ?? response.data?.signedUrl;
  if (!normalizedUrl) {
    return {
      ok: false,
      status: response.status,
      error: 'Report URL is missing from response.',
    };
  }

  return {
    ok: true,
    status: response.status,
    data: { url: normalizedUrl },
  };
}

export async function getAssessment(
  assessmentId: string,
): Promise<ApiResult<AssessmentDetail>> {
  return request<AssessmentDetail>(`/assessments/${assessmentId}`, {
    method: 'GET',
  });
}

export async function saveAssessmentResponses(
  assessmentId: string,
  payload: {
    sectionId: string;
    responses: Array<{ questionId: string; value: number | string }>;
  },
): Promise<ApiResult<AssessmentSummary>> {
  return request<AssessmentSummary>(`/assessments/${assessmentId}/responses`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function restartAssessment(
  assessmentId: string,
): Promise<ApiResult<AssessmentSummary>> {
  return request<AssessmentSummary>(`/assessments/${assessmentId}/restart`, {
    method: 'POST',
  });
}

export async function updateRemediationActions(
  assessmentId: string,
  actions: Array<{
    actionId: string;
    status: RemediationActionStatus;
    owner?: string | null;
    dueDate?: string | null;
  }>,
): Promise<ApiResult<AssessmentSummary>> {
  return request<AssessmentSummary>(`/assessments/${assessmentId}/remediation`, {
    method: 'POST',
    body: JSON.stringify({ actions }),
  });
}

type RequestOptions = {
  requiresAuth?: boolean;
};

async function request<T>(
  path: string,
  init: RequestInit,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  if (!API_BASE_URL) {
    return {
      ok: false,
      status: 500,
      error: 'VITE_API_BASE_URL is not configured.',
    };
  }

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(init.headers ?? {}),
  };

  if (options.requiresAuth ?? true) {
    const accessToken = await getAccessToken();

    if (!accessToken) {
      return {
        ok: false,
        status: 401,
        error: 'No access token is available. Sign in first.',
      };
    }

    headers.Authorization = `Bearer ${accessToken}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
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

function normaliseApiBaseUrl(value: string | undefined): string {
  if (!value) {
    return '';
  }

  return value.trim().replace(/\/$/, '');
}
