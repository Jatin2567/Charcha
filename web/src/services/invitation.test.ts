import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { invitationScope } from './invitation';
import { InvitationHelp } from '../components/InvitationHelp';

describe('invitation reach guidance', () => {
  it('recognizes IPv4, IPv6 and localhost forms even under HTTPS', () => {
    for (const host of [
      '127.0.0.1:5180',
      '127.4.5.6',
      '[::1]:5180',
      'localhost:5180',
      'room.localhost',
    ]) {
      const scope = invitationScope(`https://${host}/app/#/join/abc`);
      expect(scope.kind).toBe('same-computer');
      expect(scope.copyLabel).toBe('Copy same-computer link');
      expect(scope.detail).toContain('that device itself');
    }
  });
  it('does not mistake private HTTP for a usable camera invitation or HTTPS for media verification', () => {
    const privateHttp = invitationScope('http://192.168.1.7:5180/#/join/abc');
    expect(privateHttp.kind).toBe('needs-https');
    const secure = invitationScope('https://meet.example/app/#/join/abc');
    expect(secure.kind).toBe('device-link');
    expect(secure.detail).toContain('does not verify audio');
    expect(secure.url).toBe('https://meet.example/app/#/join/abc');
    expect(invitationScope('https://localhost.example/#/join/abc').kind).toBe('device-link');
  });
  it('provides a free device-test path without rewriting the link or opening media', () => {
    const html = renderToStaticMarkup(
      createElement(InvitationHelp, { scope: invitationScope('http://127.0.0.1:5180/#/join/abc') }),
    );
    expect(html).toContain('this computer only');
    expect(html).toContain('#/tests?stage=device-check');
    expect(html).not.toContain('<iframe');
  });
});
