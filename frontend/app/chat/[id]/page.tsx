'use client'

import { useState, useRef, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { ChatMessage } from '@/components/chat/chat-message'
import { ChatInput, Attachment } from '@/components/chat/chat-input'
import { PendingAction } from '@/components/chat/pending-action'
import { sendMessage, streamMessage, approveAction, PendingAction as PendingActionType, UserProfile, ImageAttachment, PdfAttachment } from '@/lib/api'
import { subscribeToMessages, addMessage, getChatMetadata, updateChatSessionId, Message as FirebaseMessage } from '@/lib/chat-store'
import { needsOnboarding, getUserProfile } from '@/lib/user-store'
import { fileToBase64, uploadFile } from '@/lib/file-upload'
import { track } from '@vercel/analytics'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export default function ChatPage() {
  const params = useParams()
  const chatId = params.id as string
  const router = useRouter()

  const [messages, setMessages] = useState<Message[]>([])
  const [pendingActions, setPendingActions] = useState<PendingActionType[]>([])
  const [loading, setLoading] = useState(false)
  const [streamStatus, setStreamStatus] = useState<string>('')
  const [sessionId, setSessionId] = useState<string>()
  const [sessionLoading, setSessionLoading] = useState(true)  // Track if sessionId is being loaded
  const [checkingOnboarding, setCheckingOnboarding] = useState(true)
  const [userProfile, setUserProfile] = useState<UserProfile | undefined>()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const isSendingRef = useRef(false)
  const { user, loading: authLoading } = useAuth()

  // Check onboarding status and load user profile
  useEffect(() => {
    async function checkOnboardingAndLoadProfile() {
      if (!user) {
        setCheckingOnboarding(false)
        return
      }
      const profile = await getUserProfile(user.uid)
      if (!profile?.onboardingComplete) {
        router.push('/onboarding')
        return
      }
      // Store profile for API calls (includes company info AND food preferences)
      setUserProfile({
        accountType: (profile as any).accountType,
        displayName: (profile as any).displayName,
        companyName: profile.companyName,
        companySize: profile.companySize,
        city: profile.city,
        state: profile.state,
        phoneNumber: profile.phoneNumber,
        // Food preferences
        dietaryRestrictions: profile.dietaryRestrictions,
        allergies: profile.allergies,
        favoriteCuisines: profile.favoriteCuisines,
        dislikedCuisines: profile.dislikedCuisines,
        spicePreference: profile.spicePreference,
        budgetPerPerson: profile.budgetPerPerson,
        // Saved addresses
        workAddress: (profile as any).workAddress,
        homeAddress: (profile as any).homeAddress,
      })
      setCheckingOnboarding(false)
    }
    if (!authLoading) {
      checkOnboardingAndLoadProfile()
    }
  }, [user, authLoading, router])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  // Load session ID from Firebase on mount
  useEffect(() => {
    if (!chatId) return

    setSessionLoading(true)
    getChatMetadata(chatId).then((chat) => {
      if (chat?.sessionId) {
        console.log('[ChatPage] Restored sessionId from Firebase:', chat.sessionId)
        setSessionId(chat.sessionId)
      } else {
        console.log('[ChatPage] No sessionId found in Firebase for chat:', chatId)
      }
    }).catch((e) => {
      console.error('[ChatPage] Error loading chat metadata:', e)
    }).finally(() => {
      setSessionLoading(false)
    })
  }, [chatId])

  // Load messages from Firebase
  useEffect(() => {
    if (!chatId) return

    const unsubscribe = subscribeToMessages(chatId, (firebaseMessages) => {
      const formattedMessages: Message[] = firebaseMessages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
      }))
      setMessages(formattedMessages)
    })

    return () => unsubscribe()
  }, [chatId])

  const handleSend = async (content: string, attachments?: Attachment[]) => {
    // Double-check with ref to prevent race conditions
    if (!user || !chatId || loading || isSendingRef.current) {
      console.log('[handleSend] Blocked - already sending or missing data')
      return
    }

    // Wait for session to be loaded before sending
    if (sessionLoading) {
      console.log('[handleSend] Waiting for sessionId to load...')
      return
    }

    isSendingRef.current = true
    setLoading(true)
    track('chat_message_sent', { has_attachments: !!attachments?.length })
    console.log('[handleSend] Starting, loading=true')

    try {
      // Build display content with attachment indicators
      let displayContent = content
      if (attachments && attachments.length > 0) {
        const attachmentNames = attachments.map(a => a.file.name).join(', ')
        displayContent = content ? `${content}\n\n[Attached: ${attachmentNames}]` : `[Attached: ${attachmentNames}]`
      }

      // Add user message to Firebase (fire and forget - don't wait)
      console.log('[handleSend] Adding user message to Firebase')
      addMessage(chatId, 'user', displayContent).catch(e =>
        console.error('[handleSend] User message Firebase error:', e)
      )

      console.log('[handleSend] Calling API with sessionId:', sessionId)

      // Process attachments
      let apiAttachments: (ImageAttachment | PdfAttachment)[] | undefined

      if (attachments && attachments.length > 0) {
        apiAttachments = await Promise.all(
          attachments.map(async (att) => {
            if (att.type === 'image') {
              // Convert image to base64 for vision API
              const base64 = await fileToBase64(att.file)
              return {
                type: 'image' as const,
                data: base64,
                mime_type: att.file.type,
                name: att.file.name,
              }
            } else {
              // Upload PDF to Firebase Storage
              const uploaded = await uploadFile(att.file, user.uid, chatId)
              return {
                type: 'pdf' as const,
                url: uploaded.url,
                name: att.file.name,
              }
            }
          })
        )
      }

      // Send message history as fallback for LLM context
      const messageHistory = messages.map(m => ({ role: m.role, content: m.content }))
      console.log('[handleSend] Sending message history:', messageHistory.length, 'messages')

      setStreamStatus('Connecting...')

      await streamMessage(
        content,
        {
          onStatus: (_status, message) => {
            setStreamStatus(message || 'Working...')
          },
          onDone: (newSessionId, response, actions) => {
            console.log('[handleSend] Stream done:', newSessionId)
            setStreamStatus('')

            // If this is a new session or session changed, update Firebase
            if (newSessionId && newSessionId !== sessionId) {
              setSessionId(newSessionId)
              updateChatSessionId(chatId, newSessionId).catch(e =>
                console.error('[handleSend] Failed to update sessionId in Firebase:', e)
              )
            }

            // Add assistant message to Firebase
            console.log('[handleSend] Adding assistant message to Firebase')
            addMessage(chatId, 'assistant', response).catch(e =>
              console.error('[handleSend] Firebase error:', e)
            )

            // Handle pending actions — replace, don't accumulate
            if (actions?.length > 0) {
              setPendingActions(actions)
            } else {
              setPendingActions([])
            }

            console.log('[handleSend] Success, about to set loading=false')
            isSendingRef.current = false
            setLoading(false)
          },
          onError: (error) => {
            console.error('[handleSend] Stream error:', error)
            setStreamStatus('')
            addMessage(
              chatId,
              'assistant',
              'Sorry, I encountered an error. Please try again.'
            ).catch(e => console.error('[handleSend] Failed to add error message:', e))
            isSendingRef.current = false
            setLoading(false)
          },
        },
        sessionId,
        messageHistory,
        userProfile,
        apiAttachments,
        chatId
      )
    } catch (error) {
      console.error('[handleSend] Error:', error)
      setStreamStatus('')
      addMessage(
        chatId,
        'assistant',
        'Sorry, I encountered an error. Please try again.'
      ).catch(e => console.error('[handleSend] Failed to add error message:', e))
    } finally {
      console.log('[handleSend] Finally block, setting loading=false')
      isSendingRef.current = false
      setLoading(false)
      setStreamStatus('')
    }
  }

  const handleApprove = async (actionId: string) => {
    try {
      const result = await approveAction(actionId, true, user?.email || undefined, chatId)
      track('action_approved', { action_id: actionId })

      // Handle payment errors — keep the pending action so user can retry
      if (result.status === 'error') {
        if (chatId) {
          if (result.error === 'no_payment_method') {
            await addMessage(chatId, 'assistant',
              'Please add a payment method in Settings \u2192 Billing before approving orders.')
          } else {
            await addMessage(chatId, 'assistant',
              `Payment failed: ${result.message || 'Please check your card and try again.'}`)
          }
        }
        return
      }

      setPendingActions((prev) => prev.filter((a) => a.action_id !== actionId))
      if (chatId) {
        await addMessage(
          chatId,
          'assistant',
          `Action approved! ${result.result?.message || ''}`
        )
      }
    } catch (error) {
      console.error('Error approving action:', error)
    }
  }

  const handleReject = async (actionId: string) => {
    try {
      await approveAction(actionId, false, user?.email || undefined, chatId)
      track('action_rejected', { action_id: actionId })
      setPendingActions((prev) => prev.filter((a) => a.action_id !== actionId))
      if (chatId) {
        await addMessage(
          chatId,
          'assistant',
          'Action rejected. Let me know if you need anything else.'
        )
      }
    } catch (error) {
      console.error('Error rejecting action:', error)
    }
  }

  if (authLoading || checkingOnboarding) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  const suggestions = [
    { label: '🗳️ Make a poll for lunch', prompt: 'Create a poll for the team to vote on lunch options' },
    { label: '🥙 Find halal restaurants', prompt: 'Find halal restaurants near me' },
    { label: '📋 Help me plan my event', prompt: 'Help me plan a catering event for my team' },
    { label: '🍕 Order lunch for tomorrow', prompt: 'Order lunch for my team for tomorrow' },
  ]

  // Empty state with centered welcome message (for new chats)
  if (messages.length === 0 && !sessionLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center -mt-16">
        <div className="w-full max-w-[95%] md:max-w-[95%] px-4 animate-fade-in">
          <div className="flex justify-center mb-6">
            <img src="/logo-red.png" alt="Edesia" className="h-12 dark:hidden" />
            <img src="/logo-white.png" alt="Edesia" className="h-12 hidden dark:block" />
          </div>
          <h1 className="text-4xl md:text-5xl font-medium text-foreground text-center mb-8">
            What can I help you order today?
          </h1>
          <div className="flex flex-wrap justify-center gap-2 mb-6">
            {suggestions.map((s) => (
              <button
                key={s.label}
                onClick={() => handleSend(s.prompt)}
                className="rounded-full border border-border bg-secondary/50 px-6 py-3 text-base text-foreground hover:bg-secondary transition-colors"
              >
                {s.label}
              </button>
            ))}
          </div>
          <ChatInput onSend={handleSend} loading={loading} centered />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[95%] md:max-w-[85%]">
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              role={message.role}
              content={message.content}
            />
          ))}

          {pendingActions.map((action) => (
            <div key={action.action_id} className="px-4">
              <PendingAction
                action={action}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            </div>
          ))}

          {loading && (
            <div className="flex gap-4 p-4 bg-secondary/30">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary">
                <span className="text-white text-sm">E</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1">
                  <div className="h-2 w-2 rounded-full bg-primary animate-bounce" />
                  <div className="h-2 w-2 rounded-full bg-primary animate-bounce [animation-delay:0.2s]" />
                  <div className="h-2 w-2 rounded-full bg-primary animate-bounce [animation-delay:0.4s]" />
                </div>
                {streamStatus && (
                  <span className="text-sm text-muted-foreground animate-pulse">
                    {streamStatus}
                  </span>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>
      <ChatInput onSend={handleSend} loading={loading || sessionLoading} />
    </div>
  )
}
