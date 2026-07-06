import { motion } from 'motion/react'

interface ToolchainDiagramProps {
  activeStage?: 'liftoff' | 'sloscope' | 'novascan' | 'darkscope'
}

const STAGES = [
  { key: 'liftoff', name: 'LiftOff', description: 'Readiness', color: 'var(--rh-teal)' },
  { key: 'sloscope', name: 'sloscope', description: 'Reliability', color: 'var(--rh-red)' },
  { key: 'novascan', name: 'NovaScan', description: 'Capacity', color: 'var(--rh-purple)' },
  { key: 'darkscope', name: 'DarkScope', description: 'Security', color: 'var(--rh-orange)' },
]

export function ToolchainDiagram({ activeStage = 'sloscope' }: ToolchainDiagramProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, justifyContent: 'center' }}>
      {STAGES.map((stage, i) => {
        const isActive = stage.key === activeStage
        return (
          <div key={stage.key} style={{ display: 'flex', alignItems: 'center' }}>
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.15, type: 'spring', stiffness: 400, damping: 25 }}
              style={{
                background: isActive ? `${stage.color}20` : 'var(--surface-1)',
                border: `2px solid ${isActive ? stage.color : 'var(--border)'}`,
                borderRadius: 10,
                padding: '16px 20px',
                textAlign: 'center',
                minWidth: 120,
                opacity: isActive ? 1 : 0.6,
              }}
            >
              <div style={{
                fontFamily: "'Red Hat Display', sans-serif",
                fontSize: 16,
                fontWeight: isActive ? 800 : 600,
                color: isActive ? stage.color : 'var(--text-secondary)',
              }}>
                {stage.name}
              </div>
              <div style={{
                fontFamily: "'Red Hat Mono', monospace",
                fontSize: 10,
                letterSpacing: 1,
                textTransform: 'uppercase' as const,
                color: 'var(--text-dim)',
                marginTop: 4,
              }}>
                {stage.description}
              </div>
            </motion.div>
            {i < STAGES.length - 1 && (
              <span style={{ color: 'var(--text-disabled)', fontSize: 20, margin: '0 8px' }}>
                {'→'}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
