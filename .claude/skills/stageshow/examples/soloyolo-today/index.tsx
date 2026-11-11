import { Check, MessageCircle } from 'lucide-react'
import { Avatar, Bar, Collapse, Phone, Roll, Stage, type Act } from '../../kit'
import './today.css'

// soloyolo's Today screen on an iPhone. Beats: the finger presses the first
// card (a promise, chased this morning), swipes it left with Done opening
// behind it in green, lets go; the card carries on at the finger's speed,
// the gap closes, the next card moves up, and the count rolls 3 to 2.
// Plays once; Replay is the reset. Built from examples/swipe (the throw at
// the finger's own speed, the action riding the card's trailing edge).
//
// Real strings: Today, the date and count, the swiped card (who, what, the
// message it came from, why it's here), the card that moves up (who, what,
// one reason), Done. The third card is placeholder lines.

type S = { dx: number; throw: { ms: number; ease: string } | null; gone: boolean }

const initial: S = { dx: 0, throw: null, gone: false }

async function script(a: Act<S>) {
  await a.wait(1100)

  a.mark('swipe')
  const card = a.rect('card')
  const y = card.y + card.height * 0.42
  await a.move({ x: card.x + card.width * 0.78, y })
  await a.wait(250)
  const from = card.x + card.width * 0.78
  const samples: { x: number; t: number }[] = []
  await a.drag(
    { x: card.x + card.width * 0.2, y },
    (at) => {
      samples.push({ x: at.x, t: performance.now() })
      a.put({ dx: at.x - from })
    },
    { duration: 320, path: (t, a0, b0) => ({ x: a0.x + (b0.x - a0.x) * t, y: a0.y }) },
  )

  a.mark('throw')
  const last = samples.slice(-4)
  const v = last.length > 1 ? Math.abs(last[last.length - 1]!.x - last[0]!.x) / Math.max(1, last[last.length - 1]!.t - last[0]!.t) : 1
  const dx = samples.length ? samples[samples.length - 1]!.x - from : 0
  const left = card.width + 40 + dx
  const ms = 300
  const x1 = 0.25
  const y1 = Math.min(0.95, (x1 * v * ms) / left)
  a.put({ throw: { ms, ease: `cubic-bezier(${x1}, ${y1.toFixed(3)}, 0.35, 1)` }, dx: -(card.width + 40) })
  await a.wait(ms)

  a.mark('close')
  a.put({ gone: true })
  await a.wait(2200)
  a.mark('done')
}

export default function SoloyoloToday() {
  return (
    <Stage<S>
      width={456}
      height={560}
      compact={{ below: 456, width: 358, height: 534 }}
      initial={initial}
      poster={{ dx: 0, throw: null, gone: true }}
      script={script}
      play="once"
      cursor={{ at: { x: 340, y: 500 }, style: 'touch' }}
      className="sy"
    >
      {(s, rect, layout) => {
        const box = rect('card')
        const k = box.width ? box.width / 362 : 1
        const shift = s.dx / k
        const open = Math.max(0, -shift)
        return (
          <Phone width={layout === 'compact' ? 372 : 384} className={layout === 'compact' ? 'sy-phone sy-phone--compact' : 'sy-phone'}>
            <div className="sy-app">
              <div className="sy-head">
                <div className="sy-title">Today</div>
                <div className="sy-sub">
                  Monday, 9 November · <Roll>{s.gone ? '2 things' : '3 things'}</Roll>
                </div>
              </div>
              <div className="sy-list">
                <Collapse open={!s.gone} solid>
                  <div className="sy-cell" data-target="card">
                    {(s.dx !== 0 || s.throw) && (
                      // Faded as the gap closes, so the closing edge never slices a solid green block
                      <div className="sy-action" style={{ opacity: s.gone ? 0 : 1, transition: s.gone ? 'opacity 160ms ease-out' : 'none' }} />
                    )}
                    <div
                      className="sy-card"
                      style={{ transform: `translateX(${shift}px)`, transition: s.throw ? `transform ${s.throw.ms}ms ${s.throw.ease}` : 'none' }}
                    >
                      <div className="sy-who">
                        <Avatar name="Rohan Mehta" size={28} />
                        <span className="sy-name">Rohan Mehta</span>
                        <span className="sy-app-tag"><MessageCircle size={12} strokeWidth={2.5} />WhatsApp</span>
                        <span className="sy-when">{layout === 'compact' ? <Bar w={16} h={9} r={4.5} tone={2} /> : '2d'}</span>
                      </div>
                      <div className="sy-what">Send Rohan the rent agreement scan</div>
                      <div className="sy-quote">“Agreement ka scan bhej dena kal tak”</div>
                      <div className="sy-chips">
                        <span className="sy-chip" data-hot>asked again 3h ago</span>
                        <span className="sy-chip" data-hot>due tomorrow</span>
                      </div>
                      {/* Done rides the card's trailing edge, as Mail's Archive does */}
                      <span className="sy-action__mark" style={{ opacity: s.gone ? 0 : Math.min(1, open / 70) }}>
                        <Check size={22} strokeWidth={2.5} />
                        Done
                      </span>
                    </div>
                  </div>
                </Collapse>
                <div className="sy-cell">
                  <div className="sy-card">
                    <div className="sy-who">
                      <Avatar name="Ma" size={28} />
                      <span className="sy-name">Ma</span>
                      <span className="sy-app-tag"><MessageCircle size={12} strokeWidth={2.5} />WhatsApp</span>
                      <span className="sy-when">{layout === 'compact' ? <Bar w={16} h={9} r={4.5} tone={2} /> : '1d'}</span>
                    </div>
                    <div className="sy-what">Book Ma’s train ticket for the 21st</div>
                    <div className="sy-chips">
                      <span className="sy-chip">said yesterday</span>
                    </div>
                  </div>
                </div>
                <div className="sy-cell">
                  <div className="sy-card">
                    <div className="sy-who">
                      <Avatar size={28} />
                      <Bar w={96} h={11} r={5.5} tone={4} />
                      <span className="sy-when"><Bar w={18} h={9} r={4.5} tone={2} /></span>
                    </div>
                    <div className="sy-fill"><Bar w={240} h={11} r={5.5} tone={3} /></div>
                    <div className="sy-fill"><Bar w={170} h={9} r={4.5} tone={2} /></div>
                  </div>
                </div>
              </div>
              <div className="sy-section">Quiet · assumed done</div>
              <div className="sy-quiet">
                {QUIET.map((w, i) => (
                  <div className="sy-qrow" key={i}>
                    <Avatar size={24} />
                    <span className="sy-qtext"><Bar w={w[0]} h={10} r={5} tone={3} /><Bar w={w[1]} h={8} r={4} tone={2} /></span>
                  </div>
                ))}
              </div>
            </div>
          </Phone>
        )
      }}
    </Stage>
  )
}

// The quiet list: items past their window, assumed done. Filler at a real
// row's line heights, so the screen stays full when a card leaves.
const QUIET: [number, number][] = [
  [150, 210],
  [128, 180],
  [170, 150],
  [110, 196],
]
