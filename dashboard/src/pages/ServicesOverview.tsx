import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { Summary } from '../api/client'
import { ServiceCard } from '../components/ServiceCard'
import { MetricCard } from '../components/MetricCard'

interface ServicesOverviewProps {
  onSelectService: (service: string) => void
}

export function ServicesOverview({ onSelectService }: ServicesOverviewProps) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = () => {
      api.summary().then(setSummary).catch(e => setError(e.message))
    }
    load()
    const id = setInterval(load, 15000) // poll every 15s
    return () => clearInterval(id)
  }, [])

  if (error) return <div style={{ color: 'var(--rh-red)', padding: 20 }}>Error: {error}</div>
  if (!summary) return <div style={{ color: 'var(--text-dim)', padding: 20 }}>Loading...</div>

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24 }}>
        <MetricCard label="Total Services" value={`${summary.total_services}`} color="var(--text-primary)" />
        <MetricCard label="Healthy" value={`${summary.healthy}`} color="var(--rh-green)" />
        <MetricCard label="Degraded" value={`${summary.degraded}`} color="var(--rh-orange)" />
        <MetricCard label="Critical" value={`${summary.critical}`} color="var(--rh-red)" />
        <MetricCard label="Baselined" value={`${summary.baselined}`} color="var(--rh-blue)" />
      </div>

      {/* Service cards */}
      <div style={{
        fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)',
        letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 12,
      }}>
        Services
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
        {summary.services.map(svc => (
          <ServiceCard
            key={svc.service}
            service={svc}
            onClick={() => onSelectService(svc.service)}
          />
        ))}
      </div>
    </div>
  )
}
