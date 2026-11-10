import { describe, expect, it } from 'vitest';
import { changeResource, preparationLabel, resourcePayload, type ResourceForm } from './reviewer';

const form: ResourceForm = {
  gnani_source: 'own',
  evon_source: 'own',
  gnani_api_key: ' speech-test ',
  evon_base_url: 'https://reviewer.modal.run/v1',
  evon_model: 'review-model',
  evon_api_key: 'model-test',
  evon_modal_key: 'proxy-test',
  evon_modal_secret: 'proxy-secret-test',
};
describe('reviewer resource boundaries', () => {
  it('discards credentials typed for a previous endpoint before changing destination', () => {
    const changed = changeResource(form, 'evon_base_url', 'https://another.modal.run/v1');
    expect(changed.evon_api_key).toBe('');
    expect(changed.evon_modal_key).toBe('');
    expect(changed.evon_modal_secret).toBe('');
    expect(changed.gnani_api_key).toBe(form.gnani_api_key);
  });
  it('does not restore hidden credentials after switching away from an own service', () => {
    const shared = changeResource(form, 'gnani_source', 'shared');
    expect(changeResource(shared, 'gnani_source', 'own').gnani_api_key).toBe('');
    expect(changeResource(form, 'evon_source', 'shared').evon_modal_secret).toBe('');
  });
  it('drops all custom credentials and destinations when shared resources are selected', () => {
    expect(resourcePayload({ ...form, gnani_source: 'shared', evon_source: 'shared' })).toEqual({
      gnani_source: 'shared',
      evon_source: 'shared',
      resource_consent: true,
    });
  });
  it('sends only the selected service credentials for mixed sources', () => {
    const payload = resourcePayload({ ...form, gnani_source: 'shared' });
    expect(payload).not.toHaveProperty('gnani_api_key');
    expect(payload.evon_api_key).toBe('model-test');
    expect(payload).not.toHaveProperty('host_email');
  });
  it('omits empty write-only fields so an unchanged stored secret is not erased', () => {
    expect(
      resourcePayload({
        ...form,
        gnani_api_key: '',
        evon_api_key: '',
        evon_modal_key: '',
        evon_modal_secret: '',
      }),
    ).toEqual({
      gnani_source: 'own',
      evon_source: 'own',
      resource_consent: true,
      evon_base_url: form.evon_base_url,
      evon_model: form.evon_model,
    });
  });
  it('does not present external, unmeasured or unavailable engines as ready', () => {
    expect(preparationLabel(null)).toContain('not been measured');
    expect(preparationLabel({ available: true, can_prepare: true, state: 'external' })).toContain(
      'not been measured',
    );
    expect(
      preparationLabel({
        available: false,
        can_prepare: false,
        state: 'ready',
        detail: 'Access expired',
      }),
    ).toBe('Access expired');
  });
});
