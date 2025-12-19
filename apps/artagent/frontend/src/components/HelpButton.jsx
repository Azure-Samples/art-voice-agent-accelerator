import React, { useState } from 'react';
import { styles } from '../styles/voiceAppStyles.js';

const HelpButton = () => {
  const [isHovered, setIsHovered] = useState(false);
  const [isClicked, setIsClicked] = useState(false);

  const handleClick = (e) => {
    if (e.target.tagName !== 'A') {
      e.preventDefault();
      e.stopPropagation();
      setIsClicked(!isClicked);
    }
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <div
      style={{
        width: '44px',
        height: '44px',
        borderRadius: '12px',
        border: '1px solid rgba(226,232,240,0.6)',
        background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
        color: '#6366f1',
        fontSize: '14px',
        fontWeight: '600',
        cursor: 'pointer',
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        boxShadow: '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        ...(isHovered || isClicked ? {
          transform: 'translateY(-2px)',
          boxShadow: '0 4px 16px rgba(99,102,241,0.2), inset 0 1px 0 rgba(255,255,255,0.8)',
          background: 'linear-gradient(135deg, #eef2ff, #e0e7ff)',
        } : {}),
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      ?
      <div
        style={{
          ...styles.helpTooltip,
          ...((isHovered || isClicked) ? styles.helpTooltipVisible : {}),
          // Override position to show on right side with sleek design
          top: '50%',
          left: '64px',
          right: 'auto',
          transform: (isHovered || isClicked) ? 'translateY(-50%)' : 'translateY(-50%) translateX(-8px)',
          width: '340px',
          background: 'linear-gradient(145deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95))',
          boxShadow: '0 8px 32px rgba(15,23,42,0.12), 0 0 0 1px rgba(226,232,240,0.4), inset 0 1px 0 rgba(255,255,255,0.8)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
        }}
      >
        <div style={styles.helpTooltipTitle} />
        <div
          style={{
            ...styles.helpTooltipText,
            color: '#dc2626',
            fontWeight: '600',
            fontSize: '12px',
            marginBottom: '12px',
            padding: '8px',
            backgroundColor: '#fef2f2',
            borderRadius: '4px',
            border: '1px solid #fecaca',
          }}
        >
          This is a demo available for Microsoft employees only.
        </div>
        <div style={styles.helpTooltipTitle}>🤖 ARTAgent Demo</div>
        <div style={styles.helpTooltipText}>
          ARTAgent is an accelerator that delivers a friction-free, AI-driven voice experience—whether callers dial a phone number, speak to an IVR, or click &quot;Call Me&quot; in a web app. Built entirely on Azure services, it provides a low-latency stack that scales on demand while keeping the AI layer fully under your control.
        </div>
        <div style={styles.helpTooltipText}>
          Design a single agent or orchestrate multiple specialist agents. The framework allows you to build your voice agent from scratch, incorporate memory, configure actions, and fine-tune your TTS and STT layers.
        </div>
        <div style={styles.helpTooltipText}>
          🤔 <strong>Try asking about:</strong> Transfer Agency DRIP liquidations, compliance reviews, fraud detection, or general inquiries.
        </div>
        <div style={styles.helpTooltipText}>
          📑{' '}
          <a
            href="https://microsoft.sharepoint.com/teams/rtaudioagent"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: '#3b82f6',
              textDecoration: 'underline',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            Visit the Project Hub
          </a>{' '}
          for instructions, deep dives and more.
        </div>
        <div style={styles.helpTooltipText}>
          📧 Questions or feedback?{' '}
          <a
            href="mailto:rtvoiceagent@microsoft.com?subject=ARTAgent Feedback"
            style={{
              color: '#3b82f6',
              textDecoration: 'underline',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            Contact the team
          </a>
        </div>
        {isClicked && (
          <div
            style={{
              textAlign: 'center',
              marginTop: '8px',
              fontSize: '10px',
              color: '#64748b',
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

export default HelpButton;
