'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { getUserProfile, UserProfile } from '@/lib/user-store'
import { ArrowLeft, User, Utensils, Building2, Phone, MapPin, Users, Save, CreditCard, Trash2, Loader2, Plug, Calendar, MessageSquare, Receipt, ExternalLink, Home } from 'lucide-react'
import { doc, updateDoc } from 'firebase/firestore'
import { db } from '@/lib/firebase'
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js'
import stripePromise from '@/lib/stripe'
import { createSetupIntent, getPaymentMethods, deletePaymentMethod } from '@/lib/api'

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

type TabType = 'profile' | 'preferences' | 'integrations' | 'billing'

interface PaymentMethod {
  id: string
  brand: string
  last4: string
  exp_month: number
  exp_year: number
}

function AddCardForm({ userId, email, onCardAdded }: {
  userId: string
  email: string
  onCardAdded: () => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [cardSaving, setCardSaving] = useState(false)
  const [cardError, setCardError] = useState('')
  const [cardSuccess, setCardSuccess] = useState(false)

  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setCardSaving(true)
    setCardError('')
    setCardSuccess(false)

    try {
      const { client_secret } = await createSetupIntent(userId, email)
      const cardElement = elements.getElement(CardElement)
      if (!cardElement) throw new Error('Card element not found')

      const { error, setupIntent } = await stripe.confirmCardSetup(client_secret, {
        payment_method: { card: cardElement },
      })

      if (error) {
        setCardError(error.message || 'Failed to save card')
      } else if (setupIntent?.status === 'succeeded') {
        setCardSuccess(true)
        cardElement.clear()
        onCardAdded()
        setTimeout(() => setCardSuccess(false), 3000)
      }
    } catch (err: any) {
      setCardError(err.message || 'Failed to save card')
    }
    setCardSaving(false)
  }

  return (
    <form onSubmit={handleAddCard} className="space-y-4">
      <div className="rounded-lg border border-border bg-background p-4">
        <CardElement options={{
          style: {
            base: {
              fontSize: '16px',
              color: 'var(--foreground, #1a1a1a)',
              '::placeholder': { color: '#9ca3af' },
            },
          },
        }} />
      </div>
      {cardError && (
        <p className="text-sm text-red-500">{cardError}</p>
      )}
      {cardSuccess && (
        <p className="text-sm text-green-500">Card saved successfully!</p>
      )}
      <button
        type="submit"
        disabled={cardSaving || !stripe}
        className="flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        {cardSaving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <CreditCard className="h-4 w-4" />
        )}
        {cardSaving ? 'Saving...' : 'Add Card'}
      </button>
    </form>
  )
}

