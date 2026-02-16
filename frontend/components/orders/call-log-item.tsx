'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, Phone, PhoneIncoming, PhoneOutgoing, PhoneMissed, Clock, Play, FileText } from 'lucide-react'
import { CallLog } from '@/lib/order-store'
import { cn } from '@/lib/utils'

interface CallLogItemProps {
  call: CallLog
}

export function CallLogItem({ call }: CallLogItemProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-500'
      case 'failed':
      case 'no_answer':
        return 'text-red-500'
      case 'in_progress':
        return 'text-blue-500'
      default:
        return 'text-yellow-500'
    }
  }

  const getStatusIcon = () => {
    if (call.status === 'failed' || call.status === 'no_answer') {
      return <PhoneMissed className={cn('h-4 w-4', getStatusColor(call.status))} />
    }
    if (call.direction === 'inbound') {
      return <PhoneIncoming className={cn('h-4 w-4', getStatusColor(call.status))} />
    }
    return <PhoneOutgoing className={cn('h-4 w-4', getStatusColor(call.status))} />
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '--:--'
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatTime = (timestamp: any) => {
    if (!timestamp) return ''
    const date = timestamp.toDate ? timestamp.toDate() : new Date(timestamp)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    })
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      {/* Call Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-secondary/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          {getStatusIcon()}
          <div className="text-left">
            <div className="text-sm font-medium">{call.phoneNumber}</div>
            <div className="text-xs text-muted-foreground flex items-center gap-2">
              <Clock className="h-3 w-3" />
              {formatTime(call.createdAt)}
              {call.duration && (
                <>
                  <span className="text-muted-foreground/50">•</span>
                  <span>{formatDuration(call.duration)}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn(
            'text-xs px-2 py-0.5 rounded',
            call.status === 'completed' && 'bg-green-100 text-green-700 dark:bg-green-900/20 dark:text-green-400',
            call.status === 'failed' && 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400',
            call.status === 'no_answer' && 'bg-orange-100 text-orange-700 dark:bg-orange-900/20 dark:text-orange-400',
            call.status === 'in_progress' && 'bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400',
            (call.status === 'initiated' || call.status === 'ringing') && 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400'
          )}>
            {call.status.replace('_', ' ')}
          </span>
          {isExpanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-border">
          {/* Summary */}
          {call.summary && (
            <div className="p-3 bg-secondary/30">
              <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mb-1">
                <FileText className="h-3 w-3" />
                Summary
              </div>
              <p className="text-sm">{call.summary}</p>
            </div>
          )}

          {/* Transcript */}
          {call.transcript && (
            <div className="p-3">
              <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mb-2">
                <FileText className="h-3 w-3" />
                Transcript
              </div>
              <div className="text-sm bg-secondary/50 rounded-lg p-3 max-h-60 overflow-y-auto">
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                  {call.transcript}
                </pre>
              </div>
            </div>
          )}

          {/* Recording */}
          {call.recordingUrl && (
            <div className="p-3 border-t border-border">
              <button className="flex items-center gap-2 text-sm text-primary hover:underline">
                <Play className="h-4 w-4" />
                Play Recording
              </button>
            </div>
          )}

          {/* No content message */}
          {!call.summary && !call.transcript && !call.recordingUrl && (
            <div className="p-3 text-sm text-muted-foreground text-center">
              {call.status === 'completed'
                ? 'Transcript processing...'
                : 'Call not completed'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
