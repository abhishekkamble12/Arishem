// Optional features, off by default to match the backend's ENABLE_* flags.
// Set VITE_ENABLE_MEETINGS=true at build time to show meetings.
export const FEATURES = {
  meetings: import.meta.env.VITE_ENABLE_MEETINGS === 'true',
  // Google sign-in shows exactly when a client id was supplied at build time.
  // A separate on/off flag would allow two broken states: a button with no client
  // id behind it, and a configured client id with no button.
  googleAuth: Boolean(import.meta.env.VITE_GOOGLE_CLIENT_ID),
} as const;
