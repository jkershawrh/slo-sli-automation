import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface Props {
  text: string;
  alwaysOpen?: boolean;
}

export function FlowDescription({ text, alwaysOpen = false }: Props) {
  const [open, setOpen] = useState(alwaysOpen);

  if (!text) return null;

  if (alwaysOpen) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        style={{
          padding: '14px 18px', marginBottom: 16,
          borderLeft: '3px solid var(--rh-blue)',
          background: 'var(--rh-blue-dim)',
          borderRadius: '0 8px 8px 0',
          fontSize: 13, lineHeight: 1.8, color: 'var(--text-secondary)',
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--rh-blue)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 1 }}>
          How it works
        </div>
        {text}
      </motion.div>
    );
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <button onClick={() => setOpen(!open)} style={{
        background: 'none', border: 'none', color: 'var(--rh-blue)',
        fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0,
        display: 'flex', alignItems: 'center', gap: 4,
      }}>
        <span style={{ fontFamily: 'Red Hat Mono, monospace', fontSize: 10 }}>{open ? '▼' : '▶'}</span>
        How it works
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            style={{
              padding: '12px 16px', marginTop: 8,
              borderLeft: '3px solid var(--rh-blue)',
              background: 'var(--rh-blue-dim)',
              borderRadius: '0 8px 8px 0',
              fontSize: 13, lineHeight: 1.8, color: 'var(--text-secondary)',
            }}
          >
            {text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
