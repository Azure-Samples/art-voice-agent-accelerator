import React, { useMemo, useState } from 'react';
import { Tooltip, IconButton } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

const formStyles = {
  container: {
    margin: '0',
    padding: '24px 28px 28px 28px',
    maxWidth: '420px',
    width: '420px',
    borderRadius: '20px',
    border: '1px solid rgba(226, 232, 240, 0.85)',
    backgroundColor: '#ffffff',
    boxShadow: '0 8px 28px rgba(15, 23, 42, 0.12)',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    position: 'relative',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: '20px',
    marginBottom: '4px',
  },
  titleSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    flex: 1,
  },
  title: {
    fontSize: '20px',
    fontWeight: 700,
    color: '#1e293b',
    margin: 0,
    letterSpacing: '-0.025em',
  },
  subtitle: {
    fontSize: '13px',
    color: '#64748b',
    margin: 0,
    lineHeight: 1.5,
    fontWeight: 400,
  },
  closeButton: {
    background: '#f1f5f9',
    border: 'none',
    color: '#64748b',
    fontSize: '16px',
    lineHeight: 1,
    cursor: 'pointer',
    padding: '8px',
    borderRadius: '8px',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '32px',
    height: '32px',
    flexShrink: 0,
  },
  closeButtonHover: {
    background: '#fee2e2',
    color: '#ef4444',
    transform: 'scale(1.05)',
  },
  warning: {
    fontSize: '12px',
    color: '#dc2626',
    background: '#fef2f2',
    border: '1px solid #fecaca',
    borderRadius: '12px',
    padding: '12px 16px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontWeight: 500,
  },
  form: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
    marginTop: '8px',
  },
  formRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    position: 'relative',
  },
  formRowFull: {
    gridColumn: '1 / -1',
  },
  label: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#374151',
    letterSpacing: '0.025em',
    marginBottom: '2px',
    transition: 'color 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  labelFocused: {
    color: '#3b82f6',
  },
  labelText: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    whiteSpace: 'nowrap',
  },
  labelExtras: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  requiredBadge: {
    padding: '2px 6px',
    borderRadius: '999px',
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    color: '#b91c1c',
    fontSize: '10px',
    letterSpacing: '0.08em',
    fontWeight: 700,
    textTransform: 'uppercase',
  },
  inputContainer: {
    position: 'relative',
  },
  input: {
    width: '100%',
    padding: '14px 16px',
    borderRadius: '12px',
    border: '2px solid #e5e7eb',
    fontSize: '14px',
    color: '#1f2937',
    outline: 'none',
    background: '#ffffff',
    boxShadow: 'inset 0 1px 2px rgba(15, 23, 42, 0.05)',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    fontWeight: 500,
    WebkitTextFillColor: '#1f2937',
    MozAppearance: 'none',
    appearance: 'none',
    boxSizing: 'border-box',
  },
  inputFocused: {
    borderColor: '#3b82f6',
    background: '#f8fafc',
    boxShadow: '0 0 0 3px rgba(59, 130, 246, 0.1)',
  },
  inputError: {
    borderColor: '#ef4444',
    background: 'rgba(254, 242, 242, 0.5)',
  },
  buttonRow: {
    gridColumn: '1 / -1',
    display: 'flex',
    justifyContent: 'flex-end',
    marginTop: '8px',
  },
  button: {
    padding: '16px 32px',
    borderRadius: '12px',
    border: 'none',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    backgroundColor: '#2563eb',
    color: '#ffffff',
    boxShadow: '0 4px 12px rgba(37, 99, 235, 0.25)',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    position: 'relative',
    overflow: 'hidden',
    letterSpacing: '0.025em',
    minWidth: '140px',
  },
  buttonHover: {
    transform: 'translateY(-1px)',
    boxShadow: '0 6px 16px rgba(37, 99, 235, 0.3)',
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
    transform: 'none',
    boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
  },
  buttonLoader: {
    display: 'inline-block',
    width: '16px',
    height: '16px',
    border: '2px solid rgba(255, 255, 255, 0.3)',
    borderRadius: '50%',
    borderTopColor: '#ffffff',
    animation: 'spin 1s ease-in-out infinite',
    marginRight: '8px',
  },
  status: {
    padding: '14px 18px',
    borderRadius: '12px',
    fontSize: '13px',
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    border: '1px solid #e2e8f0',
    transition: 'all 0.3s ease',
  },
  statusSuccess: {
    backgroundColor: '#ecfdf5',
    borderColor: 'rgba(34, 197, 94, 0.4)',
    color: '#059669',
  },
  statusError: {
    backgroundColor: '#fef2f2',
    borderColor: 'rgba(239, 68, 68, 0.4)',
    color: '#dc2626',
  },
  statusPending: {
    backgroundColor: '#fefce8',
    borderColor: 'rgba(234, 179, 8, 0.4)',
    color: '#92400e',
  },
  statusIcon: {
    fontSize: '16px',
    flexShrink: 0,
  },
  helperText: {
    marginTop: '6px',
    fontSize: '11px',
    color: '#64748b',
    lineHeight: 1.4,
  },
  helperTextWarning: {
    color: '#dc2626',
    fontWeight: 600,
  },
  modeSwitcher: {
    display: 'flex',
    justifyContent: 'center',
    gap: '12px',
    marginTop: '8px',
  },
  modeButton: (active) => ({
    flex: 1,
    padding: '10px 12px',
    borderRadius: '999px',
    border: '1px solid',
    borderColor: active ? '#1d4ed8' : 'rgba(148,163,184,0.5)',
    backgroundColor: active ? '#1d4ed8' : '#f8fafc',
    color: active ? '#fff' : '#1f2937',
    fontWeight: 600,
    fontSize: '12px',
    letterSpacing: '0.05em',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxShadow: active ? '0 4px 10px rgba(59,130,246,0.25)' : 'none',
  }),
  lookupHelper: {
    fontSize: '12px',
    color: '#475569',
    marginTop: '4px',
  },
  resultCard: {
    borderRadius: '12px',
    border: '1px solid rgba(226, 232, 240, 0.8)',
    padding: '16px 20px',
    backgroundColor: '#f8fafc',
    display: 'grid',
    gap: '8px',
    fontSize: '13px',
    color: '#0f172a',
    boxShadow: '0 2px 8px rgba(15, 23, 42, 0.07)',
  },
  resultList: {
    margin: '6px 0 0',
    paddingLeft: '20px',
    color: '#475569',
    lineHeight: '1.5',
  },
  ssnBanner: {
    padding: '14px 16px',
    borderRadius: '12px',
    backgroundColor: '#f97316',
    color: '#ffffff',
    fontWeight: 700,
    fontSize: '14px',
    textAlign: 'center',
    letterSpacing: '0.5px',
    boxShadow: '0 4px 12px rgba(249, 115, 22, 0.35)',
  },
  cautionBox: {
    marginTop: '12px',
    padding: '12px 16px',
    borderRadius: '12px',
    backgroundColor: '#fef2f2',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    color: '#b91c1c',
    fontSize: '12px',
    fontWeight: 600,
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
};

