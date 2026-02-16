'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { completeOnboarding, createUserProfile, getUserProfile } from '@/lib/user-store'
import { Building2, Phone, MapPin, Users, AlertTriangle, User, ArrowRight, ArrowLeft, Utensils, Home } from 'lucide-react'

const COMPANY_SIZES = [
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-500', label: '201-500 employees' },
  { value: '500+', label: '500+ employees' },
]

const US_STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
]

const DIETARY_OPTIONS = [
  'Vegetarian', 'Vegan', 'Gluten-Free', 'Halal', 'Kosher',
  'Pescatarian', 'Keto', 'Paleo', 'Dairy-Free', 'Low-Sodium'
]

const ALLERGY_OPTIONS = [
  'Nuts', 'Peanuts', 'Shellfish', 'Dairy', 'Eggs',
  'Soy', 'Wheat', 'Fish', 'Sesame'
]

const CUISINE_OPTIONS = [
  'Italian', 'Mexican', 'Chinese', 'Japanese', 'Indian',
  'Thai', 'Mediterranean', 'American', 'Korean', 'Vietnamese'
]

type AccountType = 'individual' | 'team'

export default function OnboardingPage() {
  // Step tracking: 0=account type, 1=info, 2=address, 3=food prefs
  const [step, setStep] = useState(0)
  const [accountType, setAccountType] = useState<AccountType | null>(null)

  // Info fields
  const [displayName, setDisplayName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [companySize, setCompanySize] = useState('')

  // Address fields
  const [workAddress, setWorkAddress] = useState('')
  const [homeAddress, setHomeAddress] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')

  // Food preferences
  const [dietaryRestrictions, setDietaryRestrictions] = useState<string[]>([])
  const [allergies, setAllergies] = useState<string[]>([])
  const [favoriteCuisines, setFavoriteCuisines] = useState<string[]>([])
  const [spicePreference, setSpicePreference] = useState('')
  const [budgetPerPerson, setBudgetPerPerson] = useState('')

  // UI state
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [checkingProfile, setCheckingProfile] = useState(true)
  const [showSkipWarning, setShowSkipWarning] = useState(false)
  const [skipping, setSkipping] = useState(false)

  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

  // Check if user already completed onboarding
  useEffect(() => {
    async function checkProfile() {
      if (!user) {
        setCheckingProfile(false)
        return
      }

      try {
        const profile = await getUserProfile(user.uid)
        if (profile?.onboardingComplete) {
          router.push('/chat')
          return
        }
        if (!profile) {
          await createUserProfile(user.uid, user.email || '')
        }
      } catch (e) {
        console.error('Error checking profile:', e)
      }
      setCheckingProfile(false)
    }

    if (!authLoading) {
      checkProfile()
    }
  }, [user, authLoading, router])

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/auth/login')
    }
  }, [user, authLoading, router])

  const formatPhoneNumber = (value: string) => {
    const digits = value.replace(/\D/g, '')
    if (digits.length <= 3) return digits
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`
  }

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhoneNumber(formatPhoneNumber(e.target.value))
  }

  const toggleArrayItem = (arr: string[], setArr: (v: string[]) => void, item: string) => {
    if (arr.includes(item)) {
      setArr(arr.filter(i => i !== item))
    } else {
      setArr([...arr, item])
    }
  }

  const handleSelectAccountType = (type: AccountType) => {
    setAccountType(type)
    setStep(1)
  }

  const validateStep = (): boolean => {
    setError('')
    if (step === 1) {
      if (accountType === 'team') {
        if (!companyName.trim()) {
          setError('Please enter your company name')
          return false
        }
        if (!companySize) {
          setError('Please select your company size')
          return false
        }
      } else {
        if (!displayName.trim()) {
          setError('Please enter your name')
          return false
        }
      }
      const phoneDigits = phoneNumber.replace(/\D/g, '')
      if (phoneNumber && phoneDigits.length !== 10) {
        setError('Please enter a valid 10-digit phone number')
        return false
      }
    }
    if (step === 2) {
      if (!city.trim() || !state) {
        setError('Please enter your city and state')
        return false
      }
    }
    return true
  }

  const handleNext = () => {
    if (validateStep()) {
      setStep(step + 1)
    }
  }

  const handleBack = () => {
    setError('')
    if (step === 1) {
      setStep(0)
    } else {
      setStep(step - 1)
    }
  }

  const handleSubmit = async () => {
    if (!user) {
      setError('Not authenticated')
      return
    }

    setLoading(true)
    setError('')

    try {
      await completeOnboarding(user.uid, {
        accountType: accountType || undefined,
        displayName: accountType === 'individual' ? displayName.trim() || undefined : undefined,
        phoneNumber: phoneNumber || undefined,
        companyName: accountType === 'team' ? companyName.trim() || undefined : undefined,
        companySize: accountType === 'team' ? companySize || undefined : undefined,
        city: city.trim() || undefined,
        state: state || undefined,
        workAddress: workAddress ? { rawAddress: workAddress, label: 'work' } : undefined,
        homeAddress: homeAddress ? { rawAddress: homeAddress, label: 'home' } : undefined,
        dietaryRestrictions: dietaryRestrictions.length > 0 ? dietaryRestrictions : undefined,
        allergies: allergies.length > 0 ? allergies : undefined,
        favoriteCuisines: favoriteCuisines.length > 0 ? favoriteCuisines : undefined,
        spicePreference: spicePreference || undefined,
        budgetPerPerson: budgetPerPerson ? parseFloat(budgetPerPerson) : undefined,
      })
      router.push('/chat')
    } catch (err: any) {
      setError(err.message || 'Failed to save profile')
      setLoading(false)
    }
  }

  const handleSkip = async () => {
    if (!user) return
    setSkipping(true)
    try {
      await completeOnboarding(user.uid, {})
      router.push('/chat')
    } catch (err: any) {
      setError(err.message || 'Failed to skip onboarding')
      setSkipping(false)
    }
  }

  if (authLoading || checkingProfile) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  const totalSteps = 4
  const progress = step / (totalSteps - 1)

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-6 rounded-2xl bg-background border border-border p-5 md:p-8 shadow-xl">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-primary">Welcome to Edesia</h1>
          {step === 0 && (
            <p className="mt-2 text-muted-foreground">How will you be using Edesia?</p>
          )}
          {step === 1 && accountType === 'team' && (
            <p className="mt-2 text-muted-foreground">Tell us about your team</p>
          )}
          {step === 1 && accountType === 'individual' && (
            <p className="mt-2 text-muted-foreground">Tell us about yourself</p>
          )}
          {step === 2 && (
            <p className="mt-2 text-muted-foreground">Where should we deliver?</p>
          )}
          {step === 3 && (
            <p className="mt-2 text-muted-foreground">Any food preferences?</p>
          )}
        </div>

        {/* Progress bar */}
        {step > 0 && (
          <div className="w-full bg-secondary rounded-full h-1.5">
            <div
              className="bg-primary h-1.5 rounded-full transition-all duration-300"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-500/10 p-4 text-sm text-red-600 dark:text-red-400">
            {error}
          </div>
        )}

        {/* Step 0: Account Type */}
        {step === 0 && (
          <div className="space-y-3">
            <button
              onClick={() => handleSelectAccountType('team')}
              className="w-full flex items-center gap-4 rounded-xl border border-border p-5 hover:border-primary hover:bg-primary/5 transition-all text-left group"
            >
              <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                <Building2 className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="font-semibold text-foreground">Team / Company</p>
                <p className="text-sm text-muted-foreground">Order food for your office, manage team lunches and catering</p>
              </div>
            </button>
            <button
              onClick={() => handleSelectAccountType('individual')}
              className="w-full flex items-center gap-4 rounded-xl border border-border p-5 hover:border-primary hover:bg-primary/5 transition-all text-left group"
            >
              <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                <User className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="font-semibold text-foreground">Individual</p>
                <p className="text-sm text-muted-foreground">Order food for yourself, track nutrition, find restaurants</p>
              </div>
            </button>
          </div>
        )}

        {/* Step 1: Info (Team) */}
        {step === 1 && accountType === 'team' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="company" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  Company Name
                </div>
              </label>
              <input
                id="company"
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="Acme Inc."
                autoFocus
              />
            </div>

            <div>
              <label htmlFor="size" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  Team Size
                </div>
              </label>
              <select
                id="size"
                value={companySize}
                onChange={(e) => setCompanySize(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">Select size...</option>
                {COMPANY_SIZES.map((size) => (
                  <option key={size.value} value={size.value}>
                    {size.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="phone" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <Phone className="h-4 w-4 text-muted-foreground" />
                  Phone Number
                  <span className="text-muted-foreground text-xs font-normal">(optional)</span>
                </div>
              </label>
              <input
                id="phone"
                type="tel"
                value={phoneNumber}
                onChange={handlePhoneChange}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="(555) 123-4567"
              />
            </div>
          </div>
        )}

        {/* Step 1: Info (Individual) */}
        {step === 1 && accountType === 'individual' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-muted-foreground" />
                  Your Name
                </div>
              </label>
              <input
                id="name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="Jane Doe"
                autoFocus
              />
            </div>

            <div>
              <label htmlFor="phone" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <Phone className="h-4 w-4 text-muted-foreground" />
                  Phone Number
                  <span className="text-muted-foreground text-xs font-normal">(optional)</span>
                </div>
              </label>
              <input
                id="phone"
                type="tel"
                value={phoneNumber}
                onChange={handlePhoneChange}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="(555) 123-4567"
              />
            </div>
          </div>
        )}

        {/* Step 2: Address */}
        {step === 2 && (
          <div className="space-y-4">
            <div>
              <label htmlFor="city" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                  City & State
                </div>
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="city"
                  type="text"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  className="block flex-1 rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="Memphis"
                  autoFocus
                />
                <select
                  id="state"
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  className="block w-28 rounded-lg border border-border bg-background px-3 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">State</option>
                  {US_STATES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="workAddress" className="block text-sm font-medium">
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  {accountType === 'team' ? 'Office Address' : 'Work Address'}
                  <span className="text-muted-foreground text-xs font-normal">(optional)</span>
                </div>
              </label>
              <input
                id="workAddress"
                type="text"
                value={workAddress}
                onChange={(e) => setWorkAddress(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                placeholder="123 Main St, Suite 200"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Default delivery address for orders
              </p>
            </div>

            {accountType === 'individual' && (
              <div>
                <label htmlFor="homeAddress" className="block text-sm font-medium">
                  <div className="flex items-center gap-2">
                    <Home className="h-4 w-4 text-muted-foreground" />
                    Home Address
                    <span className="text-muted-foreground text-xs font-normal">(optional)</span>
                  </div>
                </label>
                <input
                  id="homeAddress"
                  type="text"
                  value={homeAddress}
                  onChange={(e) => setHomeAddress(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="456 Oak Ave"
                />
              </div>
            )}
          </div>
        )}

        {/* Step 3: Food Preferences */}
        {step === 3 && (
          <div className="space-y-5 max-h-[50vh] overflow-y-auto pr-1">
            {/* Dietary Restrictions */}
            <div>
              <label className="block text-sm font-medium mb-2">Dietary Restrictions</label>
              <div className="flex flex-wrap gap-2">
                {DIETARY_OPTIONS.map((diet) => (
                  <button
                    key={diet}
                    type="button"
                    onClick={() => toggleArrayItem(dietaryRestrictions, setDietaryRestrictions, diet)}
                    className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                      dietaryRestrictions.includes(diet)
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {diet}
                  </button>
                ))}
              </div>
            </div>

            {/* Allergies */}
            <div>
              <label className="block text-sm font-medium mb-2">Food Allergies</label>
              <div className="flex flex-wrap gap-2">
                {ALLERGY_OPTIONS.map((allergy) => (
                  <button
                    key={allergy}
                    type="button"
                    onClick={() => toggleArrayItem(allergies, setAllergies, allergy)}
                    className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                      allergies.includes(allergy)
                        ? 'bg-red-500 text-white'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {allergy}
                  </button>
                ))}
              </div>
            </div>

            {/* Favorite Cuisines */}
            <div>
              <label className="block text-sm font-medium mb-2">Favorite Cuisines</label>
              <div className="flex flex-wrap gap-2">
                {CUISINE_OPTIONS.map((cuisine) => (
                  <button
                    key={cuisine}
                    type="button"
                    onClick={() => toggleArrayItem(favoriteCuisines, setFavoriteCuisines, cuisine)}
                    className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                      favoriteCuisines.includes(cuisine)
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {cuisine}
                  </button>
                ))}
              </div>
            </div>

            {/* Spice Preference */}
            <div>
              <label className="block text-sm font-medium mb-2">Spice Preference</label>
              <div className="flex gap-2">
                {['Mild', 'Medium', 'Spicy', 'Extra Spicy'].map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setSpicePreference(level)}
                    className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                      spicePreference === level
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            {/* Budget */}
            <div>
              <label htmlFor="budget" className="block text-sm font-medium mb-2">
                Default Budget per Person
              </label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                <input
                  id="budget"
                  type="number"
                  value={budgetPerPerson}
                  onChange={(e) => setBudgetPerPerson(e.target.value)}
                  className="block w-full rounded-lg border border-border bg-background pl-8 pr-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="15.00"
                  step="0.50"
                  min="0"
                />
              </div>
            </div>
          </div>
        )}

        {/* Navigation buttons */}
        {step > 0 && (
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleBack}
              disabled={loading || skipping}
              className="flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-3 font-medium hover:bg-secondary disabled:opacity-50 transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>

            {step < 3 ? (
              <button
                type="button"
                onClick={handleNext}
                disabled={loading || skipping}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                Next
                <ArrowRight className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading || skipping}
                className="flex-1 rounded-lg bg-primary px-4 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {loading ? 'Saving...' : 'Get Started'}
              </button>
            )}
          </div>
        )}

        {/* Skip */}
        {!showSkipWarning ? (
          <button
            onClick={() => setShowSkipWarning(true)}
            className="w-full text-center text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip for now
          </button>
        ) : (
          <div className="rounded-lg border border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/20 p-4 space-y-3">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                  Are you sure?
                </p>
                <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">
                  Without your profile, Edesia won&apos;t know your location, preferences, or dietary needs. You&apos;ll need to provide these details manually each time.
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleSkip}
                disabled={skipping}
                className="flex-1 rounded-lg border border-amber-300 dark:border-amber-700 px-3 py-2 text-sm font-medium text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              >
                {skipping ? 'Skipping...' : 'Skip anyway'}
              </button>
              <button
                onClick={() => setShowSkipWarning(false)}
                className="flex-1 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                Fill out profile
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
