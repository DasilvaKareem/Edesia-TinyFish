'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { ChatSidebar } from '@/components/chat/chat-sidebar'
import { OrderPanel } from '@/components/orders/order-panel'
import { Menu, PanelLeftOpen } from 'lucide-react'

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { user, loading, error } = useAuth()
  const router = useRouter()
  const params = useParams()
  const chatId = params.id as string | undefined

  useEffect(() => {
    if (!loading && !user && !error) {
      router.push('/auth/login')
    }
  }, [user, loading, error, router])

  if (error) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <div className="text-center p-8">
          <h2 className="text-xl font-semibold text-red-600 mb-2">Configuration Error</h2>
          <p className="text-muted-foreground">{error}</p>
          <p className="text-sm text-muted-foreground mt-4">
            Please ensure Firebase environment variables are set in Vercel.
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex h-dvh items-center justify-center">
        <div className="animate-pulse text-lg text-muted-foreground">
          Loading...
        </div>
      </div>
    )
  }

  if (!user) {
    return null
  }

  return (
    <div className="flex h-dvh">
      <ChatSidebar
        currentChatId={chatId}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Mobile header with hamburger */}
        <div className="flex items-center gap-3 border-b border-border p-3 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-secondary transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
          <img src="/logo-red.png" alt="Edesia" className="h-6 dark:hidden" />
          <img src="/logo-white.png" alt="Edesia" className="h-6 hidden dark:block" />
        </div>
        {/* Desktop expand button when sidebar is collapsed */}
        {sidebarCollapsed && (
          <button
            onClick={() => setSidebarCollapsed(false)}
            className="hidden md:flex absolute top-4 left-4 z-10 items-center justify-center rounded-lg p-2 bg-secondary/80 hover:bg-secondary border border-border transition-colors"
            title="Expand sidebar"
          >
            <PanelLeftOpen className="h-5 w-5" />
          </button>
        )}
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
      {chatId && <OrderPanel chatId={chatId} />}
    </div>
  )
}
