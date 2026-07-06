import { motion } from 'motion/react'

interface HeadroomVisualProps {
  observed: number
  target: number
  margin: number
  unit: string
  targetOp: 'lte' | 'gte'
  marginRationale: string
  sloTarget?: number
}

export function HeadroomVisual({ observed, target, margin, unit, targetOp, marginRationale, sloTarget }: HeadroomVisualProps) {
  // For lte: SLO (left, tighter) → Observed (middle) → SLA Ceiling (right, looser)
  // For gte: SLA Floor (left, looser) → Observed (middle) → SLO (right, tighter)
  const isLte = targetOp === 'lte'
  const leftVal = isLte ? (sloTarget ?? observed) : target
  const rightVal = isLte ? target : (sloTarget ?? observed)
  const leftLabel = isLte ? 'SLO' : 'SLA Floor'
  const rightLabel = isLte ? 'SLA Ceiling' : 'SLO'

  // Compute bar width ratios
  const maxVal = rightVal * 1.2
  const leftPct = (leftVal / maxVal) * 100
  const rightPct = (rightVal / maxVal) * 100
  const obsPct = sloTarget != null ? (observed / maxVal) * 100 : undefined

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      style={{
        background: 'var(--surface-2)',
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-dim)', letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 12 }}>
        Headroom Analysis
      </div>

      {/* Bar visualization */}
      <div style={{ position: 'relative', height: 40, marginBottom: 8 }}>
        {/* Background bar */}
        <div style={{ position: 'absolute', top: 14, left: 0, right: 0, height: 12, background: 'var(--surface-1)', borderRadius: 6 }} />

        {/* Margin band (SLO to SLA range) */}
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${rightPct - leftPct}%` }}
          transition={{ duration: 0.8, delay: 0.3 }}
          style={{
            position: 'absolute',
            top: 14,
            left: `${leftPct}%`,
            height: 12,
            background: 'var(--rh-green-dim)',
            borderRadius: 6,
            border: '1px solid var(--rh-green)',
          }}
        />

        {/* Left marker (SLO for lte, SLA Floor for gte) */}
        <div style={{ position: 'absolute', left: `${leftPct}%`, top: 0, transform: 'translateX(-50%)' }}>
          <div style={{ width: 3, height: 40, background: isLte ? 'var(--rh-teal)' : 'var(--rh-blue)', borderRadius: 1 }} />
        </div>

        {/* Observed marker (shown in the middle when sloTarget is provided) */}
        {obsPct != null && (
          <div style={{ position: 'absolute', left: `${obsPct}%`, top: 0, transform: 'translateX(-50%)' }}>
            <div style={{ width: 3, height: 40, background: 'var(--text-primary)', borderRadius: 1, opacity: 0.6 }} />
          </div>
        )}

        {/* Right marker (SLA Ceiling for lte, SLO for gte) */}
        <div style={{ position: 'absolute', left: `${rightPct}%`, top: 0, transform: 'translateX(-50%)' }}>
          <div style={{ width: 3, height: 40, background: isLte ? 'var(--rh-blue)' : 'var(--rh-teal)', borderRadius: 1, opacity: 0.8 }} />
        </div>
      </div>

      {/* Labels */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <div>
          <span style={{ color: 'var(--text-dim)' }}>{leftLabel}: </span>
          <span style={{ color: 'var(--text-primary)', fontFamily: "'Red Hat Mono', monospace", fontWeight: 600 }}>
            {leftVal}{unit}
          </span>
        </div>
        {obsPct != null && (
          <div>
            <span style={{ color: 'var(--text-dim)' }}>Observed: </span>
            <span style={{ color: 'var(--text-primary)', fontFamily: "'Red Hat Mono', monospace", fontWeight: 600 }}>
              {observed}{unit}
            </span>
          </div>
        )}
        <div style={{ color: 'var(--rh-green)', fontFamily: "'Red Hat Mono', monospace", fontSize: 11 }}>
          margin: {margin}{unit}
        </div>
        <div>
          <span style={{ color: 'var(--text-dim)' }}>{rightLabel}: </span>
          <span style={{ color: 'var(--text-primary)', fontFamily: "'Red Hat Mono', monospace", fontWeight: 600 }}>
            {rightVal}{unit}
          </span>
        </div>
      </div>

      {/* Rationale */}
      <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-dim)', fontStyle: 'italic', lineHeight: 1.5 }}>
        {marginRationale}
      </div>
    </motion.div>
  )
}
