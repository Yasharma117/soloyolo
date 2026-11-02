import { Avatar, Bar, Check, Collapse, Roll, Row, Stage, States, Stream, Text, Thread, Bubble, Window, type Act } from '../kit'
import './hero.css'

// soloyolo's hero: the promise you forgot, found in your own messages, kept in one click.
//
// Plan. Medium: a looping hero beside copy, 720 × 340, compact 358 × 400.
// Look: soloyolo's own tokens (warm greys, near-black ink, one orange accent), light, standard.
// Story (what the product does, under a cursor): an overdue promise sits at the top of Sam's card →
// click it and the message it came from comes forward → draft the intro → send → the promise ticks
// off and leaves the list. The completed card leaving is the reset's cause; the next one drops in.
// Layout: corner bleed from hero-demo, with static-card's satellite straddling the sidebar.
// Real strings: Sam Okafor, the promise, its due state, the source message, the draft, Send/Sent.

type S = {
  source: boolean // the evidence card
  composing: boolean
  words: number
  sent: boolean
  done: boolean
  present: boolean // the commitment card is in the "You owe" list
}

const initial: S = { source: false, composing: false, words: 0, sent: false, done: false, present: true }
const DRAFT = 'Sam, meet Priya. She built the design team at her last startup and is up for a chat.'
const WORDS = DRAFT.split(' ').length
const POSTER: S = { source: true, composing: true, words: WORDS, sent: true, done: true, present: true }
const REST = { wide: { x: 560, y: 300 }, compact: { x: 250, y: 300 } }

async function script(a: Act<S>) {
  await a.wait(700)

  // 1. The promise: where did it come from?
  await a.click({ at: 'promise', x: 0.62, y: 0.5 })
  await a.set({ source: true })
  await a.wait(1500)

  // 2. Draft the intro
  await a.click({ at: 'draft', x: 0.8, y: 0.6 })
  await a.set({ composing: true })
  await a.wait(250)
  for (let i = 1; i <= WORDS; i++) {
    a.put({ words: i })
    await a.wait(55)
  }
  await a.wait(500)

  // 3. Send: the button confirms on itself, then the promise ticks off
  await a.click({ at: 'send', x: 0.75, y: 0.6 })
  await a.set({ sent: true })
  await a.wait(220)
  await a.set({ done: true })
  a.move('rest')
  await a.wait(2200)

  // Reset with a cause: the kept promise leaves "You owe", taking its draft and source with it
  await a.set({ source: false })
  await a.wait(80)
  await a.set({ present: false })
  await a.wait(350)
  await a.snap({ ...initial, present: false })
  await a.set({ present: true })
  await a.wait(500)
}

export default function SoloyoloHero() {
  return (
    <Stage
      width={720}
      height={340}
      compact={{ below: 600, width: 358, height: 356 }}
      initial={initial}
      poster={POSTER}
      script={script}
      cursor={{ at: REST }}
      className="sy"
    >
      {(s, _rect, layout) => (
        <>
          <Window
            className="sy-window"
            title="Sam Okafor"
            sidebarWidth={layout === 'wide' ? 196 : undefined}
            sidebar={layout === 'wide' ? <People /> : undefined}
          >
            <div className="sy-main">
              <div className="sy-meta">
                <Bar w={46} h={6} tone={2} />
                <Bar w={70} h={6} tone={2} />
              </div>

              <div className="sy-label">You owe</div>
              <Collapse open={s.present} reveal="drop">
                <div className="sy-promise" data-target="promise" data-done={s.done || undefined} data-open={s.source || undefined}>
                  <div className="sy-promise-line">
                    <Check on={s.done} size={16} className="sy-check" />
                    <span className="sy-what">Intro Sam to Priya</span>
                    <span className="sy-due" data-done={s.done || undefined}>
                      <Roll align="end">{s.done ? 'Done' : '9d overdue'}</Roll>
                    </span>
                  </div>
                  <Collapse open={!s.composing}>
                    <div className="sy-actions">
                      <div className="sy-btn" data-target="draft">Draft intro</div>
                    </div>
                  </Collapse>
                  <Collapse open={s.composing}>
                    <div className="sy-compose">
                      <div className="sy-field">
                        <Stream text={DRAFT} count={s.words} />
                      </div>
                      <div className="sy-actions">
                        <div className="sy-btn sy-btn--send" data-target="send" data-sent={s.sent || undefined}>
                          <States value={s.sent ? 'sent' : 'send'} states={{ send: 'Send', sent: 'Sent' }} />
                        </div>
                      </div>
                    </div>
                  </Collapse>
                </div>
              </Collapse>

              <div className="sy-label">Owes you</div>
              <div className="sy-filler">
                <Bar w={14} h={14} r={7} tone={2} />
                <Bar w={150} h={6} tone={3} />
                <Bar w={40} h={6} tone={2} style={{ marginLeft: 'auto' }} />
              </div>
            </div>
          </Window>

          {/* The evidence: the message the promise was found in, in Messages' own colors */}
          <div className="sy-source" data-show={s.source || undefined}>
            <div className="sy-source-head">
              <Avatar name="Sam Okafor" size={18} />
              <Text className="sy-source-when">Messages · Oct 20</Text>
            </div>
            <Thread app="imessage" className="sy-thread">
              <Bubble from="me">I'll intro you to Priya by Friday</Bubble>
            </Thread>
          </div>

          <span data-target="rest" style={{ position: 'absolute', left: REST[layout].x, top: REST[layout].y }} />
        </>
      )}
    </Stage>
  )
}

function People() {
  return (
    <div className="sy-people">
      <Row selected pad={8} className="sy-row" lead={<Avatar name="Sam Okafor" size={20} />} title={<Text className="sy-name">Sam Okafor</Text>} />
      <Row pad={8} className="sy-row" lead={<Avatar name="Maya Lin" size={20} />} title={<Text className="sy-name">Maya Lin</Text>} />
      <Row pad={8} className="sy-row" lead={<Avatar name="Dev Shah" size={20} />} title={<Text className="sy-name">Dev Shah</Text>} />
      {[58, 44, 66].map((w, i) => (
        <Row key={i} pad={8} className="sy-row" lead={<Bar w={20} h={20} r={10} tone={2} />} title={<Bar w={w} h={6} tone={3} />} />
      ))}
    </div>
  )
}
