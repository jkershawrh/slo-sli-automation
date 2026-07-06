import { type ReactNode } from 'react';
import { motion, AnimatePresence } from 'motion/react';

type Status = 'idle' | 'running' | 'done' | 'error';

interface Props {
  num: number;
  title: string;
  status: Status;
  onRun?: () => void;
  buttonLabel?: string;
  children?: ReactNode;
}

const STATUS_BG: Record<Status, string> = {
  idle: 'var(--border)',
  running: 'var(--rh-blue)',
  done: 'var(--rh-green)',
  error: 'var(--rh-red)',
};

export function StepCard({ num, title, status, onRun, buttonLabel, children }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      style={{
        background: 'var(--surface-1)', border: '1px solid var(--border)',
        borderRadius: 10, padding: 20, marginBottom: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', display: 'flex',
          alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 800,
          background: STATUS_BG[status], color: '#fff',
          fontFamily: 'Red Hat Mono, monospace',
        }}>
          {status === 'running' ? '...' : status === 'done' ? '✓' : num}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 15 }}>{title}</div>
        </div>
        {onRun && status !== 'done' && (
          <button
            onClick={onRun}
            disabled={status === 'running'}
            style={{
              background: 'var(--rh-red)', color: '#fff',
              border: 'none', padding: '6px 18px', borderRadius: 6,
              fontSize: 13, fontWeight: 600,
              opacity: status === 'running' ? 0.5 : 1,
            }}
          >
            {status === 'running' ? 'Running...' : buttonLabel || 'Run'}
          </button>
        )}
        {status === 'done' && !onRun && (
          <span style={{ fontSize: 12, color: 'var(--rh-green)', fontWeight: 600 }}>Complete</span>
        )}
      </div>
      <AnimatePresence>
        {children && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ marginTop: 16 }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
