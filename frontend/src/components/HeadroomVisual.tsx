import { motion } from 'motion/react'

interface HeadroomVisualProps {
  observed: number
  target: number
  margin: number
  unit: string
  targetOp: 'lte' | 'gte'
  marginRationale: string
}

export function HeadroomVisual({ observed, target, margin, unit, targetOp, marginRationale }: HeadroomVisualProps) {
  // For lte: observed is left, target is right (target > observed = good)
  // For gte: target is left, observed is right (target < observed = good)
  const isLte = targetOp === 'lte'
  const leftVal = isLte ? observed : target
  const rightVal = isLte ? target : observed
  const leftLabel = isLte ? 'Observed' : 'Target'
  const rightLabel = isLte ? 'Target' : 'Observed'

  // Compute bar width ratios
  const maxVal = rightVal * 1.2
  const leftPct = (leftVal / maxVal) * 100
  const rightPct = (rightVal / maxVal) * 100

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

        {/* Margin band */}
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

        {/* Observed marker */}
        <div style={{ position: 'absolute', left: `${leftPct}%`, top: 0, transform: 'translateX(-50%)' }}>
          <div style={{ width: 3, height: 40, background: isLte ? 'var(--rh-blue)' : 'var(--rh-green)', borderRadius: 1 }} />
        </div>

        {/* Target marker */}
        <div style={{ position: 'absolute', left: `${rightPct}%`, top: 0, transform: 'translateX(-50%)' }}>
          <div style={{ width: 3, height: 40, background: isLte ? 'var(--rh-green)' : 'var(--rh-blue)', borderRadius: 1, opacity: 0.8 }} />
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
