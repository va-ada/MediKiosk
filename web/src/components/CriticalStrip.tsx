import type { CriticalItem, RedFlagItem, Summary } from '../api/types'
import TrustChip from './TrustChip'

/** Critical strip: allergies (always shown, whatever their trust), red flags, abnormal labs. */
export default function CriticalStrip({ critical }: { critical: Summary['critical'] }) {
  return (
    <section aria-label="Critical information" className="grid grid-cols-1 gap-2 md:grid-cols-3">
      <Box title="Allergies" items={critical.allergies} empty="None reported" tone="red" />
      <RedFlags items={critical.red_flags} />
      <Box title="Abnormal labs" items={critical.abnormal_labs} empty="None found" tone="orange" />
    </section>
  )
}

function Box({ title, items, empty, tone }: { title: string; items: CriticalItem[]; empty: string; tone: 'red' | 'orange' }) {
  const active = items.length > 0
  const ring = !active ? 'ring-slate-200 bg-white' : tone === 'red' ? 'ring-red-300 bg-red-50' : 'ring-orange-300 bg-orange-50'
  return (
    <div className={`rounded-lg p-3 ring-1 ${ring}`}>
      <h3 className={`text-xs font-bold tracking-wide uppercase ${active ? 'text-brand-red' : 'text-slate-500'}`}>
        {title}
      </h3>
      {active ? (
        <ul className="mt-1 space-y-1">
          {items.map((it) => (
            <li key={it.fact_id} className="flex flex-wrap items-center gap-2 text-sm font-medium">
              <span>{it.text}</span>
              <TrustChip trust={it.trust} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-500">{empty}</p>
      )}
    </div>
  )
}

/** Red flags come from alerts (`{alert_id, text, level, status}`), not facts — no trust chip. */
function RedFlags({ items }: { items: RedFlagItem[] }) {
  const active = items.length > 0
  return (
    <div className={`rounded-lg p-3 ring-1 ${active ? 'bg-red-50 ring-red-300' : 'bg-white ring-slate-200'}`}>
      <h3 className={`text-xs font-bold tracking-wide uppercase ${active ? 'text-brand-red' : 'text-slate-500'}`}>
        Red flags
      </h3>
      {active ? (
        <ul className="mt-1 space-y-1">
          {items.map((it) => (
            <li key={it.alert_id} className="flex flex-wrap items-center gap-2 text-sm font-medium">
              <span>{it.text}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${
                  it.level === 'emergency' ? 'bg-brand-red text-white ring-brand-red' : 'bg-orange-100 text-orange-800 ring-orange-300'
                }`}
              >
                {it.level} · {it.status}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-slate-500">None</p>
      )}
    </div>
  )
}