function SettingsContent() {
  const searchParams = useSearchParams()
  const initialTab = (searchParams.get('tab') as TabType) || 'profile'

  const [activeTab, setActiveTab] = useState<TabType>(initialTab)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  // Profile fields
  const [phoneNumber, setPhoneNumber] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [companySize, setCompanySize] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')

  // Food preference fields
  const [dietaryRestrictions, setDietaryRestrictions] = useState<string[]>([])
  const [allergies, setAllergies] = useState<string[]>([])
  const [favoriteCuisines, setFavoriteCuisines] = useState<string[]>([])
  const [dislikedCuisines, setDislikedCuisines] = useState<string[]>([])
  const [spicePreference, setSpicePreference] = useState('')
  const [budgetPerPerson, setBudgetPerPerson] = useState('')
  const [workAddress, setWorkAddress] = useState('')
  const [homeAddress, setHomeAddress] = useState('')

  // Billing fields
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([])
  const [billingLoading, setBillingLoading] = useState(false)
  const [deletingPm, setDeletingPm] = useState<string | null>(null)

  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    async function loadProfile() {
      if (!user) return

      try {
        const profile = await getUserProfile(user.uid)
        if (profile) {
          setPhoneNumber(profile.phoneNumber || '')
          setCompanyName(profile.companyName || '')
          setCompanySize(profile.companySize || '')
          setCity(profile.city || '')
          setState(profile.state || '')
        }

        // Load food preferences from the profile or a separate collection
        // For now, we'll add these fields to the user profile
        const profileData = profile as any
        if (profileData) {
          setDietaryRestrictions(profileData.dietaryRestrictions || [])
          setAllergies(profileData.allergies || [])
          setFavoriteCuisines(profileData.favoriteCuisines || [])
          setDislikedCuisines(profileData.dislikedCuisines || [])
          setSpicePreference(profileData.spicePreference || '')
          setBudgetPerPerson(profileData.budgetPerPerson?.toString() || '')
          setWorkAddress(profileData.workAddress?.formattedAddress || profileData.workAddress?.rawAddress || '')
          setHomeAddress(profileData.homeAddress?.formattedAddress || profileData.homeAddress?.rawAddress || '')
        }
      } catch (e) {
        console.error('Error loading profile:', e)
      }
      setLoading(false)
    }

    if (!authLoading) {
      if (!user) {
        router.push('/auth/login')
      } else {
        loadProfile()
      }
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

  const handleSaveProfile = async () => {
    if (!user) return
    setSaving(true)
    setMessage('')

    try {
      const docRef = doc(db, 'users', user.uid)
      await updateDoc(docRef, {
        phoneNumber,
        companyName,
        companySize,
        city,
        state,
        workAddress: workAddress ? { rawAddress: workAddress, label: 'work' } : null,
        homeAddress: homeAddress ? { rawAddress: homeAddress, label: 'home' } : null,
        updatedAt: new Date(),
      })
      setMessage('Profile saved successfully!')
    } catch (e) {
      console.error('Error saving profile:', e)
      setMessage('Error saving profile')
    }
    setSaving(false)
  }

  const handleSavePreferences = async () => {
    if (!user) return
    setSaving(true)
    setMessage('')

    try {
      const docRef = doc(db, 'users', user.uid)
      await updateDoc(docRef, {
        dietaryRestrictions,
        allergies,
        favoriteCuisines,
        dislikedCuisines,
        spicePreference,
        budgetPerPerson: budgetPerPerson ? parseFloat(budgetPerPerson) : null,
        updatedAt: new Date(),
      })
      setMessage('Preferences saved successfully!')
    } catch (e) {
      console.error('Error saving preferences:', e)
      setMessage('Error saving preferences')
    }
    setSaving(false)
  }

  const loadPaymentMethods = async () => {
    if (!user) return
    setBillingLoading(true)
    try {
      const result = await getPaymentMethods(user.uid)
      setPaymentMethods(result.payment_methods)
    } catch (e) {
      console.error('Error loading payment methods:', e)
    }
    setBillingLoading(false)
  }

  // Load payment methods when billing tab is selected
  useEffect(() => {
    if (activeTab === 'billing' && user) {
      loadPaymentMethods()
    }
  }, [activeTab, user])

  const handleDeletePaymentMethod = async (pmId: string) => {
    setDeletingPm(pmId)
    try {
      await deletePaymentMethod(pmId)
      setPaymentMethods(prev => prev.filter(pm => pm.id !== pmId))
      setMessage('Card removed successfully!')
    } catch (e) {
      console.error('Error deleting payment method:', e)
      setMessage('Error removing card')
    }
    setDeletingPm(null)
  }

  const getBrandDisplay = (brand: string) => {
    const brands: Record<string, string> = {
      visa: 'Visa',
      mastercard: 'Mastercard',
      amex: 'Amex',
      discover: 'Discover',
      diners: 'Diners',
      jcb: 'JCB',
      unionpay: 'UnionPay',
    }
    return brands[brand] || brand.charAt(0).toUpperCase() + brand.slice(1)
  }

  if (authLoading || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-secondary/30">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/chat')}
              className="p-2 rounded-lg hover:bg-secondary transition-colors"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <h1 className="text-2xl font-bold">Settings</h1>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Tabs */}
        <div className="flex gap-2 mb-8 border-b border-border overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
          <button
            onClick={() => setActiveTab('profile')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === 'profile'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <User className="h-4 w-4" />
            Profile
          </button>
          <button
            onClick={() => setActiveTab('preferences')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === 'preferences'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Utensils className="h-4 w-4" />
            Preferences
          </button>
          <button
            onClick={() => setActiveTab('integrations')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === 'integrations'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Plug className="h-4 w-4" />
            Integrations
          </button>
          <button
            onClick={() => setActiveTab('billing')}
            className={`flex items-center gap-2 px-4 py-3 border-b-2 whitespace-nowrap transition-colors ${
              activeTab === 'billing'
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <CreditCard className="h-4 w-4" />
            Billing
          </button>
        </div>

        {/* Success/Error Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg ${
            message.includes('Error')
              ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400'
              : 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400'
          }`}>
            {message}
          </div>
        )}

        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <div className="space-y-6">
            <div className="rounded-xl border border-border p-6 space-y-6">
              <h2 className="text-lg font-semibold">Company Information</h2>

              {/* Email (read-only) */}
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={user?.email || ''}
                  disabled
                  className="block w-full rounded-lg border border-border bg-secondary/50 px-4 py-3 text-muted-foreground"
                />
              </div>

              {/* Phone Number */}
              <div>
                <label htmlFor="phone" className="block text-sm font-medium mb-1">
                  <div className="flex items-center gap-2">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    Phone Number
                  </div>
                </label>
                <input
                  id="phone"
                  type="tel"
                  value={phoneNumber}
                  onChange={handlePhoneChange}
                  className="block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="(555) 123-4567"
                />
              </div>

              {/* Company Name */}
              <div>
                <label htmlFor="company" className="block text-sm font-medium mb-1">
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
                  className="block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="Acme Inc."
                />
              </div>

              {/* Company Size */}
              <div>
                <label htmlFor="size" className="block text-sm font-medium mb-1">
                  <div className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-muted-foreground" />
                    Company Size
                  </div>
                </label>
                <select
                  id="size"
                  value={companySize}
                  onChange={(e) => setCompanySize(e.target.value)}
                  className="block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="">Select size...</option>
                  {COMPANY_SIZES.map((size) => (
                    <option key={size.value} value={size.value}>
                      {size.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* City & State */}
              <div>
                <label htmlFor="city" className="block text-sm font-medium mb-1">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    City & State
                  </div>
                </label>
                <div className="flex gap-2">
                  <input
                    id="city"
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    className="block flex-1 rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    placeholder="San Francisco"
                  />
                  <select
                    id="state"
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    className="block w-28 rounded-lg border border-border bg-background px-3 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    <option value="">State</option>
                    {US_STATES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Work Address */}
              <div>
                <label htmlFor="workAddress" className="block text-sm font-medium mb-1">
                  <div className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    Work Address
                  </div>
                </label>
                <input
                  id="workAddress"
                  type="text"
                  value={workAddress}
                  onChange={(e) => setWorkAddress(e.target.value)}
                  className="block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="123 Main St, Suite 200, Memphis, TN 38103"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Used as the default delivery address for orders
                </p>
              </div>

              {/* Home Address */}
              <div>
                <label htmlFor="homeAddress" className="block text-sm font-medium mb-1">
                  <div className="flex items-center gap-2">
                    <Home className="h-4 w-4 text-muted-foreground" />
                    Home Address
                  </div>
                </label>
                <input
                  id="homeAddress"
                  type="text"
                  value={homeAddress}
                  onChange={(e) => setHomeAddress(e.target.value)}
                  className="block w-full rounded-lg border border-border bg-background px-4 py-3 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="456 Oak Ave, Memphis, TN 38104"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Say &quot;deliver to home&quot; in chat to use this address
                </p>
              </div>
            </div>

            <button
              onClick={handleSaveProfile}
              disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              <Save className="h-4 w-4" />
              {saving ? 'Saving...' : 'Save Profile'}
            </button>
          </div>
        )}

        {/* Preferences Tab */}
        {activeTab === 'preferences' && (
          <div className="space-y-6">
            {/* Dietary Restrictions */}
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Dietary Restrictions</h2>
              <p className="text-sm text-muted-foreground">
                Select any dietary restrictions that apply to your orders
              </p>
              <div className="flex flex-wrap gap-2">
                {DIETARY_OPTIONS.map((diet) => (
                  <button
                    key={diet}
                    onClick={() => toggleArrayItem(dietaryRestrictions, setDietaryRestrictions, diet)}
                    className={`px-4 py-2 rounded-full text-sm transition-colors ${
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
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Food Allergies</h2>
              <p className="text-sm text-muted-foreground">
                Select any food allergies - these will be flagged on all orders
              </p>
              <div className="flex flex-wrap gap-2">
                {ALLERGY_OPTIONS.map((allergy) => (
                  <button
                    key={allergy}
                    onClick={() => toggleArrayItem(allergies, setAllergies, allergy)}
                    className={`px-4 py-2 rounded-full text-sm transition-colors ${
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
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Favorite Cuisines</h2>
              <p className="text-sm text-muted-foreground">
                Select cuisines you prefer for recommendations
              </p>
              <div className="flex flex-wrap gap-2">
                {CUISINE_OPTIONS.map((cuisine) => (
                  <button
                    key={cuisine}
                    onClick={() => toggleArrayItem(favoriteCuisines, setFavoriteCuisines, cuisine)}
                    className={`px-4 py-2 rounded-full text-sm transition-colors ${
                      favoriteCuisines.includes(cuisine)
                        ? 'bg-primary text-white'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {cuisine}
                  </button>
                ))}
              </div>
            </div>

            {/* Disliked Cuisines */}
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Cuisines to Avoid</h2>
              <p className="text-sm text-muted-foreground">
                Select cuisines you'd prefer to avoid
              </p>
              <div className="flex flex-wrap gap-2">
                {CUISINE_OPTIONS.map((cuisine) => (
                  <button
                    key={cuisine}
                    onClick={() => toggleArrayItem(dislikedCuisines, setDislikedCuisines, cuisine)}
                    className={`px-4 py-2 rounded-full text-sm transition-colors ${
                      dislikedCuisines.includes(cuisine)
                        ? 'bg-orange-500 text-white'
                        : 'bg-secondary hover:bg-secondary/80'
                    }`}
                  >
                    {cuisine}
                  </button>
                ))}
              </div>
            </div>

            {/* Spice Preference & Budget */}
            <div className="rounded-xl border border-border p-6 space-y-6">
              <h2 className="text-lg font-semibold">Other Preferences</h2>

              <div>
                <label className="block text-sm font-medium mb-2">Spice Preference</label>
                <div className="flex gap-2">
                  {['Mild', 'Medium', 'Spicy', 'Extra Spicy'].map((level) => (
                    <button
                      key={level}
                      onClick={() => setSpicePreference(level)}
                      className={`px-4 py-2 rounded-lg text-sm transition-colors ${
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

            <button
              onClick={handleSavePreferences}
              disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              <Save className="h-4 w-4" />
              {saving ? 'Saving...' : 'Save Preferences'}
            </button>
          </div>
        )}

        {/* Integrations Tab */}
        {activeTab === 'integrations' && (
          <div className="space-y-6">
            {/* Google Calendar */}
            <div className="rounded-xl border border-border p-4 md:p-6 space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center flex-shrink-0">
                    <Calendar className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">Google Calendar</h2>
                    <p className="text-sm text-muted-foreground">
                      Schedule meals, events, and reminders on your calendar
                    </p>
                  </div>
                </div>
                <button
                  className="flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-secondary transition-colors w-full sm:w-auto"
                >
                  <ExternalLink className="h-4 w-4" />
                  Connect
                </button>
              </div>
              <div className="text-xs text-muted-foreground bg-secondary/50 rounded-lg p-3">
                Edesia will be able to create and manage food-related calendar events for your team.
              </div>
            </div>

            {/* Slack */}
            <div className="rounded-xl border border-border p-4 md:p-6 space-y-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-purple-100 dark:bg-purple-900/30 flex items-center justify-center flex-shrink-0">
                    <MessageSquare className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">Slack</h2>
                    <p className="text-sm text-muted-foreground">
                      Send polls, notifications, and order updates to your channels
                    </p>
                  </div>
                </div>
                <button
                  className="flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-secondary transition-colors w-full sm:w-auto"
                >
                  <ExternalLink className="h-4 w-4" />
                  Connect
                </button>
              </div>
              <div className="text-xs text-muted-foreground bg-secondary/50 rounded-lg p-3">
                Edesia will post order summaries, poll links, and delivery updates to your Slack workspace.
              </div>
            </div>

            {/* Expense Provider */}
            <div className="rounded-xl border border-border p-4 md:p-6 space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center flex-shrink-0">
                    <Receipt className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <h2 className="text-lg font-semibold">Expense Management</h2>
                    <p className="text-sm text-muted-foreground">
                      Auto-export receipts and categorize food expenses
                    </p>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <label className="block text-sm font-medium">Provider</label>
                <div className="flex gap-2">
                  {['Ramp', 'Brex', 'CSV Export'].map((provider) => (
                    <button
                      key={provider}
                      className="px-4 py-2 rounded-lg text-sm border border-border hover:bg-secondary transition-colors"
                    >
                      {provider}
                    </button>
                  ))}
                </div>
              </div>
              <div className="text-xs text-muted-foreground bg-secondary/50 rounded-lg p-3">
                Connect your expense platform so Edesia can automatically categorize and export food order receipts.
              </div>
            </div>
          </div>
        )}

        {/* Billing Tab */}
        {activeTab === 'billing' && (
          <div className="space-y-6">
            {/* Add Payment Method */}
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Add Payment Method</h2>
              <p className="text-sm text-muted-foreground">
                Add a card to pay for orders placed through Edesia.
              </p>
              <Elements stripe={stripePromise}>
                <AddCardForm
                  userId={user?.uid || ''}
                  email={user?.email || ''}
                  onCardAdded={loadPaymentMethods}
                />
              </Elements>
            </div>

            {/* Saved Payment Methods */}
            <div className="rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold">Saved Cards</h2>
              {billingLoading ? (
                <div className="flex items-center gap-2 py-4 text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading...
                </div>
              ) : paymentMethods.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4">
                  No cards saved yet. Add one above to get started.
                </p>
              ) : (
                <div className="space-y-3">
                  {paymentMethods.map((pm) => (
                    <div
                      key={pm.id}
                      className="flex items-center justify-between rounded-lg border border-border p-4"
                    >
                      <div className="flex items-center gap-3">
                        <CreditCard className="h-5 w-5 text-muted-foreground" />
                        <div>
                          <p className="font-medium">
                            {getBrandDisplay(pm.brand)} ending in {pm.last4}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            Expires {pm.exp_month.toString().padStart(2, '0')}/{pm.exp_year}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeletePaymentMethod(pm.id)}
                        disabled={deletingPm === pm.id}
                        className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors disabled:opacity-50"
                      >
                        {deletingPm === pm.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SettingsPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    }>
      <SettingsContent />
    </Suspense>
  )
}
