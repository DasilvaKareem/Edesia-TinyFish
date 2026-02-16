import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Concierge by Edesia | We Book Wedding Vendors For You',
  description:
    'We find, contact, and secure wedding vendors so you do not spend days chasing replies.',
}

const PHONE_NUMBER = process.env.NEXT_PUBLIC_PHONE_NUMBER || '+1XXXXXXXXXX'

function formatPhone(e164: string): string {
  const digits = e164.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('1')) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`
  }
  return e164
}

export default function WeddingPlannersLanding() {
  return (
    <div className="min-h-screen bg-[#faf9f7]">
      {/* Hero Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 min-h-screen">
        {/* Left — Content */}
        <div className="flex flex-col justify-center px-8 sm:px-14 lg:px-20 xl:px-28 py-16 lg:py-0 order-2 lg:order-1">
          {/* Category label */}
          <p className="text-[11px] font-sans font-semibold tracking-[0.25em] uppercase text-[#1a1a1a] mb-6">
            Concierge / Wedding Vendors
          </p>

          {/* Headline */}
          <h1 className="font-serif text-[2.75rem] sm:text-[3.5rem] lg:text-[4rem] xl:text-[4.5rem] font-normal leading-[1.05] text-[#1a1a1a] tracking-[-0.01em]">
            Concierge by{' '}
            <span className="block">Edesia</span>
          </h1>

          {/* Location / subtitle — italic serif */}
          <p className="font-serif italic text-xl sm:text-2xl text-[#1a1a1a] mt-4 font-medium">
            Your Virtual Wedding Assistant
          </p>

          {/* Description */}
          <p className="font-sans text-[15px] text-[#888] mt-4 max-w-sm leading-relaxed">
            We find, contact, and secure wedding vendors so you don't spend days chasing replies.
          </p>

          {/* Pill tags */}
          <div className="flex flex-wrap gap-3 mt-8">
            {['24/7 availability', 'Vendor sourcing', 'Instant booking'].map(
              (tag) => (
                <span
                  key={tag}
                  className="font-serif italic text-[15px] text-[#555] border border-[#e0ddd8] rounded-full px-5 py-2 bg-[#f5f4f1]"
                >
                  {tag}
                </span>
              )
            )}
          </div>

          {/* CTA — Phone */}
          <div className="mt-10">
            <a
              href={`tel:${PHONE_NUMBER}`}
              className="group inline-flex items-center gap-3 bg-[#1a1a1a] text-white rounded-full pl-7 pr-8 py-4 transition-all hover:bg-[#333] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1a1a1a] focus-visible:ring-offset-2 focus-visible:ring-offset-[#faf9f7]"
            >
              {/* Phone icon */}
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 transition-transform group-hover:scale-110"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>
              <span className="font-serif text-lg tracking-wide">
                {formatPhone(PHONE_NUMBER)}
              </span>
            </a>
          </div>

          <p className="font-sans text-[13px] text-[#aaa] mt-4 tracking-wide">
            Call your virtual assistant. No hold times, ever.
          </p>
        </div>

        {/* Right — Hero Image */}
        <div className="relative order-1 lg:order-2 min-h-[40vh] lg:min-h-0">
          <img
            src="/images/wedding-hero.png"
            alt="Elegant wedding setting"
            className="absolute inset-0 h-full w-full object-cover"
          />
          {/* Soft left-edge fade into content bg */}
          <div className="hidden lg:block absolute inset-y-0 left-0 w-40 bg-gradient-to-r from-[#faf9f7] to-transparent" />
          {/* Bottom fade on mobile */}
          <div className="lg:hidden absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-[#faf9f7] to-transparent" />
        </div>
      </div>
    </div>
  )
}
