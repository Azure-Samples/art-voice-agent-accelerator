import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Avatar,
  Box,
  Chip,
  Divider,
  Typography,
} from '@mui/material';
import IconButton from '@mui/material/IconButton';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const currencyWithCentsFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatCurrency = (value) => {
  if (value === null || value === undefined) return '—';
  try {
    return currencyFormatter.format(value);
  } catch {
    return value;
  }
};

const formatCurrencyWithCents = (value) => {
  if (value === null || value === undefined) return '—';
  try {
    return currencyWithCentsFormatter.format(value);
  } catch {
    return value;
  }
};

const formatNumber = (value) => {
  if (value === null || value === undefined) return '—';
  return value.toString();
};

const formatDate = (dateStr) => {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleDateString();
  } catch {
    return '—';
  }
};

const formatDateTime = (value) => {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return '—';
  }
};

const toTitleCase = (value) => {
  if (!value) return '—';
  return value
    .toString()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const maskSecretValue = (value) => {
  if (!value) return '—';
  if (value.length <= 6) {
    return '••••••';
  }
  const prefix = value.slice(0, 3);
  const suffix = value.slice(-2);
  return `${prefix}••••••${suffix}`;
};

const TAB_META = {
  verification: { icon: '🛡️', accent: '#6366f1' },
  identity: { icon: '🪪', accent: '#0ea5e9' },
  banking: { icon: '🏦', accent: '#8b5cf6' },
  transactions: { icon: '💳', accent: '#ec4899' },
  contact: { icon: '☎️', accent: '#10b981' },
  // Insurance scenario tabs
  policies: { icon: '📋', accent: '#0d9488' },
  claims: { icon: '📝', accent: '#f59e0b' },
};

const SectionCard = ({ children, sx = {} }) => (
  <Box
    sx={{
      borderRadius: '18px',
      border: '1px solid rgba(226,232,240,0.9)',
      background: 'linear-gradient(135deg, rgba(248,250,252,0.95), rgba(255,255,255,0.9))',
      boxShadow: '0 6px 18px rgba(15,23,42,0.08)',
      padding: '18px 20px',
      ...sx,
    }}
  >
    {children}
  </Box>
);

const SummaryStat = ({ label, value, icon, tooltip }) => (
  <Box
    component="span"
    title={tooltip || label}
    sx={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      padding: '4px 10px',
      borderRadius: '999px',
      backgroundColor: 'rgba(255,255,255,0.85)',
      border: '1px solid rgba(226,232,240,0.8)',
      fontSize: '11px',
      fontWeight: 600,
      color: '#0f172a',
      cursor: tooltip ? 'help' : 'default',
    }}
  >
    {icon && <span style={{ fontSize: '12px' }}>{icon}</span>}
    <span>{value || '—'}</span>
  </Box>
);

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

const SectionTitle = ({ icon, children }) => (
  <Typography sx={{
    fontSize: '11px',
    fontWeight: 700,
    color: '#475569',
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    mb: 1.5,
    display: 'flex',
    alignItems: 'center',
    gap: 1,
  }}>
    {icon && <span>{icon}</span>}
    {children}
  </Typography>
);

