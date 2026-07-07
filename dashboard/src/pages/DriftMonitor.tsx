import { useState, useEffect } from 'react'
import { motion } from 'motion/react'
import { api } from '../api/client'
import type { ServiceStatus } from '../api/client'
import { StatusDot } from '../components/StatusDot'

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }
const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--rh-red)', high: 'var(--rh-orange)', medium: 'var(--rh-yellow)',
  low: 'var(--rh-blue)', info: 'var(--text-dim)',
}

export function DriftMonitor() {
  const [services, setServices] = useState<ServiceStatus[]>([])

  useEffect(() => {
    const load = () => api.services().then(setServices).catch(() => {})
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  // Sort by severity (critical first), then by service name
  const sorted = [...services].sort((a, b) => {
    const sa = SEVERITY_ORDER[a.drift_severity || 'info'] ?? 5
    const sb = SEVERITY_ORDER[b.drift_severity || 'info'] ?? 5
    return sa - sb || a.service.localeCompare(b.service)
  })

  const drifting = services.filter(s => s.drift_class && s.drift_class !== 'no_significant_drift')
  const healthy = services.filter(s => !s.drift_class || s.drift_class === 'no_significant_drift')

  return (
    <div>
      {/* Summary */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: drifting.length > 0 ? 'var(--rh-red)' : 'var(--rh-green)' }}>
            {drifting.length}
          </span>
          <span style={{ fontSize: 14, color: 'var(--text-dim)' }}>services drifting</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-green)' }}>
            {healthy.length}
          </span>
          <span style={{ fontSize: 14, color: 'var(--text-dim)' }}>within tolerance</span>
        </div>
      </div>

      {/* Drift table */}
      <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 8 }}>
        All Services
      </div>

      {/* Header row */}
      <div style={{
        display: 'grid', gridTemplateColumns: '40px 160px 180px 100px 160px',
        gap: 8, padding: '8px 16px', fontSize: 10, fontFamily: "'Red Hat Mono', monospace",
        color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase' as const,
      }}>
        <div />
        <div>Service</div>
        <div>Drift Class</div>
        <div>Severity</div>
        <div>Last Checked</div>
      </div>

      {/* Data rows */}
      {sorted.map((svc, i) => (
        <motion.div
          key={svc.service}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.05 }}
          style={{
            display: 'grid', gridTemplateColumns: '40px 160px 180px 100px 160px',
            gap: 8, padding: '10px 16px', background: 'var(--surface-1)',
            borderRadius: 6, marginBottom: 4, alignItems: 'center', fontSize: 13,
          }}
        >
          <StatusDot status={svc.status} />
          <span style={{ fontWeight: 600 }}>{svc.service}</span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 12, color: 'var(--text-secondary)' }}>
            {svc.drift_class ? svc.drift_class.replace(/_/g, ' ') : 'no drift data'}
          </span>
          <span style={{
            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
            background: `${SEVERITY_COLORS[svc.drift_severity || 'info']}20`,
            color: SEVERITY_COLORS[svc.drift_severity || 'info'] || 'var(--text-dim)',
            display: 'inline-block',
          }}>
            {svc.drift_severity || 'N/A'}
          </span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-disabled)' }}>
            {svc.last_drift ? new Date(svc.last_drift).toLocaleString() : 'never'}
          </span>
        </motion.div>
      ))}
    </div>
  )
}
