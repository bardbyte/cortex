import { useState, useEffect } from 'react';
import type { CSSProperties } from 'react';

interface ConnectingArrowProps {
  pulse?: boolean;
}

export default function ConnectingArrow({ pulse = false }: ConnectingArrowProps) {
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (pulse) {
      setScale(1.3);
      const timer = setTimeout(() => setScale(1), 300);
      return () => clearTimeout(timer);
    }
  }, [pulse]);

  const containerStyle: CSSProperties = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '40px',
  };

  return (
    <div style={containerStyle}>
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="none"
        style={{
          transform: `scale(${scale})`,
          transition: 'transform 300ms ease-out',
        }}
      >
        <path
          d="M10 4V16M10 16L5 11M10 16L15 11"
          stroke="#006FCF"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
