// A dependency-free hop between the plain API client and the React licence
// context, so the client can flag an expired licence (HTTP 402) without
// importing React code (which would create an import cycle).
let onExpired: (() => void) | null = null;

export function setLicenseExpiredHandler(fn: (() => void) | null) {
  onExpired = fn;
}

export function reportLicenseExpired() {
  onExpired?.();
}
