import React, { useState } from 'react';

const BackendHelpButton = () => {
  const [isHovered, setIsHovered] = useState(false);
  const [isClicked, setIsClicked] = useState(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsClicked(!isClicked);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <div
      style={{
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        backgroundColor: isHovered ? '#3b82f6' : '#64748b',
        color: 'white',
        fontSize: '9px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontWeight: '600',
        position: 'relative',
        flexShrink: 0,
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      ?
      <div
        style={{
          visibility: isHovered || isClicked ? 'visible' : 'hidden',
          opacity: isHovered || isClicked ? 1 : 0,
          position: 'absolute',
          bottom: '20px',
          left: '0',
          backgroundColor: 'rgba(0, 0, 0, 0.95)',
          color: 'white',
          padding: '12px',
          borderRadius: '8px',
          fontSize: '11px',
          lineHeight: '1.4',
          minWidth: '280px',
          maxWidth: '320px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          zIndex: 10000,
          transition: 'all 0.2s ease',
          backdropFilter: 'blur(8px)',
        }}
      >
        <div
          style={{
            fontSize: '12px',
            fontWeight: '600',
            color: '#67d8ef',
            marginBottom: '8px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          🔧 Backend Status Monitor
        </div>
        <div style={{ marginBottom: '8px' }}>
          Real-time health monitoring for all ARTAgent backend services including Redis cache, Azure OpenAI, Speech Services, and Communication Services.
        </div>
        <div style={{ marginBottom: '8px' }}>
          <strong>Status Colors:</strong>
          <br />
          🟢 Healthy - All systems operational
          <br />
          🟡 Degraded - Some performance issues
          <br />
          🔴 Unhealthy - Service disruption
        </div>
        <div style={{ fontSize: '10px', color: '#94a3b8', fontStyle: 'italic' }}>
          Auto-refreshes every 30 seconds • Click to expand for details
        </div>
        {isClicked && (
          <div
            style={{
              textAlign: 'center',
              marginTop: '8px',
              fontSize: '9px',
              color: '#94a3b8',
              fontStyle: 'italic',
            }}
          >
            Click ? again to close
          </div>
        )}
      </div>
    </div>
  );
};

export default BackendHelpButton;
