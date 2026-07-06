import { motion } from 'motion/react';

interface Props {
  label: string;
  value: string | number;
  color?: string;
  detail?: string;
  onClick?: () => void;
}

export function MetricCard({ label, value, color = 'var(--text-primary)', detail, onClick }: Props) {
  return (
    <motion.div
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      onClick={onClick}
      style={{
        background: 'var(--surface-1)', border: '1px solid var(--border)',
        borderRadius: 10, padding: 16, textAlign: 'center',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 800, color, fontFamily: 'Red Hat Display, sans-serif' }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>{label}</div>
      {detail && <div style={{ fontSize: 10, color: 'var(--text-disabled)', marginTop: 2 }}>{detail}</div>}
    </motion.div>
  );
}
