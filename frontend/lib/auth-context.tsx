'use client'

import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import {
  User,
  UserCredential,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  GoogleAuthProvider,
  signInWithPopup,
  sendEmailVerification,
} from 'firebase/auth'
import { auth } from './firebase'

interface AuthContextType {
  user: User | null
  loading: boolean
  error: string | null
  signIn: (email: string, password: string) => Promise<UserCredential>
  signUp: (email: string, password: string) => Promise<UserCredential>
  signInWithGoogle: () => Promise<UserCredential>
  signOut: () => Promise<void>
  resendVerificationEmail: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    console.log('AuthProvider: useEffect running, auth object:', auth ? 'exists' : 'null')

    // Check if Firebase auth is available
    if (!auth) {
      console.error('Firebase auth not initialized - check environment variables')
      setError('Firebase configuration error. Please check environment variables.')
      setLoading(false)
      return
    }

    console.log('AuthProvider: Setting up onAuthStateChanged listener')
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      console.log('AuthProvider: onAuthStateChanged fired, user:', user ? user.email : 'null')
      setUser(user)
      setLoading(false)
    })

    return () => unsubscribe()
  }, [])

  const signIn = async (email: string, password: string) => {
    if (!auth) throw new Error('Firebase not configured')
    return signInWithEmailAndPassword(auth, email, password)
  }

  const signUp = async (email: string, password: string) => {
    if (!auth) throw new Error('Firebase not configured')
    const credential = await createUserWithEmailAndPassword(auth, email, password)
    await sendEmailVerification(credential.user)
    return credential
  }

  const signInWithGoogle = async () => {
    if (!auth) throw new Error('Firebase not configured')
    const provider = new GoogleAuthProvider()
    return signInWithPopup(auth, provider)
  }

  const resendVerificationEmail = async () => {
    if (!auth?.currentUser) throw new Error('No user signed in')
    await sendEmailVerification(auth.currentUser)
  }

  const signOut = async () => {
    if (!auth) throw new Error('Firebase not configured')
    await firebaseSignOut(auth)
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, error, signIn, signUp, signInWithGoogle, signOut, resendVerificationEmail }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
