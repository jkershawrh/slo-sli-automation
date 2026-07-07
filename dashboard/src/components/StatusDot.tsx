interface StatusDotProps {
  status: string
  size?: number
}

const STATUS_COLORS: Record<string, string> = {
  healthy: 'var(--rh-green)',
  improving: 'var(--rh-teal)',
  baselined: 'var(--rh-blue)',
  degraded: 'var(--rh-orange)',
  critical: 'var(--rh-red)',
  unknown: 'var(--text-disabled)',
}

export function StatusDot({ status, size = 10 }: StatusDotProps) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: STATUS_COLORS[status] || STATUS_COLORS.unknown,
    }} />
  )
}
