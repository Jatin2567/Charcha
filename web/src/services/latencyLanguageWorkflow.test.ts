import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import sourcePlan from '../data/latencyLanguagePlan.json';
import { latencyWorkflowReference } from './latencyLanguageWorkflow';
import { LatencyLanguageGate } from '../components/LatencyLanguageGate';

describe('ten-language physical-gated workflow reference', () => {
  it('preserves all ninety directions and forty draft templates without granting execution', () => {
    const plan = latencyWorkflowReference()!;
    expect(plan).not.toBeNull();
    expect(plan.languages).toHaveLength(10);
    expect(plan.draft_cases).toHaveLength(40);
    expect(plan.routes).toHaveLength(90);
    expect(new Set(plan.routes.map((row) => row.route_id)).size).toBe(90);
    for (const language of plan.languages) {
      expect(plan.draft_cases.filter((row) => row.source_language === language.code)).toHaveLength(
        4,
      );
      expect(plan.routes.filter((row) => row.source_language === language.code)).toHaveLength(9);
      expect(language.meaning_review).toBe('pending');
      expect(language.physical_device_acceptance).toBe('pending');
    }
    expect(plan.plan_only).toBe(true);
    expect(plan.full_matrix_authorized).toBe(false);
    expect(plan.provider_calls_made).toBe(0);
    expect(plan.routes.every((row) => !row.automatic_execution && !row.approval_granted)).toBe(
      true,
    );
  });

  it('refuses software-only boundaries, weaker review policy and inferred matrix authorization', () => {
    for (const patch of [
      { full_matrix_authorized: true },
      { approval_granted: true },
      { provider_calls_made: 1 },
      { automatic_matrix_runner: true },
      { plan_only: false },
    ]) {
      expect(latencyWorkflowReference({ ...sourcePlan, ...patch })).toBeNull();
    }
    for (const patch of [
      { provider_kind: 'mock' },
      { clock: 'single_process_monotonic' },
      { boundary: 'source_end_to_first_decoded_rtc' },
      { minimum_warm_attempts: 1 },
      { meaning_review_required: false },
      { annotations_review_required: false },
      { capture_attestation_required: false },
      { capture_kinds: ['browser_render'] },
      { p95_strictly_under_ms: 2500 },
    ]) {
      expect(
        latencyWorkflowReference({
          ...sourcePlan,
          gate_policy: { ...sourcePlan.gate_policy, ...patch },
        }),
      ).toBeNull();
    }
  });

  it('cannot label a missing or incomplete physical gate as passed', () => {
    const changed = structuredClone(sourcePlan);
    changed.gates.hi_to_ta.passed = true;
    changed.gates.hi_to_ta.status = 'passed_for_next_test_review';
    changed.gates.hi_to_ta.reason_codes = [];
    expect(latencyWorkflowReference(changed)).toBeNull();
    const inconsistent = structuredClone(sourcePlan);
    inconsistent.full_matrix_eligible_for_test_review =
      !sourcePlan.full_matrix_eligible_for_test_review;
    expect(latencyWorkflowReference(inconsistent)).toBeNull();
    const routes = structuredClone(sourcePlan);
    routes.routes[1] = routes.routes[0];
    expect(latencyWorkflowReference(routes)).toBeNull();
  });

  it('keeps source drafts pending and omits arbitrary runtime or private fields from exports', () => {
    const input = {
      ...structuredClone(sourcePlan),
      api_key: 'NEVER-EXPORT',
      room_code: 'PRIVATE-ROOM',
      flow_id: 'PRIVATE-FLOW',
      account_balance: 1000,
    };
    Object.assign(input.languages[0], { private_value: 'NEVER-EXPORT' });
    Object.assign(input.draft_cases[0], { private_value: 'NEVER-EXPORT' });
    const plan = latencyWorkflowReference(input)!;
    expect(plan).not.toBeNull();
    expect(JSON.stringify(plan)).not.toMatch(
      /NEVER-EXPORT|PRIVATE-|api_key|room_code|flow_id|account_balance|private_value/,
    );
    expect(
      plan.draft_cases.every(
        (row) =>
          row.source_reference_status === 'draft_pending_fluent_review' &&
          row.target_reference === null &&
          row.meaning_acceptance === 'pending',
      ),
    ).toBe(true);
    plan.draft_cases[0].expected_meaning.push('edited export');
    plan.gates.hi_to_ta.reason_codes.pop();
    expect(input.draft_cases[0].expected_meaning).not.toContain('edited export');
    expect(latencyWorkflowReference(input)?.gates.hi_to_ta.reason_codes).toEqual(
      input.gates.hi_to_ta.reason_codes,
    );
  });

  it('labels documented catalog support separately from physical and human acceptance', () => {
    const html = renderToStaticMarkup(createElement(LatencyLanguageGate));
    expect(html).toContain('Ten-language expansion gate');
    expect(html).toContain('90 directed pairs');
    expect(html).toContain('40 draft scripts');
    expect(html).toContain('No matrix is authorized or started here');
    expect(html).toContain('strictly below 2,000 ms');
    expect(html).toContain('Synthetic decoded audio');
    expect(html).toContain('operator-attested');
    expect(html).toContain('Draft · fluent review required');
    expect(html).toContain('Pending / pending');
    expect(html).toContain('No accepted target translation is supplied');
  });
});
