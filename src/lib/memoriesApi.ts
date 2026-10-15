/// <reference types="vite/client" />

import type { Memory, SourceType } from '../data/types';

export interface MemoryFilters {
  q?: string;
  from_date?: string;
  to_date?: string;
  domain?: string;
  source_type?: 'browser' | 'transcript' | 'note';
  page: number;
  page_size: number;
}

interface ApiMemory {
  id: string;
  source_id?: string | null;
  source_type: 'browser' | 'transcript' | 'note';
  title: string;
  normalized_text: string;
  source_url?: string | null;
  domain?: string | null;
  source_metadata?: Record<string, unknown>;
  captured_at: string;
  ingested_at: string;
  content_hash: string;
  request_id: string;
  capture_type?: string | null;
  selected_text?: string | null;
  surrounding_context?: string | null;
  extraction_status?: string | null;
  note?: string | null;
}

interface ApiSource {
  id: string;
  source_type: string;
  url?: string | null;
  domain?: string | null;
  title: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  memory_count: number;
}

interface MemoryPage {
  items: ApiMemory[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface MemoryDetail {
  memory: Memory;
  source: ApiSource;
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init.headers },
    });
  } catch (error) {
    throw new Error(error instanceof Error ? error.message : 'The backend is unavailable.');
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null;
    throw new Error(payload?.error?.message || `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function displayDate(timestamp: string): string {
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime())
    ? timestamp
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
}

function asTags(metadata: Record<string, unknown> | undefined): string[] {
  const tags = metadata?.tags;
  return Array.isArray(tags) ? tags.filter((tag): tag is string => typeof tag === 'string') : [];
}

function mapMemory(record: ApiMemory, source?: ApiSource): Memory {
  const sourceType: SourceType = record.source_type;
  const content = record.normalized_text;
  const metadata = record.source_metadata || {};
  return {
    id: record.id,
    title: record.title,
    excerpt: content.length > 240 ? `${content.slice(0, 237)}...` : content,
    content,
    sourceType,
    sourceName: source?.title || record.domain || (sourceType === 'note' ? 'Manual note' : sourceType),
    sourceUrl: source?.url || record.source_url || '',
    capturedAt: record.captured_at,
    capturedLabel: displayDate(record.captured_at),
    tags: asTags(metadata),
    localOnly: true,
    extractNote: record.note || record.extraction_status || undefined,
    sourceId: record.source_id || undefined,
    domain: record.domain || undefined,
    sourceMetadata: metadata,
    captureType: record.capture_type || undefined,
    selectedText: record.selected_text || undefined,
    surroundingContext: record.surrounding_context || undefined,
    extractionStatus: record.extraction_status || undefined,
    requestId: record.request_id,
    contentHash: record.content_hash,
  };
}

export async function listMemories(filters: MemoryFilters, signal?: AbortSignal) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const page = await request<MemoryPage>(`/memories?${params.toString()}`, { signal });
  return { ...page, items: page.items.map((item) => mapMemory(item)) };
}

export async function getMemory(id: string, signal?: AbortSignal): Promise<MemoryDetail> {
  const result = await request<{ memory: ApiMemory; source: ApiSource }>(
    `/memories/${encodeURIComponent(id)}`,
    { signal },
  );
  return { memory: mapMemory(result.memory, result.source), source: result.source };
}

export async function deleteMemory(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/memories/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Response of POST /api/v1/memories/{id}/summary (Task 5.5/5.6 backend). */
export interface MemorySummary {
  memory_id: string;
  summary: string;
  /** Identifier of the local Ollama model that produced the summary. */
  model: string;
}

/**
 * One grounded passage returned by POST /api/v1/ask (Module 6, Task 6.6).
 *
 * Every field comes from a real stored record, so an evidence item can always be
 * traced back to the memory and chunk it came from. `similarity` is a cosine
 * score, or 0 when the passage was matched by keywords only — never treat it as
 * a keyword score.
 */
export interface AskEvidence {
  chunk_id: string;
  memory_id: string;
  source_id?: string | null;
  source_type?: string | null;
  source_title?: string | null;
  source_url?: string | null;
  domain?: string | null;
  captured_at?: string | null;
  passage: string;
  similarity: number;
  keyword_rank?: number | null;
  score: number;
  matched_by: string[];
  confidence: string;
}

/** How much the retrieved evidence should be trusted. */
export type RetrievalConfidence = 'none' | 'weak' | 'strong';

/** Response of POST /api/v1/ask (Module 6, Task 6.6 backend). */
export interface AskResult {
  question: string;
  evidence: AskEvidence[];
  confidence: RetrievalConfidence;
  channels: string[];
  candidates_considered: number;
  temporal_expression?: string | null;
  temporal_from?: string | null;
  temporal_to?: string | null;
  request_id?: string | null;
}

/** Request body of POST /api/v1/ask. */
export interface AskRequest {
  question: string;
  top_k?: number;
  /** Inclusive UTC calendar days (YYYY-MM-DD); an explicit range wins over a
   * window parsed from the question text ("last week"). */
  from_date?: string;
  to_date?: string;
}

/**
 * Ask a question and retrieve grounded evidence from local memories.
 *
 * This returns **evidence, not an answer**: the backend does not generate prose,
 * so the UI must not present one. A successful search that matched nothing is a
 * normal 200 with an empty `evidence` list — the caller distinguishes that from
 * a failure via `confidence === 'none'` rather than an exception.
 */
export async function askRecallAi(
  payload: AskRequest,
  signal?: AbortSignal,
): Promise<AskResult> {
  try {
    return await request<AskResult>(`/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    const message = error instanceof Error ? error.message : '';
    if (/failed to fetch|networkerror|load failed/i.test(message)) {
      throw new Error('Could not reach the local RecallAI server. Make sure the backend is running.');
    }
    throw error;
  }
}

/** Result of indexing one memory: POST /api/v1/memories/{id}/index. */
export interface IndexOutcome {
  memory_id: string;
  status: string;
  chunk_count: number;
  detail: string;
  request_id?: string | null;
}

/**
 * Build the retrieval index for one stored memory (Module 6, Tasks 6.1-6.3).
 *
 * Indexing is explicit and user-initiated: it needs the local embedding model,
 * and saving a memory must never depend on that model being installed.
 */
export async function indexMemory(id: string, signal?: AbortSignal): Promise<IndexOutcome> {
  return request<IndexOutcome>(`/memories/${encodeURIComponent(id)}/index`, {
    method: 'POST',
    signal,
  });
}


/**
 * Request an AI summary for one stored memory (Task 5.8).
 *
 * User-initiated only — the browser posts to the local backend, which
 * summarizes with the loopback-only Ollama model. No API key and no cloud
 * service is ever involved from this call. Backend error-envelope messages
 * are surfaced as-is; raw network failures are rewritten to plain language.
 */
export async function summarizeMemory(id: string, signal?: AbortSignal): Promise<MemorySummary> {
  try {
    return await request<MemorySummary>(`/memories/${encodeURIComponent(id)}/summary`, {
      method: 'POST',
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    const message = error instanceof Error ? error.message : '';
    if (/failed to fetch|networkerror|load failed/i.test(message)) {
      throw new Error('Could not reach the local RecallAI server. Make sure the backend is running.');
    }
    throw error;
  }
}
