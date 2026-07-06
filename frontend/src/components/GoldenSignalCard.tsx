import { motion } from 'motion/react'

interface GoldenSignalCardProps {
  signal: string
  description: string
  targetOp: 'lte' | 'gte'
  example: string
  color: string
}

export function GoldenSignalCard({ signal, description, targetOp, example, color }: GoldenSignalCardProps) {
  const arrow = targetOp === 'lte' ? '↓' : '↑'

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      style={{
        background: 'var(--surface-1)',
        borderRadius: 8,
        borderLeft: `4px solid ${color}`,
        padding: 20,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{
          fontSize: 28,
          color,
          fontFamily: "'Red Hat Display', sans-serif",
          fontWeight: 800,
          lineHeight: 1,
        }}>
          {arrow}
        </span>
        <div>
          <div style={{
            fontFamily: "'Red Hat Display', sans-serif",
            fontSize: 18,
            fontWeight: 700,
            color: 'var(--text-primary)',
          }}>
            {signal}
          </div>
          <div style={{
            fontFamily: "'Red Hat Mono', monospace",
            fontSize: 11,
            letterSpacing: 1,
            textTransform: 'uppercase' as const,
            color,
          }}>
            target_op: {targetOp}
          </div>
        </div>
      </div>
      {description && (
        <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {description}
        </div>
      )}
      <div style={{
        fontSize: 13,
        color: 'var(--text-dim)',
        fontFamily: "'Red Hat Mono', monospace",
      }}>
        {example}
      </div>
    </motion.div>
  )
}
