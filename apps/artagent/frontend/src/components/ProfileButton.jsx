import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Avatar,
  Typography,
  Box,
} from '@mui/material';

/* ------------------------------------------------------------------ *
 *  PROFILE BUTTON COMPONENT WITH MATERIAL UI
 * ------------------------------------------------------------------ */
const resolveRelationshipTier = (profileData) => (
  profileData?.relationship_tier
  || profileData?.customer_intelligence?.relationship_context?.relationship_tier
  || profileData?.customer_intelligence?.relationship_context?.tier
  || '—'
);

const getInitials = (name) => {
  if (!name) return 'U';
  return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
};

const getTierColor = (tier) => {
  switch (tier?.toLowerCase()) {
    case 'platinum':
      return '#e5e7eb';
    case 'gold':
      return '#fbbf24';
    case 'silver':
      return '#9ca3af';
    case 'bronze':
      return '#d97706';
    default:
      return '#6b7280';
  }
};

const ProfileButtonComponent = ({
  profile,
  onCreateProfile,
  onTogglePanel,
  highlight = false,
}) => {
  const [highlighted, setHighlighted] = useState(false);
  const lastProfileIdentityRef = useRef(null);
  const highlightTimeoutRef = useRef(null);

  const startHighlight = useCallback(() => {
    setHighlighted(true);
    if (highlightTimeoutRef.current) {
      clearTimeout(highlightTimeoutRef.current);
    }
    highlightTimeoutRef.current = window.setTimeout(() => {
      setHighlighted(false);
      highlightTimeoutRef.current = null;
    }, 3200);
  }, []);

  const handleClick = () => {
    if (!profile) {
      // If no profile, trigger profile creation
      onCreateProfile?.();
      return;
    }
    if (highlightTimeoutRef.current) {
      clearTimeout(highlightTimeoutRef.current);
      highlightTimeoutRef.current = null;
    }
    setHighlighted(false);
    onTogglePanel?.();
  };

  useEffect(() => {
    if (!profile) {
      lastProfileIdentityRef.current = null;
      if (highlightTimeoutRef.current) {
        clearTimeout(highlightTimeoutRef.current);
        highlightTimeoutRef.current = null;
      }
      setHighlighted(false);
      return () => {};
    }

    const identity =
      profile?.sessionId ||
      profile?.entryId ||
      profile?.profile?.id ||
      profile?.profile?.full_name ||
      profile?.profile?.email;

    if (!identity || lastProfileIdentityRef.current === identity) {
      return () => {};
    }

    lastProfileIdentityRef.current = identity;
    startHighlight();

    return () => {
      if (highlightTimeoutRef.current) {
        clearTimeout(highlightTimeoutRef.current);
        highlightTimeoutRef.current = null;
      }
    };
  }, [profile, startHighlight]);

  useEffect(() => {
    if (highlight) {
      startHighlight();
    }
  }, [highlight, startHighlight]);

  useEffect(() => () => {
    if (highlightTimeoutRef.current) {
      clearTimeout(highlightTimeoutRef.current);
    }
  }, []);

  // No profile state - button handled upstream
  if (!profile) {
    return null;
  }

  const profileData = profile.profile;
  if (!profileData) {
    return null;
  }
  const tier = resolveRelationshipTier(profileData);
  const ssnLast4 = profileData?.verification_codes?.ssn4 || '----';
  const institutionName = profileData?.institution_name || 'Demo Institution';
  const companyCode = profileData?.company_code;
  const companyCodeLast4 = profileData?.company_code_last4 || companyCode?.slice?.(-4) || '----';
  const institutionSnippet = institutionName?.length > 30
    ? `${institutionName.slice(0, 27)}…`
    : institutionName;

  return (
    <>
      {/* Compact Profile Button */}
      <Box 
        onClick={handleClick}
        sx={{ 
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 10px',
          borderRadius: '20px',
          background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
          border: '2px solid #e2e8f0',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          maxWidth: '160px',
          flexShrink: 0,
          marginLeft: '4px',
          animation: highlighted ? 'profileButtonPulse 1.5s ease-in-out 3' : 'none',
          '&:hover': {
            background: 'linear-gradient(135deg, #e2e8f0 0%, #cbd5e1 100%)',
            transform: 'scale(1.02)',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
          },
          '@keyframes profileButtonPulse': {
            '0%': {
              boxShadow: '0 0 0 0 rgba(103, 216, 239, 0.55)',
              transform: 'scale(1)'
            },
            '70%': {
              boxShadow: '0 0 0 10px rgba(103, 216, 239, 0)',
              transform: 'scale(1.04)'
            },
            '100%': {
              boxShadow: '0 0 0 0 rgba(103, 216, 239, 0)',
              transform: 'scale(1)'
            }
          }
        }}
      >
        <Avatar 
          sx={{ 
            width: 24, 
            height: 24, 
            bgcolor: getTierColor(tier),
            color: tier?.toLowerCase() === 'platinum' ? '#1f2937' : '#fff',
            fontSize: '10px',
            fontWeight: 600
          }}
        >
          {getInitials(profileData?.full_name)}
        </Avatar>
        <Box sx={{ overflow: 'hidden', minWidth: 0 }}>
          <Typography 
            sx={{ 
              fontSize: '11px',
              fontWeight: 600,
              color: '#1f2937',
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}
          >
            {profileData?.full_name || 'Demo User'}
          </Typography>
          <Typography 
            sx={{ 
              fontSize: '9px',
              color: '#64748b',
              lineHeight: 1,
              display: 'flex',
              flexWrap: 'wrap',
              columnGap: '6px',
              rowGap: '2px',
              whiteSpace: 'normal'
            }}
            component="div"
          >
            <span style={{ fontWeight: 600 }}>{institutionSnippet}</span>
            <span style={{ opacity: 0.8 }}>Co · ***{companyCodeLast4}</span>
            <span style={{ opacity: 0.8 }}>SSN · ***{ssnLast4}</span>
          </Typography>
        </Box>
      </Box>

      {/* Panel moved to separate component */}
    </>
  );
};

const areProfileButtonPropsEqual = (prevProps, nextProps) => (
  prevProps.profile === nextProps.profile &&
  prevProps.highlight === nextProps.highlight &&
  prevProps.onCreateProfile === nextProps.onCreateProfile &&
  prevProps.onTogglePanel === nextProps.onTogglePanel
);

export default React.memo(ProfileButtonComponent, areProfileButtonPropsEqual);
