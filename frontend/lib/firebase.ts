import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getAuth, Auth } from 'firebase/auth'
import { getFirestore, Firestore } from 'firebase/firestore'
import { getStorage, FirebaseStorage } from 'firebase/storage'

// Use placeholder values for build time, real values will be used at runtime
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY?.trim() || 'placeholder-api-key',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN?.trim() || 'placeholder.firebaseapp.com',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID?.trim() || 'placeholder-project',
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET?.trim() || 'placeholder.appspot.com',
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID?.trim() || '123456789',
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID?.trim() || '1:123456789:web:abcdef',
}

// Check if Firebase config is valid (has real values)
const isConfigValid = process.env.NEXT_PUBLIC_FIREBASE_API_KEY && process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID

// Debug logging for client-side
if (typeof window !== 'undefined') {
  console.log('Firebase config check:', {
    hasApiKey: !!process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    hasProjectId: !!process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    hasAuthDomain: !!process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    isValid: isConfigValid,
  })

  if (!isConfigValid) {
    console.error('Firebase config is missing! Check your environment variables.')
    console.error('Required: NEXT_PUBLIC_FIREBASE_API_KEY, NEXT_PUBLIC_FIREBASE_PROJECT_ID')
  }
}

// Initialize Firebase - uses placeholder config during build, real config at runtime
const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0]
const auth = getAuth(app)
const db = getFirestore(app)
const storage = getStorage(app)

export { auth, db, storage }
export default app
