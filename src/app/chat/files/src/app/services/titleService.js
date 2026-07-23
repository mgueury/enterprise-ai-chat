const API_URL = '/api/generate-title';

/**
 * A useful title immediately, while the model generates a better one.
 * Keeping this local fallback means a failed or slow title request never leaves
 * a newly created conversation labelled "New conversation" in the history.
 */
export function createFallbackTitle(userMessage) {
  const text = String(userMessage || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return 'New conversation';

  const words = text.split(' ').slice(0, 5);
  const title = words.join(' ').replace(/[.!?:,;]+$/, '');
  return title.length > 60 ? `${title.slice(0, 57).trimEnd()}...` : title;
}

export async function generateTitle(userMessage, assistantResponse) {
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userMessage, assistantResponse })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('Title API error:', response.status, errorData);
      return createFallbackTitle(userMessage);
    }

    const data = await response.json();
    console.log('Generated title:', data.title);
    return data.title || createFallbackTitle(userMessage);
  } catch (error) {
    console.error('Title generation failed:', error);
    return createFallbackTitle(userMessage);
  }
}
