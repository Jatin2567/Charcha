import { lazy } from 'react';
import type { ComponentType } from 'react';

/**
 * Route-level code splitting. Each page loads on first visit, and the loader is
 * also called on hover, focus or touch of a navigation link, so the chunk is
 * usually cached before the click lands. After the first paint all pages are
 * fetched during browser idle time, which keeps later navigation instant even
 * on a slow LAN or phone.
 */
type Loader = () => Promise<{ default: ComponentType }>;

const loaders: Record<string, Loader> = {
  '/': () => import('./pages/Home').then((m) => ({ default: m.Home })),
  '/join': () => import('./pages/Prejoin').then((m) => ({ default: m.Prejoin })),
  '/voices': () => import('./pages/VoiceStudio').then((m) => ({ default: m.VoiceStudio })),
  '/settings': () => import('./pages/Settings').then((m) => ({ default: m.Settings })),
  '/performance': () => import('./pages/Performance').then((m) => ({ default: m.Performance })),
  '/tests': () => import('./pages/TestLab').then((m) => ({ default: m.TestLab })),
  '/audio-lab': () => import('./pages/AudioLab').then((m) => ({ default: m.AudioLab })),
  '/usage': () => import('./pages/Usage').then((m) => ({ default: m.Usage })),
  '/development': () => import('./pages/DeveloperJournal').then((m) => ({ default: m.DeveloperJournal })),
  '/deployment': () => import('./pages/Deployment').then((m) => ({ default: m.Deployment })),
  '/history': () => import('./pages/Recap').then((m) => ({ default: m.HistoryPage })),
  '/recap': () => import('./pages/Recap').then((m) => ({ default: m.RecapPage })),
  '/room': () => import('./pages/Meeting').then((m) => ({ default: m.Meeting })),
};

const pending = new Map<string, Promise<{ default: ComponentType }>>();

function load(key: string) {
  let promise = pending.get(key);
  if (!promise) {
    promise = loaders[key]();
    // A failed chunk (for example a dropped LAN connection) may be retried later.
    promise.catch(() => pending.delete(key));
    pending.set(key, promise);
  }
  return promise;
}

export const pages = Object.fromEntries(
  Object.keys(loaders).map((key) => [key, lazy(() => load(key))]),
) as Record<keyof typeof loaders, ReturnType<typeof lazy>>;

/** Map a router path such as "/recap/abc" to its page key. */
export function routeKey(path: string): string | null {
  if (path === '/' || path === '') return '/';
  const first = '/' + path.split('/').filter(Boolean)[0];
  return first in loaders ? first : null;
}

export function preloadRoute(path: string): void {
  const key = routeKey(path);
  if (key) void load(key).catch(() => {});
}

/** Warm every page chunk once the browser is idle after the first render. */
export function preloadAllWhenIdle(): void {
  const run = () => {
    for (const key of Object.keys(loaders)) void load(key).catch(() => {});
  };
  const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number })
    .requestIdleCallback;
  if (idle) idle(run, { timeout: 3000 });
  else window.setTimeout(run, 1500);
}

/**
 * Prefetch the page behind any in-app hash link the pointer or focus reaches.
 * One delegated listener covers every link, including ones added later.
 */
export function installLinkPrefetch(): void {
  const handler = (event: Event) => {
    const link = (event.target as Element | null)?.closest?.('a[href^="#/"]');
    if (link) preloadRoute(link.getAttribute('href')!.slice(1).split('?')[0]);
  };
  for (const type of ['pointerover', 'focusin', 'touchstart']) {
    document.addEventListener(type, handler, { passive: true, capture: true });
  }
}
