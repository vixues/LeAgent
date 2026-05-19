import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';

const LS_KEY = 'leagent.chatDailyGreetings.v1';
const LS_PET_BUBBLES_KEY = 'leagent.chatDailyPetBubbles.v1';

interface StoredPayload {
  date: string;
  locale: string;
  greetings: string[];
}

interface StoredPetBubblesPayload {
  date: string;
  locale: string;
  lines: string[];
}

function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function readCache(locale: string): string[] | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as StoredPayload;
    if (o.locale !== locale) return null;
    if (o.date !== utcToday()) return null;
    if (!Array.isArray(o.greetings) || o.greetings.length === 0) return null;
    return o.greetings;
  } catch {
    return null;
  }
}

function writeCache(locale: string, date: string, greetings: string[]) {
  try {
    const payload: StoredPayload = { locale, date, greetings };
    localStorage.setItem(LS_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

function writePetBubblesCache(locale: string, date: string, lines: string[]) {
  try {
    const payload: StoredPetBubblesPayload = { locale, date, lines };
    localStorage.setItem(LS_PET_BUBBLES_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}

/**
 * Non-hook getter: read a random LLM-generated pet bubble greeting from localStorage cache.
 * Returns `null` if cache is stale/missing (caller should fall back to i18n keys).
 */
export function getCachedPetBubbleGreeting(): string | null {
  try {
    const raw = localStorage.getItem(LS_PET_BUBBLES_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw) as StoredPetBubblesPayload;
    if (o.date !== utcToday()) return null;
    if (!Array.isArray(o.lines) || o.lines.length === 0) return null;
    return o.lines[Math.floor(Math.random() * o.lines.length)]!;
  } catch {
    return null;
  }
}

/** Server + localStorage cache: ten welcome lines for the empty chat hero (refreshed daily, UTC). */
export function useDailyChatGreetings() {
  const { i18n, t } = useTranslation();
  const locale = i18n.resolvedLanguage || i18n.language || 'en-US';
  const fallbackLine = t('chat.greeting');
  const fallbackLines = useMemo(() => [fallbackLine], [fallbackLine]);

  const [lines, setLines] = useState<string[]>(fallbackLines);

  useEffect(() => {
    const cached = readCache(locale);
    if (cached) {
      setLines(cached);
      return;
    }

    setLines(fallbackLines);

    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.get<{
          date: string;
          greetings: string[];
          pet_bubbles?: string[];
        }>('/chat/daily-greetings', { locale }, { timeoutMs: 12_000 });
        if (cancelled) return;
        const g =
          Array.isArray(res.greetings) && res.greetings.length > 0 ? res.greetings : fallbackLines;
        setLines(g);
        writeCache(locale, res.date, g);
        if (Array.isArray(res.pet_bubbles) && res.pet_bubbles.length > 0) {
          writePetBubblesCache(locale, res.date, res.pet_bubbles);
        }
      } catch {
        if (!cancelled) {
          setLines(readCache(locale) ?? fallbackLines);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [locale, fallbackLines]);

  return lines;
}
