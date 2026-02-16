'use client'

import { useState } from 'react'

const PHONE_NUMBER = process.env.NEXT_PUBLIC_PHONE_NUMBER || '+1XXXXXXXXXX'
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://your-modal-app.modal.run'

function formatPhone(e164: string): string {
  const digits = e164.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('1')) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`
  }
  return e164
}

export default function CallCTA({ className = '' }: { className?: string }) {
  const [showEmail, setShowEmail] = useState(false)
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!email) return
    setSubmitting(true)
    try {
      await fetch(`${API_URL}/leads/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, source: 'event-planners' }),
      })
    } catch {
      // non-blocking — still send them to the call
    }
    window.location.href = `tel:${PHONE_NUMBER}`
  }

  if (showEmail) {
    return (
      <div className={className}>
        <div className="inline-flex flex-col items-center gap-4 bg-[#faf9f7] rounded-xl px-8 py-8 max-w-md mx-auto">
          <p className="text-base font-semibold text-[#111]">
            Enter your email so we can follow up
          </p>
          <input
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            className="w-full px-4 py-3 rounded-lg border border-[#ddd] text-base text-[#111] placeholder-[#999] focus:outline-none focus:ring-2 focus:ring-[#b91c5a] focus:border-transparent"
            autoFocus
          />
          <button
            onClick={handleSubmit}
            disabled={!email || submitting}
            className="w-full group inline-flex items-center justify-center gap-3 bg-[#b91c5a] text-white rounded-lg px-8 py-4 text-base font-semibold transition-all hover:bg-[#a01850] active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
            </svg>
            {submitting ? 'Connecting...' : 'Call Now'}
          </button>
          <a
            href={`tel:${PHONE_NUMBER}`}
            className="text-sm text-[#999] hover:text-[#666] underline underline-offset-2 transition-colors"
          >
            Skip, call directly
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className={className}>
      <button
        onClick={() => setShowEmail(true)}
        className="group inline-flex items-center gap-3 bg-[#b91c5a] text-white rounded-lg px-8 py-4 text-base font-semibold font-sans transition-all hover:bg-[#a01850] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b91c5a] focus-visible:ring-offset-2"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 transition-transform group-hover:scale-110" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
        </svg>
        Stop Chasing Vendors
      </button>
      <p className="mt-3 text-sm text-[#999] font-sans">
        {formatPhone(PHONE_NUMBER)} . Available 24/7
      </p>
    </div>
  )
}
