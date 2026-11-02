import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { conferenceTestPlan, MODAL_TRANSLATION_STAGE } from './conferenceTestPlan';
import { FiveLanguagePlan } from '../components/FiveLanguagePlan';

describe('current conference translation plan', () => {
  it('shows separately completed controlled flows while preserving the original failure and pending acceptance', () => {
    const html = renderToStaticMarkup(createElement(FiveLanguagePlan));
    expect(html).toContain('Evon loaded on A100');
    expect(html).toContain(
      'Hindi → Tamil and Tamil → Hindi provider chains completed in separate controlled flows',
    );
    expect(html).toContain('See Saved checks for both records');
    expect(html).toContain('initial Tamil STT failure');
    expect(html).toContain('Five-language acceptance pending');
    expect(html).toContain('Actual billing is not reconciled here');
    expect(html).not.toContain('model readiness and live results remain pending');
    expect(html).not.toContain('Verify Evon compatibility');
  });
  it('bounds the current batch to ten flows, covering each unordered pairing once', () => {
    const report = conferenceTestPlan();
    expect(report.current_stage.compute_provider).toBe('Modal');
    expect(report.current_stage.compute_access).toBe('verified');
    expect(report.current_stage.approved_compute_ceiling_usd).toBe(5);
    expect(report.current_stage.approved_max_flows).toBe(10);
    const pairs = report.current_stage.initial_directions;
    expect(
      new Set(pairs.map((r) => [r.source_language, r.target_language].sort().join('-'))).size,
    ).toBe(10);
    for (const code of report.language_codes) {
      expect(pairs.filter((r) => r.source_language === code)).toHaveLength(2);
      expect(pairs.filter((r) => r.target_language === code)).toHaveLength(2);
    }
    expect(report.current_stage.actual_compute_cost_usd).toBeNull();
    expect(report.current_stage.remaining_compute_credit_usd).toBeNull();
  });

  it('preserves all five languages and the 20 distinct directed routes without claiming acceptance', () => {
    const report = conferenceTestPlan();
    expect(report.language_codes).toEqual(['hi', 'ta', 'bn', 'te', 'mr']);
    expect(report.routes).toHaveLength(20);
    const pairs = report.routes.map((route) => `${route.source_language}:${route.target_language}`);
    expect(new Set(pairs).size).toBe(20);
    expect(report.routes.every((route) => route.source_language !== route.target_language)).toBe(
      true,
    );
    expect(report.languages.every((entry) => entry.live_acceptance === 'not_verified')).toBe(true);
    expect(report.conference_participants_target).toBe(5);
    expect(report.conference_acceptance).toBe('pending_real_devices');
    expect(report.routes.every((route) => route.semantic_result === 'not_tested')).toBe(true);
  });

  it('keeps live measurements, account costs and automatic requests out of the saved proposal', () => {
    const report = conferenceTestPlan();
    expect(report.plan_only).toBe(true);
    expect(report.reporting.actual_observations).toBeNull();
    expect(report.reporting.actual_provider_cost).toBeNull();
    expect(report.reporting.provider_calls_from_this_page).toBe(0);
    expect(report.reporting.automatic_execution).toBe(false);
    expect(report.current_stage.voice_mode).toBe('standard');
    expect(report.current_stage.screening_mode).toBe('off');
    expect(report.current_stage.voice_cloning).toBe('deferred');
  });

  it('distinguishes route cold starts, model startup and the three different timing boundaries', () => {
    const report = conferenceTestPlan();
    expect(report.planned_pairwise_observations).toBe(60);
    expect(report.planned_setup_states[0]).toBe('new_route_model_already_loaded');
    expect(report.model_cold_start).toContain('separately');
    expect(report.measurement_boundaries.server).toContain('proxy');
    expect(report.measurement_boundaries.receiver).toContain('shared-clock');
    expect(report.measurement_boundaries.network).toContain('not translation delay');
  });

  it('omits the superseded GCP spending proposal and private configuration from the current export', () => {
    const report = conferenceTestPlan();
    const serialized = JSON.stringify(report);
    expect(serialized).not.toContain('gcp_project_ceiling_inr');
    expect(serialized).not.toContain('gcp_latency_stage_ceiling_inr');
    expect(serialized).not.toMatch(/api_key|session_token|proxy_secret|https?:\/\/[^\s"]+\/v1/i);
    expect(report.reporting.speech_cost).toContain('separate');
  });

  it('does not let an edited export mutate later plans or the approved-stage definition', () => {
    const report = conferenceTestPlan();
    report.current_stage.initial_directions.pop();
    report.language_codes.pop();
    report.routes[0].expected_meaning.push('changed export');
    expect(conferenceTestPlan().language_codes).toHaveLength(5);
    expect(conferenceTestPlan().current_stage.initial_directions).toHaveLength(10);
    expect(MODAL_TRANSLATION_STAGE.initial_directions).toHaveLength(10);
    expect(conferenceTestPlan().routes[0].expected_meaning).not.toContain('changed export');
  });
});
