import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import SoloyoloHero from './hero/SoloyoloHero'
import './app.css'

function App() {
  return (
    <main className="page">
      <section className="hero">
        <div className="copy">
          <p className="eyebrow">soloyolo</p>
          <h1>Keep the promises you make in passing.</h1>
          <p className="lede">
            soloyolo reads your iMessage and WhatsApp threads on your Mac, finds what you said you'd do, and lets you
            follow through in one click. Your messages never leave your machine.
          </p>
        </div>
        <div className="demo">
          <SoloyoloHero />
        </div>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
