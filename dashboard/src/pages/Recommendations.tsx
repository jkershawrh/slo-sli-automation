import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { ServiceStatus } from '../api/client'
import { RecommendationCard } from '../components/RecommendationCard'
import { StatusDot } from '../components/StatusDot'

export function Recommendations() {
  const [services, setServices] = useState<ServiceStatus[]>([])
  const [recs, setRecs] = useState<Record<string, any[]>>({})

  useEffect(() => {
    api.services().then(svcs => {
      setServices(svcs)
      Promise.all(svcs.map(s =>
        api.recommendations(s.service).then(r => ({ service: s.service, recs: r })).catch(() => ({ service: s.service, recs: [] }))
      )).then(results => {
        const map: Record<string, any[]> = {}
        results.forEach(r => { if (r.recs.length) map[r.service] = r.recs })
        setRecs(map)
      })
    }).catch(() => {})
  }, [])

  const servicesWithRecs = Object.entries(recs)
  const totalRecs = servicesWithRecs.reduce((n, [, r]) => n + r.length, 0)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <span style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: totalRecs > 0 ? 'var(--rh-orange)' : 'var(--rh-green)' }}>
          {totalRecs}
        </span>
        <span style={{ fontSize: 14, color: 'var(--text-dim)' }}>
          open recommendations across {servicesWithRecs.length} services
        </span>
      </div>

      {servicesWithRecs.map(([service, serviceRecs]) => {
        const svc = services.find(s => s.service === service)
        return (
          <div key={service} style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <StatusDot status={svc?.status || 'unknown'} />
              <span style={{ fontSize: 16, fontWeight: 700, fontFamily: "'Red Hat Display', sans-serif" }}>
                {service}
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-disabled)' }}>
                {serviceRecs.length} recommendations
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {serviceRecs.map((rec: any, i: number) => (
                <RecommendationCard
                  key={i}
                  action={rec.action}
                  confidence={rec.confidence}
                  rationale={rec.rationale}
                  plan={rec.remediation_plan}
                />
              ))}
            </div>
          </div>
        )
      })}

      {totalRecs === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
          No open recommendations. All services are within tolerance.
        </div>
      )}
    </div>
  )
}
