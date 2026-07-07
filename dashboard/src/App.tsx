import { useState } from 'react'
import { Header } from './components/Header'
import { ServicesOverview } from './pages/ServicesOverview'
import { ServiceDetail } from './pages/ServiceDetail'
import { DriftMonitor } from './pages/DriftMonitor'
import { ErrorBudgets } from './pages/ErrorBudgets'
import { Recommendations } from './pages/Recommendations'
import { Alerts } from './pages/Alerts'

type Tab = 'services' | 'drift' | 'budgets' | 'recommendations' | 'alerts'

export default function App() {
  const [tab, setTab] = useState<Tab>('services')
  const [selectedService, setSelectedService] = useState<string | null>(null)

  const TABS: { key: Tab; label: string }[] = [
    { key: 'services', label: 'Services' },
    { key: 'drift', label: 'Drift Monitor' },
    { key: 'budgets', label: 'Error Budgets' },
    { key: 'recommendations', label: 'Recommendations' },
    { key: 'alerts', label: 'Alerts' },
  ]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-dark)' }}>
      <Header />

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: 0, borderBottom: '1px solid var(--border)',
        padding: '0 32px', background: 'var(--surface-1)',
      }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setSelectedService(null) }}
            style={{
              padding: '12px 20px', background: 'none', border: 'none',
              color: tab === t.key ? 'var(--rh-red)' : 'var(--text-dim)',
              fontWeight: tab === t.key ? 700 : 400,
              fontSize: 14, fontFamily: "'Red Hat Text', sans-serif",
              cursor: 'pointer',
              borderBottom: tab === t.key ? '2px solid var(--rh-red)' : '2px solid transparent',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: '24px 32px', maxWidth: 1200, margin: '0 auto' }}>
        {tab === 'services' && !selectedService && <ServicesOverview onSelectService={setSelectedService} />}
        {tab === 'services' && selectedService && <ServiceDetail service={selectedService} onBack={() => setSelectedService(null)} />}
        {tab === 'drift' && <DriftMonitor />}
        {tab === 'budgets' && <ErrorBudgets />}
        {tab === 'recommendations' && <Recommendations />}
        {tab === 'alerts' && <Alerts />}
      </div>
    </div>
  )
}
