import React from 'react';
import { styles } from '../styles/voiceAppStyles.js';

const IndustryTag = () => {
  const getIndustryPresentation = () => {
    const currentBranch = import.meta.env.VITE_BRANCH_NAME || 'finance';

    if (currentBranch === 'main') {
      return {
        label: 'Insurance Edition',
        palette: {
          background: 'linear-gradient(135deg, #0ea5e9, #10b981)',
          color: '#0f172a',
          borderColor: 'rgba(14,165,233,0.35)',
          shadow: '0 12px 28px rgba(14,165,233,0.24)',
          textShadow: '0 1px 2px rgba(15,23,42,0.3)',
        },
      };
    }

    if (currentBranch.includes('finance') || currentBranch.includes('capitalmarkets')) {
      return {
        label: 'Banking Edition',
        palette: {
          background: 'linear-gradient(135deg, #4338ca, #6366f1)',
          color: '#f8fafc',
          borderColor: 'rgba(99,102,241,0.45)',
          shadow: '0 12px 28px rgba(99,102,241,0.25)',
          textShadow: '0 1px 2px rgba(30,64,175,0.4)',
        },
      };
    }

    return {
      label: 'Banking Edition',
      palette: {
        background: 'linear-gradient(135deg, #4338ca, #6366f1)',
        color: '#f8fafc',
        borderColor: 'rgba(99,102,241,0.45)',
        shadow: '0 12px 28px rgba(99,102,241,0.25)',
        textShadow: '0 1px 2px rgba(30,64,175,0.4)',
      },
    };
  };

  const { label, palette } = getIndustryPresentation();

  return (
    <div style={styles.topTabsContainer}>
      <div style={styles.topTab(true, palette)}>{label}</div>
    </div>
  );
};

export default IndustryTag;
