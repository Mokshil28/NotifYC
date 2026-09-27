import { getAuthToken } from 'deepspace'

type ActionPayload = { success: true; data: unknown } | { success: false; error: string }

export async function callAppAction(name: string, params: Record<string, unknown> = {}): Promise<ActionPayload> {
  const token = await getAuthToken()
  if (!token) return { success: false, error: 'Sign in again to continue.' }

  const res = await fetch(`/api/actions/${name}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  })
  const body = (await res.json()) as { success?: boolean; error?: string; data?: unknown }
  if (!res.ok || body.success === false) {
    return { success: false, error: body.error ?? `Request failed (${res.status})` }
  }
  return { success: true, data: body.data }
}
