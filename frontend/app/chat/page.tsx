'use client'

import { useState, useRef, useEffect } from 'react'
import { useAuth } from '@/lib/auth-context'
import { ChatMessage } from '@/components/chat/chat-message'
import { ChatInput, Attachment } from '@/components/chat/chat-input'
import { PendingAction } from '@/components/chat/pending-action'
import { sendMessage, streamMessage, approveAction, PendingAction as PendingActionType, UserProfile, ImageAttachment, PdfAttachment } from '@/lib/api'
import { createChat, addMessage, updateChatSessionId } from '@/lib/chat-store'
import { needsOnboarding, getUserProfile } from '@/lib/user-store'
import { useRouter } from 'next/navigation'
import { fileToBase64, uploadFile } from '@/lib/file-upload'
import { track } from '@vercel/analytics'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [pendingActions, setPendingActions] = useState<PendingActionType[]>([])
  const [loading, setLoading] = useState(false)
  const [streamStatus, setStreamStatus] = useState<string>('')
  const [sessionId, setSessionId] = useState<string>()
  const [checkingOnboarding, setCheckingOnboarding] = useState(true)
  const [userProfile, setUserProfile] = useState<UserProfile | undefined>()
  const [isTransitioning, setIsTransitioning] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()

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
      const profileData = {
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
      }
      console.log('[ChatPage] Loaded user profile:', profileData)
      setUserProfile(profileData)
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

  const handleSend = async (content: string, attachments?: Attachment[]) => {
    if (!user || loading) return

    track('chat_message_sent', {
      has_attachments: !!attachments?.length,
      is_first_message: messages.length === 0,
    })

    // Start transition animation if this is the first message
    if (messages.length === 0) {
      setIsTransitioning(true)
    }

    // Build display content with attachment indicators
    let displayContent = content
    if (attachments && attachments.length > 0) {
      const attachmentNames = attachments.map(a => a.file.name).join(', ')
      displayContent = content ? `${content}\n\n[Attached: ${attachmentNames}]` : `[Attached: ${attachmentNames}]`
    }

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: displayContent,
    }
    setMessages((prev) => [...prev, userMessage])
    setLoading(true)

    try {
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
              const uploaded = await uploadFile(att.file, user.uid)
              return {
                type: 'pdf' as const,
                url: uploaded.url,
                name: att.file.name,
              }
            }
          })
        )
      }

      setStreamStatus('Connecting...')

      await streamMessage(
        content,
        {
          onStatus: (_status, message) => {
            setStreamStatus(message || 'Working...')
          },
          onDone: async (newSessionId, response, actions) => {
            setSessionId(newSessionId)
            setStreamStatus('')

            // Add assistant message
            const assistantMessage: Message = {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: response,
            }
            setMessages((prev) => [...prev, assistantMessage])

            // Handle pending actions — replace, don't accumulate
            if (actions?.length > 0) {
              setPendingActions(actions)
            } else {
              setPendingActions([])
            }

            // Create chat in Firebase and navigate
            if (!sessionId) {
              setLoading(false)
              const chatId = await createChat(user.uid, content.slice(0, 50), newSessionId)
              addMessage(chatId, 'user', content).catch(console.error)
              addMessage(chatId, 'assistant', response).catch(console.error)
              router.push(`/chat/${chatId}`)
              return
            }

            setLoading(false)
          },
          onError: (error) => {
            console.error('Stream error:', error)
            setStreamStatus('')
            setMessages((prev) => [
              ...prev,
              {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.',
              },
            ])
            setLoading(false)
          },
        },
        sessionId,
        undefined,
        userProfile,
        apiAttachments
      )
    } catch (error) {
      console.error('Error sending message:', error)
      setStreamStatus('')
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
        },
      ])
    } finally {
      setLoading(false)
      setStreamStatus('')
    }
  }

  const handleApprove = async (actionId: string) => {
    try {
      const result = await approveAction(actionId, true, user?.email || undefined)
      track('action_approved', { action_id: actionId })
      setPendingActions((prev) => prev.filter((a) => a.action_id !== actionId))
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: `Action approved! ${result.result?.message || ''}`,
        },
      ])
    } catch (error) {
      console.error('Error approving action:', error)
    }
  }

  const handleReject = async (actionId: string) => {
    try {
      await approveAction(actionId, false, user?.email || undefined)
      track('action_rejected', { action_id: actionId })
      setPendingActions((prev) => prev.filter((a) => a.action_id !== actionId))
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: 'assistant',
          content: 'Action rejected. Let me know if you need anything else.',
        },
      ])
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

  // Empty state with centered welcome message
  if (messages.length === 0 && !isTransitioning) {
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

  // Chat view (with transition animation)
  return (
    <div className="flex h-full flex-col">
      {/* Animated header that fades out */}
      {isTransitioning && messages.length <= 1 && (
        <div className="absolute inset-x-0 top-0 flex items-center justify-center h-24 animate-slide-up-fade pointer-events-none">
          <h1 className="text-2xl font-medium text-muted-foreground">
            What's on the agenda today?
          </h1>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[95%] md:max-w-[85%]">
          {messages.map((message, index) => (
            <div
              key={message.id}
              className={index === 0 && isTransitioning ? 'animate-slide-down' : ''}
            >
              <ChatMessage
                role={message.role}
                content={message.content}
              />
            </div>
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
      <ChatInput onSend={handleSend} loading={loading} />
    </div>
  )
}
