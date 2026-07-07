import { motion } from 'motion/react'

interface SliSloSlaRowProps {
  sliName: string
  sliType: string
  targetOp: 'lte' | 'gte'
  observedValue: number
  sloTarget: number
  slaTarget: number
  unit: string
}

export function SliSloSlaRow({ sliName, sliType, targetOp, observedValue, sloTarget, slaTarget, unit }: SliSloSlaRowProps) {
  const isAvail = sliType === 'availability'
  const fmt = (v: number) => isAvail ? `${(v * 100).toFixed(2)}%` : `${Math.round(v)} ${unit}`
  const arrow = targetOp === 'lte' ? '↓' : '↑'
  const color = targetOp === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        display: 'grid', gridTemplateColumns: '160px 1fr 1fr 1fr',
        gap: 12, padding: '12px 16px', background: 'var(--surface-1)',
        borderRadius: 8, borderLeft: `3px solid ${color}`, alignItems: 'center',
      }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 700 }}>{sliName}</div>
        <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color, letterSpacing: 1 }}>
          {arrow} {targetOp}
        </div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1 }}>SLI (30-DAY AVG)</div>
        <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif" }}>{fmt(observedValue)}</div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-teal)', letterSpacing: 1 }}>SLO OBJECTIVE</div>
        <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-teal)' }}>{fmt(sloTarget)}</div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color, letterSpacing: 1 }}>
          SLA {targetOp === 'lte' ? 'CEILING' : 'FLOOR'}
        </div>
        <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color }}>{fmt(slaTarget)}</div>
      </div>
    </motion.div>
  )
}
