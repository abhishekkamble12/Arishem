// Optional features, off by default to match the backend's ENABLE_* flags.
// Set VITE_ENABLE_MEETINGS=true / VITE_ENABLE_SOCIAL_AUTH=true at build time to show them.
export const FEATURES = {
  meetings: import.meta.env.VITE_ENABLE_MEETINGS === 'true',
  socialAuth: import.meta.env.VITE_ENABLE_SOCIAL_AUTH === 'true',
} as const;
