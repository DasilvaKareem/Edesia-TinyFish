'use client'

import { useState, useRef, useEffect } from 'react'
import { Plus, Mic, MicOff, AudioLines, Send, Loader2, X, FileText, Square } from 'lucide-react'
import { cn } from '@/lib/utils'
import { isImageFile, isPdfFile, validateFile, getFilePreviewUrl, revokeFilePreviewUrl } from '@/lib/file-upload'
import { useVoiceRecorder, formatDuration } from '@/hooks/use-voice-recorder'
import { track } from '@vercel/analytics'

export interface Attachment {
  file: File
  previewUrl?: string
  type: 'image' | 'pdf'
}

interface ChatInputProps {
  onSend: (message: string, attachments?: Attachment[]) => void
  disabled?: boolean
  loading?: boolean
  centered?: boolean
}

export function ChatInput({ onSend, disabled, loading, centered }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [micError, setMicError] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Voice recording hook
  const {
    state: recordingState,
    duration,
    isRecording,
    isProcessing,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
  } = useVoiceRecorder({
    onTranscription: (text) => {
      // Append transcribed text to message
      setMessage((prev) => (prev ? `${prev} ${text}` : text))
      // Focus the textarea
      textareaRef.current?.focus()
    },
    onError: (error) => {
      setMicError(error)
      setTimeout(() => setMicError(null), 3000)
    },
  })

  useEffect(() => {
    if (textareaRef.current) {
      const maxH = window.innerWidth < 768 ? 120 : 200
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, maxH)}px`
    }
  }, [message])

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      attachments.forEach((att) => {
        if (att.previewUrl) {
          revokeFilePreviewUrl(att.previewUrl)
        }
      })
    }
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if ((message.trim() || attachments.length > 0) && !disabled && !loading && !isRecording && !isProcessing) {
      onSend(message.trim(), attachments.length > 0 ? attachments : undefined)
      setMessage('')
      // Cleanup preview URLs
      attachments.forEach((att) => {
        if (att.previewUrl) {
          revokeFilePreviewUrl(att.previewUrl)
        }
      })
      setAttachments([])
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return

    const newAttachments: Attachment[] = []

    for (let i = 0; i < files.length && attachments.length + newAttachments.length < 5; i++) {
      const file = files[i]
      const validation = validateFile(file)

      if (validation.valid) {
        const attachment: Attachment = {
          file,
          type: isImageFile(file) ? 'image' : 'pdf',
        }

        // Create preview for images
        if (isImageFile(file)) {
          attachment.previewUrl = getFilePreviewUrl(file)
        }

        newAttachments.push(attachment)
      } else {
        console.error(validation.error)
      }
    }

    if (newAttachments.length > 0) {
      track('file_attached', { count: newAttachments.length, types: newAttachments.map(a => a.type).join(',') })
    }
    setAttachments((prev) => [...prev, ...newAttachments])

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const removeAttachment = (index: number) => {
    setAttachments((prev) => {
      const att = prev[index]
      if (att.previewUrl) {
        revokeFilePreviewUrl(att.previewUrl)
      }
      return prev.filter((_, i) => i !== index)
    })
  }

  const openFilePicker = () => {
    fileInputRef.current?.click()
  }

  const handleMicClick = async () => {
    if (isRecording) {
      track('voice_recording_stopped')
      await stopAndTranscribe()
    } else if (!isProcessing) {
      track('voice_recording_started')
      await startRecording()
    }
  }

  const hasContent = message.trim() || attachments.length > 0

  return (
    <form onSubmit={handleSubmit} className={cn("bg-background", centered ? "p-0" : "p-4")}>
      <div className={cn("mx-auto", centered ? "max-w-5xl" : "max-w-3xl")}>
        {/* Mic error message */}
        {micError && (
          <div className="mb-2 text-sm text-red-500 text-center animate-fade-in">
            {micError}
          </div>
        )}

        {/* Recording indicator */}
        {isRecording && (
          <div className="flex items-center justify-center gap-3 mb-3 py-2 px-4 rounded-full bg-red-500/10 border border-red-500/20 animate-pulse">
            <div className="h-3 w-3 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-medium text-red-500">
              Recording {formatDuration(duration)}
            </span>
            <button
              type="button"
              onClick={cancelRecording}
              className="ml-2 p-1 rounded-full hover:bg-red-500/20 transition-colors"
              title="Cancel recording"
            >
              <X className="h-4 w-4 text-red-500" />
            </button>
          </div>
        )}

        {/* Processing indicator */}
        {isProcessing && (
          <div className="flex items-center justify-center gap-2 mb-3 py-2 px-4 rounded-full bg-primary/10 border border-primary/20">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-sm font-medium text-primary">Transcribing...</span>
          </div>
        )}

        {/* Attachment previews */}
        {attachments.length > 0 && (
          <div className="flex gap-2 mb-3 flex-wrap">
            {attachments.map((att, index) => (
              <div
                key={index}
                className="relative group rounded-lg overflow-hidden border border-border bg-secondary/30"
              >
                {att.type === 'image' && att.previewUrl ? (
                  <img
                    src={att.previewUrl}
                    alt={att.file.name}
                    className="h-20 w-20 object-cover"
                  />
                ) : (
                  <div className="h-20 w-20 flex flex-col items-center justify-center p-2">
                    <FileText className="h-8 w-8 text-muted-foreground mb-1" />
                    <span className="text-xs text-muted-foreground truncate w-full text-center">
                      {att.file.name.slice(0, 10)}...
                    </span>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(index)}
                  className="absolute top-1 right-1 h-5 w-5 rounded-full bg-background/80 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className={cn(
          "relative flex items-center gap-3 rounded-full border bg-secondary/50 px-4",
          centered
            ? "border-border/80 py-4 shadow-lg"
            : "border-border py-3",
          isRecording && "border-red-500/50 bg-red-500/5"
        )}>
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp,application/pdf"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* Plus button - opens file picker */}
          <button
            type="button"
            onClick={openFilePicker}
            disabled={attachments.length >= 5 || isRecording}
            className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-secondary transition-colors flex-shrink-0 disabled:opacity-50"
            title="Attach files (images, PDFs)"
          >
            <Plus className="h-5 w-5 text-muted-foreground" />
          </button>

          {/* Input field */}
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
            placeholder={
              isRecording
                ? "Listening..."
                : isProcessing
                ? "Transcribing..."
                : attachments.length > 0
                ? "Add a message..."
                : "Order lunch, book a reservation, find catering..."
            }
            disabled={disabled || loading || isRecording || isProcessing}
            rows={1}
            className="flex-1 min-w-0 resize-none bg-transparent text-base focus:outline-none disabled:opacity-50 placeholder:text-muted-foreground/70"
          />

          {/* Right side buttons */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Mic button */}
            <button
              type="button"
              onClick={handleMicClick}
              disabled={isProcessing || disabled || loading}
              className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full transition-colors",
                isRecording
                  ? "bg-red-500 text-white hover:bg-red-600"
                  : "hover:bg-secondary",
                isProcessing && "opacity-50 cursor-not-allowed"
              )}
              title={isRecording ? "Stop recording" : "Start voice input"}
            >
              {isRecording ? (
                <Square className="h-4 w-4 fill-current" />
              ) : (
                <Mic className={cn("h-5 w-5", isProcessing ? "text-primary" : "text-muted-foreground")} />
              )}
            </button>

            {/* Send/Audio button */}
            {hasContent && !isRecording ? (
              <button
                type="submit"
                disabled={!hasContent || disabled || loading || isProcessing}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <Send className="h-5 w-5" />
                )}
              </button>
            ) : !isRecording ? (
              <button
                type="button"
                onClick={handleMicClick}
                disabled={isProcessing || disabled || loading}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-foreground text-background transition-colors hover:bg-foreground/90 disabled:opacity-50"
                title="Start voice input"
              >
                <AudioLines className="h-5 w-5" />
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </form>
  )
}
