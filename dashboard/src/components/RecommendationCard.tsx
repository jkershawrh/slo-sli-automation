import { motion } from 'motion/react'

const PRIORITY_COLORS: Record<string, string> = {
  immediate: 'var(--rh-red)',
  short_term: 'var(--rh-orange)',
  long_term: 'var(--rh-blue)',
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'var(--rh-green)',
  medium: 'var(--rh-blue)',
  low: 'var(--rh-orange)',
}

interface RecommendationCardProps {
  action: string
  confidence: string
  rationale: string
  plan?: {
    priority: string
    evidence_basis: string
    expected_impact: string
    verification_method: string
  }
}

export function RecommendationCard({ action, confidence, rationale, plan }: RecommendationCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        padding: 16, background: 'var(--surface-1)', borderRadius: 8,
        border: '1px solid var(--border)',
        borderLeft: `3px solid ${plan ? PRIORITY_COLORS[plan.priority] || 'var(--border)' : 'var(--border)'}`,
      }}
    >
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        {plan && (
          <span style={{
            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
            background: `${PRIORITY_COLORS[plan.priority] || 'var(--text-dim)'}20`,
            color: PRIORITY_COLORS[plan.priority] || 'var(--text-dim)',
          }}>
            {plan.priority.replace(/_/g, ' ').toUpperCase()}
          </span>
        )}
        <span style={{
          padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
          background: `${CONFIDENCE_COLORS[confidence] || 'var(--text-dim)'}20`,
          color: CONFIDENCE_COLORS[confidence] || 'var(--text-dim)',
        }}>
          {confidence} confidence
        </span>
      </div>

      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{action}</div>
      <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.6 }}>{rationale}</div>

      {plan && (
        <div style={{
          marginTop: 10, padding: 10, background: 'var(--surface-2)', borderRadius: 6,
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12, color: 'var(--text-dim)',
        }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Evidence</div>
            {plan.evidence_basis}
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Verification</div>
            {plan.verification_method}
          </div>
        </div>
      )}
    </motion.div>
  )
}
