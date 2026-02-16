import {
  collection,
  doc,
  addDoc,
  updateDoc,
  deleteDoc,
  query,
  orderBy,
  onSnapshot,
  serverTimestamp,
  Timestamp,
  getDoc,
} from 'firebase/firestore'
import { db } from './firebase'

// Order types
export type OrderType = 'reservation' | 'catering' | 'doordash' | 'poll' | 'phone_call'
export type OrderStatus = 'researching' | 'quoted' | 'pending' | 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'call_completed' | 'call_failed'
export type PoemStage = 'plan' | 'order' | 'execute' | 'monitor'

export interface OrderItem {
  name: string
  quantity: number
  price: number
  notes?: string
}

export interface Order {
  id: string
  type: OrderType
  status: OrderStatus
  vendor: string  // Restaurant name, caterer, etc.
  vendorPhone?: string
  vendorEmail?: string
  vendorAddress?: string

  // Event details
  eventDate: string
  eventTime?: string
  guestCount: number
  deliveryAddress?: string

  // Financial
  estimatedCost?: number
  actualCost?: number
  subtotal?: number
  tax?: number
  deliveryFee?: number
  serviceFee?: number

  // Order items (quote)
  items?: OrderItem[]

  // Metadata
  createdAt: Timestamp
  updatedAt: Timestamp
  notes?: string

  // POEM loop tracking
  actionId?: string
  actionType?: string
  poemStage?: PoemStage
  sessionId?: string
  trackingUrl?: string
  deliveryId?: string
  paymentIntentId?: string
  paymentStatus?: 'pending' | 'paid' | 'failed' | 'refunded'

  // Call tracking
  lastCallId?: string
  lastCallSummary?: string
  lastCallTranscript?: string
  lastCallAt?: string
  lastCallDuration?: number
  lastCallEndReason?: string
  pickupTime?: string
  confirmationNumber?: string
}

// Communication log types
export type CallStatus = 'initiated' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'no_answer'
export type EmailStatus = 'draft' | 'sent' | 'delivered' | 'opened' | 'replied' | 'bounced'
export type TextStatus = 'sent' | 'delivered' | 'read' | 'replied' | 'failed'

export interface CallLog {
  id: string
  vapiCallId?: string
  direction: 'outbound' | 'inbound'
  phoneNumber: string
  status: CallStatus
  duration?: number  // seconds
  transcript?: string
  summary?: string
  recordingUrl?: string
  createdAt: Timestamp
  endedAt?: Timestamp
}

export interface EmailLog {
  id: string
  direction: 'outbound' | 'inbound'
  to: string
  from: string
  subject: string
  body: string
  status: EmailStatus
  createdAt: Timestamp
  sentAt?: Timestamp
  openedAt?: Timestamp
}

export interface TextLog {
  id: string
  direction: 'outbound' | 'inbound'
  phoneNumber: string
  message: string
  status: TextStatus
  createdAt: Timestamp
  deliveredAt?: Timestamp
}

// ==================== ORDER FUNCTIONS ====================

export async function createOrder(
  chatId: string,
  orderData: Omit<Order, 'id' | 'createdAt' | 'updatedAt'>
) {
  const orderRef = await addDoc(collection(db, 'chats', chatId, 'orders'), {
    ...orderData,
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp(),
  })
  return orderRef.id
}

export function subscribeToOrders(
  chatId: string,
  callback: (orders: Order[]) => void
) {
  const q = query(
    collection(db, 'chats', chatId, 'orders'),
    orderBy('createdAt', 'desc')
  )

  return onSnapshot(q, (snapshot) => {
    const orders = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as Order[]
    callback(orders)
  })
}

export async function getOrder(chatId: string, orderId: string): Promise<Order | null> {
  const orderDoc = await getDoc(doc(db, 'chats', chatId, 'orders', orderId))
  if (!orderDoc.exists()) return null
  return { id: orderDoc.id, ...orderDoc.data() } as Order
}

export async function updateOrder(
  chatId: string,
  orderId: string,
  updates: Partial<Order>
) {
  await updateDoc(doc(db, 'chats', chatId, 'orders', orderId), {
    ...updates,
    updatedAt: serverTimestamp(),
  })
}

export async function updateOrderStatus(
  chatId: string,
  orderId: string,
  status: OrderStatus
) {
  await updateOrder(chatId, orderId, { status })
}

export async function deleteOrder(chatId: string, orderId: string) {
  await deleteDoc(doc(db, 'chats', chatId, 'orders', orderId))
}

// ==================== CALL LOG FUNCTIONS ====================

