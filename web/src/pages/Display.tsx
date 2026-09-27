import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { CalledQueueItem, Department, DisplayState, WsMessage } from '../api/types'
import { useChannel } from '../ws/useChannel'

const DEPT_KEY = 'mk.display.department'
const POLL_MS = 15_000
const FLASH_MS = 10_000
const NEXT_SHOWN = 5

type DeptChoice = Department | 'all'
const DEPT_LABEL: Record<DeptChoice, string> = { all: 'All OPDs', general: 'General OPD', ayurveda: 'Ayurveda OPD' }

function loadDept(): DeptChoice {
  try {
    const v = localStorage.getItem(DEPT_KEY)
    return v === 'general' || v === 'ayurveda' ? v : 'all'
  } catch {
    return 'all'
  }
}

/** "A-017" → "A 17" so voices read a number rather than digits with a dash. */
function spokenToken(display: string): string {
  const m = /^([A-Za-z]+)-0*(\d+)$/.exec(display)
  return m ? `${m[1]} ${m[2]}` : display
}

/** Two-tone "ding-dong". */
function chime(ctx: AudioContext): void {
  ;[
    { f: 880, at: 0 },
    { f: 660, at: 0.35 },
  ].forEach(({ f, at }) => {
    const t = ctx.currentTime + at
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = f
    gain.gain.setValueAtTime(0.0001, t)
    gain.gain.exponentialRampToValueAtTime(0.4, t + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.9)
    osc.connect(gain).connect(ctx.destination)
    osc.start(t)
    osc.stop(t + 1)
  })
}

function announce(item: CalledQueueItem): void {
  const synth = window.speechSynthesis
  if (!synth) return
  const voices = synth.getVoices()
  const hi = voices.find((v) => v.lang.toLowerCase().replace('_', '-') === 'hi-in')
  const en = voices.find((v) => v.lang.toLowerCase().startsWith('en-in')) ?? voices.find((v) => v.lang.startsWith('en'))
  const token = spokenToken(item.display)
  const room = item.room ?? ''
  if (hi) {
    const parts = [`टोकन ${token}`, item.doctor_name, room.replace(/^room\s*/i, 'कमरा नंबर ')].filter(Boolean)
    const u = new SpeechSynthesisUtterance(parts.join(', '))
    u.voice = hi
    u.lang = 'hi-IN'
    u.rate = 0.9
    synth.speak(u)
  }
  const u = new SpeechSynthesisUtterance([`Token ${token}`, item.doctor_name, room].filter(Boolean).join(', '))
  if (en) u.voice = en
  u.lang = en?.lang ?? 'en-IN'
  u.rate = 0.9
  synth.speak(u)
}

