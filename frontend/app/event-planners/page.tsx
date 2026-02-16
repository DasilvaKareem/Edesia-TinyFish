import type { Metadata } from 'next'
import CallCTA from './CallCTA'

export const metadata: Metadata = {
  title: 'Edesia | Stop Chasing Food Vendors',
  description:
    'One phone call. We contact every caterer, confirm menus, lock in pricing, and book your food vendors before your deadline.',
}

const PHONE_NUMBER = process.env.NEXT_PUBLIC_PHONE_NUMBER || '+1XXXXXXXXXX'

function formatPhone(e164: string): string {
  const digits = e164.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('1')) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`
  }
  return e164
}

export default function EventPlannersLanding() {
  return (
    <div className="bg-white font-sans">
      {/* ═══ HERO ═══ */}
      <section className="w-full px-6 sm:px-10 lg:px-20 pt-12 pb-20 sm:pt-20 sm:pb-28 text-center">
        <img
          src="/logo-red.png"
          alt="Edesia"
          className="h-7 sm:h-8 w-auto mb-14 sm:mb-20 mx-auto"
        />

        <h1 className="text-[2rem] sm:text-[2.75rem] lg:text-[3.25rem] font-extrabold leading-[1.1] tracking-tight text-[#111]">
          Stop chasing food vendors.
          <br />
          <span className="text-[#b91c5a]">We book them for you.</span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-[#555] leading-relaxed">
          One phone call. We contact every caterer, confirm menus, lock in
          pricing, and secure your food vendors before your deadline.
        </p>

        <CallCTA className="mt-10" />
      </section>

      {/* ═══ PROBLEM ═══ */}
      <section className="bg-[#faf9f7] py-20 sm:py-28">
        <div className="w-full px-6 sm:px-10 lg:px-20 text-center">
          <h2 className="text-[1.5rem] sm:text-[2rem] font-extrabold leading-[1.15] tracking-tight text-[#111]">
            You have 30 vendors to contact,
            <br />
            12 haven't replied, and your event is in 3 weeks.
          </h2>

          <p className="mt-5 text-base sm:text-lg text-[#666] leading-relaxed">
            You're spending hours calling caterers, comparing menus, following
            up on quotes that never come back, and praying someone confirms
            before the deadline. Meanwhile, everything else on your planning
            list is piling up.
          </p>

          <p className="mt-6 text-base sm:text-lg text-[#111] font-semibold">
            Food vendors are the hardest part of event planning. That's the
            part we take off your plate.
          </p>
        </div>
      </section>

      {/* ═══ HOW IT WORKS ═══ */}
      <section className="py-20 sm:py-28">
        <div className="w-full px-6 sm:px-10 lg:px-20 text-center">
          <h2 className="text-[1.5rem] sm:text-[2rem] font-extrabold leading-[1.15] tracking-tight text-[#111]">
            One call replaces 50 emails, 20 voicemails,
            <br />
            and 3 weeks of follow-ups.
          </h2>

          <div className="mt-12 space-y-10">
            <div>
              <p className="text-sm font-bold text-[#b91c5a] uppercase tracking-wider">Step 1</p>
              <h3 className="mt-2 text-xl font-bold text-[#111]">
                Tell us what you need.
              </h3>
              <p className="mt-2 text-base text-[#666] leading-relaxed">
                Event date, headcount, cuisine preferences, budget, dietary
                restrictions. One conversation. That's it.
              </p>
            </div>

            <div>
              <p className="text-sm font-bold text-[#b91c5a] uppercase tracking-wider">Step 2</p>
              <h3 className="mt-2 text-xl font-bold text-[#111]">
                We contact every vendor for you.
              </h3>
              <p className="mt-2 text-base text-[#666] leading-relaxed">
                We call caterers, request menus, confirm availability, compare
                pricing, and chase the ones who don't reply. You don't send a
                single email.
              </p>
            </div>

            <div>
              <p className="text-sm font-bold text-[#b91c5a] uppercase tracking-wider">Step 3</p>
              <h3 className="mt-2 text-xl font-bold text-[#111]">
                Your food vendors are booked before the deadline.
              </h3>
              <p className="mt-2 text-base text-[#666] leading-relaxed">
                Menus confirmed. Pricing locked. Vendors secured. You move on
                to everything else on your list.
              </p>
            </div>
          </div>

          <CallCTA className="mt-14" />
        </div>
      </section>

      {/* ═══ WHO IT'S FOR ═══ */}
      <section className="bg-[#faf9f7] py-20 sm:py-28">
        <div className="w-full px-6 sm:px-10 lg:px-20 text-center">
          <h2 className="text-[1.5rem] sm:text-[2rem] font-extrabold leading-[1.15] tracking-tight text-[#111]">
            Built for people who are tired of
            <br />
            chasing caterers.
          </h2>

          <ul className="mt-10 space-y-6 inline-block text-left">
            {[
              {
                who: 'Wedding planners',
                pain: 'who need 4 vendors confirmed and the couple keeps changing the headcount.',
              },
              {
                who: 'Office managers',
                pain: 'who got asked to "handle lunch for 60 people by Friday" on top of their actual job.',
              },
              {
                who: 'Event coordinators',
                pain: 'running 3 events this month with 3 different caterers who all ghost on quotes.',
              },
            ].map(({ who, pain }) => (
              <li key={who} className="flex items-start gap-4">
                <span className="flex-shrink-0 mt-1 flex items-center justify-center w-5 h-5 rounded-full bg-[#b91c5a]">
                  <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2.5 6l2.5 2.5 4.5-5" />
                  </svg>
                </span>
                <p className="text-base sm:text-lg text-[#333] leading-relaxed">
                  <span className="font-bold">{who}</span> {pain}
                </p>
              </li>
            ))}
          </ul>

          <p className="mt-10 text-base sm:text-lg text-[#111] font-semibold">
            If you've ever lost sleep over whether a caterer will confirm,
            this is for you.
          </p>
        </div>
      </section>

      {/* ═══ WHAT YOU GET ═══ */}
      <section className="py-20 sm:py-28">
        <div className="w-full px-6 sm:px-10 lg:px-20 text-center">
          <h2 className="text-[1.5rem] sm:text-[2rem] font-extrabold leading-[1.15] tracking-tight text-[#111]">
            You stop chasing vendors.
            <br />
            Here's what happens instead.
          </h2>

          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { stat: 'Zero', desc: 'vendor emails you need to send.' },
              { stat: 'Zero', desc: 'follow-up calls you need to make.' },
              { stat: 'Every', desc: 'caterer contacted and compared for you.' },
              { stat: 'One', desc: 'phone call to get it all started.' },
            ].map(({ stat, desc }) => (
              <div key={desc}>
                <p className="text-2xl sm:text-3xl font-extrabold text-[#b91c5a]">{stat}</p>
                <p className="mt-1 text-base text-[#555]">{desc}</p>
              </div>
            ))}
          </div>

          <CallCTA className="mt-14" />
        </div>
      </section>

      {/* ═══ FINAL CTA ═══ */}
      <section className="bg-[#111] py-20 sm:py-28">
        <div className="w-full px-6 sm:px-10 lg:px-20 text-center">
          <h2 className="text-[1.5rem] sm:text-[2rem] font-extrabold leading-[1.15] tracking-tight text-white">
            Stop chasing food vendors.
            <br />
            Call us. We'll book them.
          </h2>

          <p className="mt-5 text-base sm:text-lg text-[#999] leading-relaxed">
            One conversation is all it takes. Tell us what you need and we
            handle the rest.
          </p>

          <div className="mt-10 flex justify-center">
            <a
              href={`tel:${PHONE_NUMBER}`}
              className="group inline-flex items-center gap-3 bg-[#b91c5a] text-white rounded-lg px-10 py-5 text-lg font-semibold font-sans transition-all hover:bg-[#d42a6f] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b91c5a] focus-visible:ring-offset-2 focus-visible:ring-offset-[#111]"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 transition-transform group-hover:scale-110" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
              </svg>
              {formatPhone(PHONE_NUMBER)}
            </a>
          </div>

          <p className="mt-4 text-sm text-[#666]">
            Available 24/7. No hold times.
          </p>
        </div>
      </section>
    </div>
  )
}
