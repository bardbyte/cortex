import { useState, useCallback, useEffect, useRef } from 'react';
import type { Session, Message } from '../types';

export interface UseConversationReturn {
  sessions: Session[];
  activeSessionId: string | null;
  createSession: () => string;
  setActiveSessionId: (id: string | null) => void;
  addMessage: (sessionId: string, message: Message) => void;
  getActiveSession: () => Session | undefined;
  updateSessionTitle: (sessionId: string, title: string) => void;
  deleteSession: (sessionId: string) => void;
  setConversationId: (sessionId: string, conversationId: string) => void;
}

const STORAGE_KEY = 'radix_sessions';
const ACTIVE_SESSION_KEY = 'radix_active_session';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Revive Date strings back into Date objects when loading from JSON. */
function reviveDates(sessions: Session[]): Session[] {
  return sessions.map((s) => ({
    ...s,
    timestamp: new Date(s.timestamp),
    messages: s.messages.map((m) => ({
      ...m,
      timestamp: new Date(m.timestamp),
    })),
  }));
}

function loadSessions(): Session[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Session[];
    return reviveDates(parsed);
  } catch {
    return [];
  }
}

function loadActiveSessionId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_SESSION_KEY);
  } catch {
    return null;
  }
}

function persistSessions(sessions: Session[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // Storage full or unavailable — fail silently.
  }
}

function persistActiveSessionId(id: string | null): void {
  try {
    if (id) {
      localStorage.setItem(ACTIVE_SESSION_KEY, id);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    }
  } catch {
    // fail silently
  }
}

export function useConversation(): UseConversationReturn {
  const [sessions, setSessions] = useState<Session[]>(loadSessions);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const isInitialMount = useRef(true);

  // Persist sessions to localStorage whenever they change
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    persistSessions(sessions);
  }, [sessions]);

  // Persist active session ID
  useEffect(() => {
    persistActiveSessionId(activeSessionId);
  }, [activeSessionId]);

  const createSession = useCallback((): string => {
    const id = generateId();
    const session: Session = {
      id,
      title: 'New conversation',
      lastMessage: '',
      timestamp: new Date(),
      messages: [],
    };
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(id);
    return id;
  }, []);

  const addMessage = useCallback((sessionId: string, message: Message) => {
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== sessionId) return s;

        const updatedMessages = [...s.messages, message];

        // Derive title from the first user message if still default.
        let title = s.title;
        if (title === 'New conversation' && message.role === 'user') {
          title = message.content.length > 60
            ? message.content.slice(0, 57) + '...'
            : message.content;
        }

        return {
          ...s,
          messages: updatedMessages,
          lastMessage: message.content,
          timestamp: message.timestamp,
          title,
        };
      }),
    );
  }, []);

  const getActiveSession = useCallback((): Session | undefined => {
    return sessions.find((s) => s.id === activeSessionId);
  }, [sessions, activeSessionId]);

  const updateSessionTitle = useCallback((sessionId: string, title: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === sessionId ? { ...s, title } : s)),
    );
  }, []);

  const deleteSession = useCallback(
    (sessionId: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
    },
    [activeSessionId],
  );

  const setConversationId = useCallback((sessionId: string, conversationId: string) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === sessionId ? { ...s, conversationId } : s)),
    );
  }, []);

  return {
    sessions,
    activeSessionId,
    createSession,
    setActiveSessionId,
    addMessage,
    getActiveSession,
    updateSessionTitle,
    deleteSession,
    setConversationId,
  };
}

export default useConversation;
