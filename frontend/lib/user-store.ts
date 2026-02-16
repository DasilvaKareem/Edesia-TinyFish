import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore'
import { db } from './firebase'

export interface UserProfile {
  uid: string
  email: string
  accountType?: 'individual' | 'team'
  displayName?: string
  phoneNumber?: string
  companyName?: string
  companySize?: string
  city?: string
  state?: string
  onboardingComplete: boolean
  stripeCustomerId?: string
  createdAt: Date
  updatedAt: Date
  // Saved addresses
  workAddress?: { rawAddress: string; formattedAddress?: string; label?: string }
  homeAddress?: { rawAddress: string; formattedAddress?: string; label?: string }
  // Food preferences (from settings page)
  dietaryRestrictions?: string[]
  allergies?: string[]
  favoriteCuisines?: string[]
  dislikedCuisines?: string[]
  spicePreference?: string
  budgetPerPerson?: number
}

export interface OnboardingData {
  accountType?: 'individual' | 'team'
  displayName?: string
  phoneNumber?: string
  companyName?: string
  companySize?: string
  city?: string
  state?: string
  workAddress?: { rawAddress: string; label: string }
  homeAddress?: { rawAddress: string; label: string }
  dietaryRestrictions?: string[]
  allergies?: string[]
  favoriteCuisines?: string[]
  dislikedCuisines?: string[]
  spicePreference?: string
  budgetPerPerson?: number
}

// Get user profile
export async function getUserProfile(uid: string): Promise<UserProfile | null> {
  const docRef = doc(db, 'users', uid)
  const docSnap = await getDoc(docRef)

  if (!docSnap.exists()) {
    return null
  }

  return { uid, ...docSnap.data() } as UserProfile
}

// Create user profile (called after signup)
export async function createUserProfile(uid: string, email: string): Promise<void> {
  const docRef = doc(db, 'users', uid)
  await setDoc(docRef, {
    email,
    onboardingComplete: false,
    createdAt: new Date(),
    updatedAt: new Date(),
  })
}

// Complete onboarding
export async function completeOnboarding(uid: string, data: OnboardingData): Promise<void> {
  const docRef = doc(db, 'users', uid)
  await updateDoc(docRef, {
    ...data,
    onboardingComplete: true,
    updatedAt: new Date(),
  })
}

// Check if user needs onboarding
export async function needsOnboarding(uid: string): Promise<boolean> {
  const profile = await getUserProfile(uid)
  return !profile || !profile.onboardingComplete
}
