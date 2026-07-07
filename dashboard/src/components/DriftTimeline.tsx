import { motion } from 'motion/react'

interface DriftIndicator {
  name: string
  live_value: number
  baseline_value: number
  abs_deviation: number
  rel_deviation: number
  direction: string
  band_breach: boolean
  first_pass_class: string
}

interface DominantSignal {
  indicator: string
  class: string
  breach_magnitude: number
}

interface DriftTimelineProps {
  indicators: DriftIndicator[]
  dominantSignal: DominantSignal
  allBreached: string[]
}

export function DriftTimeline({ indicators, dominantSignal, allBreached: _allBreached }: DriftTimelineProps) {
  const directionArrow = (d: string) => d === 'increasing' ? '↑' : d === 'decreasing' ? '↓' : '→'
  const directionColor = (d: string, breach: boolean) => {
    if (!breach) return 'var(--text-dim)'
    return d === 'increasing' ? 'var(--rh-orange)' : d === 'decreasing' ? 'var(--rh-blue)' : 'var(--text-dim)'
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      style={{ display: 'flex', flexDirection: 'column', gap: 2 }}
    >
      {/* Dominant signal banner */}
      <div style={{
        background: dominantSignal.class === 'no_significant_drift' ? 'var(--rh-green-dim)' : 'var(--rh-red-dim)',
        border: `1px solid ${dominantSignal.class === 'no_significant_drift' ? 'var(--rh-green)' : 'var(--rh-red)'}`,
        borderRadius: 8,
        padding: '12px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 8,
      }}>
        <div>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, letterSpacing: 1, textTransform: 'uppercase' as const, color: 'var(--text-dim)' }}>
            Dominant Signal
          </span>
          <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>
            {dominantSignal.class.replace(/_/g, ' ')}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-dim)' }}>
            breach magnitude
          </div>
          <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 28, fontWeight: 800, color: dominantSignal.breach_magnitude > 0 ? 'var(--rh-red)' : 'var(--rh-green)' }}>
            {dominantSignal.breach_magnitude.toFixed(1)}x
          </div>
        </div>
      </div>

      {/* Per-indicator rows */}
      {indicators.map((ind, i) => {
        const isDominant = ind.name === dominantSignal.indicator
        return (
          <motion.div
            key={ind.name}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
            style={{
              background: 'var(--surface-1)',
              borderRadius: 6,
              padding: '10px 14px',
              borderLeft: isDominant ? '3px solid var(--rh-red)' : '3px solid transparent',
              display: 'grid',
              gridTemplateColumns: '140px 80px 80px 40px 60px 1fr',
              alignItems: 'center',
              gap: 8,
              fontSize: 13,
            }}
          >
            <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 12, color: 'var(--text-secondary)' }}>
              {ind.name}
            </span>
            <span style={{ fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-dim)', fontSize: 12 }}>
              {ind.baseline_value.toFixed(2)}
            </span>
            <span style={{ fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-primary)', fontWeight: 600, fontSize: 12 }}>
              {ind.live_value.toFixed(2)}
            </span>
            <span style={{ fontSize: 16, color: directionColor(ind.direction, ind.band_breach), textAlign: 'center' }}>
              {directionArrow(ind.direction)}
            </span>
            <span style={{
              fontFamily: "'Red Hat Mono', monospace",
              fontSize: 10,
              padding: '2px 6px',
              borderRadius: 3,
              background: ind.band_breach ? 'var(--rh-red-dim)' : 'var(--rh-green-dim)',
              color: ind.band_breach ? 'var(--rh-red)' : 'var(--rh-green)',
              textAlign: 'center',
            }}>
              {ind.band_breach ? 'BREACH' : 'OK'}
            </span>
            <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10, color: 'var(--text-disabled)' }}>
              {ind.first_pass_class.replace(/_/g, ' ')}
            </span>
          </motion.div>
        )
      })}
    </motion.div>
  )
}
