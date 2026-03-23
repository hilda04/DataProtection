import 'aws-amplify/auth/enable-oauth-listener';

import { Amplify } from 'aws-amplify';
import { fetchAuthSession, getCurrentUser, signInWithRedirect, signOut } from 'aws-amplify/auth';

const {
  VITE_AWS_REGION,
  VITE_COGNITO_USER_POOL_ID,
  VITE_COGNITO_APP_CLIENT_ID,
  VITE_COGNITO_DOMAIN,
  VITE_REDIRECT_SIGN_IN,
  VITE_REDIRECT_SIGN_OUT,
} = import.meta.env;

let isConfigured = false;

function asArray(value: string | undefined): string[] {
  return value ? value.split(',').map((entry) => entry.trim()).filter(Boolean) : [];
}

export function configureAmplify(): void {
  if (isConfigured) {
    return;
  }

  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: VITE_COGNITO_USER_POOL_ID,
        userPoolClientId: VITE_COGNITO_APP_CLIENT_ID,
        loginWith: {
          oauth: {
            domain: VITE_COGNITO_DOMAIN,
            scopes: ['openid', 'email', 'profile'],
            redirectSignIn: asArray(VITE_REDIRECT_SIGN_IN),
            redirectSignOut: asArray(VITE_REDIRECT_SIGN_OUT),
            responseType: 'code',
          },
        },
      },
    },
  }, {
    ssr: false,
  });

  isConfigured = true;
}

export async function login(): Promise<void> {
  configureAmplify();
  await signInWithRedirect();
}

export async function logout(): Promise<void> {
  configureAmplify();
  await signOut();
}

export async function getAccessToken(): Promise<string | null> {
  configureAmplify();
  const session = await fetchAuthSession();
  return session.tokens?.accessToken?.toString() ?? null;
}

export async function isSignedIn(): Promise<boolean> {
  configureAmplify();

  try {
    await getCurrentUser();
    return true;
  } catch {
    return false;
  }
}

export function getAuthConfigSummary(): { region: string; userPoolId: string } {
  return {
    region: VITE_AWS_REGION || "Not set",
    userPoolId: VITE_COGNITO_USER_POOL_ID || "Not set",
  };
}