/** `/display`: public waiting-hall board — now serving (token, doctor, room) + next tokens; chime and voice on call. */
export default function Display() {
  const [dept, setDept] = useState<DeptChoice>(loadDept)
  const [state, setState] = useState<DisplayState | null>(null)
  const [error, setError] = useState(false)
  const [flash, setFlash] = useState<{ display: string; until: number } | null>(null)
  const [clock, setClock] = useState(() => new Date())

  const load = useCallback(async (): Promise<void> => {
    try {
      const q = dept === 'all' ? '' : `?department=${dept}`
      setState(await api<DisplayState>('GET', `/api/display/state${q}`, undefined, { auth: false }))
      setError(false)
    } catch {
      setError(true)
    }
  }, [dept])

  useEffect(() => {
    void load()
    const t = setInterval(() => void load(), POLL_MS)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const chooseDept = (d: DeptChoice): void => {
    setDept(d)
    try {
      localStorage.setItem(DEPT_KEY, d)
    } catch {
      // storage unavailable — choice lasts for this page only
    }
  }

  // ---- sound: browsers need one click before audio / speech may play ----
  const audio = useRef<AudioContext | null>(null)
  const [soundOn, setSoundOn] = useState(false)
  const enableSound = (): void => {
    audio.current ??= new AudioContext()
    void audio.current.resume()
    window.speechSynthesis?.getVoices() // start loading voices
    setSoundOn(true)
  }
  useEffect(() => () => void audio.current?.close(), [])

  const soundRef = useRef(soundOn)
  useEffect(() => {
    soundRef.current = soundOn
  }, [soundOn])

  const reloadTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const onMessage = useCallback(
    (msg: WsMessage) => {
      if (!msg.type.startsWith('token.')) return
      // Coalesce bursts of token events into one reload.
      clearTimeout(reloadTimer.current)
      reloadTimer.current = setTimeout(() => void load(), 150)
      if (msg.type !== 'token.called') return
      const item = msg.data
      if (dept !== 'all' && item.department !== dept) return
      setFlash({ display: item.display, until: Date.now() + FLASH_MS })
      if (soundRef.current) {
        if (audio.current) chime(audio.current)
        setTimeout(() => announce(item), 1100)
      }
    },
    [dept, load],
  )
  useEffect(() => () => clearTimeout(reloadTimer.current), [])
  const { connected } = useChannel('display', onMessage)

  const flashing = flash && flash.until > clock.getTime() ? flash.display : null
  const serving = state?.now_serving ?? []
  const next = (state?.next ?? []).slice(0, NEXT_SHOWN)

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 p-6 text-white">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="text-3xl font-bold">MediKiosk</span>
          <label className="sr-only" htmlFor="display-dept">
            Department
          </label>
          <select
            id="display-dept"
            value={dept}
            onChange={(e) => chooseDept(e.target.value as DeptChoice)}
            className="rounded-md bg-slate-800 px-3 py-2 text-xl text-white"
          >
            {(Object.keys(DEPT_LABEL) as DeptChoice[]).map((d) => (
              <option key={d} value={d}>
                {DEPT_LABEL[d]}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-4 text-2xl">
          {(error || !connected) && (
            <span className="rounded-md bg-yellow-400 px-3 py-1 text-lg font-bold text-black">
              {error ? 'Offline — showing last update' : 'Reconnecting…'}
            </span>
          )}
          <time className="font-mono text-4xl font-bold tabular-nums">
            {clock.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </time>
        </div>
      </header>

      <main className="mt-6 flex flex-1 flex-col gap-8">
        <section aria-labelledby="now-serving">
          <h1 id="now-serving" className="text-4xl font-bold text-yellow-300">
            Now serving <span className="font-normal text-yellow-200">· अभी बारी</span>
          </h1>
          {serving.length === 0 ? (
            <p className="mt-6 text-5xl text-slate-400">Please wait for your token · कृपया प्रतीक्षा करें</p>
          ) : (
            <ul className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-2">
              {serving.map((s) => (
                <li
                  key={s.display}
                  className={`rounded-3xl p-6 ring-4 ${
                    flashing === s.display ? 'bg-yellow-300 text-black ring-white' : 'bg-slate-900 ring-slate-700'
                  }`}
                >
                  <div className="font-mono text-[clamp(5rem,12vw,10rem)] leading-none font-extrabold tracking-tight">
                    {s.display}
                  </div>
                  <div className="mt-3 flex flex-wrap items-baseline gap-x-6 text-4xl font-semibold">
                    {s.room && <span>→ {s.room}</span>}
                    {s.doctor_name && <span className="opacity-80">{s.doctor_name}</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="next-up">
          <h2 id="next-up" className="text-3xl font-bold text-slate-300">
            Next <span className="font-normal">· अगले</span>
          </h2>
          {next.length === 0 ? (
            <p className="mt-3 text-3xl text-slate-500">—</p>
          ) : (
            <ol className="mt-3 flex flex-wrap gap-4">
              {next.map((d) => (
                <li key={d} className="rounded-2xl bg-slate-800 px-6 py-3 font-mono text-6xl font-bold">
                  {d}
                </li>
              ))}
            </ol>
          )}
        </section>
      </main>

      {!soundOn && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
          <button
            type="button"
            autoFocus
            onClick={enableSound}
            className="rounded-3xl bg-yellow-300 px-12 py-10 text-5xl font-extrabold text-black shadow-2xl"
          >
            🔊 Click to enable sound
            <span className="mt-2 block text-3xl font-semibold">आवाज़ चालू करने के लिए क्लिक करें</span>
          </button>
        </div>
      )}
    </div>
  )
}
