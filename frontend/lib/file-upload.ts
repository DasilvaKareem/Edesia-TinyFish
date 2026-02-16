import { ref, uploadBytes, getDownloadURL } from 'firebase/storage'
import { storage } from './firebase'

export interface UploadedFile {
  url: string
  name: string
  type: string
  size: number
}

// Allowed file types
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const ALLOWED_DOC_TYPES = ['application/pdf']
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB (Groq limit)

export function isImageFile(file: File): boolean {
  return ALLOWED_IMAGE_TYPES.includes(file.type)
}

export function isPdfFile(file: File): boolean {
  return ALLOWED_DOC_TYPES.includes(file.type)
}

export function isAllowedFile(file: File): boolean {
  return isImageFile(file) || isPdfFile(file)
}

export function validateFile(file: File): { valid: boolean; error?: string } {
  if (!isAllowedFile(file)) {
    return {
      valid: false,
      error: 'File type not supported. Please upload images (JPEG, PNG, GIF, WebP) or PDFs.',
    }
  }

  if (file.size > MAX_FILE_SIZE) {
    return {
      valid: false,
      error: `File too large. Maximum size is ${MAX_FILE_SIZE / 1024 / 1024}MB.`,
    }
  }

  return { valid: true }
}

export async function uploadFile(
  file: File,
  userId: string,
  chatId?: string
): Promise<UploadedFile> {
  // Validate file
  const validation = validateFile(file)
  if (!validation.valid) {
    throw new Error(validation.error)
  }

  // Create a unique filename
  const timestamp = Date.now()
  const sanitizedName = file.name.replace(/[^a-zA-Z0-9.-]/g, '_')
  const path = chatId
    ? `uploads/${userId}/${chatId}/${timestamp}_${sanitizedName}`
    : `uploads/${userId}/${timestamp}_${sanitizedName}`

  // Upload to Firebase Storage
  const storageRef = ref(storage, path)
  const snapshot = await uploadBytes(storageRef, file, {
    contentType: file.type,
  })

  // Get download URL
  const url = await getDownloadURL(snapshot.ref)

  return {
    url,
    name: file.name,
    type: file.type,
    size: file.size,
  }
}

export async function uploadMultipleFiles(
  files: File[],
  userId: string,
  chatId?: string
): Promise<UploadedFile[]> {
  const uploadPromises = files.map((file) => uploadFile(file, userId, chatId))
  return Promise.all(uploadPromises)
}

// Convert file to base64 (for direct API calls without storage)
export async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // Remove the data URL prefix (e.g., "data:image/jpeg;base64,")
      const base64 = result.split(',')[1]
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// Get file preview URL (for local preview before upload)
export function getFilePreviewUrl(file: File): string {
  return URL.createObjectURL(file)
}

// Revoke preview URL to free memory
export function revokeFilePreviewUrl(url: string): void {
  URL.revokeObjectURL(url)
}
