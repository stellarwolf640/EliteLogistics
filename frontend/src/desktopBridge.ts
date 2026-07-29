declare global {
  interface Window {
    pywebview?: {
      api?: Record<string, (...args: unknown[]) => Promise<unknown>>;
    };
  }
}

export function isDesktop() {
  return Boolean(window.pywebview?.api);
}

export async function desktopCall<T = unknown>(method: string, ...args: unknown[]): Promise<T | undefined> {
  const bridge = window.pywebview?.api;
  const callable = bridge?.[method];
  if (!callable) return undefined;
  return callable(...args) as Promise<T>;
}
