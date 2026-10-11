import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { memories as seedMemories } from '../data/mockData';
import type { Memory } from '../data/types';

interface MemoriesContextValue {
  memories: Memory[];
  /** Remove a memory by id. Returns true if something was deleted. */
  deleteMemory: (id: string) => boolean;
  /** Look up a single memory by id (or undefined). */
  getMemory: (id: string) => Memory | undefined;
}

const MemoriesContext = createContext<MemoriesContextValue | null>(null);

/**
 * Holds the mock memory list in React state so that deleting a memory on the
 * Detail screen is reflected everywhere (Overview + Timeline). Today this is
 * seeded from mock data; later it can be backed by API calls.
 */
export function MemoriesProvider({ children }: { children: ReactNode }) {
  const [memories, setMemories] = useState<Memory[]>(seedMemories);

  const value = useMemo<MemoriesContextValue>(
    () => ({
      memories,
      deleteMemory: (id: string) => {
        let deleted = false;
        setMemories((prev) => {
          deleted = prev.some((m) => m.id === id);
          return prev.filter((m) => m.id !== id);
        });
        return deleted;
      },
      getMemory: (id: string) => memories.find((m) => m.id === id),
    }),
    [memories],
  );

  return <MemoriesContext.Provider value={value}>{children}</MemoriesContext.Provider>;
}

/** Access the shared memory store. Must be used inside <MemoriesProvider>. */
export function useMemories(): MemoriesContextValue {
  const ctx = useContext(MemoriesContext);
  if (!ctx) {
    throw new Error('useMemories must be used within a MemoriesProvider');
  }
  return ctx;
}
