async function request<T>(method: string, path: string): Promise<T> {
  const res = await fetch(path, { method, headers: { 'Content-Type': 'application/json' } })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export interface ServiceStatus {
  service: string
  status: string
  has_baseline: boolean
  has_proposal: boolean
  has_drift_signal: boolean
  has_drift_report: boolean
  maturity_tier: string
  last_baseline: string | null
  last_drift: string | null
  drift_class: string | null
  drift_severity: string | null
}

export interface Summary {
  total_services: number
  healthy: number
  degraded: number
  critical: number
  improving: number
  baselined: number
  unknown: number
  services: ServiceStatus[]
}

export const api = {
  summary: () => request<Summary>('GET', '/api/v2/summary'),
  services: () => request<ServiceStatus[]>('GET', '/api/v2/services'),
  baseline: (service: string) => request<Record<string, unknown>>('GET', `/api/v2/services/${service}/baseline`),
  proposal: (service: string) => request<Record<string, unknown>>('GET', `/api/v2/services/${service}/proposal`),
  drift: (service: string) => request<Record<string, unknown>>('GET', `/api/v2/services/${service}/drift`),
  driftReport: (service: string) => request<Record<string, unknown>>('GET', `/api/v2/services/${service}/drift/report`),
  budget: (service: string) => request<Record<string, unknown>>('GET', `/api/v2/services/${service}/budget`),
  recommendations: (service: string) => request<Record<string, unknown>[]>('GET', `/api/v2/services/${service}/recommendations`),
}
