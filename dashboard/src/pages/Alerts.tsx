import { useState, useEffect } from 'react'
import { motion } from 'motion/react'
import { api } from '../api/client'

interface AlertRule {
  service: string
  sliName: string
  sliType: string
  severity: string
  longWindow: string
  shortWindow: string
  burnRate: number
  slaTarget: number
  targetOp: string
  errorBudget: number
  threshold: number
  status: 'armed' | 'not_configured'
}

export function Alerts() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.services().then(async (svcs) => {
      const allRules: AlertRule[] = []

      for (const svc of svcs) {
        try {
          const proposal = await api.proposal(svc.service) as any
          if (!proposal || !proposal.slos) continue

          for (const slo of proposal.slos) {
            const windows = slo.burn_rate_policy?.windows || []
            for (const w of windows) {
              const errorBudget = slo.error_budget_percent / 100
              allRules.push({
                service: svc.service,
                sliName: slo.sli_name,
                sliType: slo.sli_type,
                severity: w.severity,
                longWindow: w.long_window,
                shortWindow: w.short_window,
                burnRate: w.burn_rate,
                slaTarget: slo.sla_target,
                targetOp: slo.target_op,
                errorBudget: slo.error_budget_percent,
                threshold: w.burn_rate * errorBudget,
                status: 'armed',
              })
            }
          }
        } catch {
          // no proposal for this service
        }
      }

      setRules(allRules)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const SEVERITY_COLORS: Record<string, string> = {
    critical: 'var(--rh-red)',
    warning: 'var(--rh-orange)',
    info: 'var(--text-dim)',
  }

  const criticalCount = rules.filter(r => r.severity === 'critical').length
  const warningCount = rules.filter(r => r.severity === 'warning').length
  const services = [...new Set(rules.map(r => r.service))]

  if (loading) return <div style={{ color: 'var(--text-dim)', padding: 20 }}>Loading...</div>

  return (
    <div>
      {/* Summary */}
      <div style={{ display: 'flex', gap: 24, marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif" }}>
            {rules.length}
          </span>
          <span style={{ fontSize: 14, color: 'var(--text-dim)' }}>alert rules configured</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-red)' }}>
            {criticalCount}
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>critical</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-orange)' }}>
            {warningCount}
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>warning</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-blue)' }}>
            {services.length}
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-dim)' }}>services</span>
        </div>
      </div>

      {/* Info banner */}
      <div style={{
        padding: '10px 16px', background: 'var(--rh-blue-dim)', borderRadius: 6,
        borderLeft: '3px solid var(--rh-blue)', marginBottom: 20,
        fontSize: 13, color: 'var(--rh-blue)', lineHeight: 1.5,
      }}>
        These alert rules are generated from SLO proposals. Deploy the rendered Prometheus rules to activate them in your Alertmanager.
      </div>

      {/* Rules table header */}
      <div style={{
        display: 'grid', gridTemplateColumns: '140px 160px 80px 80px 80px 80px 100px 80px',
        gap: 8, padding: '8px 16px', fontSize: 10, fontFamily: "'Red Hat Mono', monospace",
        color: 'var(--text-disabled)', letterSpacing: 1, textTransform: 'uppercase' as const,
      }}>
        <div>Service</div>
        <div>SLI</div>
        <div>Severity</div>
        <div>Long Win</div>
        <div>Short Win</div>
        <div>Burn Rate</div>
        <div>Threshold</div>
        <div>Status</div>
      </div>

      {/* Rules rows */}
      {rules.map((rule, i) => (
        <motion.div
          key={`${rule.service}-${rule.sliName}-${rule.severity}-${rule.longWindow}`}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.03 }}
          style={{
            display: 'grid', gridTemplateColumns: '140px 160px 80px 80px 80px 80px 100px 80px',
            gap: 8, padding: '10px 16px', background: 'var(--surface-1)',
            borderRadius: 6, marginBottom: 3, alignItems: 'center', fontSize: 13,
          }}
        >
          <span style={{ fontWeight: 600 }}>{rule.service}</span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-secondary)' }}>
            {rule.sliName}
          </span>
          <span style={{
            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
            background: `${SEVERITY_COLORS[rule.severity] || 'var(--text-dim)'}20`,
            color: SEVERITY_COLORS[rule.severity] || 'var(--text-dim)',
            display: 'inline-block',
          }}>
            {rule.severity}
          </span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 12, color: 'var(--text-dim)' }}>
            {rule.longWindow}
          </span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 12, color: 'var(--text-dim)' }}>
            {rule.shortWindow}
          </span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>
            {rule.burnRate}x
          </span>
          <span style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-dim)' }}>
            {rule.threshold.toFixed(4)}
          </span>
          <span style={{
            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
            background: 'var(--rh-teal-dim)', color: 'var(--rh-teal)',
            display: 'inline-block',
          }}>
            ARMED
          </span>
        </motion.div>
      ))}

      {rules.length === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
          No alert rules configured. Generate SLO proposals first.
        </div>
      )}
    </div>
  )
}
