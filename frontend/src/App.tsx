import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Header } from './components/Header';
import { StepCard } from './components/StepCard';
import { MetricCard } from './components/MetricCard';
import { GoldenSignalCard } from './components/GoldenSignalCard';
import { HeadroomVisual } from './components/HeadroomVisual';
import { FlowDescription } from './components/FlowDescription';
import { DriftTimeline } from './components/DriftTimeline';
import { ToolchainDiagram } from './components/ToolchainDiagram';
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
  const [liveEvidence, setLiveEvidence] = useState<Evidence | null>(null);

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
      // Collect live evidence (loads latency regression fixture)
      const liveCall = await api.collectEvidence('checkout-api', 'payments');
      setLiveEvidence(liveCall.response.data);
      const driftCall = await api.computeDrift(baseline, liveCall.response.data);
      setDriftSignal(driftCall.response.data);
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

    // 3: The Proof
    () => (
      <div style={{ textAlign: 'center' }}>
        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15 }}>
          <div style={{ fontSize: 120, fontWeight: 800, color: 'var(--rh-red)', fontFamily: 'Red Hat Display, sans-serif', lineHeight: 1 }}>
            416
          </div>
        </motion.div>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}
          style={{ fontSize: 24, color: 'var(--text-dim)', marginTop: 8 }}>
          tests
        </motion.p>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}
          style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginTop: 32, maxWidth: 600, margin: '32px auto 0' }}>
          <MetricCard label="verification checks" value="25" color="var(--rh-blue)" />
          <MetricCard label="eval scenarios" value="13" color="var(--rh-teal)" />
          <MetricCard label="fabricated numbers" value="0" color="var(--rh-green)" />
        </motion.div>
      </div>
    ),

    // 4: The Four Golden Signals
    () => (
      <div style={{ maxWidth: 700 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 28, fontWeight: 700, fontFamily: 'Red Hat Display, sans-serif', textAlign: 'center', marginBottom: 8 }}>
          The Four Golden Signals
        </motion.p>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
          style={{ fontSize: 16, color: 'var(--text-dim)', textAlign: 'center', marginBottom: 32 }}>
          Direction matters.
        </motion.p>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <GoldenSignalCard signal="Latency" description="Response time must stay at or below threshold" targetOp="lte" example="p99 <= 600ms" color="var(--rh-blue)" />
          <GoldenSignalCard signal="Errors" description="Error rate must stay at or below threshold" targetOp="lte" example="error_rate <= 0.003" color="var(--rh-red)" />
          <GoldenSignalCard signal="Traffic" description="Throughput must stay at or above threshold" targetOp="gte" example="rps >= 4.0" color="var(--rh-green)" />
          <GoldenSignalCard signal="Saturation" description="Resource usage must stay at or below threshold" targetOp="lte" example="cpu <= 0.80" color="var(--rh-orange)" />
        </motion.div>
      </div>
    ),

    // 5: Incremental, not aspirational
    () => (
      <div style={{ maxWidth: 700 }}>
        <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          style={{ fontSize: 28, fontWeight: 700, fontFamily: 'Red Hat Display, sans-serif', textAlign: 'center', marginBottom: 32 }}>
          Incremental, not aspirational
        </motion.p>
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }}
          style={{ padding: 20, background: 'var(--surface-1)', borderLeft: '4px solid var(--rh-red)', borderRadius: '0 10px 10px 0', marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontFamily: 'Red Hat Mono, monospace', color: 'var(--text-disabled)', letterSpacing: 1, marginBottom: 8 }}>BEFORE</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, fontSize: 14 }}>
            <div><span style={{ color: 'var(--text-dim)' }}>Target:</span> <strong>99.9%</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Observed:</span> <strong>93.2%</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Gap:</span> <strong>6.7pp</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Result:</span> <strong style={{ color: 'var(--rh-red)' }}>permanent alert fatigue</strong></div>
          </div>
        </motion.div>
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.6 }}
          style={{ padding: 20, background: 'var(--surface-1)', borderLeft: '4px solid var(--rh-green)', borderRadius: '0 10px 10px 0' }}>
          <div style={{ fontSize: 11, fontFamily: 'Red Hat Mono, monospace', color: 'var(--text-disabled)', letterSpacing: 1, marginBottom: 8 }}>AFTER</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, fontSize: 14 }}>
            <div><span style={{ color: 'var(--text-dim)' }}>Target:</span> <strong>89.2%</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Observed:</span> <strong>93.2%</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Headroom:</span> <strong>2 stddev</strong></div>
            <div><span style={{ color: 'var(--text-dim)' }}>Result:</span> <strong style={{ color: 'var(--rh-green)' }}>achievable, defensible, promotable</strong></div>
          </div>
        </motion.div>
      </div>
    ),

    // 6: CTA
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

                      {/* Target value */}
                      <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 12 }}>
                        Target: <strong style={{ fontFamily: 'Red Hat Mono, monospace' }}>
                          {slo.target}{slo.target_unit}
                        </strong>
                        {' '}| Error Budget: <strong style={{ fontFamily: 'Red Hat Mono, monospace' }}>
                          {slo.error_budget_percent}%
                        </strong>
                      </div>

                      {/* Headroom visual */}
                      {slo.headroom && (
                        <HeadroomVisual
                          observed={slo.headroom.observed_value}
                          target={slo.target}
                          margin={slo.headroom.margin}
                          unit={slo.target_unit}
                          targetOp={slo.target_op}
                          marginRationale={slo.headroom.margin_rationale}
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
                  {liveEvidence && (
                    <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-disabled)', fontFamily: 'Red Hat Mono, monospace' }}>
                      Evaluated at: {driftSignal.evaluated_at} | Window: {driftSignal.evaluation_window}
                    </div>
                  )}
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
            {/* Toolchain */}
            <div style={{ marginBottom: 24 }}>
              <ToolchainDiagram activeStage="sloscope" />
            </div>

            {/* Maturity ladder */}
            <div style={{ marginBottom: 24 }}>
              <MaturityLadder current="growing" />
            </div>

            {/* Summary metrics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 24 }}>
              <MetricCard label="tests" value="416" color="var(--rh-red)" />
              <MetricCard label="verification checks" value="25" color="var(--rh-blue)" />
              <MetricCard label="fabricated numbers" value="0" color="var(--rh-green)" />
            </div>

            {/* CTA */}
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
              style={{ textAlign: 'center', padding: 24, background: 'var(--surface-1)', borderRadius: 10, border: '1px solid var(--rh-red)40' }}>
              <p style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
                The complete lifecycle: evidence, baseline, proposal, artifacts, drift, remediation.
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
