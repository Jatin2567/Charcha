import evidence from '../data/localRoutingResults.json';

/** Saved public fixture evidence only. Never merges room state or provider measurements. */
export function localRoutingReport() {
  return structuredClone(evidence);
}
