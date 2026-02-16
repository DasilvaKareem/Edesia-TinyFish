import {
  collection,
  doc,
  addDoc,
  updateDoc,
  deleteDoc,
  query,
  where,
  orderBy,
  onSnapshot,
  serverTimestamp,
  Timestamp,
} from 'firebase/firestore'
import { db } from './firebase'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: Timestamp
}

export interface Chat {
  id: string
  userId: string
  title: string
  sessionId?: string  // Backend session ID for LLM context
  createdAt: Timestamp
  updatedAt: Timestamp
}

// Generate unique chat title with timestamp
function generateChatTitle(): string {
  const now = new Date()
  const timestamp = now.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  })
  const shortId = Math.random().toString(36).substring(2, 8).toUpperCase()
  return `Chat ${shortId} - ${timestamp}`
}

// Create a new chat
export async function createChat(userId: string, title?: string, sessionId?: string) {
  const chatTitle = title || generateChatTitle()
  const chatRef = await addDoc(collection(db, 'chats'), {
    userId,
    title: chatTitle,
    sessionId: sessionId || null,  // Store backend session ID
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  })
  return chatRef.id
}

// Update session ID for a chat
export async function updateChatSessionId(chatId: string, sessionId: string) {
  await updateDoc(doc(db, 'chats', chatId), { sessionId })
}

// Get chat metadata (including sessionId)
export async function getChatMetadata(chatId: string): Promise<Chat | null> {
  const { getDoc } = await import('firebase/firestore')
  const docSnap = await getDoc(doc(db, 'chats', chatId))
  if (!docSnap.exists()) return null
  return { id: docSnap.id, ...docSnap.data() } as Chat
}

// Get user's chats
export function subscribeToChats(
  userId: string,
  callback: (chats: Chat[]) => void
) {
  const q = query(
    collection(db, 'chats'),
    where('userId', '==', userId),
    orderBy('updatedAt', 'desc')
  )

  return onSnapshot(q, (snapshot) => {
    const chats = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as Chat[]
    callback(chats)
  })
}

// Add message to chat
export async function addMessage(
  chatId: string,
  role: 'user' | 'assistant',
  content: string
) {
  await addDoc(collection(db, 'chats', chatId, 'messages'), {
    role,
    content,
    createdAt: serverTimestamp(),
  })

  // Update chat's updatedAt
  await updateDoc(doc(db, 'chats', chatId), {
    updatedAt: serverTimestamp(),
  })
}

// Get messages for a chat
export function subscribeToMessages(
  chatId: string,
  callback: (messages: Message[]) => void
) {
  const q = query(
    collection(db, 'chats', chatId, 'messages'),
    orderBy('createdAt', 'asc')
  )

  return onSnapshot(q, (snapshot) => {
    const messages = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as Message[]
    callback(messages)
  })
}

// Update chat title
export async function updateChatTitle(chatId: string, title: string) {
  await updateDoc(doc(db, 'chats', chatId), { title })
}

// Auto-generate title from first message (truncate to 50 chars)
export async function autoTitleFromMessage(chatId: string, firstMessage: string) {
  const title = firstMessage.length > 50
    ? firstMessage.substring(0, 47) + '...'
    : firstMessage
  await updateChatTitle(chatId, title)
}

// Delete chat
export async function deleteChat(chatId: string) {
  await deleteDoc(doc(db, 'chats', chatId))
}
