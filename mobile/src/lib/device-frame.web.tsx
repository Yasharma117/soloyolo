// The web build as a phone, after Markon's prototype shell (app-shell/phone-frame.tsx, device-switcher.tsx,
// device-chrome.tsx, touch-cursor.tsx). On a phone or tablet the app fills the browser. On a desktop it sits in a
// device-sized frame with that OS's status bar and home indicator drawn in, a device picker above, scaled to fit.
import { useTheme } from '@soloyolo/design-system'
import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { SafeAreaFrameContext, SafeAreaInsetsContext, SafeAreaProvider } from 'react-native-safe-area-context'

type Device = { id: string; name: string; short: string; width: number; height: number; os: 'ios' | 'android'; cutout: 'island' | 'hole' | 'none'; homeButton?: boolean }

const devices: Device[] = [
  { id: 'galaxy-s23', name: 'Galaxy S23', short: 'S23', width: 360, height: 780, os: 'android', cutout: 'hole' },
  { id: 'pixel-7', name: 'Pixel 7', short: 'Pixel 7', width: 412, height: 915, os: 'android', cutout: 'hole' },
  { id: 'iphone-se', name: 'iPhone SE', short: 'SE', width: 375, height: 667, os: 'ios', cutout: 'none', homeButton: true },
  { id: 'iphone-15', name: 'iPhone 15', short: 'iPhone 15', width: 390, height: 844, os: 'ios', cutout: 'island' },
  { id: 'iphone-15-pro-max', name: 'iPhone 15 Pro Max', short: '15 Pro Max', width: 430, height: 932, os: 'ios', cutout: 'island' },
]

const KEY = 'soloyolo.device'
const DESKTOP_QUERY = '(min-width: 1024px) and (pointer: fine)'
const BAR = 64 // the device picker above the frame
const CAPTION = 44 // the caption under it
const BEZEL = 10
/** The fingertip: about 7 mm, Apple's 44 pt minimum target. */
const TOUCH = 44

/** Heights of the drawn OS chrome, which become the app's safe-area insets. */
const chrome = (d: Device) => (d.os === 'ios' ? (d.homeButton ? { status: 20, bottom: 0 } : { status: 47, bottom: 34 }) : { status: 28, bottom: 24 })

const stored = () => {
  try { return devices.find((d) => d.id === window.localStorage.getItem(KEY)) } catch { return undefined }
}

function useDesktop() {
  const [desktop, setDesktop] = useState(() => window.matchMedia(DESKTOP_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_QUERY)
    const update = () => setDesktop(mq.matches)
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])
  return desktop
}

