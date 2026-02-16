'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { Plus, MessageSquare, Trash2, LogOut, Settings, Utensils, ChevronUp, Plug, CreditCard, X, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Chat, subscribeToChats, createChat, deleteChat } from '@/lib/chat-store'
import { cn } from '@/lib/utils'
import { track } from '@vercel/analytics'

interface ChatSidebarProps {
  currentChatId?: string
  isOpen?: boolean
  onClose?: () => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

export function ChatSidebar({ currentChatId, isOpen, onClose, collapsed, onToggleCollapse }: ChatSidebarProps) {
  const [chats, setChats] = useState<Chat[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const { user, signOut } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!user) return

    const unsubscribe = subscribeToChats(user.uid, setChats)
    return () => unsubscribe()
  }, [user])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleNewChat = async () => {
    if (!user) return
    track('new_chat_created')
    const chatId = await createChat(user.uid)
    router.push(`/chat/${chatId}`)
  }

  const handleDeleteChat = async (e: React.MouseEvent, chatId: string) => {
    e.stopPropagation()
    await deleteChat(chatId)
    if (currentChatId === chatId) {
      router.push('/chat')
    }
  }

  const handleSignOut = async () => {
    setShowDropdown(false)
    track('user_signed_out')
    await signOut()
    router.push('/auth/login')
  }

  const handleNavigate = (path: string) => {
    setShowDropdown(false)
    const tab = new URL(path, 'http://x').searchParams.get('tab') || 'profile'
    track('settings_navigated', { tab })
    router.push(path)
  }

  const handleChatClick = (chatId: string) => {
    router.push(`/chat/${chatId}`)
    onClose?.()
  }

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}
      <div className={cn(
        "flex h-full flex-col bg-secondary/50 flex-shrink-0",
        "fixed inset-y-0 left-0 z-50 md:relative md:z-auto",
        "transition-all duration-200 ease-in-out",
        collapsed ? "md:w-0 md:overflow-hidden" : "w-[308px]",
        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      )}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        <img src="/logo-red.png" alt="Edesia" className="h-7 dark:hidden" />
        <img src="/logo-white.png" alt="Edesia" className="h-7 hidden dark:block" />
        <div className="flex items-center gap-1">
          <button
            onClick={handleNewChat}
            className="rounded-lg p-2 hover:bg-secondary transition-colors"
            title="New Chat"
          >
            <Plus className="h-5 w-5" />
          </button>
          <button
            onClick={onToggleCollapse}
            className="rounded-lg p-2 hover:bg-secondary transition-colors hidden md:flex"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="h-5 w-5" />
          </button>
          <button
            onClick={onClose}
            className="rounded-lg p-2 hover:bg-secondary transition-colors md:hidden"
            title="Close sidebar"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Chat List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {chats.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            No conversations yet
          </p>
        ) : (
          chats.map((chat) => (
            <div
              key={chat.id}
              onClick={() => handleChatClick(chat.id)}
              className={cn(
                'group flex items-center justify-between rounded-lg px-3 py-2 cursor-pointer transition-colors',
                currentChatId === chat.id
                  ? 'bg-primary/10 text-primary'
                  : 'hover:bg-secondary'
              )}
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <MessageSquare className="h-4 w-4 flex-shrink-0" />
                <span className="truncate text-sm">{chat.title}</span>
              </div>
              <button
                onClick={(e) => handleDeleteChat(e, chat.id)}
                className="opacity-0 group-hover:opacity-100 rounded p-1 hover:bg-red-100 dark:hover:bg-red-900/20 transition-all"
              >
                <Trash2 className="h-4 w-4 text-red-500" />
              </button>
            </div>
          ))
        )}
      </div>

      {/* User Section with Dropdown */}
      <div className="border-t border-border p-4 relative" ref={dropdownRef}>
        {/* Dropdown Menu */}
        {showDropdown && (
          <div className="absolute bottom-full left-2 right-2 mb-2 rounded-lg border border-border bg-background shadow-lg overflow-hidden">
            <button
              onClick={() => handleNavigate('/settings?tab=profile')}
              className="flex items-center gap-3 w-full px-4 py-3 hover:bg-secondary transition-colors text-left"
            >
              <Settings className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Settings</span>
            </button>
            <button
              onClick={() => handleNavigate('/settings?tab=preferences')}
              className="flex items-center gap-3 w-full px-4 py-3 hover:bg-secondary transition-colors text-left"
            >
              <Utensils className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Food Preferences</span>
            </button>
            <button
              onClick={() => handleNavigate('/settings?tab=integrations')}
              className="flex items-center gap-3 w-full px-4 py-3 hover:bg-secondary transition-colors text-left"
            >
              <Plug className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Integrations</span>
            </button>
            <button
              onClick={() => handleNavigate('/settings?tab=billing')}
              className="flex items-center gap-3 w-full px-4 py-3 hover:bg-secondary transition-colors text-left"
            >
              <CreditCard className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">Billing</span>
            </button>
            <div className="border-t border-border" />
            <button
              onClick={handleSignOut}
              className="flex items-center gap-3 w-full px-4 py-3 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors text-left text-red-600 dark:text-red-400"
            >
              <LogOut className="h-4 w-4" />
              <span className="text-sm">Sign Out</span>
            </button>
          </div>
        )}

        {/* User Button */}
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          className="flex items-center justify-between w-full rounded-lg p-2 hover:bg-secondary transition-colors"
        >
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center">
              <span className="text-sm font-medium text-primary">
                {user?.email?.[0].toUpperCase()}
              </span>
            </div>
            <span className="text-sm truncate">{user?.email}</span>
          </div>
          <ChevronUp className={cn(
            "h-4 w-4 text-muted-foreground transition-transform",
            showDropdown ? "rotate-180" : ""
          )} />
        </button>
      </div>
    </div>
    </>
  )
}
