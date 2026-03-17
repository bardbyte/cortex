import { useState, useCallback } from 'react';
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
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function useConversation(): UseConversationReturn {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

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

  return {
    sessions,
    activeSessionId,
    createSession,
    setActiveSessionId,
    addMessage,
    getActiveSession,
    updateSessionTitle,
    deleteSession,
  };
}

export default useConversation;
