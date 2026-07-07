import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { MetricCard } from '../components/MetricCard'
import { SliSloSlaRow } from '../components/SliSloSlaRow'
import { DriftTimeline } from '../components/DriftTimeline'

interface ServiceDetailProps {
  service: string
  onBack: () => void
}

export function ServiceDetail({ service, onBack }: ServiceDetailProps) {
  const [baseline, setBaseline] = useState<any>(null)
  const [proposal, setProposal] = useState<any>(null)
  const [driftSignal, setDriftSignal] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.baseline(service).catch(() => null),
      api.proposal(service).catch(() => null),
      api.drift(service).catch(() => null),
    ]).then(([bl, pr, ds]) => {
      setBaseline(bl)
      setProposal(pr)
      setDriftSignal(ds)
    }).catch(e => setError(e.message))
  }, [service])

  return (
    <div>
      {/* Back button + service name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <button onClick={onBack} style={{
          background: 'none', border: '1px solid var(--border)', color: 'var(--text-dim)',
          padding: '4px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
        }}>
          ← Back
        </button>
        <h2 style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", margin: 0 }}>
          {service}
        </h2>
      </div>

      {error && <div style={{ color: 'var(--rh-red)' }}>Error: {error}</div>}

      {/* Baseline indicators */}
      {baseline && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>
            {baseline.lookback_window || '30d'} Baseline
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
            <MetricCard label="p99 Latency" value={`${baseline.indicators?.latency?.p99_ms?.toFixed(0) || '?'}ms`} color="var(--rh-blue)" />
            <MetricCard label="Error Rate" value={`${((baseline.indicators?.error_rate?.ratio || 0) * 100).toFixed(2)}%`} color="var(--rh-red)" />
            <MetricCard label="Availability" value={`${((baseline.indicators?.availability?.ratio || 0) * 100).toFixed(2)}%`} color="var(--rh-green)" />
            <MetricCard label="Throughput" value={`${baseline.indicators?.throughput?.mean_rps?.toFixed(1) || '?'} rps`} color="var(--rh-teal)" />
            <MetricCard label="Maturity" value={baseline.maturity_tier || 'growing'} color="var(--text-dim)" />
          </div>
        </div>
      )}

      {/* SLI / SLO / SLA hierarchy */}
      {proposal && proposal.slos && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>
            SLI → SLO → SLA
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {proposal.slos.map((slo: any) => (
              <SliSloSlaRow
                key={slo.sli_name}
                sliName={slo.sli_name}
                sliType={slo.sli_type}
                targetOp={slo.target_op}
                observedValue={slo.headroom?.observed_value || 0}
                sloTarget={slo.slo_target}
                slaTarget={slo.sla_target}
                unit={slo.target_unit}
              />
            ))}
          </div>
        </div>
      )}

      {/* Drift status */}
      {driftSignal && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>
            Drift Signal
          </div>
          <DriftTimeline
            indicators={driftSignal.indicators || []}
            dominantSignal={driftSignal.dominant_signal || { indicator: 'none', class: 'no_significant_drift', breach_magnitude: 0 }}
            allBreached={driftSignal.all_breached_indicators || []}
          />
        </div>
      )}

      {!baseline && !proposal && !driftSignal && !error && (
        <div style={{ color: 'var(--text-dim)', padding: 20 }}>Loading...</div>
      )}
    </div>
  )
}
