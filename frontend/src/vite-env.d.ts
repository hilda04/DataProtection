/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_AWS_REGION?: string;
  readonly VITE_COGNITO_USER_POOL_ID?: string;
  readonly VITE_COGNITO_APP_CLIENT_ID?: string;
  readonly VITE_COGNITO_DOMAIN?: string;
  readonly VITE_REDIRECT_SIGN_IN?: string;
  readonly VITE_REDIRECT_SIGN_OUT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
