'use client'

import { useState } from 'react'
import { Check, X, Loader2 } from 'lucide-react'

interface PendingActionProps {
  action: {
    action_id: string
    action_type: string
    description: string
    payload: any
  }
  onApprove: (actionId: string) => Promise<void>
  onReject: (actionId: string) => Promise<void>
}

export function PendingAction({ action, onApprove, onReject }: PendingActionProps) {
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null)

  const handleApprove = async () => {
    setLoading('approve')
    try {
      await onApprove(action.action_id)
    } finally {
      setLoading(null)
    }
  }

  const handleReject = async () => {
    setLoading('reject')
    try {
      await onReject(action.action_id)
    } finally {
      setLoading(null)
    }
  }

  const getActionIcon = () => {
    switch (action.action_type) {
      case 'reservation':
        return '🍽️'
      case 'catering_order':
        return '🥗'
      case 'poll_send':
        return '📊'
      case 'call_restaurant':
      case 'call_caterer':
      case 'call_chef':
        return '📞'
      case 'food_order':
      case 'doordash_order':
        return '🚗'
      default:
        return '📋'
    }
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-900/20 p-4 my-4">
      <div className="flex items-start gap-3">
        <span className="text-2xl">{getActionIcon()}</span>
        <div className="flex-1">
          <h4 className="font-medium text-amber-800 dark:text-amber-200">
            Action Requires Approval
          </h4>
          <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
            {action.description}
          </p>

          {action.action_type === 'catering_order' && action.payload?.pricing && (
            <div className="mt-3 rounded-lg bg-white dark:bg-gray-900 p-3 text-sm">
              <div className="flex justify-between">
                <span>Subtotal:</span>
                <span>${action.payload.pricing.subtotal?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Tax:</span>
                <span>${action.payload.pricing.tax?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Delivery:</span>
                <span>${action.payload.pricing.delivery_fee?.toFixed(2)}</span>
              </div>
              <div className="flex justify-between font-medium border-t border-border mt-2 pt-2">
                <span>Total:</span>
                <span>${action.payload.pricing.total?.toFixed(2)}</span>
              </div>
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={handleApprove}
              disabled={loading !== null}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {loading === 'approve' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Approve
            </button>
            <button
              onClick={handleReject}
              disabled={loading !== null}
              className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              {loading === 'reject' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <X className="h-4 w-4" />
              )}
              Reject
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
