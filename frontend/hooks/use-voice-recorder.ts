'use client'

import { useState, useRef, useCallback } from 'react'

export type RecordingState = 'idle' | 'recording' | 'processing'

interface UseVoiceRecorderOptions {
  onTranscription?: (text: string) => void
  onError?: (error: string) => void
}

export function useVoiceRecorder(options: UseVoiceRecorderOptions = {}) {
  const [state, setState] = useState<RecordingState>('idle')
  const [duration, setDuration] = useState(0)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const startRecording = useCallback(async () => {
    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      })
      streamRef.current = stream

      // Create MediaRecorder with webm/opus format (good quality, small size)
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus',
      })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      mediaRecorder.start(100) // Collect data every 100ms
      setState('recording')
      setDuration(0)

      // Start duration timer
      timerRef.current = setInterval(() => {
        setDuration((d) => d + 1)
      }, 1000)
    } catch (error) {
      console.error('Error starting recording:', error)
      options.onError?.('Could not access microphone. Please allow microphone access.')
    }
  }, [options])

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      if (!mediaRecorderRef.current || state !== 'recording') {
        resolve(null)
        return
      }

      // Clear timer
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }

      const mediaRecorder = mediaRecorderRef.current

      mediaRecorder.onstop = () => {
        // Stop all tracks
        streamRef.current?.getTracks().forEach((track) => track.stop())
        streamRef.current = null

        // Create blob from chunks
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        chunksRef.current = []

        resolve(blob)
      }

      mediaRecorder.stop()
      setState('idle')
      setDuration(0)
    })
  }, [state])

  const cancelRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    if (mediaRecorderRef.current && state === 'recording') {
      mediaRecorderRef.current.stop()
    }

    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    chunksRef.current = []

    setState('idle')
    setDuration(0)
  }, [state])

  const transcribe = useCallback(
    async (audioBlob: Blob): Promise<string | null> => {
      setState('processing')

      try {
        const formData = new FormData()
        formData.append('file', audioBlob, 'recording.webm')

        const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        const response = await fetch(`${API_URL}/transcribe`, {
          method: 'POST',
          body: formData,
        })

        if (!response.ok) {
          throw new Error(`Transcription failed: ${response.status}`)
        }

        const data = await response.json()
        setState('idle')

        if (data.text) {
          options.onTranscription?.(data.text)
          return data.text
        }

        return null
      } catch (error) {
        console.error('Transcription error:', error)
        options.onError?.('Failed to transcribe audio. Please try again.')
        setState('idle')
        return null
      }
    },
    [options]
  )

  // Convenience method: stop and transcribe
  const stopAndTranscribe = useCallback(async (): Promise<string | null> => {
    const blob = await stopRecording()
    if (blob && blob.size > 0) {
      return transcribe(blob)
    }
    return null
  }, [stopRecording, transcribe])

  return {
    state,
    duration,
    isRecording: state === 'recording',
    isProcessing: state === 'processing',
    startRecording,
    stopRecording,
    cancelRecording,
    transcribe,
    stopAndTranscribe,
  }
}

// Format duration as MM:SS
export function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${secs.toString().padStart(2, '0')}`
}
