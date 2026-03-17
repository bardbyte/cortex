import type { CSSProperties } from 'react';
import type { Session } from '../types';
import { colors, typography, radius, shadows } from '../tokens';

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  open: boolean;
}

/** Group key used for rendering date headers. */
type DateGroup = 'TODAY' | 'YESTERDAY' | 'LAST 7 DAYS' | 'OLDER';

function getDateGroup(date: Date): DateGroup {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  if (date >= today) return 'TODAY';
  if (date >= yesterday) return 'YESTERDAY';
  if (date >= sevenDaysAgo) return 'LAST 7 DAYS';
  return 'OLDER';
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function groupSessions(
  sessions: Session[],
): { group: DateGroup; items: Session[] }[] {
  const order: DateGroup[] = ['TODAY', 'YESTERDAY', 'LAST 7 DAYS', 'OLDER'];
  const map = new Map<DateGroup, Session[]>();

  for (const g of order) {
    map.set(g, []);
  }

  for (const s of sessions) {
    const g = getDateGroup(s.timestamp);
    map.get(g)!.push(s);
  }

  return order
    .filter((g) => map.get(g)!.length > 0)
    .map((g) => ({ group: g, items: map.get(g)! }));
}

function truncatePreview(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + '...';
}

function formatMessageCount(count: number): string {
  return count === 1 ? '1 msg' : `${count} msgs`;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  open,
}: SidebarProps) {
  const grouped = groupSessions(sessions);

  const containerStyle: CSSProperties = {
    width: open ? '280px' : '0px',
    minWidth: open ? '280px' : '0px',
    overflow: 'hidden',
    background: colors.surfacePrimary,
    borderRight: open ? `1px solid ${colors.borderDefault}` : 'none',
    transition: 'width 250ms ease-out, min-width 250ms ease-out',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: typography.fontPrimary,
    height: '100%',
  };

  const innerStyle: CSSProperties = {
    width: '280px',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
  };

  const topAreaStyle: CSSProperties = {
    padding: '16px',
    flexShrink: 0,
  };

  const newButtonStyle: CSSProperties = {
    width: '100%',
    padding: '10px 16px',
    background: colors.amexBlue,
    color: colors.amexWhite,
    border: 'none',
    borderRadius: radius.md,
    fontSize: '14px',
    fontWeight: 600,
    fontFamily: typography.fontPrimary,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    boxShadow: shadows.sm,
    transition: 'background 150ms ease',
  };

  const listAreaStyle: CSSProperties = {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '0 8px 16px',
  };

  const groupHeaderStyle: CSSProperties = {
    fontSize: '11px',
    fontWeight: 600,
    color: colors.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    padding: '16px 8px 6px',
    fontFamily: typography.fontPrimary,
  };

  const getSessionItemStyle = (isActive: boolean): CSSProperties => ({
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    padding: '10px 12px',
    borderRadius: radius.md,
    cursor: 'pointer',
    background: isActive ? colors.infoLight : 'transparent',
    borderLeft: isActive ? `3px solid ${colors.amexBlue}` : '3px solid transparent',
    transition: 'background 150ms ease',
    marginBottom: '2px',
  });

  const sessionTitleStyle = (isActive: boolean): CSSProperties => ({
    fontSize: '13px',
    fontWeight: isActive ? 600 : 400,
    color: colors.textPrimary,
    fontFamily: typography.fontPrimary,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    lineHeight: '1.4',
  });

  const sessionPreviewStyle: CSSProperties = {
    fontSize: '11px',
    color: colors.textTertiary,
    fontFamily: typography.fontPrimary,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    lineHeight: '1.3',
  };

  const sessionMetaRowStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  };

  const sessionTimestampStyle: CSSProperties = {
    fontSize: '11px',
    color: colors.textTertiary,
    fontFamily: typography.fontPrimary,
    lineHeight: '1.3',
  };

  const messageCountBadgeStyle: CSSProperties = {
    fontSize: '11px',
    color: colors.textTertiary,
    fontFamily: typography.fontPrimary,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: radius.full,
    padding: '1px 6px',
    lineHeight: '1.4',
    whiteSpace: 'nowrap',
  };

  return (
    <div style={containerStyle}>
      <div style={innerStyle}>
        {/* New conversation button */}
        <div style={topAreaStyle}>
          <button
            style={newButtonStyle}
            onClick={onNewSession}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = '#0059A6';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = colors.amexBlue;
            }}
          >
            <span style={{ fontSize: '18px', lineHeight: '1', fontWeight: 300 }}>+</span>
            New Conversation
          </button>
        </div>

        {/* Session list */}
        <div style={listAreaStyle}>
          {grouped.map(({ group, items }) => (
            <div key={group}>
              <div style={groupHeaderStyle}>{group}</div>
              {items.map((session) => {
                const isActive = session.id === activeSessionId;
                const displayTitle =
                  session.title.length > 35
                    ? session.title.slice(0, 35) + '...'
                    : session.title;

                return (
                  <div
                    key={session.id}
                    role="button"
                    tabIndex={0}
                    style={getSessionItemStyle(isActive)}
                    onClick={() => onSelectSession(session.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectSession(session.id);
                      }
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        (e.currentTarget as HTMLDivElement).style.background =
                          colors.surfaceSecondary;
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                      }
                    }}
                  >
                    <span style={sessionTitleStyle(isActive)}>{displayTitle}</span>
                    {session.lastMessage && session.lastMessage.length > 0 && (
                      <span style={sessionPreviewStyle}>
                        {truncatePreview(session.lastMessage, 45)}
                      </span>
                    )}
                    <div style={sessionMetaRowStyle}>
                      <span style={sessionTimestampStyle}>{formatTime(session.timestamp)}</span>
                      <span style={messageCountBadgeStyle}>
                        {formatMessageCount(session.messages.length)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}

          {sessions.length === 0 && (
            <div
              style={{
                padding: '24px 8px',
                textAlign: 'center',
                color: colors.textTertiary,
                fontSize: '13px',
                fontFamily: typography.fontPrimary,
              }}
            >
              No conversations yet.
              <br />
              Ask a question to get started.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
