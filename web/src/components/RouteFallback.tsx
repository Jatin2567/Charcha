/** Shown only while a page chunk downloads for the first time. */
export function RouteFallback() {
  return <div className="route-fallback" role="status" aria-label="Loading page" />;
}
