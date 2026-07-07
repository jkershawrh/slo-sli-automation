import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { ServiceStatus } from '../api/client'
import { BudgetGauge } from '../components/BudgetGauge'

export function ErrorBudgets() {
  const [services, setServices] = useState<ServiceStatus[]>([])
  const [budgets, setBudgets] = useState<Record<string, any>>({})

  useEffect(() => {
    api.services().then(svcs => {
      setServices(svcs)
      Promise.all(svcs.map(s =>
        api.budget(s.service).then(b => ({ service: s.service, data: b })).catch(() => null)
      )).then(results => {
        const map: Record<string, any> = {}
        results.filter(Boolean).forEach((r: any) => { map[r.service] = r.data })
        setBudgets(map)
      })
    }).catch(() => {})
  }, [])

  return (
    <div>
      {services.map(svc => {
        const budget = budgets[svc.service]
        if (!budget || !budget.budgets) return null

        return (
          <div key={svc.service} style={{ marginBottom: 24 }}>
            <div style={{
              fontSize: 16, fontWeight: 700, fontFamily: "'Red Hat Display', sans-serif",
              marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8,
            }}>
              {svc.service}
              <span style={{ fontSize: 11, color: 'var(--text-disabled)', fontWeight: 400 }}>
                {budget.budgets.length} SLOs
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
              {budget.budgets.map((b: any) => (
                <BudgetGauge
                  key={b.sli_name}
                  sliName={b.sli_name}
                  budgetPercent={b.error_budget_percent}
                  breaching={b.currently_breaching}
                  status={b.status}
                />
              ))}
            </div>
          </div>
        )
      })}

      {services.length === 0 && (
        <div style={{ color: 'var(--text-dim)', padding: 20 }}>Loading...</div>
      )}
    </div>
  )
}
