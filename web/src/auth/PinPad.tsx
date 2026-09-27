import { useEffect } from 'react'

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'clear', '0', 'back'] as const
export const PIN_LENGTH = 4

interface Props {
  value: string
  onChange: (pin: string) => void
  /** Called when the 4th digit is entered. */
  onComplete?: (pin: string) => void
  disabled?: boolean
  /** Also accept digits typed on a physical keyboard (off while another input has focus). */
  captureKeyboard?: boolean
}

/** Large 4-digit PIN keypad with dots. */
export default function PinPad({ value, onChange, onComplete, disabled = false, captureKeyboard = true }: Props) {
  const press = (key: (typeof KEYS)[number]): void => {
    if (disabled) return
    if (key === 'clear') return onChange('')
    if (key === 'back') return onChange(value.slice(0, -1))
    if (value.length >= PIN_LENGTH) return
    const next = value + key
    onChange(next)
    if (next.length === PIN_LENGTH) onComplete?.(next)
  }

  useEffect(() => {
    if (!captureKeyboard) return
    const onKey = (e: KeyboardEvent): void => {
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return
      if (/^\d$/.test(e.key)) press(e.key as (typeof KEYS)[number])
      else if (e.key === 'Backspace') press('back')
      else if (e.key === 'Escape') press('clear')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-3" aria-label={`${value.length} of ${PIN_LENGTH} digits entered`}>
        {Array.from({ length: PIN_LENGTH }, (_, i) => (
          <span
            key={i}
            className={`h-4 w-4 rounded-full border-2 border-navy ${i < value.length ? 'bg-navy' : 'bg-transparent'}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((key) => (
          <button
            key={key}
            type="button"
            disabled={disabled}
            onClick={() => press(key)}
            className={`h-16 w-20 rounded-xl text-2xl font-semibold shadow-sm transition active:scale-95 disabled:opacity-50 ${
              key === 'clear' || key === 'back'
                ? 'bg-slate-200 text-base text-slate-700 hover:bg-slate-300'
                : 'bg-white text-navy ring-1 ring-slate-300 hover:bg-slate-50'
            }`}
            aria-label={key === 'back' ? 'Delete last digit' : key === 'clear' ? 'Clear PIN' : key}
          >
            {key === 'back' ? '⌫' : key === 'clear' ? 'Clear' : key}
          </button>
        ))}
      </div>
    </div>
  )
}
