import { motion } from 'motion/react'

interface MaturityLadderProps {
  current: 'new' | 'growing' | 'mature'
  onSelect?: (tier: 'new' | 'growing' | 'mature') => void
}

const TIERS = [
  { key: 'new' as const, label: 'New', headroom: '2-3 stddev', description: 'Wide margins, conservative targets', color: 'var(--rh-blue)' },
  { key: 'growing' as const, label: 'Growing', headroom: '1-2 stddev', description: 'Standard margins, incremental improvements', color: 'var(--rh-teal)' },
  { key: 'mature' as const, label: 'Mature', headroom: '0.5-1 stddev', description: 'Tight margins, ready for promotion', color: 'var(--rh-green)' },
]

export function MaturityLadder({ current, onSelect }: MaturityLadderProps) {
  return (
    <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
      {TIERS.map((tier, i) => {
        const isActive = tier.key === current
        const isPast = TIERS.findIndex(t => t.key === current) > i
        return (
          <motion.div
            key={tier.key}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.12 }}
            onClick={() => onSelect?.(tier.key)}
            style={{
              background: isActive ? `${tier.color}20` : 'var(--surface-1)',
              border: `2px solid ${isActive ? tier.color : isPast ? 'var(--rh-green)' : 'var(--border)'}`,
              borderRadius: 10,
              padding: '16px 20px',
              textAlign: 'center',
              minWidth: 140,
              cursor: onSelect ? 'pointer' : 'default',
              opacity: isActive ? 1 : 0.5,
            }}
          >
            <div style={{
              fontFamily: "'Red Hat Display', sans-serif",
              fontSize: 18,
              fontWeight: isActive ? 800 : 600,
              color: isActive ? tier.color : 'var(--text-secondary)',
            }}>
              {tier.label}
            </div>
            <div style={{
              fontFamily: "'Red Hat Mono', monospace",
              fontSize: 12,
              color: isActive ? tier.color : 'var(--text-dim)',
              marginTop: 6,
            }}>
              {tier.headroom}
            </div>
            <div style={{
              fontSize: 12,
              color: 'var(--text-dim)',
              marginTop: 6,
              lineHeight: 1.4,
            }}>
              {tier.description}
            </div>
            {isPast && (
              <div style={{ color: 'var(--rh-green)', fontSize: 14, marginTop: 8 }}>
                {'✓'}
              </div>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}
