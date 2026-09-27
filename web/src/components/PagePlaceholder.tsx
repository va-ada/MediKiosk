import type { ReactNode } from 'react'

/** Temporary page body used until a route's task card is built. */
export default function PagePlaceholder({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold text-navy">{title}</h1>
      <p className="mt-2 text-slate-600">{children ?? 'Coming soon.'}</p>
    </main>
  )
}
