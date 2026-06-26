import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'RepoChat | Ask anything about any codebase',
  description: 'RAG-powered chat for your GitHub repositories.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}