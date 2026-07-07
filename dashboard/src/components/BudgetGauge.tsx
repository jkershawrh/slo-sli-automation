import { motion } from 'motion/react'

interface BudgetGaugeProps {
  sliName: string
  budgetPercent: number
  breaching: boolean
  status: string
}

export function BudgetGauge({ sliName, budgetPercent, breaching, status }: BudgetGaugeProps) {
  const color = breaching ? 'var(--rh-red)' : budgetPercent < 30 ? 'var(--rh-orange)' : 'var(--rh-green)'

  return (
    <div style={{
      padding: 16, background: 'var(--surface-1)', borderRadius: 8,
      border: `1px solid ${breaching ? 'var(--rh-red)40' : 'var(--border)'}`,
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>{sliName}</div>

      {/* Gauge bar */}
      <div style={{
        width: '100%', height: 12, background: 'var(--surface-2)',
        borderRadius: 6, overflow: 'hidden', marginBottom: 8,
      }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(budgetPercent, 100)}%` }}
          transition={{ duration: 0.8 }}
          style={{
            height: '100%', borderRadius: 6,
            background: color,
          }}
        />
      </div>

      <div style={{
        fontSize: 24, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif",
        color,
      }}>
        {budgetPercent.toFixed(1)}%
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-disabled)' }}>
        error budget
      </div>
      <div style={{
        marginTop: 8, fontSize: 10, fontFamily: "'Red Hat Mono', monospace",
        padding: '2px 8px', borderRadius: 4, display: 'inline-block',
        background: breaching ? 'var(--rh-red-dim)' : 'var(--rh-green-dim)',
        color: breaching ? 'var(--rh-red)' : 'var(--rh-green)',
      }}>
        {status.toUpperCase()}
      </div>
    </div>
  )
}