function useFit(device: Device) {
  const fit = () => Math.min(1, (window.innerHeight - BAR - CAPTION - 40) / (device.height + BEZEL * 2), (window.innerWidth - 48) / (device.width + BEZEL * 2))
  const [scale, setScale] = useState(fit)
  useEffect(() => {
    const update = () => setScale(fit())
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [device]) // eslint-disable-line react-hooks/exhaustive-deps
  return scale
}

export function DeviceFrame({ children }: { children: ReactNode }) {
  const desktop = useDesktop()
  if (!desktop) return <SafeAreaProvider>{children}</SafeAreaProvider>
  return <Stage>{children}</Stage>
}

function Stage({ children }: { children: ReactNode }) {
  const t = useTheme()
  const [device, setDeviceState] = useState<Device>(() => stored() ?? devices[3])
  const scale = useFit(device)
  const frameRef = useRef<HTMLDivElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const os = chrome(device)
  const setDevice = (d: Device) => {
    setDeviceState(d)
    try { window.localStorage.setItem(KEY, d.id) } catch { /* storage unavailable: lasts this visit */ }
  }

  useEffect(() => {
    document.body.style.backgroundColor = t.color.wash
  }, [t.color.wash])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', overflow: 'hidden', fontFamily: 'system-ui, -apple-system, sans-serif',
                  color: t.color.textPrimary, background: `radial-gradient(120% 80% at 50% 0%, ${t.color.wash}, ${t.color.background})` }}>
      <div style={{ height: BAR, flexShrink: 0, display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', padding: '0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18, fontWeight: 700, letterSpacing: -0.3 }}>soloyolo</span>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.4, textTransform: 'uppercase', padding: '3px 8px', borderRadius: 999,
                         color: t.color.textTertiary, border: `1px solid ${t.color.border}` }}>Prototype</span>
        </div>
        <div role="radiogroup" aria-label="Preview device"
             style={{ display: 'flex', gap: 2, padding: 4, borderRadius: 999, background: t.color.surface, border: `1px solid ${t.color.border}` }}>
          {devices.map((d) => {
            const on = d.id === device.id
            return (
              <button key={d.id} type="button" role="radio" aria-checked={on} title={`${d.name} · ${d.width} × ${d.height}`} onClick={() => setDevice(d)}
                      style={{ border: 0, cursor: 'pointer', borderRadius: 999, padding: '6px 12px', fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', fontFamily: 'inherit',
                               transition: 'background-color 120ms linear, color 120ms linear',
                               background: on ? t.color.textPrimary : 'transparent', color: on ? t.color.background : t.color.textTertiary }}>
                {d.short}
              </button>
            )
          })}
        </div>
        <div />
      </div>

      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, paddingBottom: 24 }}>
        <div ref={wrapperRef} style={{ position: 'relative', width: (device.width + BEZEL * 2) * scale, height: (device.height + BEZEL * 2) * scale, flexShrink: 0 }}>
          {/* zoom, not transform: zoom scales layout itself, so scroll, sticky and hit-testing stay true (Markon learnt this in Safari). */}
          <div ref={frameRef} style={{
            zoom: scale, width: device.width, height: device.height, position: 'relative', overflow: 'hidden',
            // contain: paint makes fixed-position layers (sheets, dialogs) fill the frame, like a real screen.
            contain: 'paint', cursor: 'none', backgroundColor: t.color.background,
            border: `${BEZEL}px solid #111`, borderRadius: device.cutout === 'none' ? 38 : 54, boxSizing: 'content-box',
            boxShadow: '0 30px 80px -20px rgba(0,0,0,0.35), 0 0 0 1px rgba(0,0,0,0.25)',
          } as CSSProperties}>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRadius: device.cutout === 'none' ? 28 : 44 }}>
              <SafeAreaFrameContext.Provider value={{ x: 0, y: 0, width: device.width, height: device.height }}>
                <SafeAreaInsetsContext.Provider value={{ top: os.status, bottom: os.bottom, left: 0, right: 0 }}>
                  {children}
                </SafeAreaInsetsContext.Provider>
              </SafeAreaFrameContext.Provider>
              {/* Sheets and dialogs portal here (the design system's Overlay), so they stay inside the phone. */}
              <div data-overlay-host="" style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 50 }} />
              <StatusBar device={device} />
              <BottomChrome device={device} />
            </div>
          </div>
          <TouchCursor frameRef={frameRef} wrapperRef={wrapperRef} scale={scale} />
        </div>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 500, color: t.color.textTertiary, padding: '4px 12px', borderRadius: 999,
                    background: t.color.surface, border: `1px solid ${t.color.border}` }}>
          {device.name} · {device.width} × {device.height} · {device.os === 'ios' ? 'iOS' : 'Android'}
        </p>
      </div>
    </div>
  )
}

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])
  return now
}

const Signal = () => (
  <svg width="18" height="12" viewBox="0 0 18 12" fill="currentColor" aria-hidden="true">
    <rect x="0" y="8" width="3" height="4" rx="0.8" /><rect x="5" y="5.5" width="3" height="6.5" rx="0.8" />
    <rect x="10" y="3" width="3" height="9" rx="0.8" /><rect x="15" y="0" width="3" height="12" rx="0.8" />
  </svg>
)

const Wifi = () => (
  <svg width="16" height="12" viewBox="0 0 16 12" fill="currentColor" aria-hidden="true">
    <path d="M8 11.5a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8Z" /><path d="M4.6 7.4a4.8 4.8 0 0 1 6.8 0l-1.1 1.1a3.2 3.2 0 0 0-4.6 0L4.6 7.4Z" />
    <path d="M2 4.8a8.5 8.5 0 0 1 12 0l-1.1 1.1a7 7 0 0 0-9.8 0L2 4.8Z" /><path d="M0 2.3a11.8 11.8 0 0 1 16 0l-1.1 1.1a10.3 10.3 0 0 0-13.8 0L0 2.3Z" />
  </svg>
)

const Battery = () => (
  <svg width="27" height="12" viewBox="0 0 27 12" fill="currentColor" aria-hidden="true">
    <rect x="0.5" y="0.5" width="22" height="11" rx="3" fill="none" stroke="currentColor" opacity="0.4" />
    <rect x="2" y="2" width="15.6" height="8" rx="1.5" /><path d="M24 4v4a2 2 0 0 0 0-4Z" opacity="0.4" />
  </svg>
)

