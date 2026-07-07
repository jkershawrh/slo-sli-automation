import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { StepCard } from './StepCard'
import { HeadroomVisual } from './HeadroomVisual'
import { DriftTimeline } from './DriftTimeline'
import { MaturityLadder } from './MaturityLadder'
// GoldenSignalCard not used in lab — signals shown in slides
import { MetricCard } from './MetricCard'
import { api } from '../api/client'
import type { Baseline, Proposal, DriftSignal, DriftReport } from '../api/client'

type Status = 'idle' | 'running' | 'done' | 'error'

interface LabWizardProps {
  onExit: () => void
}

const STEP_LABELS = ['Configure', 'Baseline', 'Propose', 'Drift']

const SERVICES = [
  { id: 'checkout-api', label: 'checkout-api', desc: 'Moderate traffic web API. p99 ~500ms, ~0.2% error rate.' },
  { id: 'api-gateway', label: 'api-gateway', desc: 'High-traffic gateway. p99 ~50ms, ~0.01% error rate. 60M requests.' },
  { id: 'batch-processor', label: 'batch-processor', desc: 'Batch processing. p99 ~30s, ~1% error rate. High variance.' },
]

const DRIFT_SCENARIOS = [
  'latency_regression',
  'latency_improvement',
  'error_rate_elevation',
  'error_rate_reduction',
  'throughput_collapse',
  'throughput_surge',
  'saturation_approach',
  'availability_drop',
  'distribution_shift',
  'no_significant_drift',
]

