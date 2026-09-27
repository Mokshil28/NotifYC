/**
 * Presentation shell over the working DeepSpace app.
 * Queries, mutations, and responder steps stay in that app.
 * This file only mounts the existing auth and record-room providers.
 */

import { useState, type ReactNode } from 'react'
import { AuthOverlay, DeepSpaceAuthProvider, RecordProvider, RecordScope, useAuthStatus } from 'deepspace'
import { schemas } from '@notifyc/schemas'

export const DEEPSPACE_APP_ID = 'app_01M3FMQNVAKJ43MEPJXK4T404F'
export const SCOPE_ID = `app:${DEEPSPACE_APP_ID}`

export function LiveShell({ children }: { children: ReactNode }) {
  return (
    <DeepSpaceAuthProvider>
      <AuthGate>{children}</AuthGate>
    </DeepSpaceAuthProvider>
  )
}

function AuthGate({ children }: { children: ReactNode }) {
  const { isLoaded } = useAuthStatus()
  const [writeError, setWriteError] = useState<string | null>(null)
  if (!isLoaded) return <div aria-busy="true" className="app" />
  return (
    <RecordProvider
      allowAnonymous
      onWriteError={(error) => setWriteError(error.detail || error.title)}
    >
      <RecordScope roomId={SCOPE_ID} schemas={schemas}>
        {writeError && <p className="live-write-error">{writeError}</p>}
        {children}
      </RecordScope>
    </RecordProvider>
  )
}

export function SignInButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="button button-compact button-light" onClick={() => setOpen(true)} type="button">
        Sign in
      </button>
      {open && <AuthOverlay onClose={() => setOpen(false)} />}
    </>
  )
}
