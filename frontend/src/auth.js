// Cognito auth wrapper (AgentCore Identity IdP). Uses amazon-cognito-identity-js.
// When the pool env vars are absent the module runs in demo mode: any well-formed
// input registers/logs in and a synthetic token is issued, so the gate flow works
// before any backend deploy. No payment or sensitive IDs are ever collected.

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserAttribute,
} from "amazon-cognito-identity-js";

const USER_POOL_ID = import.meta.env.VITE_USER_POOL_ID || "";
const CLIENT_ID = import.meta.env.VITE_USER_POOL_CLIENT_ID || "";

export const cognitoConfigured = Boolean(USER_POOL_ID && CLIENT_ID);

let pool = null;
if (cognitoConfigured) {
  pool = new CognitoUserPool({ UserPoolId: USER_POOL_ID, ClientId: CLIENT_ID });
}

// Registers a new user. In demo mode resolves immediately.
export function register({ name, email, password }) {
  if (!cognitoConfigured) {
    return Promise.resolve({ demo: true, email });
  }
  return new Promise((resolve, reject) => {
    const attributes = [
      new CognitoUserAttribute({ Name: "email", Value: email }),
      new CognitoUserAttribute({ Name: "name", Value: name }),
    ];
    pool.signUp(email, password, attributes, [], (err, result) => {
      if (err) return reject(err);
      resolve(result);
    });
  });
}

// Logs in and returns { token, email }. token is the Cognito ID token (JWT) used
// as the Bearer credential on /api/* calls. Demo mode issues a synthetic token.
export function login({ email, password }) {
  if (!cognitoConfigured) {
    return Promise.resolve({ token: `demo.${btoa(email)}.token`, email });
  }
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool });
    const details = new AuthenticationDetails({
      Username: email,
      Password: password,
    });
    user.authenticateUser(details, {
      onSuccess: (session) => {
        resolve({ token: session.getIdToken().getJwtToken(), email });
      },
      onFailure: (err) => reject(err),
      // A fresh sign-up may require a new password challenge; surface it as an error
      // so the demo UI can inform the user without handling credentials unsafely.
      newPasswordRequired: () => {
        reject(new Error("New password required — confirm the account, then log in."));
      },
    });
  });
}
