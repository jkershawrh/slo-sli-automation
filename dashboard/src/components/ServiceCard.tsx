import { motion } from 'motion/react'
import { StatusDot } from './StatusDot'

interface ServiceCardProps {
  service: {
    service: string
    status: string
    maturity_tier: string
    last_baseline: string | null
    drift_class: string | null
    drift_severity: string | null
  }
  onClick: () => void
}

export function ServiceCard({ service: svc, onClick }: ServiceCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      onClick={onClick}
      style={{
        padding: 20, background: 'var(--surface-1)', borderRadius: 10,
        border: '1px solid var(--border)', cursor: 'pointer',
        transition: 'border-color 0.2s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <StatusDot status={svc.status} />
        <span style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 18, fontWeight: 700 }}>
          {svc.service}
        </span>
        <span style={{
          marginLeft: 'auto', padding: '2px 8px', borderRadius: 4,
          fontSize: 10, fontWeight: 700, fontFamily: "'Red Hat Mono', monospace",
          letterSpacing: 1, textTransform: 'uppercase' as const,
          background: 'var(--surface-2)', color: 'var(--text-dim)',
        }}>
          {svc.maturity_tier}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-dim)' }}>
        <div>
          <span style={{ color: 'var(--text-disabled)' }}>Status: </span>
          <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{svc.status}</span>
        </div>
        {svc.drift_class && svc.drift_class !== 'no_significant_drift' && (
          <div>
            <span style={{ color: 'var(--text-disabled)' }}>Drift: </span>
            <span style={{ color: svc.drift_severity === 'critical' ? 'var(--rh-red)' : 'var(--rh-orange)', fontWeight: 600 }}>
              {svc.drift_class.replace(/_/g, ' ')}
            </span>
          </div>
        )}
      </div>

      {svc.last_baseline && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-disabled)', fontFamily: "'Red Hat Mono', monospace" }}>
          Last baseline: {new Date(svc.last_baseline).toLocaleDateString()}
        </div>
      )}
    </motion.div>
  )
}
