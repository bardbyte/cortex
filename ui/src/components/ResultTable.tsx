import React, { useState, useMemo, useCallback } from 'react';
import { colors, typography, radius } from '../tokens';

interface ResultTableProps {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  truncated: boolean;
}

type SortDirection = 'asc' | 'desc' | null;

function isNumeric(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return false;
  return !isNaN(Number(value));
}

function formatHeader(col: string): string {
  return col
    .replace(/_/g, ' ')
    .replace(/\./g, ' > ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '\u2014';
  if (typeof value === 'number') {
    return value.toLocaleString();
  }
  return String(value);
}

const VISIBLE_ROWS = 20;

const ResultTable: React.FC<ResultTableProps> = ({ columns, rows, rowCount, truncated }) => {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDirection>(null);
  const [showAll, setShowAll] = useState(false);

  const numericColumns = useMemo(() => {
    const set = new Set<string>();
    for (const col of columns) {
      const sample = rows.slice(0, 5).map((r) => r[col]);
      if (sample.some((v) => v !== null && v !== undefined) && sample.filter((v) => v !== null && v !== undefined).every(isNumeric)) {
        set.add(col);
      }
    }
    return set;
  }, [columns, rows]);

  const sortedRows = useMemo(() => {
    if (!sortCol || !sortDir) return rows;
    const isNum = numericColumns.has(sortCol);
    return [...rows].sort((a, b) => {
      const aVal = a[sortCol];
      const bVal = b[sortCol];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      let cmp: number;
      if (isNum) {
        cmp = Number(aVal) - Number(bVal);
      } else {
        cmp = String(aVal).localeCompare(String(bVal));
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });
  }, [rows, sortCol, sortDir, numericColumns]);

  const visibleRows = showAll ? sortedRows : sortedRows.slice(0, VISIBLE_ROWS);
  const hasMore = rows.length > VISIBLE_ROWS;

  const handleSort = useCallback((col: string) => {
    if (sortCol === col) {
      if (sortDir === 'asc') setSortDir('desc');
      else if (sortDir === 'desc') { setSortCol(null); setSortDir(null); }
      else setSortDir('asc');
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }, [sortCol, sortDir]);

  const sortIndicator = (col: string) => {
    if (sortCol !== col) return <span style={{ opacity: 0.3, marginLeft: 4 }}>{'\u2195'}</span>;
    if (sortDir === 'asc') return <span style={{ marginLeft: 4 }}>{'\u2191'}</span>;
    return <span style={{ marginLeft: 4 }}>{'\u2193'}</span>;
  };

  return (
    <div style={{ width: '100%', overflowX: 'auto', marginTop: 12 }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: typography.fontPrimary,
          fontSize: 13,
        }}
      >
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                onClick={() => handleSort(col)}
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: colors.textTertiary,
                  padding: '8px 12px',
                  textAlign: numericColumns.has(col) ? 'right' : 'left',
                  borderBottom: `2px solid ${colors.borderDefault}`,
                  cursor: 'pointer',
                  userSelect: 'none',
                  whiteSpace: 'nowrap',
                }}
              >
                {formatHeader(col)}
                {sortIndicator(col)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row, idx) => (
            <tr
              key={idx}
              style={{
                backgroundColor: idx % 2 === 0 ? colors.surfacePrimary : colors.surfaceSecondary,
                height: 32,
              }}
            >
              {columns.map((col) => (
                <td
                  key={col}
                  style={{
                    padding: '6px 12px',
                    textAlign: numericColumns.has(col) ? 'right' : 'left',
                    borderBottom: `1px solid ${colors.borderDefault}`,
                    color: colors.textPrimary,
                    whiteSpace: 'nowrap',
                    fontVariantNumeric: numericColumns.has(col) ? 'tabular-nums' : undefined,
                    fontFamily: numericColumns.has(col) ? typography.fontMono : undefined,
                    fontSize: numericColumns.has(col) ? 12 : 13,
                  }}
                >
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          fontSize: 12,
          color: colors.textSecondary,
        }}
      >
        <span>
          Showing {visibleRows.length} of {rowCount} rows
        </span>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          {truncated && (
            <span
              style={{
                color: colors.warning,
                backgroundColor: colors.warningLight,
                padding: '2px 8px',
                borderRadius: radius.sm,
                fontSize: 11,
                fontWeight: 500,
              }}
            >
              Results truncated by server
            </span>
          )}
          {hasMore && !showAll && (
            <button
              onClick={() => setShowAll(true)}
              style={{
                background: 'none',
                border: 'none',
                color: colors.textLink,
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 500,
                fontFamily: typography.fontPrimary,
                padding: 0,
              }}
            >
              Show all {rows.length} rows
            </button>
          )}
          {showAll && hasMore && (
            <button
              onClick={() => setShowAll(false)}
              style={{
                background: 'none',
                border: 'none',
                color: colors.textLink,
                cursor: 'pointer',
                fontSize: 12,
                fontWeight: 500,
                fontFamily: typography.fontPrimary,
                padding: 0,
              }}
            >
              Collapse
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResultTable;
