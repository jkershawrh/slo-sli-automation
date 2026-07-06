import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface Props {
  label: string;
  data: unknown;
  defaultOpen?: boolean;
}

export function JsonViewer({ label, data, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', marginTop: 8 }}>
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', cursor: 'pointer', fontSize: 12, color: 'var(--text-dim)',
        }}
      >
        <span>{label}</span>
        <span style={{ fontFamily: 'Red Hat Mono, monospace' }}>{open ? '▼' : '▶'}</span>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            <pre style={{
              padding: '8px 12px', margin: 0, fontSize: 11, lineHeight: 1.5,
              color: 'var(--text-secondary)', overflow: 'auto', maxHeight: 300,
              fontFamily: 'Red Hat Mono, monospace', borderTop: '1px solid var(--border)',
            }}>
              {JSON.stringify(data, null, 2)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
