'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ChevronRight,
  ChevronLeft,
  Phone,
  Mail,
  MessageSquare,
  Package,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Search,
  ExternalLink,
  MapPin,
  Calendar,
  Users,
  Receipt,
  DollarSign,
  Truck,
} from 'lucide-react'
import {
  Order,
  CallLog,
  EmailLog,
  TextLog,
  PoemStage,
  subscribeToOrders,
  subscribeToCallLogs,
  subscribeToEmailLogs,
  subscribeToTextLogs,
} from '@/lib/order-store'
import { cn } from '@/lib/utils'
import { CallLogItem } from './call-log-item'

interface OrderPanelProps {
  chatId: string
}

const POEM_STAGES: { key: PoemStage; label: string; icon: React.ReactNode }[] = [
  { key: 'plan', label: 'Plan', icon: <MapPin className="h-3 w-3" /> },
  { key: 'order', label: 'Order', icon: <Receipt className="h-3 w-3" /> },
  { key: 'execute', label: 'Execute', icon: <Phone className="h-3 w-3" /> },
  { key: 'monitor', label: 'Monitor', icon: <Truck className="h-3 w-3" /> },
]

export function OrderPanel({ chatId }: OrderPanelProps) {
  const [isOpen, setIsOpen] = useState(true)
  const [orders, setOrders] = useState<Order[]>([])
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [callLogs, setCallLogs] = useState<CallLog[]>([])
  const [emailLogs, setEmailLogs] = useState<EmailLog[]>([])
  const [textLogs, setTextLogs] = useState<TextLog[]>([])
  const [panelWidth, setPanelWidth] = useState(384)
  const isResizing = useRef(false)

  const handleMouseDown = useCallback(() => {
    isResizing.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing.current) return
      const newWidth = window.innerWidth - e.clientX
      setPanelWidth(Math.min(Math.max(newWidth, 280), 700))
    }

    const handleMouseUp = () => {
      isResizing.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [])

  useEffect(() => {
    if (!chatId) return
    const unsubscribe = subscribeToOrders(chatId, setOrders)
    return () => unsubscribe()
  }, [chatId])

  useEffect(() => {
    if (!chatId || !selectedOrderId) {
      setCallLogs([])
      setEmailLogs([])
      setTextLogs([])
      return
    }
    const unsubCalls = subscribeToCallLogs(chatId, selectedOrderId, setCallLogs)
    const unsubEmails = subscribeToEmailLogs(chatId, selectedOrderId, setEmailLogs)
    const unsubTexts = subscribeToTextLogs(chatId, selectedOrderId, setTextLogs)
    return () => {
      unsubCalls()
      unsubEmails()
      unsubTexts()
    }
  }, [chatId, selectedOrderId])

  useEffect(() => {
    if (orders.length > 0 && !selectedOrderId) {
      setSelectedOrderId(orders[0].id)
    }
  }, [orders, selectedOrderId])

  const selectedOrder = orders.find(o => o.id === selectedOrderId)

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'cancelled':
      case 'call_failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      case 'in_progress':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
      case 'researching':
        return <Search className="h-4 w-4 text-purple-500 animate-pulse" />
      case 'quoted':
        return <Clock className="h-4 w-4 text-orange-500" />
      case 'confirmed':
      case 'call_completed':
        return <CheckCircle className="h-4 w-4 text-blue-500" />
      default:
        return <Clock className="h-4 w-4 text-yellow-500" />
    }
  }

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      completed: 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400',
      cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400',
      call_failed: 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400',
      in_progress: 'bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
      confirmed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
      call_completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
      pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400',
      researching: 'bg-purple-100 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400',
      quoted: 'bg-orange-100 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400',
    }
    return styles[status] || 'bg-gray-100 text-gray-700 dark:bg-gray-900/20 dark:text-gray-400'
  }

  const getOrderTypeIcon = (type: string) => {
    switch (type) {
      case 'reservation': return '🍽️'
      case 'catering': return '🍱'
      case 'doordash': return '🚗'
      case 'poll': return '🗳️'
      case 'phone_call': return '📞'
      default: return '📦'
    }
  }

  const getPoemStageIndex = (stage?: PoemStage) => {
    if (!stage) return -1
    return POEM_STAGES.findIndex(s => s.key === stage)
  }

  const formatTime = (timestamp: any) => {
    if (!timestamp) return ''
    const date = timestamp.toDate ? timestamp.toDate() : new Date(timestamp)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed right-0 top-1/2 -translate-y-1/2 bg-secondary/80 hover:bg-secondary p-2 rounded-l-lg border border-r-0 border-border transition-colors hidden md:block"
      >
        <ChevronLeft className="h-5 w-5" />
      </button>
    )
  }

  const currentStageIdx = getPoemStageIndex(selectedOrder?.poemStage)

  return (
    <div className="hidden md:flex border-l border-border bg-background flex-col h-dvh relative" style={{ width: panelWidth }}>
      {/* Drag handle */}
      <div
        onMouseDown={handleMouseDown}
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors z-10"
      />
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Package className="h-5 w-5" />
          Orders
        </h2>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1 hover:bg-secondary rounded transition-colors"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {orders.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-base text-muted-foreground text-center">
            No orders yet. Start a conversation to create reservations or orders.
          </p>
        </div>
      ) : (
        <>
          {/* Order Tabs */}
          <div className="flex gap-1 p-2 border-b border-border overflow-x-auto">
            {orders.map((order) => (
              <button
                key={order.id}
                onClick={() => setSelectedOrderId(order.id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm whitespace-nowrap transition-colors',
                  selectedOrderId === order.id
                    ? 'bg-primary/10 text-primary'
                    : 'hover:bg-secondary'
                )}
              >
                <span>{getOrderTypeIcon(order.type)}</span>
                <span className="truncate max-w-[100px]">{order.vendor}</span>
                {getStatusIcon(order.status)}
              </button>
            ))}
          </div>

          {/* Selected Order Details */}
          {selectedOrder && (
            <div className="flex-1 overflow-y-auto min-h-0">
              {/* POEM Stage Progress */}
              {selectedOrder.poemStage && (
                <div className="px-4 pt-3 pb-2">
                  <div className="flex items-center gap-1">
                    {POEM_STAGES.map((stage, i) => {
                      const isActive = i === currentStageIdx
                      const isCompleted = i < currentStageIdx
                      return (
                        <div key={stage.key} className="flex items-center flex-1">
                          <div className="flex flex-col items-center flex-1">
                            <div className={cn(
                              'w-full h-1.5 rounded-full transition-colors',
                              isCompleted && 'bg-primary',
                              isActive && 'bg-primary',
                              !isCompleted && !isActive && 'bg-secondary'
                            )} />
                            <span className={cn(
                              'text-xs mt-1 font-medium',
                              isActive && 'text-primary',
                              isCompleted && 'text-primary',
                              !isCompleted && !isActive && 'text-muted-foreground'
                            )}>
                              {stage.label}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Vendor & Status Header */}
              <div className="px-4 py-3 border-b border-border">
                <div className="flex items-center justify-between">
                  <span className="text-xl font-medium">{selectedOrder.vendor}</span>
                  <span className={cn(
                    'px-2 py-1 rounded text-sm font-medium',
                    getStatusBadge(selectedOrder.status)
                  )}>
                    {selectedOrder.status.replace('_', ' ')}
                  </span>
                </div>
              </div>

              {/* ===== PLAN PHASE ===== */}
              <div className={cn(
                'border-b border-border',
                currentStageIdx === 0 ? 'bg-primary/[0.03]' : ''
              )}>
                <div className="px-4 py-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-3">
                    <MapPin className="h-3.5 w-3.5" />
                    Plan Details
                    {currentStageIdx > 0 && <CheckCircle className="h-3 w-3 text-primary ml-auto" />}
                  </h3>
                  <div className="space-y-3">
                    {/* Where */}
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary flex-shrink-0">
                        <MapPin className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div className="min-w-0">
                        <span className="block text-xs uppercase tracking-wide text-muted-foreground">Where</span>
                        <span className="text-base font-medium">{selectedOrder.vendor || '—'}</span>
                        {selectedOrder.vendorAddress && (
                          <span className="block text-sm text-muted-foreground">{selectedOrder.vendorAddress}</span>
                        )}
                        {selectedOrder.deliveryAddress && (
                          <span className="block text-sm text-muted-foreground mt-0.5">Deliver to: {selectedOrder.deliveryAddress}</span>
                        )}
                      </div>
                    </div>

                    {/* When */}
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary flex-shrink-0">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div className="min-w-0">
                        <span className="block text-xs uppercase tracking-wide text-muted-foreground">When</span>
                        <span className="text-base font-medium">
                          {selectedOrder.eventDate || '—'}
                          {selectedOrder.eventTime && ` at ${selectedOrder.eventTime}`}
                        </span>
                      </div>
                    </div>

                    {/* How Many */}
                    <div className="flex items-start gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary flex-shrink-0">
                        <Users className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div className="min-w-0">
                        <span className="block text-xs uppercase tracking-wide text-muted-foreground">How Many</span>
                        <span className="text-base font-medium">
                          {selectedOrder.guestCount > 0 ? `${selectedOrder.guestCount} people` : '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* ===== ORDER PHASE (Quote) ===== */}
              <div className={cn(
                'border-b border-border',
                currentStageIdx === 1 ? 'bg-primary/[0.03]' : ''
              )}>
                <div className="px-4 py-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-3">
                    <Receipt className="h-3.5 w-3.5" />
                    Quote
                    {currentStageIdx > 1 && <CheckCircle className="h-3 w-3 text-primary ml-auto" />}
                  </h3>

                  {selectedOrder.items && selectedOrder.items.length > 0 ? (
                    <div className="space-y-2">
                      {/* Itemized list */}
                      <div className="space-y-1.5">
                        {selectedOrder.items.map((item, i) => (
                          <div key={i} className="flex items-center justify-between text-base">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-muted-foreground text-sm w-6 text-right flex-shrink-0">{item.quantity}x</span>
                              <span className="truncate">{item.name}</span>
                            </div>
                            <span className="text-muted-foreground flex-shrink-0 ml-2">
                              ${(item.price * item.quantity).toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>

                      {/* Totals */}
                      <div className="border-t border-border pt-2 mt-2 space-y-1">
                        {selectedOrder.subtotal != null && (
                          <div className="flex justify-between text-sm text-muted-foreground">
                            <span>Subtotal</span>
                            <span>${selectedOrder.subtotal.toFixed(2)}</span>
                          </div>
                        )}
                        {selectedOrder.tax != null && selectedOrder.tax > 0 && (
                          <div className="flex justify-between text-sm text-muted-foreground">
                            <span>Tax</span>
                            <span>${selectedOrder.tax.toFixed(2)}</span>
                          </div>
                        )}
                        {selectedOrder.deliveryFee != null && selectedOrder.deliveryFee > 0 && (
                          <div className="flex justify-between text-sm text-muted-foreground">
                            <span>Delivery</span>
                            <span>${selectedOrder.deliveryFee.toFixed(2)}</span>
                          </div>
                        )}
                        {selectedOrder.serviceFee != null && selectedOrder.serviceFee > 0 && (
                          <div className="flex justify-between text-sm text-muted-foreground">
                            <span>Service fee</span>
                            <span>${selectedOrder.serviceFee.toFixed(2)}</span>
                          </div>
                        )}
                        <div className="flex justify-between text-base font-semibold pt-1 border-t border-border">
                          <span>Total</span>
                          <span>
                            ${(selectedOrder.estimatedCost ?? selectedOrder.actualCost ?? 0).toFixed(2)}
                          </span>
                        </div>
                      </div>

                      {/* Payment status */}
                      {selectedOrder.paymentStatus && (
                        <div className="flex items-center gap-2 pt-1">
                          <DollarSign className="h-3 w-3 text-muted-foreground" />
                          <span className={cn(
                            'px-2 py-0.5 rounded text-xs font-medium',
                            selectedOrder.paymentStatus === 'paid' && 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400',
                            selectedOrder.paymentStatus === 'failed' && 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400',
                            selectedOrder.paymentStatus === 'refunded' && 'bg-gray-100 text-gray-700 dark:bg-gray-900/20 dark:text-gray-400',
                            selectedOrder.paymentStatus === 'pending' && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400',
                          )}>
                            {selectedOrder.paymentStatus}
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-base text-muted-foreground">
                      {selectedOrder.estimatedCost ? (
                        <div className="flex justify-between font-medium">
                          <span>Estimated total</span>
                          <span>${selectedOrder.estimatedCost.toFixed(2)}</span>
                        </div>
                      ) : (
                        <p className="text-center py-2">No quote yet</p>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* ===== EXECUTE PHASE (Comms) ===== */}
              <div className={cn(
                'border-b border-border',
                currentStageIdx === 2 ? 'bg-primary/[0.03]' : ''
              )}>
                <div className="px-4 py-3">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-3">
                    <Phone className="h-3.5 w-3.5" />
                    Activity
                    {currentStageIdx > 2 && <CheckCircle className="h-3 w-3 text-primary ml-auto" />}
                  </h3>

                  {callLogs.length === 0 && emailLogs.length === 0 && textLogs.length === 0 ? (
                    <p className="text-base text-muted-foreground text-center py-2">
                      No activity yet
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {/* Calls */}
                      {callLogs.map((call) => (
                        <CallLogItem key={call.id} call={call} />
                      ))}

                      {/* Emails */}
                      {emailLogs.map((email) => (
                        <div key={email.id} className="border border-border rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <Mail className="h-4 w-4 text-blue-500" />
                            <span className="text-sm font-medium truncate">{email.subject}</span>
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>{email.direction === 'outbound' ? `To: ${email.to}` : `From: ${email.from}`}</span>
                            <span className="text-muted-foreground/50">·</span>
                            <span className={cn(
                              'px-1.5 py-0.5 rounded text-[10px] font-medium',
                              email.status === 'delivered' || email.status === 'opened' || email.status === 'replied'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                                : email.status === 'bounced'
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                                  : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400'
                            )}>
                              {email.status}
                            </span>
                          </div>
                        </div>
                      ))}

                      {/* Texts */}
                      {textLogs.map((text) => (
                        <div key={text.id} className="border border-border rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <MessageSquare className="h-4 w-4 text-primary" />
                            <span className="text-sm truncate">{text.message}</span>
                          </div>
                          <div className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>{text.phoneNumber}</span>
                            <span className="text-muted-foreground/50">·</span>
                            <span className={cn(
                              'px-1.5 py-0.5 rounded text-[10px] font-medium',
                              text.status === 'delivered' || text.status === 'read' || text.status === 'replied'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                                : text.status === 'failed'
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                                  : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400'
                            )}>
                              {text.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* ===== MONITOR PHASE ===== */}
              {(currentStageIdx >= 3 || selectedOrder.trackingUrl) && (
                <div className={cn(
                  'border-b border-border',
                  currentStageIdx === 3 ? 'bg-primary/[0.03]' : ''
                )}>
                  <div className="px-4 py-3">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-3">
                      <Truck className="h-3.5 w-3.5" />
                      Tracking
                    </h3>
                    {selectedOrder.trackingUrl ? (
                      <a
                        href={selectedOrder.trackingUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-sm text-primary hover:underline"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Track delivery
                      </a>
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-2">
                        Awaiting tracking info
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Last Call Summary */}
              {selectedOrder.lastCallSummary && (
                <div className="border-b border-border">
                  <div className="px-4 py-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2 mb-2">
                      <Phone className="h-3.5 w-3.5" />
                      Last Call
                      {selectedOrder.lastCallDuration != null && (
                        <span className="ml-auto font-normal normal-case">
                          {Math.round(selectedOrder.lastCallDuration)}s
                        </span>
                      )}
                    </h3>
                    <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                      {selectedOrder.lastCallSummary}
                    </p>
                    {selectedOrder.pickupTime && (
                      <div className="flex items-center gap-2 mt-2 text-sm">
                        <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                        <span>Pickup: {selectedOrder.pickupTime}</span>
                      </div>
                    )}
                    {selectedOrder.confirmationNumber && (
                      <div className="flex items-center gap-2 mt-1 text-sm">
                        <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                        <span>Confirmation: {selectedOrder.confirmationNumber}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Notes */}
              {selectedOrder.notes && (
                <div className="px-4 py-3">
                  <p className="text-sm text-muted-foreground">{selectedOrder.notes}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
