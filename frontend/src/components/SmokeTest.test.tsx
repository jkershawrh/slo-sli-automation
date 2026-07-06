import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

// Import all components
import { Header } from './Header'
import { MetricCard } from './MetricCard'
import { GoldenSignalCard } from './GoldenSignalCard'
import { HeadroomVisual } from './HeadroomVisual'
import { ToolchainDiagram } from './ToolchainDiagram'
import { MaturityLadder } from './MaturityLadder'
import { DriftTimeline } from './DriftTimeline'
import { StepCard } from './StepCard'
import { FlowDescription } from './FlowDescription'
import { JsonViewer } from './JsonViewer'

// Mock fetch for Header's health check
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ json: () => Promise.resolve({}) })))
})

describe('Header', () => {
  it('renders the product name', () => {
    render(<Header />)
    // The header renders "slo<span>scope</span>" — text is split across elements
    expect(screen.getByText('scope')).toBeInTheDocument()
    // Verify "slo" is present via the parent element's textContent
    expect(screen.getByText((_, element) =>
      element?.tagName === 'SPAN' && element?.textContent === 'sloscope' && element?.children.length > 0
    )).toBeInTheDocument()
  })

  it('renders both logos', () => {
    render(<Header />)
    const imgs = screen.getAllByRole('img')
    expect(imgs.length).toBeGreaterThanOrEqual(2)
  })
})

describe('MetricCard', () => {
  it('renders value and label', () => {
    render(<MetricCard value="416" label="tests" />)
    expect(screen.getByText('416')).toBeInTheDocument()
    expect(screen.getByText('tests')).toBeInTheDocument()
  })

  it('renders detail when provided', () => {
    render(<MetricCard value="25" label="checks" detail="verification" />)
    expect(screen.getByText('verification')).toBeInTheDocument()
  })
})

describe('GoldenSignalCard', () => {
  it('renders signal name and target_op', () => {
    render(<GoldenSignalCard signal="Latency" description="Lower is better" targetOp="lte" example="p99 <= 600ms" color="var(--rh-blue)" />)
    expect(screen.getByText('Latency')).toBeInTheDocument()
    expect(screen.getByText(/target_op: lte/)).toBeInTheDocument()
  })

  it('renders down arrow for lte', () => {
    render(<GoldenSignalCard signal="Latency" description="test" targetOp="lte" example="test" color="red" />)
    expect(screen.getByText('↓')).toBeInTheDocument()
  })

  it('renders up arrow for gte', () => {
    render(<GoldenSignalCard signal="Traffic" description="test" targetOp="gte" example="test" color="green" />)
    expect(screen.getByText('↑')).toBeInTheDocument()
  })
})

describe('HeadroomVisual', () => {
  it('renders observed and target values', () => {
    render(<HeadroomVisual observed={500} target={595} margin={95} unit="ms" targetOp="lte" marginRationale="1 stddev headroom" />)
    expect(screen.getByText('500ms')).toBeInTheDocument()
    expect(screen.getByText('595ms')).toBeInTheDocument()
  })

  it('renders margin rationale', () => {
    render(<HeadroomVisual observed={500} target={595} margin={95} unit="ms" targetOp="lte" marginRationale="1 stddev headroom" />)
    expect(screen.getByText('1 stddev headroom')).toBeInTheDocument()
  })

  it('renders margin value', () => {
    render(<HeadroomVisual observed={500} target={595} margin={95} unit="ms" targetOp="lte" marginRationale="test" />)
    expect(screen.getByText('margin: 95ms')).toBeInTheDocument()
  })
})

describe('ToolchainDiagram', () => {
  it('renders all four stages', () => {
    render(<ToolchainDiagram />)
    expect(screen.getByText('LiftOff')).toBeInTheDocument()
    expect(screen.getByText('sloscope')).toBeInTheDocument()
    expect(screen.getByText('NovaScan')).toBeInTheDocument()
    expect(screen.getByText('DarkScope')).toBeInTheDocument()
  })

  it('renders stage descriptions', () => {
    render(<ToolchainDiagram />)
    expect(screen.getByText('Readiness')).toBeInTheDocument()
    expect(screen.getByText('Reliability')).toBeInTheDocument()
    expect(screen.getByText('Capacity')).toBeInTheDocument()
    expect(screen.getByText('Security')).toBeInTheDocument()
  })
})