export async function addCallLog(
  chatId: string,
  orderId: string,
  callData: Omit<CallLog, 'id' | 'createdAt'>
) {
  const callRef = await addDoc(
    collection(db, 'chats', chatId, 'orders', orderId, 'calls'),
    {
      ...callData,
      createdAt: serverTimestamp(),
    }
  )
  return callRef.id
}

export function subscribeToCallLogs(
  chatId: string,
  orderId: string,
  callback: (calls: CallLog[]) => void
) {
  const q = query(
    collection(db, 'chats', chatId, 'orders', orderId, 'calls'),
    orderBy('createdAt', 'desc')
  )

  return onSnapshot(q, (snapshot) => {
    const calls = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as CallLog[]
    callback(calls)
  })
}

export async function updateCallLog(
  chatId: string,
  orderId: string,
  callId: string,
  updates: Partial<CallLog>
) {
  await updateDoc(
    doc(db, 'chats', chatId, 'orders', orderId, 'calls', callId),
    updates
  )
}

// ==================== EMAIL LOG FUNCTIONS ====================

export async function addEmailLog(
  chatId: string,
  orderId: string,
  emailData: Omit<EmailLog, 'id' | 'createdAt'>
) {
  const emailRef = await addDoc(
    collection(db, 'chats', chatId, 'orders', orderId, 'emails'),
    {
      ...emailData,
      createdAt: serverTimestamp(),
    }
  )
  return emailRef.id
}

export function subscribeToEmailLogs(
  chatId: string,
  orderId: string,
  callback: (emails: EmailLog[]) => void
) {
  const q = query(
    collection(db, 'chats', chatId, 'orders', orderId, 'emails'),
    orderBy('createdAt', 'desc')
  )

  return onSnapshot(q, (snapshot) => {
    const emails = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as EmailLog[]
    callback(emails)
  })
}

export async function updateEmailLog(
  chatId: string,
  orderId: string,
  emailId: string,
  updates: Partial<EmailLog>
) {
  await updateDoc(
    doc(db, 'chats', chatId, 'orders', orderId, 'emails', emailId),
    updates
  )
}

// ==================== TEXT LOG FUNCTIONS ====================

export async function addTextLog(
  chatId: string,
  orderId: string,
  textData: Omit<TextLog, 'id' | 'createdAt'>
) {
  const textRef = await addDoc(
    collection(db, 'chats', chatId, 'orders', orderId, 'texts'),
    {
      ...textData,
      createdAt: serverTimestamp(),
    }
  )
  return textRef.id
}

export function subscribeToTextLogs(
  chatId: string,
  orderId: string,
  callback: (texts: TextLog[]) => void
) {
  const q = query(
    collection(db, 'chats', chatId, 'orders', orderId, 'texts'),
    orderBy('createdAt', 'desc')
  )

  return onSnapshot(q, (snapshot) => {
    const texts = snapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as TextLog[]
    callback(texts)
  })
}

export async function updateTextLog(
  chatId: string,
  orderId: string,
  textId: string,
  updates: Partial<TextLog>
) {
  await updateDoc(
    doc(db, 'chats', chatId, 'orders', orderId, 'texts', textId),
    updates
  )
}

// ==================== AGGREGATE FUNCTIONS ====================

export interface OrderWithLogs extends Order {
  calls: CallLog[]
  emails: EmailLog[]
  texts: TextLog[]
}

export function subscribeToOrderWithLogs(
  chatId: string,
  orderId: string,
  callback: (order: OrderWithLogs | null) => void
) {
  let order: Order | null = null
  let calls: CallLog[] = []
  let emails: EmailLog[] = []
  let texts: TextLog[] = []

  const updateCallback = () => {
    if (order) {
      callback({ ...order, calls, emails, texts })
    } else {
      callback(null)
    }
  }

  // Subscribe to order
  const unsubOrder = onSnapshot(
    doc(db, 'chats', chatId, 'orders', orderId),
    (snapshot) => {
      if (snapshot.exists()) {
        order = { id: snapshot.id, ...snapshot.data() } as Order
      } else {
        order = null
      }
      updateCallback()
    }
  )

  // Subscribe to calls
  const unsubCalls = subscribeToCallLogs(chatId, orderId, (c) => {
    calls = c
    updateCallback()
  })

  // Subscribe to emails
  const unsubEmails = subscribeToEmailLogs(chatId, orderId, (e) => {
    emails = e
    updateCallback()
  })

  // Subscribe to texts
  const unsubTexts = subscribeToTextLogs(chatId, orderId, (t) => {
    texts = t
    updateCallback()
  })

  // Return unsubscribe function
  return () => {
    unsubOrder()
    unsubCalls()
    unsubEmails()
    unsubTexts()
  }
}

