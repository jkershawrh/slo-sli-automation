import { type ReactNode } from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function DetailModal({ open, title, onClose, children }: Props) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} exit={{ opacity: 0 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: '#000', zIndex: 200 }}
          />
          <motion.div
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{
              position: 'fixed', top: 0, right: 0, bottom: 0, width: 420,
              background: 'var(--surface-1)', borderLeft: '1px solid var(--border)',
              zIndex: 201, display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}
          >
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '14px 16px', borderBottom: '1px solid var(--border)',
            }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
              <button onClick={onClose} style={{
                background: 'none', border: 'none', color: 'var(--text-dim)',
                fontSize: 18, cursor: 'pointer', padding: '0 4px',
              }}>×</button>
            </div>
            <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export function KeyValueTable({ data, label }: { data: Record<string, unknown>; label?: string }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 6, fontWeight: 600 }}>{label}</div>}
      <div style={{ background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden' }}>
        {entries.map(([key, val]) => (
          <div key={key} style={{
            display: 'flex', justifyContent: 'space-between', padding: '6px 10px',
            borderBottom: '1px solid var(--border)', fontSize: 12,
          }}>
            <span style={{ color: 'var(--text-dim)', fontFamily: 'Red Hat Mono, monospace' }}>{key}</span>
            <span style={{ color: 'var(--text-secondary)', fontFamily: 'Red Hat Mono, monospace', textAlign: 'right', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {typeof val === 'object' ? JSON.stringify(val) : String(val)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ComparisonTable({ before, after, label }: { before: Record<string, unknown>; after: Record<string, unknown>; label?: string }) {
  const allKeys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  if (allKeys.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 6, fontWeight: 600 }}>{label}</div>}
      <div style={{ background: 'var(--surface-2)', borderRadius: 6, overflow: 'hidden' }}>
        <div style={{ display: 'flex', padding: '6px 10px', borderBottom: '1px solid var(--border)', fontSize: 10, color: 'var(--text-disabled)' }}>
          <span style={{ flex: 1 }}>Key</span>
          <span style={{ width: 100, textAlign: 'right' }}>Before</span>
          <span style={{ width: 20, textAlign: 'center' }}>→</span>
          <span style={{ width: 100, textAlign: 'right' }}>After</span>
        </div>
        {allKeys.map(key => {
          const b = before[key];
          const a = after[key];
          const changed = JSON.stringify(b) !== JSON.stringify(a);
          return (
            <div key={key} style={{
              display: 'flex', padding: '6px 10px', borderBottom: '1px solid var(--border)',
              fontSize: 12, background: changed ? 'var(--rh-orange-dim)' : undefined,
            }}>
              <span style={{ flex: 1, color: 'var(--text-dim)', fontFamily: 'Red Hat Mono, monospace' }}>{key}</span>
              <span style={{ width: 100, textAlign: 'right', color: 'var(--text-disabled)', fontFamily: 'Red Hat Mono, monospace' }}>{b !== undefined ? String(b) : '—'}</span>
              <span style={{ width: 20, textAlign: 'center', color: changed ? 'var(--rh-orange)' : 'var(--text-disabled)' }}>{changed ? '→' : '='}</span>
              <span style={{ width: 100, textAlign: 'right', color: changed ? 'var(--rh-orange)' : 'var(--text-secondary)', fontFamily: 'Red Hat Mono, monospace' }}>{a !== undefined ? String(a) : '—'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
