import React, { useState } from 'react';

const BackendStatisticsButton = ({ onToggle, isActive }) => {
  const [isHovered, setIsHovered] = useState(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onToggle();
  };

  return (
    <div
      style={{
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        backgroundColor: isActive ? '#3b82f6' : isHovered ? '#3b82f6' : '#64748b',
        color: 'white',
        fontSize: '8px',
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
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleClick}
      title="Toggle session statistics"
    >
      📊
    </div>
  );
};

export default BackendStatisticsButton;