describe('MaturityLadder', () => {
  it('renders all three tiers', () => {
    render(<MaturityLadder current="growing" />)
    expect(screen.getByText('New')).toBeInTheDocument()
    expect(screen.getByText('Growing')).toBeInTheDocument()
    expect(screen.getByText('Mature')).toBeInTheDocument()
  })

  it('renders headroom descriptions', () => {
    render(<MaturityLadder current="growing" />)
    expect(screen.getByText('2-3 stddev')).toBeInTheDocument()
    expect(screen.getByText('1-2 stddev')).toBeInTheDocument()
    expect(screen.getByText('0.5-1 stddev')).toBeInTheDocument()
  })
})

describe('DriftTimeline', () => {
  const mockIndicators = [
    {
      name: 'latency_p99_ms',
      live_value: 5000,
      baseline_value: 500,
      abs_deviation: 4500,
      rel_deviation: 9.0,
      direction: 'increasing',
      band_breach: true,
      first_pass_class: 'latency_regression',
    },
    {
      name: 'error_rate_ratio',
      live_value: 0.003,
      baseline_value: 0.002,
      abs_deviation: 0.001,
      rel_deviation: 0.5,
      direction: 'increasing',
      band_breach: false,
      first_pass_class: 'no_significant_drift',
    },
  ]
  const mockDominant = { indicator: 'latency_p99_ms', class: 'latency_regression', breach_magnitude: 22.5 }

  it('renders dominant signal class', () => {
    render(<DriftTimeline indicators={mockIndicators} dominantSignal={mockDominant} allBreached={['latency_p99_ms']} />)
    // "latency regression" appears in both the dominant signal banner and the indicator row
    const matches = screen.getAllByText('latency regression')
    expect(matches.length).toBeGreaterThanOrEqual(1)
  })

  it('renders breach magnitude', () => {
    render(<DriftTimeline indicators={mockIndicators} dominantSignal={mockDominant} allBreached={['latency_p99_ms']} />)
    expect(screen.getByText('22.5x')).toBeInTheDocument()
  })

  it('renders indicator names', () => {
    render(<DriftTimeline indicators={mockIndicators} dominantSignal={mockDominant} allBreached={['latency_p99_ms']} />)
    expect(screen.getByText('latency_p99_ms')).toBeInTheDocument()
    expect(screen.getByText('error_rate_ratio')).toBeInTheDocument()
  })

  it('shows BREACH and OK badges', () => {
    render(<DriftTimeline indicators={mockIndicators} dominantSignal={mockDominant} allBreached={['latency_p99_ms']} />)
    expect(screen.getByText('BREACH')).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
  })
})

describe('StepCard', () => {
  it('renders title and step number', () => {
    render(<StepCard title="Collect Evidence" num={1} status="idle" onRun={() => {}}>Content here</StepCard>)
    expect(screen.getByText('Collect Evidence')).toBeInTheDocument()
  })

  it('renders children content', () => {
    render(<StepCard title="Test" num={1} status="done" onRun={() => {}}>Result content</StepCard>)
    expect(screen.getByText('Result content')).toBeInTheDocument()
  })
})

describe('FlowDescription', () => {
  it('renders label and content when alwaysOpen', () => {
    render(<FlowDescription text="This is how it works" alwaysOpen />)
    // "How it works" label appears as a child div; use getAllByText since the parent also contains it
    const matches = screen.getAllByText(/how it works/i)
    expect(matches.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('This is how it works')).toBeInTheDocument()
  })

  it('renders toggle button when not alwaysOpen', () => {
    render(<FlowDescription text="Some explanation" />)
    expect(screen.getByText(/how it works/i)).toBeInTheDocument()
  })
})

describe('JsonViewer', () => {
  it('renders JSON label', () => {
    render(<JsonViewer data={{ key: 'value' }} label="Test JSON" />)
    expect(screen.getByText('Test JSON')).toBeInTheDocument()
  })
})