// Add keyframe animations
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @keyframes slideInUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;
if (!document.head.querySelector('style[data-form-animations]')) {
  styleSheet.setAttribute('data-form-animations', 'true');
  document.head.appendChild(styleSheet);
}

const TemporaryUserFormComponent = ({ apiBaseUrl, onClose, sessionId, onSuccess }) => {
  const [formState, setFormState] = useState({
    full_name: '',
    email: '',
    phone_number: '',
    preferred_channel: 'email',
    // Insurance-specific fields
    insurance_company_name: '',
    insurance_role: 'policyholder',
    test_scenario: 'golden_path',  // Default to golden_path for consistent B2B testing
  });
  const [status, setStatus] = useState({ type: 'idle', message: '', data: null });
  const [focusedField, setFocusedField] = useState(null);
  const [isButtonHovered, setIsButtonHovered] = useState(false);
  const [isCloseHovered, setIsCloseHovered] = useState(false);
  const [touchedFields, setTouchedFields] = useState({});
  const [attemptedSubmit, setAttemptedSubmit] = useState(false);

  const [mode, setMode] = useState('create'); // 'create' | 'lookup'
  const [scenario, setScenario] = useState('banking'); // 'banking' | 'insurance'
  const [lookupEmail, setLookupEmail] = useState('');
  const [lookupPending, setLookupPending] = useState(false);
  const [lookupError, setLookupError] = useState('');

  const submitDisabled = useMemo(
    () => status.type === 'pending' || lookupPending,
    [status.type, lookupPending],
  );

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormState((prev) => {
      const next = { ...prev, [name]: value };
      if (
        status.type === 'error' &&
        status.message?.startsWith('Full name and email') &&
        next.full_name.trim() &&
        next.email.trim()
      ) {
        setStatus({ type: 'idle', message: '', data: null });
        setAttemptedSubmit(false);
      }
      return next;
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitDisabled) {
      return;
    }

    setAttemptedSubmit(true);

    if (!formState.full_name.trim() || !formState.email.trim()) {
      setStatus({
        type: 'error',
        message: 'Full name and email are required to create a demo profile.',
        data: null,
      });
      return;
    }

    setStatus({ type: 'pending', message: 'Creating demo profile…', data: null });

    const payload = {
      full_name: formState.full_name.trim(),
      email: formState.email.trim(),
      preferred_channel: formState.preferred_channel,
      scenario: scenario,
    };
    if (formState.phone_number.trim()) {
      payload.phone_number = formState.phone_number.trim();
    }
    if (sessionId) {
      payload.session_id = sessionId;
    }
    // Add insurance-specific fields if insurance scenario
    if (scenario === 'insurance') {
      if (formState.insurance_company_name.trim()) {
        payload.insurance_company_name = formState.insurance_company_name.trim();
      }
      payload.insurance_role = formState.insurance_role;
      // Add test_scenario for CC reps to enable consistent B2B workflow testing
      if (formState.insurance_role === 'cc_rep' && formState.test_scenario) {
        payload.test_scenario = formState.test_scenario;
      }
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/demo-env/temporary-user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `Request failed (${response.status})`);
      }

      const data = await response.json();
      const scenarioLabel = scenario === 'insurance' ? 'Insurance' : 'Banking';
      setStatus({
        type: 'success',
        message: `${scenarioLabel} demo profile ready. Check the User Profile panel for details.`,
        data: {
          safety_notice: data?.safety_notice,
          institution_name: data?.profile?.institution_name,
          company_code: data?.profile?.company_code,
          company_code_last4:
            data?.profile?.company_code_last4 ||
            data?.profile?.company_code?.slice?.(-4),
          scenario: data?.scenario,
        },
      });
      onSuccess?.(data);
      setFormState({ 
        full_name: '', 
        email: '', 
        phone_number: '', 
        preferred_channel: 'email',
        insurance_company_name: '',
        insurance_role: 'policyholder',
        test_scenario: 'golden_path',
      });
      setTouchedFields({});
      setAttemptedSubmit(false);
    } catch (error) {
      setStatus({
        type: 'error',
        message: error.message || 'Unable to create demo profile.',
        data: null,
      });
    }
  };

  const handleLookup = async (event) => {
    event.preventDefault();
    if (lookupPending) {
      return;
    }
    const emailValue = lookupEmail.trim();
    if (!emailValue) {
      setLookupError('Email is required to lookup a demo profile.');
      return;
    }
    setLookupError('');
    setLookupPending(true);
    setStatus({ type: 'pending', message: 'Looking up demo profile…', data: null });
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/v1/demo-env/temporary-user?email=${encodeURIComponent(emailValue)}&session_id=${encodeURIComponent(sessionId)}`
      );
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `Lookup failed (${response.status})`);
      }
      const data = await response.json();
      setStatus({
        type: 'success',
        message: `Loaded demo profile for ${data?.profile?.full_name || emailValue}.`,
        data: {
          safety_notice: data?.safety_notice,
          institution_name: data?.profile?.institution_name,
          company_code: data?.profile?.company_code,
          company_code_last4: data?.profile?.company_code_last4 || data?.profile?.company_code?.slice?.(-4),
        },
      });
      setLookupEmail('');
      onSuccess?.(data);
    } catch (error) {
      setStatus({
        type: 'error',
        message: error.message || 'Unable to lookup demo profile.',
        data: null,
      });
    } finally {
      setLookupPending(false);
    }
  };

  const showRequiredError = (fieldName) => {
    if (fieldName !== 'full_name' && fieldName !== 'email') {
      return false;
    }
    const isEmpty = !formState[fieldName].trim();
    return isEmpty && (touchedFields[fieldName] || attemptedSubmit);
  };

  return (
    <section style={{
      ...formStyles.container,
      animation: 'slideInUp 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
    }}>
      <div style={formStyles.headerRow}>
        <div style={formStyles.titleSection}>
          <h2 style={formStyles.title}>Create Demo Access</h2>
          <p style={formStyles.subtitle}>
            Generate a temporary 24-hour profile for testing. SMS-based verification is currently not enabled for this environment.
          </p>
        </div>
        {onClose && (
          <button
            type="button"
            style={{
              ...formStyles.closeButton,
              ...(isCloseHovered ? formStyles.closeButtonHover : {})
            }}
            onMouseEnter={() => setIsCloseHovered(true)}
            onMouseLeave={() => setIsCloseHovered(false)}
            onClick={onClose}
            aria-label="Close demo form"
            title="Close demo form"
          >
            ✕
          </button>
        )}
      </div>
      <div style={formStyles.warning}>
        <span style={formStyles.statusIcon}>⚠️</span>
        <span>Demo environment - All data is automatically purged after 24 hours</span>
      </div>

      <div style={formStyles.modeSwitcher}>
        <button
          type="button"
          style={formStyles.modeButton(mode === 'create')}
          onClick={() => setMode('create')}
          disabled={lookupPending}
        >
          Create Profile
        </button>
        <button
          type="button"
          style={formStyles.modeButton(mode === 'lookup')}
          onClick={() => setMode('lookup')}
          disabled={lookupPending}
        >
          Lookup by Email
        </button>
      </div>

      {mode === 'create' && (
        <div style={{ ...formStyles.modeSwitcher, marginTop: '12px' }}>
          <button
            type="button"
            style={{
              ...formStyles.modeButton(scenario === 'banking'),
              backgroundColor: scenario === 'banking' ? '#8b5cf6' : '#f8fafc',
              borderColor: scenario === 'banking' ? '#7c3aed' : 'rgba(148,163,184,0.5)',
            }}
            onClick={() => setScenario('banking')}
            disabled={lookupPending}
          >
            🏦 Banking
          </button>
          <button
            type="button"
            style={{
              ...formStyles.modeButton(scenario === 'insurance'),
              backgroundColor: scenario === 'insurance' ? '#059669' : '#f8fafc',
              borderColor: scenario === 'insurance' ? '#047857' : 'rgba(148,163,184,0.5)',
            }}
            onClick={() => setScenario('insurance')}
            disabled={lookupPending}
          >
            🛡️ Insurance
          </button>
        </div>
      )}

      {mode === 'create' ? (
      <form style={formStyles.form} onSubmit={handleSubmit}>
        <div style={formStyles.formRow}>
          <label 
            style={{
              ...formStyles.label,
              ...(focusedField === 'full_name' ? formStyles.labelFocused : {})
            }} 
            htmlFor="full_name"
          >
            <span style={formStyles.labelText}>Full Name</span>
            <span style={formStyles.requiredBadge}>Required</span>
          </label>
          <div style={formStyles.inputContainer}>
            <input
              id="full_name"
              name="full_name"
              value={formState.full_name}
              onChange={handleChange}
              onFocus={() => setFocusedField('full_name')}
              onBlur={() => {
                setFocusedField(null);
                setTouchedFields((prev) => ({ ...prev, full_name: true }));
              }}
              style={{
                ...formStyles.input,
                ...(focusedField === 'full_name' ? formStyles.inputFocused : {}),
                ...(showRequiredError('full_name') ? formStyles.inputError : {})
              }}
              placeholder="Ada Lovelace"
              required
            />
          </div>
          <div
            style={{
              ...formStyles.helperText,
              ...(showRequiredError('full_name') ? formStyles.helperTextWarning : {}),
            }}
          >
            Sample value shown is a placeholder. Please enter the full name you want to use.
          </div>
        </div>
        <div style={formStyles.formRow}>
          <label 
            style={{
              ...formStyles.label,
              ...(focusedField === 'email' ? formStyles.labelFocused : {})
            }} 
            htmlFor="email"
          >
            <span style={formStyles.labelText}>Email Address</span>
            <div style={formStyles.labelExtras}>
              <span style={formStyles.requiredBadge}>Required</span>
              <Tooltip
                title="Provide a valid, accessible email address for MFA verification during the demo."
                arrow
                placement="right"
                sx={{
                  '& .MuiTooltip-tooltip': {
                    backgroundColor: 'rgba(59, 130, 246, 0.9)',
                    color: 'white',
                    fontSize: '12px',
                    maxWidth: '250px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
                  },
                  '& .MuiTooltip-arrow': {
                    color: 'rgba(59, 130, 246, 0.9)',
                  }
                }}
              >
                <IconButton
                  size="small"
                  sx={{
                    padding: '2px',
                    color: '#6b7280',
                    '&:hover': {
                      color: '#3b82f6',
                      backgroundColor: 'rgba(59, 130, 246, 0.08)'
                    },
                    transition: 'all 0.2s ease'
                  }}
                >
                  <InfoOutlinedIcon sx={{ fontSize: '16px' }} />
                </IconButton>
              </Tooltip>
            </div>
          </label>
          <div style={formStyles.inputContainer}>
            <input
              id="email"
              name="email"
              type="email"
              value={formState.email}
              onChange={handleChange}
              onFocus={() => setFocusedField('email')}
              onBlur={() => {
                setFocusedField(null);
                setTouchedFields((prev) => ({ ...prev, email: true }));
              }}
              style={{
                ...formStyles.input,
                ...(focusedField === 'email' ? formStyles.inputFocused : {}),
                ...(showRequiredError('email') ? formStyles.inputError : {})
              }}
              placeholder="ada@example.com"
              required
            />
          </div>
          <div
            style={{
              ...formStyles.helperText,
              ...(showRequiredError('email') ? formStyles.helperTextWarning : {}),
            }}
          >
            Placeholder email won’t be submitted. Use an inbox you can access for the demo.
          </div>
        </div>
        <div style={formStyles.formRow}>
          <label 
            style={{
              ...formStyles.label,
              ...(focusedField === 'phone_number' ? formStyles.labelFocused : {})
            }} 
            htmlFor="phone_number"
          >
            Phone Number (Coming Soon)
          </label>
          <div style={formStyles.inputContainer}>
            <input
              id="phone_number"
              name="phone_number"
              value={formState.phone_number}
              onChange={handleChange}
              onFocus={() => setFocusedField('phone_number')}
              onBlur={() => setFocusedField(null)}
              disabled
              style={{
                ...formStyles.input,
                ...(focusedField === 'phone_number' ? formStyles.inputFocused : {}),
                opacity: 0.6,
                cursor: 'not-allowed'
              }}
              placeholder="+1 (555) 123-4567 (Coming Soon)"
            />
          </div>
        </div>

        {/* Insurance-specific fields */}
        {scenario === 'insurance' && (
          <>
            <div style={formStyles.formRow}>
              <label 
                style={{
                  ...formStyles.label,
                  ...(focusedField === 'insurance_company_name' ? formStyles.labelFocused : {})
                }} 
                htmlFor="insurance_company_name"
              >
                <span style={formStyles.labelText}>Your Insurance Company</span>
              </label>
              <div style={formStyles.inputContainer}>
                <input
                  id="insurance_company_name"
                  name="insurance_company_name"
                  value={formState.insurance_company_name}
                  onChange={handleChange}
                  onFocus={() => setFocusedField('insurance_company_name')}
                  onBlur={() => setFocusedField(null)}
                  style={{
                    ...formStyles.input,
                    ...(focusedField === 'insurance_company_name' ? formStyles.inputFocused : {}),
                  }}
                  placeholder="e.g., Fabrikam Insurance"
                />
              </div>
              <div style={formStyles.helperText}>
                For B2B calls: Enter the claimant carrier company name.
              </div>
            </div>
            <div style={formStyles.formRow}>
              <label 
                style={{
                  ...formStyles.label,
                  ...(focusedField === 'insurance_role' ? formStyles.labelFocused : {})
                }} 
                htmlFor="insurance_role"
              >
                <span style={formStyles.labelText}>Role</span>
              </label>
              <div style={formStyles.inputContainer}>
                <select
                  id="insurance_role"
                  name="insurance_role"
                  value={formState.insurance_role}
                  onChange={handleChange}
                  onFocus={() => setFocusedField('insurance_role')}
                  onBlur={() => setFocusedField(null)}
                  style={{
                    ...formStyles.input,
                    ...(focusedField === 'insurance_role' ? formStyles.inputFocused : {}),
                    paddingRight: '32px',
                    backgroundImage: 'url("data:image/svg+xml,%3csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3e%3cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3e%3c/svg%3e")',
                    backgroundPosition: 'right 12px center',
                    backgroundRepeat: 'no-repeat',
                    backgroundSize: '16px',
                  }}
                >
                  <option value="policyholder">👤 Policyholder (My Own Claim)</option>
                  <option value="cc_rep">🏢 CC Representative (Subrogation)</option>
                </select>
              </div>
              <div style={formStyles.helperText}>
                Policyholder: Calling about your own policy/claim. CC Rep: Calling from another insurer about subrogation.
              </div>
            </div>
            {/* Test Scenario dropdown - only for CC Representatives */}
            {formState.insurance_role === 'cc_rep' && (
              <div style={formStyles.formRow}>
                <label 
                  style={{
                    ...formStyles.label,
                    ...(focusedField === 'test_scenario' ? formStyles.labelFocused : {})
                  }} 
                  htmlFor="test_scenario"
                >
                  <span style={formStyles.labelText}>Test Scenario</span>
                </label>
                <div style={formStyles.inputContainer}>
                  <select
                    id="test_scenario"
                    name="test_scenario"
                    value={formState.test_scenario}
                    onChange={handleChange}
                    onFocus={() => setFocusedField('test_scenario')}
                    onBlur={() => setFocusedField(null)}
                    style={{
                      ...formStyles.input,
                      ...(focusedField === 'test_scenario' ? formStyles.inputFocused : {}),
                      paddingRight: '32px',
                      backgroundImage: 'url("data:image/svg+xml,%3csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3e%3cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3e%3c/svg%3e")',
                      backgroundPosition: 'right 12px center',
                      backgroundRepeat: 'no-repeat',
                      backgroundSize: '16px',
                    }}
                  >
                    <option value="golden_path">⭐ Golden Path (Full B2B Workflow)</option>
                    <option value="demand_under_review">📋 Demand Under Review</option>
                    <option value="demand_paid">✅ Demand Paid</option>
                    <option value="no_demand">📭 No Demand Received</option>
                    <option value="coverage_denied">❌ Coverage Denied</option>
                    <option value="pending_assignment">⏳ Pending Assignment</option>
                    <option value="liability_denied">⚠️ Liability Denied</option>
                    <option value="cvq_open">❓ CVQ Open</option>
                    <option value="demand_exceeds_limits">💰 Demand Exceeds Limits</option>
                    <option value="random">🎲 Random</option>
                  </select>
                </div>
                <div style={formStyles.helperText}>
                  Golden Path: Tests coverage, liability, limits, payments, demand status & escalation.
                </div>
              </div>
            )}
          </>
        )}

        <div style={{ ...formStyles.formRow, ...formStyles.formRowFull }}>
          <label 
            style={{
              ...formStyles.label,
              ...(focusedField === 'preferred_channel' ? formStyles.labelFocused : {})
            }} 
            htmlFor="preferred_channel"
          >
            Verification Method
          </label>
          <div style={formStyles.inputContainer}>
            <select
              id="preferred_channel"
              name="preferred_channel"
              value={formState.preferred_channel}
              onChange={handleChange}
              onFocus={() => setFocusedField('preferred_channel')}
              onBlur={() => setFocusedField(null)}
              style={{
                ...formStyles.input,
                ...(focusedField === 'preferred_channel' ? formStyles.inputFocused : {}),
                paddingRight: '32px',
                backgroundImage: 'url("data:image/svg+xml,%3csvg xmlns=\'http://www.w3.org/2000/svg\' fill=\'none\' viewBox=\'0 0 20 20\'%3e%3cpath stroke=\'%236b7280\' stroke-linecap=\'round\' stroke-linejoin=\'round\' stroke-width=\'1.5\' d=\'m6 8 4 4 4-4\'/%3e%3c/svg%3e")',
                backgroundPosition: 'right 12px center',
                backgroundRepeat: 'no-repeat',
                backgroundSize: '16px',
              }}
            >
              <option value="email">📧 Email Verification</option>
              <option value="sms" disabled>📱 SMS Verification (Coming Soon)</option>
            </select>
          </div>
        </div>
        <div style={formStyles.buttonRow}>
          <button
            type="submit"
            style={{
              ...formStyles.button,
              ...(submitDisabled ? formStyles.buttonDisabled : {}),
              ...(isButtonHovered && !submitDisabled ? formStyles.buttonHover : {}),
            }}
            onMouseEnter={() => setIsButtonHovered(true)}
            onMouseLeave={() => setIsButtonHovered(false)}
            disabled={submitDisabled}
          >
            {status.type === 'pending' && (
              <span style={formStyles.buttonLoader}></span>
            )}
            {status.type === 'pending' ? 'Creating Profile...' : 'Create Demo Profile'}
          </button>
        </div>
      </form>
      ) : (
      <form
        style={{ ...formStyles.form, gridTemplateColumns: '1fr', marginTop: '8px' }}
        onSubmit={handleLookup}
      >
        <div style={formStyles.formRow}>
          <label
            style={{
              ...formStyles.label,
              ...(focusedField === 'lookup_email' ? formStyles.labelFocused : {}),
            }}
            htmlFor="lookup_email"
          >
            Lookup Email
          </label>
          <div style={formStyles.inputContainer}>
            <input
              id="lookup_email"
              type="email"
              value={lookupEmail}
              onChange={(e) => setLookupEmail(e.target.value)}
              onFocus={() => setFocusedField('lookup_email')}
              onBlur={() => setFocusedField(null)}
              placeholder="someone@example.com"
              style={{
                ...formStyles.input,
                ...(focusedField === 'lookup_email' ? formStyles.inputFocused : {}),
                ...(lookupError ? formStyles.inputError : {}),
              }}
            />
          </div>
          <div
            style={{
              ...formStyles.helperText,
              ...(lookupError ? formStyles.helperTextWarning : {}),
            }}
          >
            {lookupError || 'Enter the email used when the demo profile was created.'}
          </div>
        </div>
        <div style={formStyles.buttonRow}>
          <button
            type="submit"
            style={{
              ...formStyles.button,
              ...(lookupPending ? formStyles.buttonDisabled : {}),
              ...(isButtonHovered && !lookupPending ? formStyles.buttonHover : {}),
            }}
            onMouseEnter={() => setIsButtonHovered(true)}
            onMouseLeave={() => setIsButtonHovered(false)}
            disabled={lookupPending}
          >
            {lookupPending && <span style={formStyles.buttonLoader}></span>}
            {lookupPending ? 'Looking Up…' : 'Lookup Demo Profile'}
          </button>
        </div>
        <div style={formStyles.lookupHelper}>
          Don’t see the email? Create a new profile in the tab above.
        </div>
      </form>
      )}

      {status.type !== 'idle' && status.message && (
        <div
          style={{
            ...formStyles.status,
            ...(status.type === 'success'
              ? formStyles.statusSuccess
              : status.type === 'pending'
              ? formStyles.statusPending
              : formStyles.statusError),
            animation: 'slideInUp 0.3s ease-out'
          }}
        >
          <span style={formStyles.statusIcon}>
            {status.type === 'success' ? '✅' : status.type === 'pending' ? '⏳' : '❌'}
          </span>
          <div>
            {status.message}
            {status.type === 'success' && status.data?.safety_notice && (
              <div style={{ marginTop: '6px', fontWeight: 600, fontSize: '12px', opacity: 0.8 }}>
                {status.data.safety_notice}
              </div>
            )}
          </div>
        </div>
      )}

      {status.type === 'success' && (
        <div style={{ ...formStyles.resultCard, animation: 'slideInUp 0.35s ease-out' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {status.data?.scenario === 'insurance' ? '🛡️' : '🏦'}
            Demo Profile Snapshot ({status.data?.scenario === 'insurance' ? 'Insurance' : 'Banking'})
          </div>
          <div>
            <strong>Institution:</strong>{' '}
            {status.data?.institution_name || '—'}
          </div>
          <div>
            <strong>Company Code:</strong>{' '}
            {status.data?.company_code || '—'}
          </div>
          <div>
            <strong>Code Last 4:</strong>{' '}
            {status.data?.company_code_last4 || status.data?.company_code?.slice?.(-4) || '—'}
          </div>
        </div>
      )}

      {/* Demo details now live in the main UI profile panel */}
    </section>
  );
};

const TemporaryUserForm = React.memo(TemporaryUserFormComponent);

export default TemporaryUserForm;
