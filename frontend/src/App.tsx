import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Header } from './components/Header';
import { StepCard } from './components/StepCard';
import { MetricCard } from './components/MetricCard';
import { GoldenSignalCard } from './components/GoldenSignalCard';
import { HeadroomVisual } from './components/HeadroomVisual';
import { FlowDescription } from './components/FlowDescription';
import { DriftTimeline } from './components/DriftTimeline';
// ToolchainDiagram available but not used in demo acts — sloscope stands on its own
import { MaturityLadder } from './components/MaturityLadder';
import { LabWizard } from './components/LabWizard';
import { api } from './api/client';
import type { Evidence, Baseline, Proposal, DriftSignal, DriftReport, RenderOutput } from './api/client';

type Mode = 'slides' | 'demo' | 'lab';
type Status = 'idle' | 'running' | 'done' | 'error';

const ACT_LABELS = [
  'Ordinary World',
  'Call to Adventure',
  'Crossing the Threshold',
  'The Ordeal',
  'The Reward',
  'The Return',
  'The Claim',
];

export default function App() {
  const [mode, setMode] = useState<Mode>('slides');
  const [slide, setSlide] = useState(0);
  const [actIndex, setActIndex] = useState(0);

  // --- Demo state ---
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [renderOutput, setRenderOutput] = useState<RenderOutput | null>(null);
  const [driftSignal, setDriftSignal] = useState<DriftSignal | null>(null);
  const [driftReport, setDriftReport] = useState<DriftReport | null>(null);
  // liveEvidence state removed — drift demo uses pre-computed fixtures directly

  // Step statuses
  const [evidenceStatus, setEvidenceStatus] = useState<Status>('idle');
  const [baselineStatus, setBaselineStatus] = useState<Status>('idle');
  const [proposalStatus, setProposalStatus] = useState<Status>('idle');
  const [renderStatus, setRenderStatus] = useState<Status>('idle');
  const [driftStatus, setDriftStatus] = useState<Status>('idle');
  const [classifyStatus, setClassifyStatus] = useState<Status>('idle');

  // Collapsible state for artifacts
  const [expandedArtifact, setExpandedArtifact] = useState<string | null>(null);
  const [expandedRationale, setExpandedRationale] = useState<string | null>(null);

  // --- Callbacks ---
  const doCollectEvidence = useCallback(async () => {
    setEvidenceStatus('running');
    try {
      const call = await api.collectEvidence('checkout-api', 'payments');
      setEvidence(call.response.data);
      setEvidenceStatus('done');
    } catch {
      setEvidenceStatus('error');
    }
  }, []);

  const doComputeBaseline = useCallback(async () => {
    if (!evidence) return;
    setBaselineStatus('running');
    try {
      const call = await api.computeBaseline(evidence);
      setBaseline(call.response.data);
      setBaselineStatus('done');
    } catch {
      setBaselineStatus('error');
    }
  }, [evidence]);

  const doProposeSLOs = useCallback(async () => {
    if (!baseline) return;
    setProposalStatus('running');
    try {
      const call = await api.proposeSLOs(baseline);
      setProposal(call.response.data);
      setProposalStatus('done');
    } catch {
      setProposalStatus('error');
    }
  }, [baseline]);

  const doRenderArtifacts = useCallback(async () => {
    if (!proposal) return;
    setRenderStatus('running');
    try {
      const call = await api.renderArtifacts(proposal);
      setRenderOutput(call.response.data);
      setRenderStatus('done');
    } catch {
      setRenderStatus('error');
    }
  }, [proposal]);

  const doDetectDrift = useCallback(async () => {
    if (!baseline) return;
    setDriftStatus('running');
    try {
      // Load the latency regression drift fixture as "live" evidence
      // This simulates a service whose p99 latency has regressed significantly
      const liveCall = await api.getDriftFixture('latency_regression');
      const driftFixture = liveCall.response.data;
      // The drift fixture IS the pre-computed drift signal — use it directly
      setDriftSignal(driftFixture);
      setDriftStatus('done');
    } catch {
      setDriftStatus('error');
    }
  }, [baseline]);

  const doClassifyDrift = useCallback(async () => {
    if (!driftSignal) return;
    setClassifyStatus('running');
    try {
      const call = await api.classifyDrift(driftSignal);
      setDriftReport(call.response.data);
      setClassifyStatus('done');
    } catch {
      setClassifyStatus('error');
    }
  }, [driftSignal]);


  // ========================================================
  // SLIDES MODE
  // ========================================================

  const SLIDES = [
    // 0: Title
    () => (
      <div style={{ textAlign: 'center' }}>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
          <img src="/logos/redhat.svg" alt="Red Hat" style={{ height: 28 }} />
          <span style={{ color: 'var(--text-disabled)', fontSize: 28, fontWeight: 300 }}>&times;</span>
          <img src="/logos/intel.png" alt="Intel" style={{ height: 28 }} />
        </motion.div>
        <motion.h1 initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3, duration: 0.7 }}
          style={{ fontSize: 56, fontWeight: 800, fontFamily: 'Red Hat Display, sans-serif', lineHeight: 1.1, margin: '24px 0 0' }}>
          slo<span style={{ color: 'var(--rh-red)' }}>scope</span>
        </motion.h1>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }}
          style={{ fontSize: 20, color: 'var(--text-dim)', marginTop: 24 }}>
          Evidence-Based SLO Engine
        </motion.p>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.1 }}
          style={{ fontSize: 15, color: 'var(--text-disabled)', marginTop: 12, fontStyle: 'italic' }}>
          Every target traces to observed history
        </motion.p>
      </div>
    ),

    // 1: The Problem
    () => (
      <div style={{ textAlign: 'center', maxWidth: 800 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 36, fontWeight: 700, fontFamily: 'Red Hat Display, sans-serif', lineHeight: 1.3 }}>
          Your SLOs are guesswork.
        </motion.p>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginTop: 40 }}>
          <MetricCard label="of SLO targets set without historical data" value="73%" color="var(--rh-red)" />
          <MetricCard label="the gap between aspiration and reality" value="6.7pp" color="var(--rh-orange)" />
          <MetricCard label="days of false alerts per aspirational target" value="365" color="var(--rh-yellow)" />
        </motion.div>
      </div>
    ),

    // 2: The Thesis
    () => (
      <div style={{ textAlign: 'center', maxWidth: 750 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 28, fontWeight: 700, fontFamily: 'Red Hat Display, sans-serif', lineHeight: 1.5, fontStyle: 'italic', color: 'var(--text-secondary)' }}>
          "The first job of AI in observability is not prediction. It is measuring reality and telling you what your data actually says you can commit to."
        </motion.p>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 40 }}>
          <div style={{ padding: 20, background: 'var(--surface-1)', borderLeft: '4px solid var(--rh-blue)', borderRadius: '0 10px 10px 0', textAlign: 'left' }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--rh-blue)', marginBottom: 8 }}>Stage 1: Evidence</div>
            <div style={{ fontSize: 14, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Deterministic. Reproducible. No LLM.
            </div>
          </div>
          <div style={{ padding: 20, background: 'var(--surface-1)', borderLeft: '4px solid var(--rh-purple)', borderRadius: '0 10px 10px 0', textAlign: 'left' }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--rh-purple)', marginBottom: 8 }}>Stage 2: Judgment</div>
            <div style={{ fontSize: 14, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              Grounded in evidence. Every number cited.
            </div>
          </div>
        </motion.div>
      </div>
    ),

    // 3: The Four Golden Signals — just the signals, clean
    () => (
      <div style={{ textAlign: 'center', maxWidth: 650 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", lineHeight: 1.3, marginBottom: 40 }}>
          The Four Golden Signals
        </motion.p>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <GoldenSignalCard signal="Latency" description="" targetOp="lte" example="p99 <= 600ms" color="var(--rh-blue)" />
          <GoldenSignalCard signal="Errors" description="" targetOp="lte" example="error_rate <= 0.3%" color="var(--rh-red)" />
          <GoldenSignalCard signal="Traffic" description="" targetOp="gte" example="rps >= 4.0" color="var(--rh-green)" />
          <GoldenSignalCard signal="Saturation" description="" targetOp="lte" example="cpu <= 80%" color="var(--rh-orange)" />
        </motion.div>
      </div>
    ),

    // 4: The trap — visual contrast, not paragraphs
    () => (
      <div style={{ textAlign: 'center', maxWidth: 700 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 36, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", lineHeight: 1.3, marginBottom: 40 }}>
          The aspirational trap.
        </motion.p>

        {/* The bad target */}
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 }}
          style={{ display: 'flex', justifyContent: 'center', gap: 32, marginBottom: 16 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-disabled)', letterSpacing: 1 }}>TARGET</div>
            <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 56, fontWeight: 800, color: 'var(--rh-red)' }}>99.9%</div>
          </div>
          <div style={{ alignSelf: 'center', fontSize: 28, color: 'var(--text-disabled)' }}>vs</div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 11, color: 'var(--text-disabled)', letterSpacing: 1 }}>OBSERVED</div>
            <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 56, fontWeight: 800, color: 'var(--text-primary)' }}>93.2%</div>
          </div>
        </motion.div>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
          style={{ fontSize: 18, color: 'var(--rh-red)', fontWeight: 600, marginBottom: 40 }}>
          Breached from day one. Alerts ignored. Real incidents missed.
        </motion.p>

        {/* The earned target */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.7 }}
          style={{ padding: '20px 0', borderTop: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 20, alignItems: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10, color: 'var(--text-disabled)', letterSpacing: 1 }}>START HERE</div>
              <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 32, fontWeight: 800, color: 'var(--rh-teal)' }}>89%</div>
            </div>
            <div style={{ color: 'var(--text-disabled)', fontSize: 18 }}>{'→'}</div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10, color: 'var(--text-disabled)', letterSpacing: 1 }}>&nbsp;</div>
              <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 32, fontWeight: 800, color: 'var(--rh-teal)' }}>91%</div>
            </div>
            <div style={{ color: 'var(--text-disabled)', fontSize: 18 }}>{'→'}</div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10, color: 'var(--text-disabled)', letterSpacing: 1 }}>&nbsp;</div>
              <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 32, fontWeight: 800, color: 'var(--rh-green)' }}>93.5%</div>
            </div>
            <div style={{ color: 'var(--text-disabled)', fontSize: 18 }}>{'→'}</div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Red Hat Mono', monospace", fontSize: 10, color: 'var(--text-disabled)', letterSpacing: 1 }}>EARNED</div>
              <div style={{ fontFamily: "'Red Hat Display', sans-serif", fontSize: 32, fontWeight: 800, color: 'var(--rh-green)' }}>96%</div>
            </div>
          </div>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', marginTop: 16 }}>
            Each target is earned, not wished for.
          </p>
        </motion.div>
      </div>
    ),

    // 5: CTA
    () => (
      <div style={{ textAlign: 'center' }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 36, fontWeight: 800, fontFamily: 'Red Hat Display, sans-serif', lineHeight: 1.3, marginBottom: 32 }}>
          See the evidence.
        </motion.p>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
          <button onClick={(e) => { e.stopPropagation(); setMode('demo'); setActIndex(0); }}
            style={{ background: 'var(--rh-red)', border: 'none', color: '#fff', padding: '16px 48px', borderRadius: 10, fontSize: 18, fontWeight: 700, cursor: 'pointer' }}>
            Run the journey
          </button>
        </motion.div>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
          <button onClick={(e) => { e.stopPropagation(); setMode('lab'); }}
            style={{ background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: 14, cursor: 'pointer', marginTop: 24, textDecoration: 'underline', display: 'inline-block' }}>
            Or skip to the lab
          </button>
        </motion.div>
      </div>
    ),
  ];

  if (mode === 'slides') {
    const isLastSlide = slide === SLIDES.length - 1;
    return (
      <div
        onClick={() => { if (!isLastSlide) setSlide(s => s + 1); }}
        style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-dark)', cursor: isLastSlide ? 'default' : 'pointer' }}
      >
        {/* Slide dots */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: '20px 0' }}>
          {SLIDES.map((_, i) => (
            <div key={i}
              onClick={(e) => { e.stopPropagation(); setSlide(i); }}
              style={{
                width: 10, height: 10, borderRadius: '50%', cursor: 'pointer',
                background: i === slide ? 'var(--rh-red)' : i < slide ? 'var(--rh-green)' : 'var(--border)',
                transition: 'background 0.3s',
              }}
            />
          ))}
        </div>

        {/* Slide content */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 48px' }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={slide}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            >
              {SLIDES[slide]()}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer nav */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 32px' }}>
          <button
            onClick={(e) => { e.stopPropagation(); if (slide > 0) setSlide(s => s - 1); }}
            style={{ background: 'none', border: 'none', color: slide > 0 ? 'var(--text-dim)' : 'transparent', fontSize: 13, cursor: slide > 0 ? 'pointer' : 'default', padding: '6px 16px' }}>
            Back
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-disabled)', fontFamily: 'Red Hat Mono, monospace' }}>
            {slide + 1} / {SLIDES.length}
          </span>
          {!isLastSlide ? (
            <button onClick={(e) => { e.stopPropagation(); setSlide(s => s + 1); }}
              style={{ background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: 13, cursor: 'pointer', padding: '6px 16px' }}>
              Next
            </button>
          ) : (
            <div style={{ width: 80 }} />
          )}
        </div>
      </div>
    );
  }


  // ========================================================
  // LAB MODE (placeholder)
  // ========================================================

  if (mode === 'lab') {
    return <LabWizard onExit={() => setMode('demo')} />;
  }


  // ========================================================
  // DEMO MODE
  // ========================================================

  const sevColor = (sev: string) => {
    if (sev === 'critical') return 'var(--rh-red)';
    if (sev === 'high') return 'var(--rh-orange)';
    if (sev === 'medium') return 'var(--rh-yellow)';
    return 'var(--text-dim)';
  };

  const renderAct = () => {
    switch (actIndex) {
      // ---- Act 0: Ordinary World ----
      case 0:
        return (
          <div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
              <MetricCard label="p99 Latency" value="500ms" color="var(--rh-blue)" />
              <MetricCard label="Availability" value="99.8%" color="var(--rh-green)" />
              <MetricCard label="Throughput" value="5.0 rps" color="var(--rh-teal)" />
              <MetricCard label="Error Rate" value="0.2%" color="var(--rh-orange)" />
            </div>
            <div style={{
              padding: 16, borderRadius: 8,
              background: 'var(--rh-orange-dim)',
              borderLeft: '4px solid var(--rh-orange)',
              fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7,
            }}>
              Current SLO: 99.9% availability — set without evidence
            </div>
          </div>
        );

      // ---- Act 1: Call to Adventure ----
      case 1:
        return (
          <div>
            <StepCard num={1} title="Collect Evidence" status={evidenceStatus} onRun={doCollectEvidence} buttonLabel="Collect Evidence">
              {evidence && (
                <div>
                  <FlowDescription text="sloscope queries Prometheus for latency histograms, request counts, error totals, and saturation metrics over the configured lookback window. All data is pulled from existing instrumentation — no agents, no sidecars, no new dependencies." alwaysOpen />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 12 }}>
                    <MetricCard label="Service" value={evidence.service} color="var(--rh-blue)" />
                    <MetricCard label="Lookback" value={evidence.lookback_window} color="var(--rh-teal)" />
                    <MetricCard label="Coverage" value={`${(evidence.coverage_ratio * 100).toFixed(0)}%`} color="var(--rh-green)" />
                  </div>
                  <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    <strong>{evidence.series.request_total.total.toLocaleString()}</strong> requests observed over{' '}
                    <strong>{evidence.lookback_window}</strong>.{' '}
                    Latency histogram with <strong>{evidence.series.latency_histogram.buckets.length}</strong> buckets.{' '}
                    <strong>{evidence.series.error_total.total.toLocaleString()}</strong> errors recorded.
                  </div>
                </div>
              )}
            </StepCard>
          </div>
        );

      // ---- Act 2: Crossing the Threshold ----
      case 2:
        return (
          <div>
            <StepCard num={2} title="Compute Baseline" status={baselineStatus}
              onRun={evidenceStatus === 'done' ? doComputeBaseline : undefined}
              buttonLabel="Compute Baseline">
              {baselineStatus === 'idle' && evidenceStatus !== 'done' && (
                <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                  Complete Act 1 first to collect evidence.
                </div>
              )}
              {baseline && (
                <div>
                  <div style={{
                    fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-dim)',
                    letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 16,
                  }}>
                    {baseline.lookback_window} empirical baseline
                  </div>
                  {/* Latency indicators */}
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-blue)', marginBottom: 8 }}>Latency</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginBottom: 16 }}>
                    <MetricCard label="p50" value={`${baseline.indicators.latency.p50_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                    <MetricCard label="p90" value={`${baseline.indicators.latency.p90_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                    <MetricCard label="p95" value={`${baseline.indicators.latency.p95_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                    <MetricCard label="p99" value={`${baseline.indicators.latency.p99_ms.toFixed(0)}ms`} color="var(--rh-blue)" />
                    <MetricCard label="stddev" value={`${baseline.indicators.latency.stddev_ms.toFixed(1)}ms`} color="var(--text-dim)" />
                  </div>

                  {/* Error rate */}
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-red)', marginBottom: 8 }}>Error Rate</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6, marginBottom: 16 }}>
                    <MetricCard label="ratio" value={baseline.indicators.error_rate.ratio.toFixed(4)} color="var(--rh-red)" />
                    <MetricCard label="stddev" value={baseline.indicators.error_rate.stddev.toFixed(4)} color="var(--text-dim)" />
                  </div>

                  {/* Availability */}
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-green)', marginBottom: 8 }}>Availability</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 6, marginBottom: 16, maxWidth: 200 }}>
                    <MetricCard label="ratio" value={`${(baseline.indicators.availability.ratio * 100).toFixed(2)}%`} color="var(--rh-green)" />
                  </div>

                  {/* Throughput */}
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-teal)', marginBottom: 8 }}>Throughput</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 16 }}>
                    <MetricCard label="mean rps" value={baseline.indicators.throughput.mean_rps.toFixed(1)} color="var(--rh-teal)" />
                    <MetricCard label="p95 rps" value={baseline.indicators.throughput.p95_rps.toFixed(1)} color="var(--rh-teal)" />
                    <MetricCard label="stddev" value={baseline.indicators.throughput.stddev_rps.toFixed(2)} color="var(--text-dim)" />
                  </div>

                  {/* Trace indicators (if available) */}
                  {baseline.indicators.trace_latency?.available && (
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-purple)', marginBottom: 8 }}>Trace Latency</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 16 }}>
                        <MetricCard label="service p99" value={`${baseline.indicators.trace_latency.service_p99_ms.toFixed(0)}ms`} color="var(--rh-purple)" />
                        <MetricCard label={`top dep: ${baseline.indicators.trace_latency.top_dependency}`} value={`${baseline.indicators.trace_latency.top_dependency_p99_ms.toFixed(0)}ms`} color="var(--rh-purple)" />
                        <MetricCard label="contribution" value={`${(baseline.indicators.trace_latency.top_dependency_contribution * 100).toFixed(0)}%`} color="var(--rh-purple)" />
                      </div>
                    </div>
                  )}

                  {/* Log error breakdown (if available) */}
                  {baseline.indicators.error_breakdown?.available && (
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-orange)', marginBottom: 8 }}>Error Breakdown</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6, marginBottom: 16 }}>
                        <MetricCard label={`top: ${baseline.indicators.error_breakdown.top_category.replace(/_/g, ' ')}`} value={`${(baseline.indicators.error_breakdown.top_category_ratio * 100).toFixed(1)}%`} color="var(--rh-orange)" />
                        <MetricCard label="error categories" value={`${baseline.indicators.error_breakdown.categories}`} color="var(--rh-orange)" />
                      </div>
                    </div>
                  )}

                  {/* Key reveal */}
                  <div style={{
                    padding: 14, borderRadius: 8, marginTop: 8,
                    background: 'var(--rh-teal-dim)',
                    borderLeft: '4px solid var(--rh-teal)',
                    fontSize: 14, color: 'var(--rh-teal)', fontFamily: 'Red Hat Mono, monospace', lineHeight: 1.7,
                  }}>
                    p99 = {baseline.indicators.latency.p99_ms.toFixed(0)}ms with {baseline.indicators.latency.stddev_ms.toFixed(1)}ms stddev
                    {' '}— {((baseline.indicators.latency.stddev_ms / baseline.indicators.latency.p99_ms) * 100).toFixed(0)}% variability
                  </div>
                </div>
              )}
            </StepCard>
          </div>
        );

      // ---- Act 3: The Ordeal ----
      case 3:
        return (
          <div>
            <StepCard num={3} title="Propose SLOs" status={proposalStatus}
              onRun={baselineStatus === 'done' ? doProposeSLOs : undefined}
              buttonLabel="Propose SLOs">
              {proposalStatus === 'idle' && baselineStatus !== 'done' && (
                <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                  Complete Act 2 first to compute a baseline.
                </div>
              )}
              {proposal && (
                <div>
                  {proposal.slos.map((slo, i) => (
                    <motion.div key={slo.sli_name}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.1 }}
                      style={{
                        padding: 16, background: 'var(--surface-2)', borderRadius: 8,
                        marginBottom: 12, border: '1px solid var(--border)',
                      }}>
                      {/* SLO header */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 16, fontWeight: 700 }}>{slo.sli_name}</span>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                          background: 'var(--rh-blue-dim)', color: 'var(--rh-blue)',
                        }}>
                          {slo.sli_type}
                        </span>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                          background: slo.target_op === 'lte' ? 'var(--rh-blue-dim)' : 'var(--rh-green-dim)',
                          color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)',
                        }}>
                          {slo.target_op}
                        </span>
                        {slo.requires_review && (
                          <span style={{
                            padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                            background: 'var(--rh-orange-dim)', color: 'var(--rh-orange)',
                            marginLeft: 'auto',
                          }}>
                            REQUIRES REVIEW
                          </span>
                        )}
                      </div>

                      {/* 30-day avg → SLO (objective) → SLA (commitment) → Error Budget */}
                      {slo.headroom && (() => {
                        const obs = slo.headroom.observed_value;
                        const fmtVal = (v: number) => {
                          if (slo.sli_type === 'availability') return `${(v * 100).toFixed(2)}%`;
                          if (slo.sli_type === 'error_rate') return `${(v * 100).toFixed(2)}%`;
                          if (Math.abs(v) < 1) return `${v.toFixed(4)} ${slo.target_unit}`;
                          if (Math.abs(v) < 10) return `${v.toFixed(2)} ${slo.target_unit}`;
                          return `${Math.round(v)} ${slo.target_unit}`;
                        };
                        return (
                          <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                            <div style={{ padding: '8px 14px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: '3px solid var(--text-dim)' }}>
                              <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1 }}>30-DAY AVG</div>
                              <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--text-primary)' }}>
                                {fmtVal(obs)}
                              </div>
                            </div>
                            <div style={{ alignSelf: 'center', color: 'var(--text-disabled)', fontSize: 16 }}>{'→'}</div>
                            <div style={{ padding: '8px 14px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: '3px solid var(--rh-teal)' }}>
                              <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-teal)', letterSpacing: 1 }}>SLO OBJECTIVE</div>
                              <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--rh-teal)' }}>
                                {fmtVal(slo.slo_target)}
                              </div>
                              <div style={{ fontSize: 9, color: 'var(--text-disabled)' }}>where you aim</div>
                            </div>
                            <div style={{ alignSelf: 'center', color: 'var(--text-disabled)', fontSize: 16 }}>{'→'}</div>
                            <div style={{ padding: '8px 14px', background: 'var(--surface-1)', borderRadius: 6, borderLeft: `3px solid ${slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)'}` }}>
                              <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)', letterSpacing: 1 }}>
                                SLA {slo.target_op === 'lte' ? 'CEILING' : 'FLOOR'}
                              </div>
                              <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Red Hat Display', sans-serif", color: slo.target_op === 'lte' ? 'var(--rh-blue)' : 'var(--rh-green)' }}>
                                {fmtVal(slo.sla_target)}
                              </div>
                              <div style={{ fontSize: 9, color: 'var(--text-disabled)' }}>what you guarantee</div>
                            </div>
                            <div style={{ padding: '8px 14px', background: 'var(--surface-1)', borderRadius: 6, alignSelf: 'center' }}>
                              <div style={{ fontSize: 10, fontFamily: "'Red Hat Mono', monospace", color: 'var(--text-disabled)', letterSpacing: 1 }}>ERROR BUDGET</div>
                              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'Red Hat Display', sans-serif", color: 'var(--text-secondary)' }}>
                                {slo.error_budget_percent}%
                              </div>
                            </div>
                          </div>
                        );
                      })()}

                      {/* Headroom visual */}
                      {slo.headroom && (
                        <HeadroomVisual
                          observed={slo.headroom.observed_value}
                          target={slo.sla_target}
                          margin={slo.headroom.margin}
                          unit={slo.target_unit}
                          targetOp={slo.target_op}
                          marginRationale={slo.headroom.margin_rationale}
                          sloTarget={slo.slo_target}
                        />
                      )}

                      {/* Collapsible rationale */}
                      <div style={{ marginTop: 10 }}>
                        <button
                          onClick={() => setExpandedRationale(expandedRationale === slo.sli_name ? null : slo.sli_name)}
                          style={{
                            background: 'none', border: 'none', color: 'var(--rh-blue)',
                            fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0,
                            display: 'flex', alignItems: 'center', gap: 4,
                          }}>
                          <span style={{ fontFamily: 'Red Hat Mono, monospace', fontSize: 10 }}>
                            {expandedRationale === slo.sli_name ? '▼' : '▶'}
                          </span>
                          Rationale
                        </button>
                        <AnimatePresence>
                          {expandedRationale === slo.sli_name && (
                            <motion.div
                              initial={{ opacity: 0, height: 0 }}
                              animate={{ opacity: 1, height: 'auto' }}
                              exit={{ opacity: 0, height: 0 }}
                              style={{
                                marginTop: 8, padding: 12,
                                background: 'var(--surface-1)', borderRadius: 6,
                                fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7,
                              }}>
                              {slo.rationale}
                              {slo.review_reason && (
                                <div style={{ marginTop: 8, color: 'var(--rh-orange)', fontSize: 12 }}>
                                  Review reason: {slo.review_reason}
                                </div>
                              )}
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </motion.div>
                  ))}
                  <div style={{
                    marginTop: 12, padding: 10, borderRadius: 6,
                    background: 'var(--surface-1)', border: '1px solid var(--border)',
                    fontSize: 12, color: 'var(--text-dim)', textAlign: 'center',
                    fontFamily: "'Red Hat Mono', monospace",
                  }}>
                    Generated from {baseline?.lookback_window || '30d'} baseline. Stays until promoted or demoted.
                  </div>
                </div>
              )}
            </StepCard>
          </div>
        );

      // ---- Act 4: The Reward ----
      case 4:
        return (
          <div>
            <StepCard num={4} title="Render Artifacts" status={renderStatus}
              onRun={proposalStatus === 'done' ? doRenderArtifacts : undefined}
              buttonLabel="Render Artifacts">
              {renderStatus === 'idle' && proposalStatus !== 'done' && (
                <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                  Complete Act 3 first to propose SLOs.
                </div>
              )}
              {renderOutput && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {/* OpenSLO YAML */}
                  <div>
                    <button
                      onClick={() => setExpandedArtifact(expandedArtifact === 'openslo' ? null : 'openslo')}
                      style={{
                        width: '100%', textAlign: 'left',
                        padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid var(--border)',
                        borderRadius: 8, color: 'var(--text-primary)', fontSize: 14, fontWeight: 600,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                      }}>
                      <span style={{ fontFamily: 'Red Hat Mono, monospace', fontSize: 10, color: 'var(--rh-blue)' }}>
                        {expandedArtifact === 'openslo' ? '▼' : '▶'}
                      </span>
                      OpenSLO YAML
                    </button>
                    <AnimatePresence>
                      {expandedArtifact === 'openslo' && (
                        <motion.pre
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          style={{
                            margin: 0, padding: 16,
                            background: 'var(--surface-1)', border: '1px solid var(--border)',
                            borderTop: 'none', borderRadius: '0 0 8px 8px',
                            fontSize: 12, fontFamily: 'Red Hat Mono, monospace',
                            color: 'var(--text-secondary)', overflow: 'auto', maxHeight: 400,
                            lineHeight: 1.6, whiteSpace: 'pre-wrap',
                          }}>
                          {renderOutput.openslo_yaml}
                        </motion.pre>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* Prometheus Rules */}
                  <div>
                    <button
                      onClick={() => setExpandedArtifact(expandedArtifact === 'prom' ? null : 'prom')}
                      style={{
                        width: '100%', textAlign: 'left',
                        padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid var(--border)',
                        borderRadius: 8, color: 'var(--text-primary)', fontSize: 14, fontWeight: 600,
                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
                      }}>
                      <span style={{ fontFamily: 'Red Hat Mono, monospace', fontSize: 10, color: 'var(--rh-green)' }}>
                        {expandedArtifact === 'prom' ? '▼' : '▶'}
                      </span>
                      Prometheus Rules
                    </button>
                    <AnimatePresence>
                      {expandedArtifact === 'prom' && (
                        <motion.pre
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          style={{
                            margin: 0, padding: 16,
                            background: 'var(--surface-1)', border: '1px solid var(--border)',
                            borderTop: 'none', borderRadius: '0 0 8px 8px',
                            fontSize: 12, fontFamily: 'Red Hat Mono, monospace',
                            color: 'var(--text-secondary)', overflow: 'auto', maxHeight: 400,
                            lineHeight: 1.6, whiteSpace: 'pre-wrap',
                          }}>
                          {renderOutput.prom_rules}
                        </motion.pre>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* Audit bundle info */}
                  <div style={{
                    padding: 14, background: 'var(--surface-2)', borderRadius: 8,
                    border: '1px solid var(--border)', fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7,
                  }}>
                    <div style={{ fontSize: 11, fontFamily: 'Red Hat Mono, monospace', color: 'var(--text-disabled)', letterSpacing: 1, marginBottom: 6 }}>
                      AUDIT BUNDLE
                    </div>
                    All artifacts include SHA-256 content hashes for audit trail.
                    Evidence, baseline, proposal, and rendered outputs form a tamper-evident chain.
                  </div>
                </div>
              )}
            </StepCard>
          </div>
        );

      // ---- Act 5: The Return ----
      case 5:
        return (
          <div>
            {/* Step 1: Detect Drift */}
            <StepCard num={5} title="Detect Drift" status={driftStatus}
              onRun={baselineStatus === 'done' ? doDetectDrift : undefined}
              buttonLabel="Detect Drift">
              {driftStatus === 'idle' && baselineStatus !== 'done' && (
                <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                  Complete Act 2 first to compute a baseline.
                </div>
              )}
              {driftSignal && (
                <div>
                  <DriftTimeline
                    indicators={driftSignal.indicators}
                    dominantSignal={driftSignal.dominant_signal}
                    allBreached={driftSignal.all_breached_indicators}
                  />
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-disabled)', fontFamily: "'Red Hat Mono', monospace" }}>
                    Evaluated at: {driftSignal.evaluated_at} | Window: {driftSignal.evaluation_window}
                  </div>
                </div>
              )}
            </StepCard>

            {/* Step 2: Classify & Remediate */}
            <StepCard num={6} title="Classify & Remediate" status={classifyStatus}
              onRun={driftStatus === 'done' ? doClassifyDrift : undefined}
              buttonLabel="Classify & Remediate">
              {classifyStatus === 'idle' && driftStatus !== 'done' && (
                <div style={{ fontSize: 13, color: 'var(--text-disabled)', fontStyle: 'italic' }}>
                  Detect drift first to generate a drift signal.
                </div>
              )}
              {driftReport && (
                <div>
                  {/* Classification badge */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                    <span style={{
                      padding: '4px 12px', borderRadius: 6, fontSize: 13, fontWeight: 700,
                      background: `${sevColor(driftReport.severity)}20`,
                      color: sevColor(driftReport.severity),
                    }}>
                      {driftReport.severity.toUpperCase()}
                    </span>
                    <span style={{
                      padding: '4px 12px', borderRadius: 6, fontSize: 13, fontWeight: 700,
                      background: 'var(--surface-1)', color: 'var(--text-primary)',
                      border: '1px solid var(--border)',
                    }}>
                      {driftReport.classification.replace(/_/g, ' ')}
                    </span>
                  </div>

                  {/* Likely cause */}
                  <div style={{
                    padding: 14, background: 'var(--surface-2)', borderRadius: 8,
                    border: '1px solid var(--border)', marginBottom: 16,
                    fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7,
                  }}>
                    <div style={{ fontSize: 11, fontFamily: 'Red Hat Mono, monospace', color: 'var(--text-disabled)', letterSpacing: 1, marginBottom: 6 }}>
                      LIKELY CAUSE
                    </div>
                    {driftReport.likely_cause}
                  </div>

                  {/* Recommendations */}
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--rh-blue)', marginBottom: 8 }}>
                    Recommendations
                  </div>
                  {driftReport.recommendations.map((rec, i) => (
                    <motion.div key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                      style={{
                        padding: 14, background: 'var(--surface-2)', borderRadius: 8,
                        border: '1px solid var(--border)', marginBottom: 8,
                      }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                        <span style={{
                          padding: '2px 8px', borderRadius: 4, fontSize: 10, fontWeight: 700,
                          background: rec.confidence === 'high' ? 'var(--rh-green-dim)' : rec.confidence === 'medium' ? 'var(--rh-blue-dim)' : 'var(--rh-orange-dim)',
                          color: rec.confidence === 'high' ? 'var(--rh-green)' : rec.confidence === 'medium' ? 'var(--rh-blue)' : 'var(--rh-orange)',
                        }}>
                          {rec.confidence}
                        </span>
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>{rec.action}</div>
                      <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.6 }}>{rec.rationale}</div>
                      {rec.remediation_plan && (
                        <div style={{
                          marginTop: 10, padding: 10, background: 'var(--surface-1)', borderRadius: 6,
                          fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6,
                        }}>
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                            <div>
                              <span style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Evidence basis:</span>
                              <div>{rec.remediation_plan.evidence_basis}</div>
                            </div>
                            <div>
                              <span style={{ fontSize: 10, color: 'var(--text-disabled)' }}>Verification:</span>
                              <div>{rec.remediation_plan.verification_method}</div>
                            </div>
                          </div>
                        </div>
                      )}
                    </motion.div>
                  ))}
                </div>
              )}
            </StepCard>
          </div>
        );

      // ---- Act 6: The Claim ----
      case 6:
        return (
          <div>
            {/* What sloscope gives you operationally */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              style={{ marginBottom: 24 }}>
              <p style={{ fontSize: 20, fontWeight: 700, fontFamily: "'Red Hat Display', sans-serif", marginBottom: 16 }}>
                What this means for your operations
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {/* For infrastructure */}
                <div style={{ padding: 16, background: 'var(--surface-1)', borderRadius: 8, borderLeft: '4px solid var(--rh-blue)' }}>
                  <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-blue)', letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 6 }}>
                    For infrastructure teams
                  </div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    Know when a node is approaching saturation before inference latency triples.
                    Set CPU and memory SLOs grounded in observed utilization, not guesswork.
                    When you consolidate or migrate infrastructure, sloscope tells you if the service is still meeting its commitments.
                  </div>
                </div>

                {/* For services */}
                <div style={{ padding: 16, background: 'var(--surface-1)', borderRadius: 8, borderLeft: '4px solid var(--rh-green)' }}>
                  <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-green)', letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 6 }}>
                    For service owners
                  </div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    Stop setting availability targets you cannot meet. Start with what you can prove.
                    Every SLO comes with a rationale that explains why it was chosen and what to fix to tighten it.
                    When latency regresses after a deployment, sloscope tells you whether it is systemic or tail-only, and what to investigate first.
                  </div>
                </div>

                {/* For demos/events */}
                <div style={{ padding: 16, background: 'var(--surface-1)', borderRadius: 8, borderLeft: '4px solid var(--rh-orange)' }}>
                  <div style={{ fontSize: 11, fontFamily: "'Red Hat Mono', monospace", color: 'var(--rh-orange)', letterSpacing: 1, textTransform: 'uppercase' as const, marginBottom: 6 }}>
                    For live events
                  </div>
                  <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    Run drift detection before every event. Know if your demo service has degraded since the last baseline.
                    Get a prioritized remediation plan — what to fix immediately, what to investigate, what to address long-term — instead of scrambling during setup.
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Maturity journey */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
              style={{ marginBottom: 24 }}>
              <p style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 12, textAlign: 'center' }}>
                SLOs that start achievable and tighten as you earn the right
              </p>
              <MaturityLadder current="growing" />
            </motion.div>

            {/* CTA */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
              style={{ textAlign: 'center', padding: 24, background: 'var(--surface-1)', borderRadius: 10, border: '1px solid var(--rh-red)40' }}>
              <p style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>
                Your turn.
              </p>
              <p style={{ fontSize: 14, color: 'var(--text-dim)', marginBottom: 16 }}>
                Pick a service. See its baseline. Get an SLO you can actually meet. Inject drift and see the response.
              </p>
              <button onClick={() => setMode('lab')}
                style={{ background: 'var(--rh-red)', border: 'none', color: '#fff', padding: '12px 36px', borderRadius: 8, fontSize: 16, fontWeight: 700, cursor: 'pointer' }}>
                Try it yourself
              </button>
            </motion.div>
          </div>
        );

      default:
        return null;
    }
  };

  const campbellStage = [
    'Ordinary World',
    'Call to Adventure',
    'Crossing the Threshold',
    'The Ordeal',
    'The Reward',
    'The Return',
    'The Claim',
  ];

  const actTitles = [
    'The Platform Hums',
    'The Evidence Arrives',
    'Measuring Reality',
    'What Can You Actually Commit To?',
    'Deployable Truth',
    'When Reality Shifts',
    'The Complete Lifecycle',
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />

      {/* Act indicator dots */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, padding: '10px 0', borderBottom: '1px solid var(--border)', background: 'var(--bg-dark)' }}>
        {ACT_LABELS.map((label, i) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div
              onClick={() => { if (i <= actIndex) setActIndex(i); }}
              style={{
                width: 10, height: 10, borderRadius: '50%',
                cursor: i <= actIndex ? 'pointer' : 'default',
                background: i === actIndex ? 'var(--rh-red)' : i < actIndex ? 'var(--rh-green)' : 'var(--border)',
                transition: 'background 0.3s',
              }}
            />
            <span style={{ fontSize: 10, color: i === actIndex ? 'var(--text-primary)' : 'var(--text-disabled)' }}>{label.split(' ').pop()}</span>
          </div>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, maxWidth: 900, margin: '0 auto', padding: '32px 24px', width: '100%' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={actIndex}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.4 }}
          >
            {/* Act header */}
            <div style={{ marginBottom: 24 }}>
              <div style={{
                fontSize: 11, fontFamily: 'Red Hat Mono, monospace', fontWeight: 700,
                color: 'var(--rh-red)', letterSpacing: 2, textTransform: 'uppercase' as const,
                marginBottom: 4,
              }}>
                ACT {actIndex + 1} OF 7
              </div>
              <h2 style={{ fontSize: 24, fontWeight: 800, fontFamily: 'Red Hat Display, sans-serif', marginBottom: 4 }}>
                {actTitles[actIndex]}
              </h2>
              <p style={{ fontSize: 13, color: 'var(--text-disabled)', margin: 0, fontStyle: 'italic' }}>
                {campbellStage[actIndex]}
              </p>
            </div>

            {/* Act content */}
            {renderAct()}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Footer */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '14px 32px', borderTop: '1px solid var(--border)', background: 'var(--surface-1)',
      }}>
        <button
          onClick={() => {
            if (actIndex > 0) {
              setActIndex(actIndex - 1);
            } else {
              setMode('slides');
              setSlide(SLIDES.length - 1);
            }
          }}
          style={{
            background: 'none', border: '1px solid var(--border)',
            color: 'var(--text-dim)', padding: '6px 16px', borderRadius: 6,
            fontSize: 13, cursor: 'pointer',
          }}>
          {actIndex === 0 ? 'Exit' : 'Back'}
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-disabled)', fontFamily: 'Red Hat Mono, monospace' }}>
          {actIndex + 1} / {ACT_LABELS.length}
        </span>
        {actIndex < ACT_LABELS.length - 1 ? (
          <button
            onClick={() => setActIndex(actIndex + 1)}
            style={{
              background: 'var(--rh-red)', border: 'none', color: '#fff',
              padding: '6px 18px', borderRadius: 6, fontSize: 13, fontWeight: 600,
              cursor: 'pointer',
            }}>
            Next
          </button>
        ) : (
          <div style={{ width: 80 }} />
        )}
      </div>
    </div>
  );
}
