const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Get user's timezone from browser
export function getUserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

export interface ChatResponse {
  response: string
  session_id: string
  pending_actions: PendingAction[]
}

export interface PendingAction {
  action_id: string
  action_type: string
  description: string
  status: string
  payload: any
}

export interface MessageHistory {
  role: 'user' | 'assistant'
  content: string
}

export interface ImageAttachment {
  type: 'image'
  data: string // base64 encoded
  mime_type: string
  name: string
}

export interface PdfAttachment {
  type: 'pdf'
  url: string // Firebase Storage URL
  name: string
}

export interface UserProfile {
  accountType?: 'individual' | 'team'
  displayName?: string
  companyName?: string
  companySize?: string
  city?: string
  state?: string
  phoneNumber?: string
  // Food preferences
  dietaryRestrictions?: string[]
  allergies?: string[]
  favoriteCuisines?: string[]
  dislikedCuisines?: string[]
  spicePreference?: string
  budgetPerPerson?: number
  // Saved addresses
  workAddress?: { rawAddress: string; formattedAddress?: string; latitude?: number; longitude?: number; placeId?: string }
  homeAddress?: { rawAddress: string; formattedAddress?: string; latitude?: number; longitude?: number; placeId?: string }
}

export async function sendMessage(
  message: string,
  sessionId?: string,
  messageHistory?: MessageHistory[],
  userProfile?: UserProfile,
  attachments?: (ImageAttachment | PdfAttachment)[],
  chatId?: string,
): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      chat_id: chatId,
      message_history: messageHistory,
      timezone: getUserTimezone(),
      user_profile: userProfile,
      attachments: attachments,
    }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}

export interface StreamCallbacks {
  onStatus?: (status: string, message: string) => void
  onToken?: (content: string, node: string) => void
  onDone?: (sessionId: string, response: string, pendingActions: PendingAction[]) => void
  onError?: (error: Error) => void
}

export async function streamMessage(
  message: string,
  callbacks: StreamCallbacks,
  sessionId?: string,
  messageHistory?: MessageHistory[],
  userProfile?: UserProfile,
  attachments?: (ImageAttachment | PdfAttachment)[],
  chatId?: string,
): Promise<void> {
  const response = await fetch(`${API_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      chat_id: chatId,
      message_history: messageHistory,
      timezone: getUserTimezone(),
      user_profile: userProfile,
      attachments: attachments,
    }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Parse SSE events from buffer
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // Keep incomplete line in buffer

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const jsonStr = line.slice(6).trim()
        if (!jsonStr) continue

        try {
          const event = JSON.parse(jsonStr)

          switch (event.type) {
            case 'status':
              callbacks.onStatus?.(event.status, event.message || '')
              break
            case 'token':
              callbacks.onToken?.(event.content, event.node || '')
              break
            case 'done':
              callbacks.onDone?.(
                event.session_id,
                event.response || '',
                event.pending_actions || []
              )
              break
          }
        } catch {
          // Skip malformed JSON
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function approveAction(
  actionId: string,
  approved: boolean,
  approvedBy?: string,
  chatId?: string,
): Promise<any> {
  const response = await fetch(`${API_URL}/approve/${actionId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      approved,
      approved_by: approvedBy,
      chat_id: chatId,
    }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}

// ==================== STRIPE PAYMENT FUNCTIONS ====================

export async function createSetupIntent(userId: string, email: string) {
  const res = await fetch(`${API_URL}/stripe/setup-intent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, email }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json() as Promise<{ client_secret: string; id: string }>
}

export async function getPaymentMethods(userId: string) {
  const res = await fetch(`${API_URL}/stripe/payment-methods/${userId}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json() as Promise<{
    payment_methods: {
      id: string
      brand: string
      last4: string
      exp_month: number
      exp_year: number
    }[]
  }>
}

export async function deletePaymentMethod(pmId: string) {
  const res = await fetch(`${API_URL}/stripe/payment-methods/${pmId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

// ==================== POLL FUNCTIONS ====================

export async function getPoll(pollId: string): Promise<any> {
  const response = await fetch(`${API_URL}/polls/${pollId}`)

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}

export async function votePoll(
  pollId: string,
  voterId: string,
  optionId: string
): Promise<any> {
  const response = await fetch(`${API_URL}/polls/${pollId}/vote`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      voter_id: voterId,
      option_id: optionId,
    }),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}
