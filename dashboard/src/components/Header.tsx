import { useState, useEffect } from 'react'
import { motion } from 'motion/react'

export function Header() {
  const [healthy, setHealthy] = useState(true)
  useEffect(() => {
    fetch('/health').then(r => setHealthy(r.ok)).catch(() => setHealthy(false))
    const id = setInterval(() => {
      fetch('/health').then(r => setHealthy(r.ok)).catch(() => setHealthy(false))
    }, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '12px 32px', borderBottom: '1px solid var(--border)',
      background: 'var(--surface-1)', position: 'sticky', top: 0, zIndex: 100,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <img src="/logos/redhat.svg" alt="Red Hat" style={{ height: 20 }} />
        <span style={{ color: 'var(--text-disabled)', fontSize: 22, fontWeight: 300 }}>&times;</span>
        <img src="/logos/intel.png" alt="Intel" style={{ height: 20 }} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 16, fontWeight: 700 }}>
          slo<span style={{ color: 'var(--rh-red)' }}>scope</span>
        </span>
        <span style={{ color: 'var(--text-disabled)', fontSize: 14 }}>Dashboard</span>
      </div>
      <motion.div
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ repeat: Infinity, duration: 2 }}
        style={{
          width: 8, height: 8, borderRadius: '50%',
          background: healthy ? 'var(--rh-green)' : 'var(--rh-red)',
        }}
      />
    </div>
  )
}