/** Drawn over the top of the screen and transparent: the app's own top bar fills in behind it as content scrolls. */
function StatusBar({ device }: { device: Device }) {
  const t = useTheme()
  const now = useClock()
  const time = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: device.os === 'ios' }).replace(/\s?[AP]M/, '')
  const base: CSSProperties = { position: 'absolute', top: 0, left: 0, right: 0, height: chrome(device).status, zIndex: 60, display: 'flex',
                                justifyContent: 'space-between', color: t.color.textPrimary, pointerEvents: 'none', userSelect: 'none', fontVariantNumeric: 'tabular-nums' }
  if (device.os === 'ios') {
    return (
      <div style={{ ...base, alignItems: device.cutout === 'island' ? 'flex-end' : 'center', padding: device.cutout === 'island' ? '0 28px 8px' : '0 16px' }}>
        <span style={{ width: 64, fontSize: device.cutout === 'island' ? 15 : 13, fontWeight: 600 }}>{time}</span>
        {device.cutout === 'island' && <span style={{ position: 'absolute', top: 10, left: '50%', width: 108, height: 30, marginLeft: -54, borderRadius: 999, background: '#000' }} />}
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Signal /><Wifi /><Battery /></span>
      </div>
    )
  }
  const date = now.toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' })
  return (
    <div style={{ ...base, alignItems: 'center', padding: '0 20px' }}>
      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 13, fontWeight: 500 }}>
        {time}<span style={{ fontSize: 11, color: t.color.textTertiary }}>{date}</span>
      </span>
      <span style={{ position: 'absolute', top: 6, left: '50%', width: 16, height: 16, marginLeft: -8, borderRadius: 999, background: '#000' }} />
      <span style={{ display: 'flex', alignItems: 'center', gap: 6, transform: 'scale(0.85)' }}><Wifi /><Signal /><Battery /></span>
    </div>
  )
}

/** The iOS home indicator or Android gesture bar. Takes no space; the app clears it through the bottom inset. */
function BottomChrome({ device }: { device: Device }) {
  const t = useTheme()
  const h = chrome(device).bottom
  if (h === 0) return null
  return (
    <div aria-hidden="true" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: h, zIndex: 70, display: 'flex', alignItems: 'flex-end',
                                     justifyContent: 'center', paddingBottom: 8, boxSizing: 'border-box', pointerEvents: 'none' }}>
      <span style={{ width: device.os === 'ios' ? 134 : 108, height: device.os === 'ios' ? 5 : 4, borderRadius: 999, background: t.color.textPrimary,
                     opacity: device.os === 'ios' ? 1 : 0.8 }} />
    </div>
  )
}

/** The pointer inside the frame is a fingertip: a disc the size of a real tap, with a dot where the click lands. */
function TouchCursor({ frameRef, wrapperRef, scale }: { frameRef: RefObject<HTMLDivElement | null>; wrapperRef: RefObject<HTMLDivElement | null>; scale: number }) {
  const t = useTheme()
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const [down, setDown] = useState(false)
  useEffect(() => {
    const frame = frameRef.current
    const wrapper = wrapperRef.current
    if (!frame || !wrapper) return
    const move = (e: MouseEvent) => {
      const r = wrapper.getBoundingClientRect()
      setPos({ x: e.clientX - r.left, y: e.clientY - r.top })
    }
    const leave = () => { setPos(null); setDown(false) }
    const press = () => setDown(true)
    const release = () => setDown(false)
    frame.addEventListener('mousemove', move)
    frame.addEventListener('mouseleave', leave)
    frame.addEventListener('mousedown', press)
    window.addEventListener('mouseup', release)
    return () => {
      frame.removeEventListener('mousemove', move)
      frame.removeEventListener('mouseleave', leave)
      frame.removeEventListener('mousedown', press)
      window.removeEventListener('mouseup', release)
    }
  }, [frameRef, wrapperRef])
  if (!pos) return null
  const size = TOUCH * scale
  return (
    <span aria-hidden="true" style={{
      position: 'absolute', left: pos.x, top: pos.y, width: size, height: size, zIndex: 80, pointerEvents: 'none', borderRadius: 999,
      transform: `translate(-50%, -50%) scale(${down ? 0.9 : 1})`, transition: 'transform 75ms linear',
      border: `1px solid ${t.color.textPrimary}66`, background: `${t.color.textPrimary}${down ? '40' : '26'}`,
    }}>
      <span style={{ position: 'absolute', top: '50%', left: '50%', width: 4, height: 4, margin: -2, borderRadius: 999, background: t.color.textPrimary }} />
    </span>
  )
}