const ProfileDetailRow = ({ icon, label, value, multiline = false }) => (
  <Box sx={{
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '6px 0',
    minHeight: '24px',
  }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      {icon && <Box sx={{ color: '#64748b', fontSize: '14px' }}>{icon}</Box>}
      <Typography sx={{
        fontWeight: 600,
        color: '#64748b',
        fontSize: '11px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}>
        {label}
      </Typography>
    </Box>
    <Typography sx={{
      fontWeight: 500,
      color: '#1f2937',
      fontSize: '12px',
      textAlign: 'right',
      maxWidth: '220px',
      overflow: multiline ? 'visible' : 'hidden',
      textOverflow: multiline ? 'unset' : 'ellipsis',
      whiteSpace: multiline ? 'normal' : 'nowrap',
    }}>
      {value || '—'}
    </Typography>
  </Box>
);

const ProfileDetailsPanel = ({ profile, sessionId, open, onClose }) => {
  const [renderContent, setRenderContent] = useState(false);
  const [activeTab, setActiveTab] = useState('verification');
  const contentRef = useRef(null);
  const [panelWidth, setPanelWidth] = useState(360);
  const resizingRef = useRef(null);

  useEffect(() => {
    if (open) {
      setRenderContent(true);
      return undefined;
    }
    const timeout = window.setTimeout(() => {
      setRenderContent(false);
    }, 200);
    return () => window.clearTimeout(timeout);
  }, [open]);

  const baseProfile = profile ?? {};
  const profilePayload = baseProfile.profile ?? null;
  const data = profilePayload ?? {};
  const hasProfile = Boolean(profilePayload);
  const tier = resolveRelationshipTier(data);
  const ssnLast4 = data?.verification_codes?.ssn4 || '----';
  const verificationCodes = data?.verification_codes ?? {};
  const institutionName = data?.institution_name || 'Demo Institution';
  const companyCode = data?.company_code;
  const companyCodeLast4 = data?.company_code_last4 || companyCode?.slice?.(-4) || '----';
  const demoMeta = data?.demo_metadata ?? baseProfile.demo_metadata ?? {};
  const transactions = (Array.isArray(data?.transactions) && data.transactions.length
      ? data.transactions
      : Array.isArray(baseProfile.transactions) && baseProfile.transactions.length
        ? baseProfile.transactions
        : Array.isArray(demoMeta.transactions)
          ? demoMeta.transactions
          : []) ?? [];
  const interactionPlan = baseProfile.interactionPlan
    ?? demoMeta.interaction_plan
    ?? data?.interaction_plan
    ?? null;
  const entryId = baseProfile.entryId ?? demoMeta.entry_id ?? demoMeta.entryId;
  const expiresAt = baseProfile.expiresAt ?? baseProfile.expires_at ?? demoMeta.expires_at;
  const compliance = data?.compliance ?? {};
  const mfaSettings = data?.mfa_settings ?? {};
  const customerIntel = data?.customer_intelligence ?? {};
  const coreIdentity = customerIntel.core_identity ?? {};
  const bankProfile = customerIntel.bank_profile ?? {};
  const accounts = customerIntel.accounts ?? {};
  const employment = customerIntel.employment ?? {};
  const payrollSetup = customerIntel.payroll_setup ?? {};
  const retirementProfile = customerIntel.retirement_profile ?? {};
  const preferences = customerIntel.preferences ?? {};
  const relationshipContext = customerIntel.relationship_context ?? {};
  const accountStatus = customerIntel.account_status ?? {};
  const spendingPatterns = customerIntel.spending_patterns ?? {};
  const memoryScore = customerIntel.memory_score ?? {};
  const fraudContext = customerIntel.fraud_context ?? {};
  const conversationContext = customerIntel.conversation_context ?? {};
  const activeAlerts = customerIntel.active_alerts ?? [];
  const knownPreferences = conversationContext.known_preferences ?? [];
  const suggestedTalkingPoints = conversationContext.suggested_talking_points ?? [];
  const financialGoals = conversationContext.financial_goals ?? [];
  const lifeEvents = conversationContext.life_events ?? [];

  // Scenario-based data (banking vs insurance)
  const scenario = baseProfile.scenario ?? data?.scenario ?? 'banking';
  const isBankingScenario = scenario === 'banking';
  const isInsuranceScenario = scenario === 'insurance';
  
  // Insurance-specific data
  const policies = (Array.isArray(baseProfile.policies) && baseProfile.policies.length
    ? baseProfile.policies
    : Array.isArray(data?.policies)
      ? data.policies
      : []) ?? [];
  const claims = (Array.isArray(baseProfile.claims) && baseProfile.claims.length
    ? baseProfile.claims
    : Array.isArray(data?.claims)
      ? data.claims
      : []) ?? [];
  const typicalBehavior = fraudContext.typical_transaction_behavior ?? {};
  const sessionDisplayId = baseProfile.sessionId ?? sessionId;
  const profileId = data?._id ?? data?.id ?? data?.client_id ?? baseProfile.sessionId;
  const createdAt = data?.created_at ?? data?.createdAt;
  const updatedAt = data?.updated_at ?? data?.updatedAt;
  const topLevelLastLogin = data?.last_login ?? data?.lastLogin;
  const loginAttempts = data?.login_attempts ?? data?.loginAttempts;
  const ttlValue = data?.ttl ?? data?.TTL;
  const recordExpiresAt = data?.expires_at ?? data?.expiresAt ?? expiresAt;
  const safetyNotice = baseProfile.safetyNotice ?? demoMeta.safety_notice;
  const profileIdentityKey = `${profileId ?? ''}-${sessionDisplayId ?? ''}`;

  useEffect(() => {
    setActiveTab('verification');
  }, [profileIdentityKey]);

  const tabs = useMemo(
    () => [
      {
        id: 'verification',
        label: 'Verification',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="🛡️">Verification Tokens</SectionTitle>
              <ProfileDetailRow label="SSN Last 4" value={ssnLast4} />
              <ProfileDetailRow label="Institution" value={institutionName} />
              <ProfileDetailRow label="Employee ID Last 4" value={verificationCodes.employee_id4 || '----'} />
              <ProfileDetailRow label="Phone Last 4" value={verificationCodes.phone4 || '----'} />
              <ProfileDetailRow label="Company Code Last 4" value={companyCodeLast4} />
            </SectionCard>

            {mfaSettings && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="🔐">MFA Settings</SectionTitle>
                <ProfileDetailRow label="Enabled" value={mfaSettings.enabled ? 'Yes' : 'No'} />
                <ProfileDetailRow label="Preferred Method" value={data?.contact_info?.preferred_mfa_method ?? '—'} />
                <ProfileDetailRow label="Secret Key" value={maskSecretValue(mfaSettings.secret_key)} multiline />
                <ProfileDetailRow label="Code Expiry (min)" value={mfaSettings.code_expiry_minutes} />
                <ProfileDetailRow label="Max Attempts" value={mfaSettings.max_attempts} />
              </SectionCard>
            )}
          </>
        ),
      },
      {
        id: 'identity',
        label: 'Identity',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="🪪">Identity Snapshot</SectionTitle>
              <ProfileDetailRow label="Profile ID" value={profileId} />
              <ProfileDetailRow label="Client ID" value={data?.client_id} />
              <ProfileDetailRow label="Company Code" value={data?.company_code} />
              <ProfileDetailRow label="Client Type" value={toTitleCase(data?.client_type)} />
              <ProfileDetailRow label="Authorization Level" value={toTitleCase(data?.authorization_level)} />
              <ProfileDetailRow label="Max Transaction Limit" value={formatCurrency(data?.max_transaction_limit)} />
              <ProfileDetailRow label="MFA Threshold" value={formatCurrency(data?.mfa_required_threshold)} />
              <ProfileDetailRow label="Demo Entry" value={entryId} />
              <ProfileDetailRow label="Demo Expiry" value={formatDateTime(expiresAt)} />
              <ProfileDetailRow label="Session" value={sessionDisplayId} multiline />
            </SectionCard>

            <SectionCard sx={{ mt: 2 }}>
              <SectionTitle icon="⚖️">Compliance</SectionTitle>
              <ProfileDetailRow label="KYC Verified" value={compliance.kyc_verified ? 'Yes' : 'No'} />
              <ProfileDetailRow label="AML Cleared" value={compliance.aml_cleared ? 'Yes' : 'No'} />
              <ProfileDetailRow label="Last Review" value={formatDate(compliance.last_review_date)} />
              <ProfileDetailRow label="Risk Rating" value={toTitleCase(compliance.risk_rating)} />
            </SectionCard>

            <SectionCard sx={{ mt: 2 }}>
              <SectionTitle icon="📂">Record Metadata</SectionTitle>
              <ProfileDetailRow label="Created" value={formatDateTime(createdAt)} />
              <ProfileDetailRow label="Updated" value={formatDateTime(updatedAt)} />
              <ProfileDetailRow label="Last Login" value={formatDateTime(topLevelLastLogin)} />
              <ProfileDetailRow label="Login Attempts" value={formatNumber(loginAttempts)} />
              <ProfileDetailRow label="TTL (s)" value={formatNumber(ttlValue)} />
              <ProfileDetailRow label="Record Expires" value={formatDateTime(recordExpiresAt)} />
            </SectionCard>
          </>
        ),
      },
      {
        id: 'banking',
        label: 'Banking',
        content: (
          <>
            {/* Core Identity */}
            {(coreIdentity.displayName || coreIdentity.segment) && (
              <SectionCard>
                <SectionTitle icon="👤">Core Identity</SectionTitle>
                <ProfileDetailRow label="Display Name" value={coreIdentity.displayName} />
                <ProfileDetailRow label="Segment" value={coreIdentity.segment} />
                <ProfileDetailRow label="Channel" value={toTitleCase(coreIdentity.channel)} />
                <ProfileDetailRow label="Language" value={coreIdentity.primaryLanguage} />
                <ProfileDetailRow label="Country" value={coreIdentity.country} />
              </SectionCard>
            )}

            {/* Bank Accounts */}
            {(bankProfile.current_balance !== undefined || bankProfile.accountTenureYears || accounts.checking || accounts.savings) && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="🏦">Bank Accounts</SectionTitle>
                
                {/* Checking Account */}
                {accounts.checking && (
                  <Box sx={{ mb: 2 }}>
                    <ProfileDetailRow label="Account Type" value="Checking" />
                    <ProfileDetailRow label="Last 4" value={`****${accounts.checking.account_number_last4}`} />
                    <ProfileDetailRow label="Balance" value={formatCurrency(accounts.checking.balance)} />
                    <ProfileDetailRow label="Available" value={formatCurrency(accounts.checking.available)} />
                    <ProfileDetailRow label="Routing" value={bankProfile.routing_number} />
                  </Box>
                )}
                
                {accounts.checking && accounts.savings && <Divider sx={{ my: 1.5 }} />}
                
                {/* Savings Account */}
                {accounts.savings && (
                  <Box>
                    <ProfileDetailRow label="Account Type" value="Savings" />
                    <ProfileDetailRow label="Last 4" value={`****${accounts.savings.account_number_last4}`} />
                    <ProfileDetailRow label="Balance" value={formatCurrency(accounts.savings.balance)} />
                    <ProfileDetailRow label="Available" value={formatCurrency(accounts.savings.available)} />
                  </Box>
                )}
                
                {/* Account Summary (fallback for older profiles) */}
                {!accounts.checking && !accounts.savings && (
                  <>
                    <ProfileDetailRow label="Balance" value={formatCurrency(bankProfile.current_balance)} />
                    <ProfileDetailRow label="Routing Number" value={bankProfile.routing_number} />
                    <ProfileDetailRow label="Account Last 4" value={`****${bankProfile.account_number_last4}`} />
                  </>
                )}
                
                <Divider sx={{ my: 1.5 }} />
                <ProfileDetailRow label="Account Tenure" value={bankProfile.accountTenureYears ? `${bankProfile.accountTenureYears} years` : '—'} />
                <ProfileDetailRow label="Direct Deposit" value={bankProfile.has_direct_deposit ? '✅ Active' : '❌ Not Set Up'} />
                <ProfileDetailRow label="Preferred Branch" value={bankProfile.preferred_branch} />
              </SectionCard>
            )}

            {/* Credit Cards */}
            {bankProfile.cards && bankProfile.cards.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="💳">Credit Cards</SectionTitle>
                {bankProfile.cards.map((card, idx) => (
                  <Box key={card.cardAccountId || idx} sx={{ mb: idx < bankProfile.cards.length - 1 ? 2 : 0 }}>
                    <ProfileDetailRow label="Card" value={card.productName} multiline />
                    <ProfileDetailRow label="Last 4" value={`****${card.last4}`} />
                    <ProfileDetailRow label="Opened" value={formatDate(card.openedDate)} />
                    <ProfileDetailRow label="Rewards" value={toTitleCase(card.rewardsType)} />
                    <ProfileDetailRow label="Annual Fee" value={card.hasAnnualFee ? 'Yes' : 'No'} />
                    <ProfileDetailRow label="Foreign Tx Fee" value={card.foreignTxFeePct ? `${card.foreignTxFeePct}%` : 'None'} />
                    {idx < bankProfile.cards.length - 1 && <Divider sx={{ mt: 1.5 }} />}
                  </Box>
                ))}
              </SectionCard>
            )}

            {/* Employment & Payroll */}
            {(employment.currentEmployerName || payrollSetup.hasDirectDeposit !== undefined) && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="💼">Employment & Payroll</SectionTitle>
                <ProfileDetailRow label="Current Employer" value={employment.currentEmployerName} />
                <ProfileDetailRow label="Start Date" value={formatDate(employment.currentEmployerStartDate)} />
                <ProfileDetailRow label="Previous Employer" value={employment.previousEmployerName} />
                <ProfileDetailRow label="Left On" value={formatDate(employment.previousEmployerEndDate)} />
                <ProfileDetailRow label="Income Band" value={toTitleCase(employment.incomeBand)} />
                <Divider sx={{ my: 1.5 }} />
                <ProfileDetailRow 
                  label="Direct Deposit" 
                  value={payrollSetup.hasDirectDeposit ? '✅ Active' : '❌ Not Set Up'} 
                />
                {payrollSetup.pendingSetup && (
                  <ProfileDetailRow label="Status" value="⚠️ Setup Pending" />
                )}
                {payrollSetup.lastPaycheckDate && (
                  <ProfileDetailRow label="Last Paycheck" value={formatDate(payrollSetup.lastPaycheckDate)} />
                )}
              </SectionCard>
            )}

            {/* Retirement Profile */}
            {retirementProfile.retirement_accounts && retirementProfile.retirement_accounts.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="💰">Retirement Accounts</SectionTitle>
                {retirementProfile.retirement_accounts.map((account, idx) => (
                  <Box key={account.accountId || idx} sx={{ mb: idx < retirementProfile.retirement_accounts.length - 1 ? 2 : 0 }}>
                    <ProfileDetailRow label="Type" value={account.type.toUpperCase()} />
                    <ProfileDetailRow label="Employer" value={account.employerName} />
                    <ProfileDetailRow label="Provider" value={account.provider} />
                    <ProfileDetailRow label="Status" value={toTitleCase(account.status)} />
                    <ProfileDetailRow label="Balance" value={formatCurrency(account.estimatedBalance)} />
                    <ProfileDetailRow label="Balance Band" value={account.balanceBand} />
                    <ProfileDetailRow label="Vesting" value={account.vestingStatus} />
                    {account.notes && (
                      <ProfileDetailRow label="Notes" value={account.notes} multiline />
                    )}
                    {idx < retirementProfile.retirement_accounts.length - 1 && <Divider sx={{ mt: 1.5 }} />}
                  </Box>
                ))}
                
                {retirementProfile.plan_features && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <SectionTitle icon="✨">Plan Features</SectionTitle>
                    <ProfileDetailRow 
                      label="401(k) Pay Available" 
                      value={retirementProfile.plan_features.has401kPayOnCurrentPlan ? '✅ Yes' : '❌ No'} 
                    />
                    <ProfileDetailRow 
                      label="Employer Match" 
                      value={retirementProfile.plan_features.currentEmployerMatchPct ? `${retirementProfile.plan_features.currentEmployerMatchPct}%` : '—'} 
                    />
                    <ProfileDetailRow 
                      label="Rollover Eligible" 
                      value={retirementProfile.plan_features.rolloverEligible ? 'Yes' : 'No'} 
                    />
                  </>
                )}

                {retirementProfile.merrill_accounts && retirementProfile.merrill_accounts.length > 0 && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <SectionTitle icon="📊">Merrill Accounts</SectionTitle>
                    {retirementProfile.merrill_accounts.map((account, idx) => (
                      <Box key={account.accountId || idx} sx={{ mb: idx < retirementProfile.merrill_accounts.length - 1 ? 1 : 0 }}>
                        <ProfileDetailRow label="Account Type" value={`${account.brand} ${toTitleCase(account.accountType)}`} />
                        <ProfileDetailRow label="Balance" value={formatCurrency(account.estimatedBalance)} />
                        {account.notes && <ProfileDetailRow label="Notes" value={account.notes} multiline />}
                        {idx < retirementProfile.merrill_accounts.length - 1 && <Divider sx={{ mt: 1 }} />}
                      </Box>
                    ))}
                  </>
                )}

                {(retirementProfile.risk_profile || retirementProfile.investmentKnowledgeLevel) && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <ProfileDetailRow label="Risk Profile" value={toTitleCase(retirementProfile.risk_profile)} />
                    <ProfileDetailRow label="Investment Knowledge" value={toTitleCase(retirementProfile.investmentKnowledgeLevel)} />
                  </>
                )}
              </SectionCard>
            )}

            {/* Preferences */}
            {(preferences.preferredContactMethod || preferences.adviceStyle) && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="⚙️">Preferences</SectionTitle>
                <ProfileDetailRow label="Contact Method" value={toTitleCase(preferences.preferredContactMethod)} />
                <ProfileDetailRow label="Advice Style" value={toTitleCase(preferences.adviceStyle)} />
                <ProfileDetailRow 
                  label="Prefers Human for Investments" 
                  value={preferences.prefersHumanForInvestments ? 'Yes' : 'No'} 
                />
                <ProfileDetailRow 
                  label="Decision Threshold" 
                  value={formatCurrency(preferences.prefersHumanForDecisionsOverThreshold)} 
                />
                {preferences.previousAdvisorInteractions && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <ProfileDetailRow 
                      label="Has Merrill Advisor" 
                      value={preferences.previousAdvisorInteractions.hasMerrillAdvisor ? 'Yes' : 'No'} 
                    />
                    <ProfileDetailRow 
                      label="Interested in Advisor" 
                      value={preferences.previousAdvisorInteractions.interestedInAdvisor ? 'Yes' : 'No'} 
                    />
                  </>
                )}
              </SectionCard>
            )}

            {/* Active Alerts */}
            {activeAlerts.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="🚨">Active Alerts</SectionTitle>
                {activeAlerts.map((alert, idx) => (
                  <Box key={idx} sx={{ 
                    mb: idx < activeAlerts.length - 1 ? 1.5 : 0,
                    p: 1.5,
                    borderRadius: '12px',
                    backgroundColor: alert.priority === 'high' ? 'rgba(239, 68, 68, 0.08)' : 'rgba(251, 191, 36, 0.08)',
                    border: `1px solid ${alert.priority === 'high' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(251, 191, 36, 0.2)'}`,
                  }}>
                    <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#0f172a', mb: 0.5 }}>
                      {alert.priority === 'high' ? '🔴' : '🟡'} {toTitleCase(alert.type)}
                    </Typography>
                    <Typography sx={{ fontSize: '11px', color: '#475569', mb: 0.5 }}>
                      {alert.message}
                    </Typography>
                    <Typography sx={{ fontSize: '10px', color: '#64748b', fontWeight: 600 }}>
                      Action: {alert.action}
                    </Typography>
                  </Box>
                ))}
              </SectionCard>
            )}

            {/* Conversation Context */}
            {(financialGoals.length > 0 || lifeEvents.length > 0 || suggestedTalkingPoints.length > 0) && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="💬">Conversation Context</SectionTitle>
                
                {lifeEvents.length > 0 && (
                  <>
                    <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 1 }}>
                      Recent Life Events
                    </Typography>
                    {lifeEvents.map((event, idx) => (
                      <Box key={idx} sx={{ mb: 1 }}>
                        <ProfileDetailRow label={toTitleCase(event.event)} value={formatDate(event.date)} />
                        {event.details && (
                          <Typography sx={{ fontSize: '10px', color: '#64748b', ml: 2, mt: 0.5 }}>
                            {event.details}
                          </Typography>
                        )}
                      </Box>
                    ))}
                  </>
                )}

                {suggestedTalkingPoints.length > 0 && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 1 }}>
                      Suggested Talking Points
                    </Typography>
                    {suggestedTalkingPoints.slice(0, 5).map((point, idx) => (
                      <Typography key={idx} sx={{ fontSize: '11px', color: '#1f2937', mb: 0.5, pl: 2 }}>
                        • {point}
                      </Typography>
                    ))}
                  </>
                )}

                {financialGoals.length > 0 && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 1 }}>
                      Financial Goals
                    </Typography>
                    {financialGoals.map((goal, idx) => (
                      <Typography key={idx} sx={{ fontSize: '11px', color: '#1f2937', mb: 0.5, pl: 2 }}>
                        • {goal}
                      </Typography>
                    ))}
                  </>
                )}

                {knownPreferences.length > 0 && (
                  <>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 1 }}>
                      Known Preferences
                    </Typography>
                    {knownPreferences.map((pref, idx) => (
                      <Typography key={idx} sx={{ fontSize: '11px', color: '#1f2937', mb: 0.5, pl: 2 }}>
                        • {pref}
                      </Typography>
                    ))}
                  </>
                )}
              </SectionCard>
            )}
          </>
        ),
      },
      {
        id: 'contact',
        label: 'Contact',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="📞">Contact</SectionTitle>
              <ProfileDetailRow label="Email" value={data?.contact_info?.email} multiline />
              <ProfileDetailRow label="Phone" value={data?.contact_info?.phone} />
              <ProfileDetailRow label="Preferred MFA Method" value={toTitleCase(data?.contact_info?.preferred_mfa_method)} />
            </SectionCard>

            {interactionPlan && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="🗓️">Interaction Plan</SectionTitle>
                <ProfileDetailRow label="Primary Channel" value={toTitleCase(interactionPlan.primary_channel)} />
                <ProfileDetailRow label="Fallback Channel" value={toTitleCase(interactionPlan.fallback_channel)} />
                <ProfileDetailRow label="MFA Required" value={interactionPlan.mfa_required ? 'Yes' : 'No'} />
                <ProfileDetailRow label="Notification" value={interactionPlan.notification_message} multiline />
              </SectionCard>
            )}
          </>
        ),
      },
      {
        id: 'transactions',
        label: 'Transactions',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="💳">Recent Transactions</SectionTitle>
              {transactions.length ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {transactions.map((txn) => {
                    const location = txn.location || {};
                    const isInternational = location.is_international || location.country_code !== 'US';
                    const hasFee = txn.foreign_transaction_fee && txn.foreign_transaction_fee > 0;
                    const locationStr = location.city 
                      ? `${location.city}, ${location.country || location.state || ''}`
                      : location.country || '—';
                    
                    return (
                      <Box
                        key={txn.transaction_id}
                        sx={{
                          border: '1px solid',
                          borderColor: hasFee ? 'rgba(239, 68, 68, 0.3)' : 'rgba(226,232,240,0.9)',
                          borderRadius: '14px',
                          padding: '12px 14px',
                          backgroundColor: hasFee ? 'rgba(254, 242, 242, 0.5)' : '#fff',
                          boxShadow: '0 6px 16px rgba(15,23,42,0.08)',
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
                          <Box sx={{ flex: 1 }}>
                            <Typography sx={{ fontWeight: 700, color: '#0f172a', fontSize: '13px' }}>
                              {isInternational && '🌍 '}{txn.merchant}
                            </Typography>
                            <Typography sx={{ color: '#64748b', fontSize: '10px', mt: 0.3 }}>
                              📍 {locationStr}
                            </Typography>
                          </Box>
                          <Box sx={{ textAlign: 'right' }}>
                            <Typography sx={{ fontWeight: 700, color: '#111827', fontSize: '12px' }}>
                              {formatCurrencyWithCents(txn.amount)}
                            </Typography>
                            {txn.original_currency && txn.original_currency !== 'USD' && (
                              <Typography sx={{ color: '#64748b', fontSize: '9px', fontStyle: 'italic' }}>
                                {txn.original_amount} {txn.original_currency}
                              </Typography>
                            )}
                          </Box>
                        </Box>
                        
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
                          <Typography sx={{ color: '#64748b', fontSize: '10px' }}>
                            {formatDateTime(txn.timestamp)} • {toTitleCase(txn.category)}
                          </Typography>
                          <Typography sx={{ color: '#64748b', fontSize: '9px', fontWeight: 600 }}>
                            Card ****{txn.card_last4}
                          </Typography>
                        </Box>
                        
                        {hasFee && (
                          <Box sx={{ 
                            mt: 1, 
                            pt: 1, 
                            borderTop: '1px solid rgba(239, 68, 68, 0.2)',
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center'
                          }}>
                            <Typography sx={{ color: '#dc2626', fontSize: '10px', fontWeight: 700 }}>
                              ⚠️ {txn.fee_reason || 'Foreign Transaction Fee'}
                            </Typography>
                            <Typography sx={{ color: '#dc2626', fontSize: '11px', fontWeight: 700 }}>
                              +{formatCurrencyWithCents(txn.foreign_transaction_fee)}
                            </Typography>
                          </Box>
                        )}
                        
                        {txn.notes && (
                          <Typography sx={{ color: '#64748b', fontSize: '9px', mt: 0.5, fontStyle: 'italic' }}>
                            Note: {txn.notes}
                          </Typography>
                        )}
                      </Box>
                    );
                  })}
                </Box>
              ) : (
                <Typography sx={{ fontSize: '11px', color: '#94a3b8' }}>
                  No transactions available for this profile yet.
                </Typography>
              )}
            </SectionCard>
            
            {transactions.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="📊">Transaction Summary</SectionTitle>
                <ProfileDetailRow 
                  label="Total Transactions" 
                  value={transactions.length.toString()} 
                />
                <ProfileDetailRow 
                  label="International" 
                  value={transactions.filter(t => t.location?.is_international).length.toString()} 
                />
                <ProfileDetailRow 
                  label="Total Fees" 
                  value={formatCurrencyWithCents(
                    transactions.reduce((sum, t) => sum + (t.foreign_transaction_fee || 0), 0)
                  )} 
                />
                <ProfileDetailRow 
                  label="Total Spent" 
                  value={formatCurrencyWithCents(
                    transactions.reduce((sum, t) => sum + t.amount, 0)
                  )} 
                />
              </SectionCard>
            )}
          </>
        ),
      },
      // ═══════════════════════════════════════════════════════════════════════════════
      // INSURANCE SCENARIO TABS
      // ═══════════════════════════════════════════════════════════════════════════════
      {
        id: 'policies',
        label: 'Policies',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="📋">Insurance Policies</SectionTitle>
              {policies.length ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {policies.map((policy, idx) => {
                    const isActive = policy.status === 'active';
                    const isPending = policy.status === 'pending';
                    return (
                      <Box
                        key={policy.policy_number || idx}
                        sx={{
                          border: '1px solid',
                          borderColor: isActive 
                            ? 'rgba(16, 185, 129, 0.3)' 
                            : isPending 
                              ? 'rgba(251, 191, 36, 0.3)'
                              : 'rgba(226,232,240,0.9)',
                          borderRadius: '14px',
                          padding: '12px 14px',
                          backgroundColor: isActive 
                            ? 'rgba(240, 253, 244, 0.5)' 
                            : isPending
                              ? 'rgba(254, 252, 232, 0.5)'
                              : '#fff',
                          boxShadow: '0 6px 16px rgba(15,23,42,0.08)',
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
                          <Box sx={{ flex: 1 }}>
                            <Typography sx={{ fontWeight: 700, color: '#0f172a', fontSize: '13px' }}>
                              {toTitleCase(policy.policy_type)} Policy
                            </Typography>
                            <Typography sx={{ color: '#64748b', fontSize: '10px', mt: 0.3 }}>
                              # {policy.policy_number}
                            </Typography>
                          </Box>
                          <Chip
                            label={toTitleCase(policy.status)}
                            size="small"
                            sx={{
                              backgroundColor: isActive 
                                ? 'rgba(16, 185, 129, 0.15)' 
                                : isPending
                                  ? 'rgba(251, 191, 36, 0.15)'
                                  : 'rgba(239, 68, 68, 0.15)',
                              color: isActive 
                                ? '#059669' 
                                : isPending
                                  ? '#d97706'
                                  : '#dc2626',
                              fontSize: '9px',
                              fontWeight: 700,
                              height: '20px',
                            }}
                          />
                        </Box>
                        
                        <Divider sx={{ my: 1 }} />
                        
                        <ProfileDetailRow label="Premium" value={formatCurrency(policy.premium_amount)} />
                        <ProfileDetailRow label="Deductible" value={formatCurrency(policy.deductible)} />
                        <ProfileDetailRow label="Effective" value={formatDate(policy.effective_date)} />
                        <ProfileDetailRow label="Expires" value={formatDate(policy.expiration_date)} />
                        
                        {policy.coverage_limits && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                              Coverage Limits
                            </Typography>
                            {Object.entries(policy.coverage_limits).map(([key, val]) => (
                              <ProfileDetailRow 
                                key={key} 
                                label={toTitleCase(key)} 
                                value={typeof val === 'number' ? formatCurrency(val) : String(val)} 
                              />
                            ))}
                          </>
                        )}
                        
                        {policy.vehicles && policy.vehicles.length > 0 && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                              🚗 Vehicles
                            </Typography>
                            {policy.vehicles.map((vehicle, vIdx) => (
                              <Typography key={vIdx} sx={{ fontSize: '11px', color: '#1f2937', mb: 0.3 }}>
                                {vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.vin?.slice(-6) || 'N/A'})
                              </Typography>
                            ))}
                          </>
                        )}
                        
                        {policy.property_address && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <ProfileDetailRow label="🏠 Property" value={policy.property_address} multiline />
                          </>
                        )}
                      </Box>
                    );
                  })}
                </Box>
              ) : (
                <Typography sx={{ fontSize: '11px', color: '#94a3b8' }}>
                  No policies available for this profile.
                </Typography>
              )}
            </SectionCard>
            
            {policies.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="📊">Policy Summary</SectionTitle>
                <ProfileDetailRow 
                  label="Total Policies" 
                  value={policies.length.toString()} 
                />
                <ProfileDetailRow 
                  label="Active" 
                  value={policies.filter(p => p.status === 'active').length.toString()} 
                />
                <ProfileDetailRow 
                  label="Total Premium" 
                  value={formatCurrency(
                    policies.filter(p => p.status === 'active').reduce((sum, p) => sum + (p.premium_amount || 0), 0)
                  )} 
                />
              </SectionCard>
            )}
          </>
        ),
      },
      {
        id: 'claims',
        label: 'Claims',
        content: (
          <>
            <SectionCard>
              <SectionTitle icon="📝">Insurance Claims</SectionTitle>
              {claims.length ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  {claims.map((claim, idx) => {
                    const isOpen = claim.status === 'open' || claim.status === 'under_investigation';
                    const isDenied = claim.status === 'denied';
                    const hasSubro = claim.subro_demand?.received;
                    return (
                      <Box
                        key={claim.claim_number || idx}
                        sx={{
                          border: '1px solid',
                          borderColor: isOpen 
                            ? 'rgba(59, 130, 246, 0.3)' 
                            : isDenied
                              ? 'rgba(239, 68, 68, 0.3)'
                              : 'rgba(16, 185, 129, 0.3)',
                          borderRadius: '14px',
                          padding: '12px 14px',
                          backgroundColor: isOpen 
                            ? 'rgba(239, 246, 255, 0.5)' 
                            : isDenied
                              ? 'rgba(254, 242, 242, 0.5)'
                              : 'rgba(240, 253, 244, 0.5)',
                          boxShadow: '0 6px 16px rgba(15,23,42,0.08)',
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
                          <Box sx={{ flex: 1 }}>
                            <Typography sx={{ fontWeight: 700, color: '#0f172a', fontSize: '13px' }}>
                              {toTitleCase(claim.claim_type)} Claim
                            </Typography>
                            <Typography sx={{ color: '#64748b', fontSize: '10px', mt: 0.3 }}>
                              # {claim.claim_number}
                            </Typography>
                          </Box>
                          <Chip
                            label={toTitleCase(claim.status?.replace(/_/g, ' '))}
                            size="small"
                            sx={{
                              backgroundColor: isOpen 
                                ? 'rgba(59, 130, 246, 0.15)' 
                                : isDenied
                                  ? 'rgba(239, 68, 68, 0.15)'
                                  : 'rgba(16, 185, 129, 0.15)',
                              color: isOpen 
                                ? '#2563eb' 
                                : isDenied
                                  ? '#dc2626'
                                  : '#059669',
                              fontSize: '9px',
                              fontWeight: 700,
                              height: '20px',
                            }}
                          />
                        </Box>
                        
                        <Typography sx={{ fontSize: '11px', color: '#475569', mt: 0.5, mb: 1 }}>
                          {claim.description}
                        </Typography>
                        
                        <Divider sx={{ my: 1 }} />
                        
                        <ProfileDetailRow label="Loss Date" value={formatDate(claim.loss_date)} />
                        <ProfileDetailRow label="Reported" value={formatDate(claim.reported_date)} />
                        <ProfileDetailRow label="Policy" value={claim.policy_number} />
                        <ProfileDetailRow label="Insured" value={claim.insured_name} />
                        
                        {claim.claimant_name && (
                          <ProfileDetailRow label="Claimant" value={claim.claimant_name} />
                        )}
                        {claim.claimant_carrier && (
                          <ProfileDetailRow label="Claimant Carrier" value={claim.claimant_carrier} />
                        )}
                        
                        <Divider sx={{ my: 1 }} />
                        
                        <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                          💰 Financials
                        </Typography>
                        <ProfileDetailRow label="Estimated" value={formatCurrency(claim.estimated_amount)} />
                        <ProfileDetailRow label="Paid" value={formatCurrency(claim.paid_amount)} />
                        {claim.deductible_applied && (
                          <ProfileDetailRow label="Deductible Applied" value={formatCurrency(claim.deductible_applied)} />
                        )}
                        
                        {(claim.pd_limits || claim.bi_limits) && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                              📊 Policy Limits
                            </Typography>
                            {claim.pd_limits && <ProfileDetailRow label="PD Limit" value={formatCurrency(claim.pd_limits)} />}
                            {claim.bi_limits && <ProfileDetailRow label="BI Limit" value={formatCurrency(claim.bi_limits)} />}
                          </>
                        )}
                        
                        <Divider sx={{ my: 1 }} />
                        
                        <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                          ⚖️ Coverage & Liability
                        </Typography>
                        <ProfileDetailRow label="Coverage Status" value={toTitleCase(claim.coverage_status)} />
                        {claim.cvq_status && (
                          <ProfileDetailRow label="CVQ Status" value={claim.cvq_status} />
                        )}
                        <ProfileDetailRow label="Liability Decision" value={toTitleCase(claim.liability_decision)} />
                        {claim.liability_percentage !== null && claim.liability_percentage !== undefined && (
                          <ProfileDetailRow label="Liability %" value={`${claim.liability_percentage}%`} />
                        )}
                        
                        {claim.feature_owners && Object.keys(claim.feature_owners).length > 0 && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                              👤 Feature Owners
                            </Typography>
                            {Object.entries(claim.feature_owners).map(([feature, owner]) => (
                              <ProfileDetailRow key={feature} label={feature} value={owner} />
                            ))}
                          </>
                        )}
                        
                        {hasSubro && (
                          <Box sx={{ 
                            mt: 1.5, 
                            p: 1.5,
                            borderRadius: '10px',
                            backgroundColor: 'rgba(245, 158, 11, 0.08)',
                            border: '1px solid rgba(245, 158, 11, 0.2)',
                          }}>
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#b45309', mb: 0.5 }}>
                              📨 Subrogation Demand
                            </Typography>
                            <ProfileDetailRow label="Amount" value={formatCurrency(claim.subro_demand.amount)} />
                            <ProfileDetailRow label="Received" value={formatDate(claim.subro_demand.received_date)} />
                            <ProfileDetailRow label="Status" value={toTitleCase(claim.subro_demand.status)} />
                            {claim.subro_demand.assigned_to && (
                              <ProfileDetailRow label="Assigned To" value={claim.subro_demand.assigned_to} />
                            )}
                          </Box>
                        )}
                        
                        {claim.payments && claim.payments.length > 0 && (
                          <>
                            <Divider sx={{ my: 1 }} />
                            <Typography sx={{ fontSize: '10px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                              💳 Payments
                            </Typography>
                            {claim.payments.map((pmt, pIdx) => (
                              <Box key={pIdx} sx={{ mb: 0.5 }}>
                                <ProfileDetailRow 
                                  label={formatDate(pmt.date)} 
                                  value={`${formatCurrency(pmt.amount)} - ${toTitleCase(pmt.type || 'Payment')}`} 
                                />
                              </Box>
                            ))}
                          </>
                        )}
                      </Box>
                    );
                  })}
                </Box>
              ) : (
                <Typography sx={{ fontSize: '11px', color: '#94a3b8' }}>
                  No claims available for this profile.
                </Typography>
              )}
            </SectionCard>
            
            {claims.length > 0 && (
              <SectionCard sx={{ mt: 2 }}>
                <SectionTitle icon="📊">Claims Summary</SectionTitle>
                <ProfileDetailRow 
                  label="Total Claims" 
                  value={claims.length.toString()} 
                />
                <ProfileDetailRow 
                  label="Open" 
                  value={claims.filter(c => c.status === 'open' || c.status === 'under_investigation').length.toString()} 
                />
                <ProfileDetailRow 
                  label="Total Demand" 
                  value={formatCurrency(
                    claims.reduce((sum, c) => sum + (c.subro_demand?.amount || c.estimated_amount || 0), 0)
                  )} 
                />
                <ProfileDetailRow 
                  label="Total Paid" 
                  value={formatCurrency(
                    claims.reduce((sum, c) => {
                      // Sum all payments from payments array
                      const paymentsTotal = (c.payments || []).reduce((pSum, p) => pSum + (p.amount || 0), 0);
                      return sum + paymentsTotal;
                    }, 0)
                  )} 
                />
                <ProfileDetailRow 
                  label="Subro Demands" 
                  value={claims.filter(c => c.subro_demand?.received).length.toString()} 
                />
              </SectionCard>
            )}
          </>
        ),
      },
    ],
    [
      activeAlerts,
      bankProfile,
      claims,
      coreIdentity,
      companyCodeLast4,
      compliance,
      conversationContext,
      createdAt,
      data,
      employment,
      entryId,
      expiresAt,
      financialGoals,
      institutionName,
      interactionPlan,
      knownPreferences,
      lifeEvents,
      loginAttempts,
      mfaSettings,
      payrollSetup,
      policies,
      preferences,
      profileId,
      recordExpiresAt,
      retirementProfile,
      scenario,
      sessionDisplayId,
      ssnLast4,
      suggestedTalkingPoints,
      topLevelLastLogin,
      transactions,
      ttlValue,
      updatedAt,
      verificationCodes,
    ],
  );

  // Filter tabs based on scenario
  const visibleTabs = useMemo(() => {
    if (isInsuranceScenario) {
      // Insurance: show verification, identity, policies, claims, contact
      return tabs.filter(tab => ['verification', 'identity', 'policies', 'claims', 'contact'].includes(tab.id));
    }
    // Banking (default): show verification, identity, banking, transactions, contact
    return tabs.filter(tab => ['verification', 'identity', 'banking', 'transactions', 'contact'].includes(tab.id));
  }, [tabs, isInsuranceScenario]);

  const activeTabContent = visibleTabs.find((tab) => tab.id === activeTab)?.content;

  if (!hasProfile) {
    return null;
  }

  const panel = (
    <Box
      sx={{
        position: 'fixed',
        top: '0px',
        right: '0px',
        width: `${panelWidth}px`,
        height: '100vh',
        maxHeight: '100vh',
        background: 'linear-gradient(180deg, #f8fafc, #ffffff)',
        borderRadius: '0px',
        border: '1px solid rgba(226,232,240,0.9)',
        boxShadow: '8px 0 24px rgba(15,23,42,0.12)',
        zIndex: 1200,
        transform: open ? 'translateY(0)' : 'translateY(12px)',
        opacity: open ? 1 : 0,
        pointerEvents: open ? 'auto' : 'none',
        transition: 'opacity 0.25s ease, transform 0.25s ease',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        backdropFilter: 'blur(8px)',
        minWidth: '320px',
        maxWidth: '520px',
      }}
    >
      {/* Left-edge resize handle */}
      <Box
        onMouseDown={(e) => {
          resizingRef.current = {
            startX: e.clientX,
            startWidth: panelWidth,
          };
          const onMove = (evt) => {
            if (!resizingRef.current) return;
            const delta = evt.clientX - resizingRef.current.startX;
            const next = Math.min(
              520,
              Math.max(320, resizingRef.current.startWidth - delta),
            );
            setPanelWidth(next);
          };
          const onUp = () => {
            resizingRef.current = null;
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
          };
          window.addEventListener('mousemove', onMove);
          window.addEventListener('mouseup', onUp);
        }}
        sx={{
          position: 'absolute',
          left: '-6px',
          top: 0,
          bottom: 0,
          width: '12px',
          cursor: 'ew-resize',
          zIndex: 3,
        }}
      />
        {renderContent && (
          <>
            <Box sx={{
              padding: '18px',
              background: 'linear-gradient(150deg, #eef2ff 0%, rgba(238,242,255,0.7) 40%, #f8fafc 100%)',
              borderBottom: '1px solid rgba(226,232,240,0.9)',
              position: 'relative',
              overflow: 'hidden',
            }}>
              <Box
                sx={{
                  position: 'absolute',
                  inset: 0,
                  background: 'radial-gradient(circle at top right, rgba(99,102,241,0.25), transparent 45%)',
                  pointerEvents: 'none',
                }}
              />
              <Box sx={{ position: 'relative', zIndex: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2 }}>
                    <Typography variant="h6" sx={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.02em' }}>
                      Profile Details
                    </Typography>
                    {expiresAt && (
                      <SummaryStat
                        label="Expiration"
                        value={formatDateTime(expiresAt)}
                        icon="⏱️"
                        tooltip={`Expiration time in ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}
                      />
                    )}
                  </Box>
                  <IconButton
                    size="small"
                    aria-label="Close profile details"
                    onClick={onClose}
                    sx={{
                      color: '#0f172a',
                      backgroundColor: 'rgba(255,255,255,0.9)',
                      border: '1px solid rgba(148,163,184,0.4)',
                      '&:hover': {
                        backgroundColor: '#fff',
                      },
                    }}
                  >
                    <CloseRoundedIcon fontSize="small" />
                  </IconButton>
                </Box>

                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Avatar
                    sx={{
                      width: 48,
                      height: 48,
                      bgcolor: getTierColor(tier),
                      color: tier?.toLowerCase() === 'platinum' ? '#1f2937' : '#fff',
                      fontSize: '18px',
                      fontWeight: 700,
                      boxShadow: '0 10px 20px rgba(15,23,42,0.15)',
                    }}
                  >
                    {getInitials(data?.full_name)}
                  </Avatar>
                  <Box sx={{ flex: 1 }}>
                  <Typography variant="h6" sx={{ fontSize: '16px', fontWeight: 800, color: '#0f172a', lineHeight: 1.1 }}>
                    {data?.full_name || 'Demo User'}
                  </Typography>
                  {data?.contact_info?.email && (
                    <Typography sx={{ fontSize: '11px', color: '#475569', fontWeight: 600 }}>
                      {data.contact_info.email}
                    </Typography>
                  )}
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8, mt: 1 }}>
                      <Chip
                        label={tier}
                        size="small"
                        sx={{
                          backgroundColor: getTierColor(tier),
                          color: tier?.toLowerCase() === 'platinum' ? '#1f2937' : '#111827',
                          fontSize: '10px',
                          fontWeight: 700,
                          height: '22px',
                        }}
                      />
                      {ssnLast4 && (
                        <Chip
                          label={`SSN · ***${ssnLast4}`}
                          size="small"
                          sx={{
                            backgroundColor: 'rgba(59,130,246,0.15)',
                            color: '#1d4ed8',
                            fontSize: '10px',
                            fontWeight: 700,
                            height: '22px',
                          }}
                        />
                      )}
                      {institutionName && isBankingScenario && (
                        <Chip
                          label={
                            companyCodeLast4
                              ? `${institutionName} · Co ***${companyCodeLast4}`
                              : institutionName
                          }
                          size="small"
                          sx={{
                            backgroundColor: 'rgba(15,118,110,0.12)',
                            color: '#0f766e',
                            fontSize: '10px',
                            fontWeight: 700,
                            height: '22px',
                          }}
                        />
                      )}
                      {/* Scenario Badge */}
                      <Chip
                        label={isInsuranceScenario ? '🛡️ Insurance' : '🏦 Banking'}
                        size="small"
                        sx={{
                          backgroundColor: isInsuranceScenario 
                            ? 'rgba(245, 158, 11, 0.15)' 
                            : 'rgba(139, 92, 246, 0.15)',
                          color: isInsuranceScenario ? '#b45309' : '#7c3aed',
                          fontSize: '10px',
                          fontWeight: 700,
                          height: '22px',
                        }}
                      />
                    </Box>
                  </Box>
                </Box>

              </Box>
            </Box>

            <Box
              sx={{
                padding: '12px 20px 10px',
                borderBottom: '1px solid #e2e8f0',
                background: 'linear-gradient(135deg, rgba(248,250,252,0.95), rgba(238,242,255,0.9))',
              }}
            >
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                  gap: '10px',
                }}
              >
                {visibleTabs.map((tab) => {
                  const isActive = activeTab === tab.id;
                  const { icon = '•', accent = '#6366f1' } = TAB_META[tab.id] || {};
                  return (
                    <Box
                      key={tab.id}
                      component="button"
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      sx={{
                        border: '1px solid',
                        borderColor: isActive ? `${accent}66` : 'rgba(148,163,184,0.4)',
                        borderRadius: '14px',
                        background: isActive
                          ? `linear-gradient(135deg, ${accent}, ${accent}dd)`
                          : 'rgba(148,163,184,0.15)',
                        color: isActive ? '#fff' : '#0f172a',
                        fontSize: '11px',
                        fontWeight: 600,
                        letterSpacing: '0.04em',
                        padding: '8px 12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        cursor: 'pointer',
                        boxShadow: isActive
                          ? `0 10px 18px ${accent}33`
                          : 'inset 0 1px 0 rgba(255,255,255,0.6)',
                        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                        textTransform: 'uppercase',
                        backgroundSize: '200% 200%',
                        '&:hover': {
                          transform: 'translateY(-1px)',
                          boxShadow: isActive
                            ? `0 14px 24px ${accent}55`
                            : '0 6px 12px rgba(15,23,42,0.15)',
                        },
                      }}
                    >
                      <Box component="span" sx={{ fontSize: '13px' }}>
                        {icon}
                      </Box>
                      {tab.label}
                    </Box>
                  );
                })}
              </Box>
            </Box>

            <Box
              ref={contentRef}
              sx={{
                flex: 1,
                padding: '20px',
                overflowY: 'auto',
                scrollbarWidth: 'none',
                '&::-webkit-scrollbar': { display: 'none' },
                overscrollBehavior: 'contain',
                scrollBehavior: 'smooth',
                WebkitOverflowScrolling: 'touch',
                display: 'flex',
                flexDirection: 'column',
                gap: 2.5,
              }}
            >
              {activeTabContent}
              {safetyNotice && (
                <Box
                  sx={{
                    marginTop: '8px',
                    padding: '12px 16px',
                    borderRadius: '8px',
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    color: '#b91c1c',
                    fontSize: '11px',
                    fontWeight: 600,
                    textAlign: 'center',
                  }}
                >
                  {safetyNotice}
                </Box>
              )}
            </Box>
          </>
        )}
      </Box>
    );

  return createPortal(panel, document.body);
};

export default ProfileDetailsPanel;