export function LabWizard({ onExit }: LabWizardProps) {
  const [step, setStep] = useState(0)

  // Step 1 state
  const [selectedService, setSelectedService] = useState<string>('checkout-api')
  const [maturityTier, setMaturityTier] = useState<'new' | 'growing' | 'mature'>('growing')
  const [contextType, setContextType] = useState<'service' | 'infra'>('service')

  // Step 2 state
  const [baseline, setBaseline] = useState<Baseline | null>(null)
  const [baselineStatus, setBaselineStatus] = useState<Status>('idle')

  // Step 3 state
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [proposalStatus, setProposalStatus] = useState<Status>('idle')
  const [expandedRationale, setExpandedRationale] = useState<string | null>(null)

  // Step 4 state
  const [driftScenario, setDriftScenario] = useState<string>('latency_regression')
  const [driftSignal, setDriftSignal] = useState<DriftSignal | null>(null)
  const [driftReport, setDriftReport] = useState<DriftReport | null>(null)
  const [driftStatus, setDriftStatus] = useState<Status>('idle')
  const [classifyStatus, setClassifyStatus] = useState<Status>('idle')

  // --- Callbacks ---

  const doGenerateBaseline = useCallback(async () => {
    setBaselineStatus('running')
    try {
      const call = await api.getBaselineFixture(selectedService)
      setBaseline(call.response.data)
      setBaselineStatus('done')
    } catch {
      setBaselineStatus('error')
    }
  }, [selectedService])

  const doProposeSLOs = useCallback(async () => {
    if (!baseline) return
    setProposalStatus('running')
    try {
      const call = await api.proposeSLOs(baseline, maturityTier, contextType)
      setProposal(call.response.data)
      setProposalStatus('done')
    } catch {
      setProposalStatus('error')
    }
  }, [baseline, maturityTier, contextType])

  const doDetectDrift = useCallback(async () => {
    setDriftStatus('running')
    try {
      const call = await api.getDriftFixture(driftScenario)
      setDriftSignal(call.response.data)
      setDriftStatus('done')
    } catch {
      setDriftStatus('error')
    }
  }, [driftScenario])

  const doClassifyDrift = useCallback(async () => {
    if (!driftSignal) return
    setClassifyStatus('running')
    try {
      const call = await api.classifyDrift(driftSignal)
      setDriftReport(call.response.data)
      setClassifyStatus('done')
    } catch {
      setClassifyStatus('error')
    }
  }, [driftSignal])

  const resetAll = () => {
    setStep(0)
    setSelectedService('checkout-api')
    setMaturityTier('growing')
    setContextType('service')
    setBaseline(null)
    setBaselineStatus('idle')
    setProposal(null)
    setProposalStatus('idle')
    setExpandedRationale(null)
    setDriftScenario('latency_regression')
    setDriftSignal(null)
    setDriftReport(null)
    setDriftStatus('idle')
    setClassifyStatus('idle')
  }

  const sevColor = (sev: string) => {
    if (sev === 'critical') return 'var(--rh-red)'
    if (sev === 'high') return 'var(--rh-orange)'
    if (sev === 'medium') return 'var(--rh-yellow)'
    return 'var(--text-dim)'
  }

  // Golden signal mapping removed — signals shown in presentation slides

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 32px', borderBottom: '1px solid var(--border)', background: 'var(--surface-1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <img src="/logos/redhat.svg" alt="Red Hat" style={{ height: 20 }} />
          <span style={{ color: 'var(--text-disabled)', fontSize: 22, fontWeight: 300 }}>&times;</span>
          <img src="/logos/intel.png" alt="Intel" style={{ height: 20 }} />
        </div>
        <span style={{ fontSize: 16, fontWeight: 700, fontFamily: 'Red Hat Display, sans-serif' }}>
          SLO Lab
        </span>
        <button onClick={onExit} style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-dim)', padding: '4px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer' }}>
          Back to Demo
        </button>
      </div>

      {/* Step progress indicator */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 0, padding: '16px 0', borderBottom: '1px solid var(--border)' }}>
        {STEP_LABELS.map((label, i) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center' }}>
            {i > 0 && (
              <div style={{
                width: 40, height: 2,
                background: i <= step ? 'var(--rh-green)' : 'var(--border)',
                transition: 'background 0.3s',
              }} />
            )}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
                background: i < step ? 'var(--rh-green)' : i === step ? 'var(--rh-red)' : 'var(--surface-2)',
                color: i < step || i === step ? '#fff' : 'var(--text-disabled)',
                transition: 'background 0.3s',
              }}>
                {i < step ? '✓' : i + 1}
              </div>
              <span style={{ fontSize: 11, color: i === step ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{label}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, maxWidth: 860, margin: '0 auto', padding: '24px', width: '100%' }}>
        <AnimatePresence mode="wait">
          <motion.div key={step} initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>

            {/* ============ Step 0: Configure ============ */}
            {step === 0 && (
              <div>
                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>Choose Your Service</h2>
                <p style={{ color: 'var(--text-dim)', marginBottom: 24 }}>
                  Select a service profile, maturity tier, and context type.
                </p>

                {/* Service selector */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
                  {SERVICES.map(svc => (
                    <div
                      key={svc.id}
                      onClick={() => setSelectedService(svc.id)}
                      style={{
                        padding: 16, borderRadius: 8, cursor: 'pointer',
                        background: 'var(--surface-1)',
                        borderLeft: selectedService === svc.id ? '4px solid var(--rh-blue)' : '4px solid transparent',
                        border: `1px solid ${selectedService === svc.id ? 'var(--rh-blue)' : 'var(--border)'}`,
                        borderLeftWidth: 4,
                        borderLeftColor: selectedService === svc.id ? 'var(--rh-blue)' : 'transparent',
                      }}
                    >
                      <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', fontFamily: "'Red Hat Mono', monospace" }}>
                        {svc.label}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginTop: 6, lineHeight: 1.5 }}>
                        {svc.desc}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Maturity tier */}
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 12 }}>Maturity Tier</div>
                  <MaturityLadder current={maturityTier} onSelect={setMaturityTier} />
                </div>

                {/* Context type */}
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 12 }}>Context Type</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {(['service', 'infra'] as const).map(ct => (
                      <button
                        key={ct}
                        onClick={() => setContextType(ct)}
                        style={{
                          padding: '6px 18px', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                          background: contextType === ct ? 'var(--rh-red)' : 'var(--surface-2)',
                          border: `1px solid ${contextType === ct ? 'var(--rh-red)' : 'var(--border)'}`,
                          color: contextType === ct ? '#fff' : 'var(--text-dim)',
                        }}
                      >
                        {ct.charAt(0).toUpperCase() + ct.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Next button */}
                <div style={{ textAlign: 'right' }}>
                  <button
                    onClick={() => setStep(1)}
                    style={{
                      background: 'var(--rh-red)', border: 'none', color: '#fff',
                      padding: '10px 28px', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* ============ Step 1: Baseline ============ */}
            {step === 1 && (
              <div>
                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>Generate Evidence-Based Baseline</h2>
                <p style={{ color: 'var(--text-dim)', marginBottom: 20 }}>
                  Load the pre-computed baseline fixture for <strong style={{ color: 'var(--text-primary)' }}>{selectedService}</strong>.
                </p>

                <StepCard num={1} title="Generate Baseline" status={baselineStatus} onRun={doGenerateBaseline} buttonLabel="Generate Baseline">
                  {baseline && (
                    <div>
                      {/* Latency table */}
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-blue)', marginBottom: 8 }}>Latency</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginBottom: 16 }}>
                        <MetricCard label="p50" value={`${baseline.indicators.latency.p50_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                        <MetricCard label="p90" value={`${baseline.indicators.latency.p90_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                        <MetricCard label="p95" value={`${baseline.indicators.latency.p95_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                        <MetricCard label="p99" value={`${baseline.indicators.latency.p99_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                        <MetricCard label="stddev" value={`${baseline.indicators.latency.stddev_ms.toFixed(1)}ms`} color="var(--text-dim)" />
                      </div>

                      {/* Error rate */}
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-red)', marginBottom: 8 }}>Error Rate</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6, marginBottom: 16 }}>
                        <MetricCard label="ratio" value={baseline.indicators.error_rate.ratio.toFixed(4)} color="var(--rh-red)" />
                        <MetricCard label="stddev" value={baseline.indicators.error_rate.stddev.toFixed(4)} color="var(--text-dim)" />
                      </div>

                      {/* Availability */}
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-green)', marginBottom: 8 }}>Availability</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 6, marginBottom: 16, maxWidth: 200 }}>
                        <MetricCard label="ratio" value={`${(baseline.indicators.availability.ratio * 100).toFixed(2)}%`} color="var(--rh-green)" />
                      </div>

                      {/* Throughput */}
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-teal)', marginBottom: 8 }}>Throughput</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 16 }}>
                        <MetricCard label="mean rps" value={baseline.indicators.throughput.mean_rps.toFixed(1)} color="var(--rh-teal)" />
                        <MetricCard label="p95 rps" value={baseline.indicators.throughput.p95_rps.toFixed(1)} color="var(--rh-teal)" />
                        <MetricCard label="stddev" value={baseline.indicators.throughput.stddev_rps.toFixed(2)} color="var(--text-dim)" />
                      </div>

                      {/* Saturation (if available) */}
                      {baseline.indicators.saturation?.available && (
                        <>
                          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-orange)', marginBottom: 8 }}>Saturation</div>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginBottom: 16 }}>
                            <MetricCard label="CPU mean" value={`${(baseline.indicators.saturation.cpu_mean_ratio * 100).toFixed(1)}%`} color="var(--rh-orange)" />
                            <MetricCard label="CPU p95" value={`${(baseline.indicators.saturation.cpu_p95_ratio * 100).toFixed(1)}%`} color="var(--rh-orange)" />
                            <MetricCard label="Mem mean" value={`${(baseline.indicators.saturation.memory_mean_ratio * 100).toFixed(1)}%`} color="var(--rh-orange)" />
                            <MetricCard label="Mem p95" value={`${(baseline.indicators.saturation.memory_p95_ratio * 100).toFixed(1)}%`} color="var(--rh-orange)" />
                          </div>
                        </>
                      )}

                      {/* Key insight */}
                      <div style={{
                        padding: 14, borderRadius: 8, marginTop: 8,
                        background: 'var(--rh-teal-dim)',
                        borderLeft: '4px solid var(--rh-teal)',
                        fontSize: 14, color: 'var(--rh-teal)', fontFamily: "'Red Hat Mono', monospace", lineHeight: 1.7,
                      }}>
                        p99/p50 ratio: {(baseline.indicators.latency.p99_ms / baseline.indicators.latency.p50_ms).toFixed(1)}x
                        {' | '}
                        stddev as % of p99: {((baseline.indicators.latency.stddev_ms / baseline.indicators.latency.p99_ms) * 100).toFixed(1)}%
                      </div>
                    </div>
                  )}
                </StepCard>

                {/* Navigation */}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
                  <button onClick={() => setStep(0)}
                    style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-dim)', padding: '8px 20px', borderRadius: 6, fontSize: 13, cursor: 'pointer' }}>
                    Back
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    disabled={baselineStatus !== 'done'}
                    style={{
                      background: baselineStatus === 'done' ? 'var(--rh-red)' : 'var(--surface-2)',
                      border: 'none', color: baselineStatus === 'done' ? '#fff' : 'var(--text-disabled)',
                      padding: '10px 28px', borderRadius: 8, fontSize: 14, fontWeight: 700,
                      cursor: baselineStatus === 'done' ? 'pointer' : 'not-allowed',
                      opacity: baselineStatus === 'done' ? 1 : 0.5,
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* ============ Step 2: Propose SLOs ============ */}
            {step === 2 && (
              <div>
                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>AI-Proposed SLOs with Evidence-Based Headroom</h2>
                <p style={{ color: 'var(--text-dim)', marginBottom: 20 }}>
                  Propose SLOs grounded in the baseline for <strong style={{ color: 'var(--text-primary)' }}>{selectedService}</strong>.
                </p>

                {/* Interactive maturity display */}
                <div style={{ marginBottom: 20 }}>
                  <MaturityLadder current={maturityTier} onSelect={() => {}} />
                  <div style={{ fontSize: 12, color: 'var(--text-disabled)', textAlign: 'center', marginTop: 8, fontStyle: 'italic' }}>
                    (To regenerate with different maturity, go back to Configure)
                  </div>
                </div>

                <StepCard num={2} title="Propose SLOs" status={proposalStatus} onRun={doProposeSLOs} buttonLabel="Propose SLOs">
                  {proposal && (
                    <div>
                      {proposal.slos.map((slo, i) => (
                        <motion.div key={slo.sli_name}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.1 }}
                          style={{
                            padding: 16, background: 'var(--surface-2)', borderRadius: 8,
                            marginBottom: 12, border: '1px solid var(--border)',
                          }}
                        >
                          {/* SLO header */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 16, fontWeight: 700 }}>{slo.sli_name}</span>
                            <span style={{
                              padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                              background: 'var(--rh-blue-dim)', color: 'var(--rh-blue)',
                            }}>
                              {slo.sli_type}
                            </span>
                            <span style={{
                              padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                              background: slo.target_op === 'lte' ? 'var(--rh-blue-dim)' : 'var(--rh-green-dim)',
                              color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)',
                            }}>
                              {slo.target_op}
                            </span>
                            {slo.requires_review && (
                              <span style={{
                                padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                                background: 'var(--rh-orange-dim)', color: 'var(--rh-orange)',
                                marginLeft: 'auto',
                              }}>
                                REQUIRES REVIEW
                              </span>
                            )}
                          </div>

                          {/* 30-day avg → SLO (objective) → SLA (commitment) → Error Budget */}
                          {slo.headroom && (() => {
                            const obs = slo.headroom.observed_value;
                            const fmt = (v: number) => {
                              if (slo.sli_type === 'availability') return `${(v * 100).toFixed(2)}%`;
                              if (slo.sli_type === 'error_rate') return `${(v * 100).toFixed(2)}%`;
                              if (Math.abs(v) < 1) return `${v.toFixed(4)} ${slo.target_unit}`;
                              if (Math.abs(v) < 10) return `${v.toFixed(2)} ${slo.target_unit}`;
                              return `${Math.round(v)} ${slo.target_unit}`;
                            };
                            return (
                              <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
                                <div style={{ padding: '6px 10px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: '3px solid var(--text-dim)' }}>
                                  <div style={{ fontSize: 9, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1 }}>30-DAY AVG</div>
                                  <div style={{ fontSize: 16, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif" }}>{fmt(obs)}</div>
                                </div>
                                <div style={{ alignSelf: 'center', color: 'var(--text-disabled)', fontSize: 14 }}>{'→'}</div>
                                <div style={{ padding: '6px 10px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: '3px solid var(--rh-teal)' }}>
                                  <div style={{ fontSize: 9, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-teal)', letterSpacing: 1 }}>SLO OBJECTIVE</div>
                                  <div style={{ fontSize: 16, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-teal)' }}>{fmt(slo.slo_target)}</div>
                                  <div style={{ fontSize: 8, color: 'var(--text-disabled)' }}>where you aim</div>
                                </div>
                                <div style={{ alignSelf: 'center', color: 'var(--text-disabled)', fontSize: 14 }}>{'→'}</div>
                                <div style={{ padding: '6px 10px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: `3px solid ${slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)'}` }}>
                                  <div style={{ fontSize: 9, fontFamily: "'Red Hat Mono', monospace", color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)', letterSpacing: 1 }}>
                                    SLA {slo.target_op === 'lte' ? 'CEILING' : 'FLOOR'}
                                  </div>
                                  <div style={{ fontSize: 16, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)' }}>
                                    {fmt(slo.sla_target)}
                                  </div>
                                  <div style={{ fontSize: 8, color: 'var(--text-disabled)' }}>what you guarantee</div>
                                </div>
                                <div style={{ padding: '6px 10px', background: 'var(--surface-1)', borderRadius: 6, alignSelf: 'center' }}>
                                  <div style={{ fontSize: 9, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1 }}>ERROR BUDGET</div>
                                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-secondary)' }}>{slo.error_budget_percent}%</div>
                                </div>
                              </div>
                            );
                          })()}

                          {/* Headroom visual */}
                          {slo.headroom && (
                            <HeadroomVisual
                              observed={slo.headroom.observed_value}
                              target={slo.sla_target}
                              margin={slo.headroom.margin}
                              unit={slo.target_unit}
                              targetOp={slo.target_op}
                              marginRationale={slo.headroom.margin_rationale}
                              sloTarget={slo.slo_target}
                            />
                          )}

                          {/* Collapsible rationale */}
                          <div style={{ marginTop: 10 }}>
                            <button
                              onClick={() => setExpandedRationale(expandedRationale === slo.sli_name ? null : slo.sli_name)}
                              style={{
                                background: 'none', border: 'none', color: 'var(--rh-blue)',
                                fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0,
                                display: 'flex', alignItems: 'center', gap: 4,
                              }}
                            >
                              <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10 }}>
                                {expandedRationale === slo.sli_name ? '▼' : '▶'}
                              </span>
                              Rationale
                            </button>
                            <AnimatePresence>
                              {expandedRationale === slo.sli_name && (
                                <motion.div
                                  initial={{ opacity: 0, height: 0 }}
                                  animate={{ opacity: 1, height: 'auto' }}
                                  exit={{ opacity: 0, height: 0 }}
                                  style={{
                                    marginTop: 8, padding: 12,
                                    background: 'var(--surface-1)', borderRadius: 6,
                                    fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7,
                                  }}
                                >
                                  {slo.rationale}
                                  {slo.review_reason && (
                                    <div style={{ marginTop: 8, color: 'var(--rh-orange)', fontSize: 12 }}>
                                      Review reason: {slo.review_reason}
                                    </div>
                                  )}
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        </motion.div>
                      ))}

                      {/* Lifecycle note */}
                      <div style={{
                        marginTop: 12, padding: 10, borderRadius: 6,
                        background: 'var(--surface-1)', border: '1px solid var(--border)',
                        fontSize: 12, color: 'var(--text-dim)', textAlign: 'center',
                        fontFamily: "'Red Hat Mono', monospace",
                      }}>
                        Generated from {baseline?.lookback_window || '30d'} baseline. Stays until promoted or demoted.
                      </div>
                    </div>
                  )}
                </StepCard>

                {/* Navigation */}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
                  <button onClick={() => setStep(1)}
                    style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-dim)', padding: '8px 20px', borderRadius: 6, fontSize: 13, cursor: 'pointer' }}>
                    Back
                  </button>
                  <button
                    onClick={() => setStep(3)}
                    disabled={proposalStatus !== 'done'}
                    style={{
                      background: proposalStatus === 'done' ? 'var(--rh-red)' : 'var(--surface-2)',
                      border: 'none', color: proposalStatus === 'done' ? '#fff' : 'var(--text-disabled)',
                      padding: '10px 28px', borderRadius: 8, fontSize: 14, fontWeight: 700,
                      cursor: proposalStatus === 'done' ? 'pointer' : 'not-allowed',
                      opacity: proposalStatus === 'done' ? 1 : 0.5,
                    }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* ============ Step 3: Drift Detection ============ */}
            {step === 3 && (
              <div>
                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8 }}>Inject Drift and See the Response</h2>
                <p style={{ color: 'var(--text-dim)', marginBottom: 20 }}>
                  Select a drift scenario, detect it, then classify and get remediation advice.
                </p>

                {/* Scenario selector */}
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 12 }}>Drift Scenario</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 24 }}>
                  {DRIFT_SCENARIOS.map(sc => (
                    <div
                      key={sc}
                      onClick={() => {
                        setDriftScenario(sc)
                        // Reset drift state when scenario changes
                        setDriftSignal(null)
                        setDriftReport(null)
                        setDriftStatus('idle')
                        setClassifyStatus('idle')
                      }}
                      style={{
                        padding: '10px 8px', borderRadius: 6, cursor: 'pointer', textAlign: 'center',
                        background: driftScenario === sc ? 'var(--rh-red)15' : 'var(--surface-1)',
                        border: `2px solid ${driftScenario === sc ? 'var(--rh-red)' : 'var(--border)'}`,
                      }}
                    >
                      <div style={{
                        fontSize: 11, fontWeight: 600, lineHeight: 1.4,
                        color: driftScenario === sc ? 'var(--rh-red)' : 'var(--text-dim)',
                        fontFamily: "'Red Hat Mono', monospace",
                      }}>
                        {sc.replace(/_/g, ' ')}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Detect Drift */}
                <StepCard num={1} title="Detect Drift" status={driftStatus} onRun={doDetectDrift} buttonLabel="Detect Drift">
                  {driftSignal && (
                    <DriftTimeline
                      indicators={driftSignal.indicators}
                      dominantSignal={driftSignal.dominant_signal}
                      allBreached={driftSignal.all_breached_indicators}
                    />
                  )}
                </StepCard>

                {/* Classify & Remediate */}
                <StepCard num={2} title="Classify & Remediate" status={classifyStatus}
                  onRun={driftStatus === 'done' ? doClassifyDrift : undefined}
                  buttonLabel="Classify & Remediate">
                  {classifyStatus === 'idle' && driftStatus !== 'done' && (
                    <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                      Detect drift first to generate a drift signal.
                    </div>
                  )}
                  {driftReport && (
                    <div>
                      {/* Classification badge */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                        <span style={{
                          padding: '4px 12px', borderRadius: 6, fontSize: 13, fontWeight: 700,
                          background: `${sevColor(driftReport.severity)}20`,
                          color: sevColor(driftReport.severity),
                        }}>
                          {driftReport.severity.toUpperCase()}
                        </span>
                        <span style={{
                          padding: '4px 12px', borderRadius: 6, fontSize: 13, fontWeight: 700,
                          background: 'var(--surface-1)', color: 'var(--text-primary)',
                          border: '1px solid var(--border)',
                        }}>
                          {driftReport.classification.replace(/_/g, ' ')}
                        </span>
                      </div>

                      {/* Likely cause */}
                      <div style={{
                        padding: 14, background: 'var(--surface-2)', borderRadius: 8,
                        border: '1px solid var(--border)', marginBottom: 16,
                        fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7,
                      }}>
                        <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1, marginBottom: 6 }}>
                          LIKELY CAUSE
                        </div>
                        {driftReport.likely_cause}
                      </div>

                      {/* Recommendations */}
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-blue)', marginBottom: 8 }}>
                        Recommendations
                      </div>
                      {driftReport.recommendations.map((rec, i) => (
                        <motion.div key={i}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: i * 0.1 }}
                          style={{
                            padding: 14, background: 'var(--surface-2)', borderRadius: 8,
                            border: '1px solid var(--border)', marginBottom: 8,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                            <span style={{
                              padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                              background: rec.confidence === 'high' ? 'var(--rh-green-dim)' : rec.confidence === 'medium' ? 'var(--rh-blue-dim)' : 'var(--rh-orange-dim)',
                              color: rec.confidence === 'high' ? 'var(--rh-green)' : rec.confidence === 'medium' ? 'var(--rh-blue)' : 'var(--rh-orange)',
                            }}>
                              {rec.confidence}
                            </span>
                          </div>
                          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{rec.action}</div>
                          <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.6 }}>{rec.rationale}</div>
                          {rec.remediation_plan && (
                            <div style={{
                              marginTop: 10, padding: 10, background: 'var(--surface-1)', borderRadius: 6,
                              fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6,
                            }}>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                                <div>
                                  <span style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Evidence basis:</span>
                                  <div>{rec.remediation_plan.evidence_basis}</div>
                                </div>
                                <div>
                                  <span style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Verification:</span>
                                  <div>{rec.remediation_plan.verification_method}</div>
                                </div>
                              </div>
                            </div>
                          )}
                        </motion.div>
                      ))}
                    </div>
                  )}
                </StepCard>

                {/* Footer */}
                <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 24 }}>
                  <button onClick={resetAll}
                    style={{
                      background: 'var(--rh-red)', border: 'none', color: '#fff',
                      padding: '10px 24px', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                    }}>
                    Start Over
                  </button>
                  <button onClick={onExit}
                    style={{
                      background: 'none', border: '1px solid var(--border)', color: 'var(--text-dim)',
                      padding: '10px 24px', borderRadius: 8, fontSize: 14, cursor: 'pointer',
                    }}>
                    Back to Demo
                  </button>
                </div>
              </div>
            )}

          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
