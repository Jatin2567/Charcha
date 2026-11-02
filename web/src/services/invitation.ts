/** A URL's shape cannot establish reachability or certificate trust on another device. */
export function invitationScope(href: string) {
  const url = new URL(href);
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  const loopback =
    host === 'localhost' || host.endsWith('.localhost') || host === '::1' || /^127\./.test(host);
  return {
    url: `${url.origin}${url.pathname}${url.hash}`,
    kind: loopback
      ? ('same-computer' as const)
      : url.protocol !== 'https:'
        ? ('needs-https' as const)
        : ('device-link' as const),
    title: loopback
      ? 'This invitation works on this computer only'
      : url.protocol !== 'https:'
        ? 'A secure address is needed for another device'
        : 'Check this invitation on the second device',
    detail: loopback
      ? 'Use another Chrome profile or Incognito on this laptop. On a second device, localhost points to that device itself.'
      : url.protocol !== 'https:'
        ? 'Microphone and camera access on another device require trusted HTTPS. Do not send this HTTP link as a ready-to-use device invitation.'
        : 'The other device must reach the app and media service and trust its HTTPS certificate. An HTTPS link alone does not verify audio or camera connectivity.',
    copyLabel: loopback
      ? 'Copy same-computer link'
      : url.protocol !== 'https:'
        ? 'Copy current test link'
        : 'Copy invitation',
  };
}
