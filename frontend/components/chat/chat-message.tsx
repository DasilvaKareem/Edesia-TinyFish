'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Bot, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  const isUser = role === 'user'

  return (
    <div
      className={cn(
        'flex w-full py-3 px-4',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      <div
        className={cn(
          'flex flex-col max-w-[90%] md:max-w-[80%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        <div className="flex items-center gap-2 mb-1">
          <div
            className={cn(
              'flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full',
              isUser ? 'bg-primary order-2' : 'bg-primary order-1'
            )}
          >
            {isUser ? (
              <User className="h-3 w-3 text-primary-foreground" />
            ) : (
              <Bot className="h-3 w-3 text-white" />
            )}
          </div>
          <span className={cn(
            'text-xs font-semibold text-foreground',
            isUser ? 'order-1' : 'order-2'
          )}>
            {isUser ? 'You' : 'Edesia'}
          </span>
        </div>
        <div
          className={cn(
            'rounded-2xl px-4 py-2 text-[20px] leading-relaxed text-foreground overflow-hidden break-words min-w-0',
            isUser
              ? 'bg-primary text-primary-foreground rounded-tr-sm'
              : 'bg-secondary/50 rounded-tl-sm'
          )}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => (
                <ul className="mb-2 list-disc pl-4">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="mb-2 list-decimal pl-4">{children}</ol>
              ),
              li: ({ children }) => <li className="mb-1">{children}</li>,
              table: ({ children }) => (
                <div className="overflow-x-auto mb-2">
                  <table className="min-w-full border-collapse text-sm">{children}</table>
                </div>
              ),
              thead: ({ children }) => (
                <thead className="bg-muted/50">{children}</thead>
              ),
              tbody: ({ children }) => <tbody>{children}</tbody>,
              tr: ({ children }) => (
                <tr className="border-b border-border">{children}</tr>
              ),
              th: ({ children }) => (
                <th className="px-3 py-2 text-left font-semibold">{children}</th>
              ),
              td: ({ children }) => (
                <td className="px-3 py-2">{children}</td>
              ),
              strong: ({ children }) => (
                <strong className="font-semibold">{children}</strong>
              ),
              code: ({ className, children }) => {
                const isInline = !className
                return isInline ? (
                  <code className="rounded bg-muted px-1 py-0.5 text-sm">
                    {children}
                  </code>
                ) : (
                  <code className="block rounded-lg bg-muted p-3 text-sm overflow-x-auto">
                    {children}
                  </code>
                )
              },
              pre: ({ children }) => (
                <pre className="mb-2 rounded-lg bg-muted p-3 overflow-x-auto">
                  {children}
                </pre>
              ),
              img: ({ src, alt }) => (
                <img
                  src={src}
                  alt={alt || 'Image'}
                  className="rounded-lg max-w-full h-auto my-2 shadow-md"
                  style={{ maxHeight: '300px', objectFit: 'cover' }}
                  loading="lazy"
                />
              ),
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    'inline-flex items-center gap-1 underline underline-offset-2 hover:opacity-80 transition-opacity',
                    isUser ? 'text-primary-foreground font-medium' : 'text-primary'
                  )}
                >
                  {children}
                  <ExternalLink className="h-3 w-3 flex-shrink-0" />
                </a>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
