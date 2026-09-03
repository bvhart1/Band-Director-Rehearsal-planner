import { supabase, BACKEND_URL } from './supabaseClient'

export async function triggerAnalysis(
  rehearsalId: string,
  options?: { sourceUrl?: string }
): Promise<{ ok: boolean }> {
  if (!BACKEND_URL) return { ok: false }
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) return { ok: false }
  try {
    const response = await fetch(`${BACKEND_URL}/analyze/${rehearsalId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options?.sourceUrl ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options?.sourceUrl ? JSON.stringify({ source_url: options.sourceUrl }) : undefined,
    })
    return { ok: response.ok }
  } catch {
    return { ok: false }
  }
}
