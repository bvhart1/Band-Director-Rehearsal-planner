import { supabase, BACKEND_URL } from './supabaseClient'

export async function triggerAnalysis(
  rehearsalId: string,
  options?: { sourceUrl?: string; referenceSourceUrl?: string }
): Promise<{ ok: boolean }> {
  if (!BACKEND_URL) return { ok: false }
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) return { ok: false }
  const hasBody = !!(options?.sourceUrl || options?.referenceSourceUrl)
  try {
    const response = await fetch(`${BACKEND_URL}/analyze/${rehearsalId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      },
      body: hasBody
        ? JSON.stringify({
            source_url: options?.sourceUrl,
            reference_source_url: options?.referenceSourceUrl,
          })
        : undefined,
    })
    return { ok: response.ok }
  } catch {
    return { ok: false }
  }
}
