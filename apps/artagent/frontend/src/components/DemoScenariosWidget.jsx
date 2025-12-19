import React, { useMemo, useState } from 'react';

const DEFAULT_SCENARIOS = [
  {
    title: 'Microsoft Copilot Studio + ACS Call Routing',
    tags: ['Voice Live'],
    focus:
      'Validated end-to-end scenario: Copilot Studio IVR triggers ACS telephony, surfaces Venmo/PayPal knowledge, and escalates to fraud',
    sections: [
      {
        label: 'Setup',
        items: [
          'Wire your Copilot Studio experience so that the spoken intent “I need to file a claim” triggers a SIP transfer into this ACS demo. Once connected, the rest of the scenario runs inside this environment.',
          'Open the current ARTAgent frontend and create a demo profile with your email. Keep the profile card (SSN, company code, Venmo/PayPal balances) handy for reference.',
        ],
      },
      {
        label: 'Talk Track',
        items: [
          'Kick off: “My name is <demo profile name>. I’m looking for assistance with Venmo/PayPal transfers.” The auth agent should prompt for verification and then warm-transfer to the PayPal/Venmo KB agent.',
          'Ground the response: ask “What fees apply if I transfer $10,000 to Venmo today?” or “Without transferring me, walk me through PayPal Purchase Protection from the KB.” Expect citations to https://help.venmo.com/cs or https://www.paypal.com/us/cshelp/personal.',
          'Use profile context: “What is my current PayPal/Venmo balance?” then “What are my most recent transactions?” The assistant should read the demo profile snapshot.',
          'Trigger fraud: “I received a notification about suspicious activity—can you help me investigate?” After MFA, the agent should list suspicious transactions.',
          'Test conversational memory by spacing requests: “Let me check my PayPal balance… actually before you do that, remind me what fees apply if I transfer $10,000.” The assistant should resume the balance check afterwards without losing context.',
        ],
      },
      {
        label: 'Expected Behavior',
        items: [
          'Agent confirms identity (SSN + company code) and reuses demo profile data in subsequent responses.',
          'Knowledge answers cite the Venmo/PayPal KB and follow the RAG flow you’ve pre-indexed.',
          'Fraud workflow surfaces tagged transactions and allows you to command “Block the card” followed by “Escalate me to a human.”',
        ],
      },
      {
        label: 'Experiment',
        items: [
          'Interrupt the flow with creative pivots (“Actually pause that balance check—can you compare PayPal vs. Venmo fees?”) and ensure the agent resumes gracefully.',
          'Blend business + personal asks (“While we wait, summarize PayPal Purchase Protection, then finish the Venmo transaction review”).',
          'Inject what-if scenarios (e.g., “What would change if I sent $12,500 tomorrow?”) to test grounding limits.',
          'If you have multilingual voice models enabled, try mixing in Spanish, Korean, or Mandarin prompts mid-conversation and confirm the agent stays on track.',
        ],
      },
    ],
  },
  {
    title: 'Custom Cascade Treasury & Risk Orchestration',
    tags: ['Custom Cascade'],
    focus:
      'Exercise the ARTStore agent cascade (auth → treasury → compliance/fraud) across digital-asset drip liquidations, wire transfers, and incident escalation.',
    sections: [
      {
        label: 'Setup',
        items: [
          'Connect via Copilot Studio (or an ACS inbound route) that lands on the ARTAgent backend. Ensure the artstore profile contains wallet balances, risk limits, and prior incidents.',
          'Keep the compliance agent YAMLs handy—this scenario pulls from the artstore treasury, compliance, and fraud toolchains (liquidations, transfers, sanctions).',
        ],
      },
      {
        label: 'Talk Track',
        items: [
          'Authenticate: “My name is <demo profile name>. I need to review our artstore treasury activities.” Allow the auth agent to challenge for SSN/company code.',
          'Trigger drip liquidation: “Initiate a drip liquidation for the Modern Art fund—liquidate $250k over the next 24 hours.” Expect the treasury agent to schedule staggered sells and echo position impacts.',
          'Run compliance: “Before you execute, run compliance on the counterparties and confirm we’re still within sanctions thresholds.” The compliance agent should cite the tool output.',
          'Move funds: “Wire the proceeds to the restoration escrow and post the transfer reference.” Follow up with “Add a note that this covers the Venice exhibit repairs.”',
          'Fraud check: “I just saw a suspicious transfer—can you investigate and block if needed?” Let the fraud agent review recent ledgers, flag anomalies, and offer to escalate.',
        ],
      },
      {
        label: 'Expected Behavior',
        items: [
          'Auth agent reuses the artstore profile (SSN/company code) and surfaces contextual balances.',
          'Treasury tool schedules drip liquidations and wires with ledger updates that the compliance agent validates.',
          'Fraud agent produces a report (transactions, risk level, recommended action) and offers escalation to compliance or human desk.',
        ],
      },
      {
        label: 'Experiment',
        items: [
          'Interrupt: “Pause the liquidation—actually drop the amount to $150k, then resume.” Verify state continuity.',
          'Ask for compliance deltas (“What changed in our sanctions exposure after the transfer?”) followed by “Summarize today’s treasury moves for the board.”',
          'Request a multi-step escalation: “Open a fraud case, alert compliance, and warm-transfer me if the risk is high.”',
        ],
      },
    ],
  },
  {
    title: 'VoiceLive Knowledge + Fraud Assist',
    tags: ['Voice Live'],
    focus:
      'Use the realtime VoiceLive connection to ground responses in the PayPal/Venmo KB and walk through authentication + fraud mitigation',
    sections: [
      {
        label: 'Preparation',
        items: [
          'Connect via the VoiceLive web experience (or Copilot Studio → ACS) and create a demo profile. This seeds the system with synthetic SSN, company code, balance, and transactions.',
          'Ensure the Venmo/PayPal KB has been ingested into the vector DB (run the bootstrap script if needed).',
        ],
      },
      {
        label: 'Talk Track',
        items: [
          'Intro: “My name is <demo profile name>. I need details about a Venmo/PayPal transfer.” Agent should confirm your name and request verification.',
          'The Auth Agent should confirm your name and transfer you to the paypal/venmo agent.',
          'Ask KB questions with explicit intent (“Please stay on the line and just explain this—what fees apply if I move $10,000 into Venmo?” / “Walk me through PayPal Purchase Protection from the KB.”) followed by account-level questions (“What’s my balance?” “List my two most recent transactions.”).',
          'Asking account level questions should trigger the agent to ask more verification questions based on the demo profile (SSN, company code).',
          'Trigger fraud: “I received a suspicious activity alert—help me investigate.” Agent should request MFA, then surface suspicious transactions.',
        ],
      },
      {
        label: 'Expected Behavior',
        items: [
          'Responses include citations to the Venmo/PayPal KB.',
          'Balance and transaction details match the generated demo profile.',
          'Fraud workflow prompts for MFA, flags suspicious entries, and supports commands such as “block the card” and “escalate to a human.”',
        ],
      },
      {
        label: 'Notes',
        items: [
          'Grounded answers require the Venmo/PayPal vector store. If you haven’t indexed the KB, run the ingestion script before testing.',
        ],
      },
      {
        label: 'Experiment',
        items: [
          'Try creative memory tests (“Check my Venmo balance… actually, before that, give me the PayPal fee table—then resume the balance”).',
          'Trigger multiple intents back-to-back (“Explain Purchase Protection, then immediately flag fraud”) to ensure state carries through.',
          'Ask for comparisons (“Which policy would help me more—Venmo Purchase Protection or PayPal Chargeback?”) to encourage grounded, multi-source answers.',
          'Mix languages (e.g., ask the next question in Spanish or Korean) if your VoiceLive model supports it, then switch back to English.',
        ],
      },
    ],
  },
  {
    title: 'High-Value PayPal Transfer Orchestration',
    tags: ['Voice Live'],
    focus:
      'Demonstrate the $50,000 PayPal → bank transfer flow end-to-end: business authentication with institution + company code, profile-aware limits, and chained RAG lookups that inform the PayPal agent handoff.',
    sections: [
      {
        label: 'Preparation',
        items: [
          'Seed the demo profile with PayPal balance ($75k+), daily and monthly transfer limits, linked bank routing metadata, and recent payout history.',
          'Ensure the profile includes a business institution name (e.g., “BlueStone Art Collective LLC”) and the PayPal company code last four digits; keep them handy for the auth flow.',
          'Verify that the PayPal/Venmo KB has coverage for “large transfer fees,” “instant transfer timelines,” and “high-value withdrawals” so RAG can cite those policies.',
          'Open the VoiceLive console plus the PayPal specialist prompt so you can watch the chained tool calls (identity → authorization → knowledge lookups).',
        ],
      },
      {
        label: 'Talk Track',
        items: [
          'Kick off with the auth agent: “Hi, I’m <demo profile name>. I need to move $50,000 from my PayPal to my bank today—it’s just my personal account.” The agent should acknowledge but immediately explain that high-value transfers require the business/institution record and will request the company code.',
          'Follow up with the correct details: provide the institution name from the profile and the company code last four digits so the agent can re-run identity verification.',
          'Complete identity verification (full name + institution + company code + SSN last four) and MFA via email. Listen for confirmation that the agent stored `client_id`, `session_id`, and whether additional authorization is required.',
          'Prompt the agent to check transfer eligibility: “Before we move the funds, confirm my remaining transfer limit and whether I can send $50,000 right now.” This should trigger `check_transaction_authorization` or similar tooling using the profile’s limit metadata.',
          'Once warm-transferred to the PayPal agent, ask: “What would happen if I transferred $50,000 from PayPal to my bank account?” The agent should launch a RAG query, cite policy guidance, and blend in your profile limits.',
          'Follow up with: “Okay—chain another lookup to see if there are detailed steps or fees I should expect for high-value transfers.” Expect a second RAG query that builds on the first answer while staying grounded in the profile context.',
          'Have the agent surface personalized insight: “Given my profile and limits, recommend whether I should initiate one $50,000 transfer or break it into two $25k transfers, and outline the steps.” This should blend vector search results with the stored transfer limit attributes.',
        ],
      },
      {
        label: 'Expected Behavior',
        items: [
          'Initial “personal account” claim is rejected for high-value transfer; the assistant requests institution name and company code before proceeding.',
          'Authentication flow succeeds only after full name, institution, SSN last four, and company code are supplied.',
          'MFA delivery happens via email, and the assistant restates delivery per policy (“Only email is available right now”).',
          'Authorization logic references profile limits, echoes remaining transfer headroom, and notes if supervisor approval is needed.',
          'PayPal specialist issues at least two chained RAG calls: the first explaining the immediate outcome of moving $50,000, the second detailing fees and execution steps, citing distinct knowledge sources.',
          'Final recommendation cites both the KB entries and profile-specific data (limits, prior transfer history) before outlining the execution steps.',
        ],
      },
      {
        label: 'Experiment',
        items: [
          'Interrupt after the first RAG answer (“Hold on—before finishing, confirm whether instant transfer is available for $50k and what the fee would be.”) The agent should reuse prior findings and only fetch new knowledge if needed.',
          'Ask for multi-lingual confirmation (“Repeat the compliance summary in Spanish, then switch back to English”) to ensure the chained context survives language pivots.',
          'Request a scenario analysis: “If compliance delays me 24 hours, what’s my best alternative?” Expect the agent to cite another RAG snippet plus the profile’s past transfer cadence.',
          'Deliberately ask for a bank reference number before the transfer (“Generate a reference ID now”). The agent should explain that the reference appears only after the transfer, reinforcing policy-grounded guidance.',
        ],
      },
    ],
  },
  {
    title: 'ACS Call-Center Transfer',
    tags: ['Custom Cascade', 'Voice Live'],
    focus: 'Quick telephony scenario to exercise the transfer tool and CALL_CENTER_TRANSFER_TARGET wiring',
    note: 'Call-center transfers require an ACS telephony leg. Voice Live sessions must be paired with ACS media for the transfer to succeed.',
    sections: [
      {
        label: 'Steps',
        items: [
          'Place an outbound ACS call from the ARTAgent UI (or through Copilot Studio → ACS) to your own phone and wait for the introduction.',
          'Say “Transfer me to a call center.” This invokes the call-center transfer tool, which relays the call to the destination configured in CALL_CENTER_TRANSFER_TARGET via SIP headers.',
          'Verify that the assistant announces the transfer and that the call lands in the downstream contact center.',
          'For inbound tests, ensure your IVR forwards to the ACS number attached to this backend, then repeat the same spoken command.',
        ],
      },
      {
        label: 'Expected Behavior',
        items: [
          'Assistant acknowledges the transfer request and confirms the move to a live agent.',
          'Call routing uses the SIP target defined in CALL_CENTER_TRANSFER_TARGET.',
          'Any failures return a friendly “No active ACS call to transfer… please use the telephony experience” message.',
        ],
      },
      {
        label: 'Experiment',
        items: [
          'Test nuanced phrasing (“Can you loop in the call center?” / “Warm-transfer me to a live agent”) to confirm intent detection.',
          'Add creative pre-transfer requests (“Before you transfer me, summarize what you’ve done so far.”) to ensure status envelopes show up.',
          'Toggle between successful and failed transfers by editing CALL_CENTER_TRANSFER_TARGET to validate fallback messaging.',
          'If your ACS voice model supports multiple languages, request the transfer in another language (Spanish, Korean, etc.) and verify the intent still fires.',
        ],
      },
    ],
  },
];

const TAG_OPTIONS = [
  {
    key: 'Custom Cascade',
    description: 'Copilot Studio → ACS telephony stack',
  },
  {
    key: 'Voice Live',
    description: 'Voice Live realtime orchestration stack',
  },
];

const PANEL_CLASSNAME = 'demo-scenarios-panel';

const styles = {
  container: {
    position: 'fixed',
    bottom: '32px',
    right: '32px',
    zIndex: 11000,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    pointerEvents: 'none',
  },
  toggleButton: (open) => ({
    pointerEvents: 'auto',
    border: 'none',
    outline: 'none',
    borderRadius: '999px',
    background: open
      ? 'linear-gradient(135deg, #312e81, #1d4ed8)'
      : 'linear-gradient(135deg, #0f172a, #1f2937)',
    color: '#fff',
    padding: '10px 16px',
    fontWeight: 600,
    fontSize: '13px',
    letterSpacing: '0.4px',
    cursor: 'pointer',
    boxShadow: '0 12px 32px rgba(15, 23, 42, 0.35)',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
  }),
  iconBadge: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    background: 'rgba(255, 255, 255, 0.15)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '16px',
  },
  panel: {
    pointerEvents: 'auto',
    width: '280px',
    maxWidth: 'calc(100vw - 48px)',
    maxHeight: '70vh',
    background: '#0f172a',
    color: '#f8fafc',
    borderRadius: '20px',
    padding: '20px',
    marginBottom: '12px',
    boxShadow: '0 20px 50px rgba(15, 23, 42, 0.55)',
    border: '1px solid rgba(255, 255, 255, 0.06)',
    backdropFilter: 'blur(16px)',
    transition: 'opacity 0.2s ease, transform 0.2s ease',
    overflowY: 'auto',
    scrollbarWidth: 'none',
    msOverflowStyle: 'none',
  },
  panelHidden: {
    opacity: 0,
    transform: 'translateY(10px)',
    pointerEvents: 'none',
  },
  panelVisible: {
    opacity: 1,
    transform: 'translateY(0)',
  },
  panelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },
  panelTitle: {
    fontSize: '14px',
    fontWeight: 700,
    letterSpacing: '0.8px',
    textTransform: 'uppercase',
  },
  closeButton: {
    border: 'none',
    background: 'rgba(255, 255, 255, 0.08)',
    color: '#cbd5f5',
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    cursor: 'pointer',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  scenarioList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  scenarioCard: {
    background: 'rgba(15, 23, 42, 0.75)',
    borderRadius: '14px',
    padding: '14px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
  },
  scenarioTitle: {
    fontSize: '13px',
    fontWeight: 700,
    marginBottom: '4px',
  },
  scenarioFocus: {
    fontSize: '11px',
    color: '#94a3b8',
    marginBottom: '10px',
  },
  scenarioTagGroup: {
    display: 'flex',
    gap: '6px',
    flexWrap: 'wrap',
    marginBottom: '6px',
  },
  scenarioTag: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '2px 8px',
    borderRadius: '999px',
    fontSize: '10px',
    fontWeight: 600,
    letterSpacing: '0.4px',
    textTransform: 'uppercase',
    background: 'rgba(248, 250, 252, 0.08)',
    color: '#67d8ef',
    border: '1px solid rgba(103, 216, 239, 0.35)',
  },
  scenarioSteps: {
    margin: 0,
    paddingLeft: '18px',
    color: '#cbd5f5',
    fontSize: '12px',
    lineHeight: 1.6,
  },
  scenarioStep: {
    marginBottom: '6px',
  },
  scenarioNote: {
    fontSize: '10px',
    color: '#fcd34d',
    marginBottom: '6px',
    lineHeight: 1.4,
  },
  quotedText: {
    color: '#fbbf24',
    fontWeight: 600,
  },
  helperText: {
    fontSize: '11px',
    color: '#94a3b8',
    marginBottom: '12px',
    lineHeight: 1.5,
  },
  filterBar: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    marginBottom: '12px',
  },
  filterButtons: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  },
  filterButton: (active) => ({
    borderRadius: '999px',
    padding: '4px 10px',
    fontSize: '10px',
    letterSpacing: '0.4px',
    textTransform: 'uppercase',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    color: active ? '#0f172a' : '#e2e8f0',
    background: active ? '#67d8ef' : 'rgba(248, 250, 252, 0.08)',
    border: active ? '1px solid rgba(103, 216, 239, 0.6)' : '1px solid rgba(248, 250, 252, 0.14)',
  }),
  filterDescription: {
    fontSize: '10px',
    color: '#94a3b8',
  },
};

const highlightQuotedText = (text) => {
  if (typeof text !== 'string') {
    return text;
  }

  const regex = /(“[^”]+”|"[^"]+")/g;
  const segments = text.split(regex);

  if (segments.length === 1) {
    return text;
  }

  const isQuoted = (segment) =>
    (segment.startsWith('"') && segment.endsWith('"')) ||
    (segment.startsWith('“') && segment.endsWith('”'));

  return segments.map((segment, idx) => {
    if (segment && isQuoted(segment)) {
      return (
        <span key={`quoted-${idx}`} style={styles.quotedText}>
          {segment}
        </span>
      );
    }
    return <React.Fragment key={`plain-${idx}`}>{segment}</React.Fragment>;
  });
};

const DemoScenariosWidget = ({ scenarios = DEFAULT_SCENARIOS, inline = false }) => {
  const [open, setOpen] = useState(false);
  const [activeTags, setActiveTags] = useState([]);

  const togglePanel = () => setOpen((prev) => !prev);
  const toggleTag = (tag) =>
    setActiveTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );

  const filteredScenarios = useMemo(() => {
    if (!activeTags.length) {
      return scenarios;
    }
    return scenarios.filter((scenario) => {
      const scenarioTags = scenario.tags || [];
      return scenarioTags.some((tag) => activeTags.includes(tag));
    });
  }, [scenarios, activeTags]);

  const containerStyle = inline
    ? {
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        pointerEvents: 'auto',
        gap: '6px',
      }
    : styles.container;

  const panelStyle = {
    ...styles.panel,
    ...(inline
      ? {
          position: 'absolute',
          top: 'calc(100% + 10px)',
          left: 0,
          width: '320px',
          maxHeight: '60vh',
          marginTop: 0,
          transform: 'none',
          boxShadow: '0 18px 35px rgba(15,23,42,0.25)',
          border: '1px solid rgba(15,23,42,0.08)',
        }
      : {}),
  };

  const visibilityStyle = inline
    ? open
      ? { display: 'block', opacity: 1, transform: 'none' }
      : { display: 'none' }
    : open
    ? styles.panelVisible
    : styles.panelHidden;

  const toggleButtonStyle = inline
    ? {
        ...styles.toggleButton(open),
        padding: '8px 14px',
        fontSize: '12px',
        boxShadow: '0 8px 18px rgba(15,23,42,0.2)',
        position: 'relative',
        zIndex: 2,
      }
    : styles.toggleButton(open);

  const renderScenario = (scenario, index) => (
    <div key={index} style={styles.scenarioCard}>
      {Array.isArray(scenario.tags) && scenario.tags.length > 0 && (
        <div style={styles.scenarioTagGroup}>
          {scenario.tags.map((tag) => (
            <span key={tag} style={styles.scenarioTag}>
              {tag}
            </span>
          ))}
        </div>
      )}
      <div style={styles.scenarioTitle}>{scenario.title}</div>
      <div style={styles.scenarioFocus}>{scenario.focus}</div>
      {scenario.note && <div style={styles.scenarioNote}>{scenario.note}</div>}
      {(scenario.sections || []).map((section) => (
        <div key={section.label} style={{ marginBottom: '12px' }}>
          <div style={{ fontSize: '11px', color: '#67d8ef', fontWeight: 600, textTransform: 'uppercase' }}>
            {section.label}
          </div>
          <ul style={styles.scenarioSteps}>
            {section.items.map((item, idx) => (
              <li key={idx} style={styles.scenarioStep}>
                {highlightQuotedText(item)}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {scenario.steps && (
        <ul style={styles.scenarioSteps}>
          {scenario.steps.map((step, idx) => (
            <li key={idx} style={styles.scenarioStep}>
              {highlightQuotedText(step)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  const renderPanel = () => (
    <div
      className={PANEL_CLASSNAME}
      style={{
        ...panelStyle,
        ...visibilityStyle,
      }}
      role="dialog"
      aria-label="Demo script scenarios"
      aria-hidden={!open}
    >
      <div style={styles.panelHeader}>
        <div style={styles.panelTitle}>Demo Script Scenarios</div>
        <button
          type="button"
          style={styles.closeButton}
          aria-label="Hide demo script scenarios"
          onClick={togglePanel}
        >
          ×
        </button>
      </div>
      <div style={styles.helperText}>
        Use these talk tracks to anchor your demo—and don’t be afraid to get creative.
        Mix and match prompts, interrupt mid-turn, and explore “what if?” questions to show off memory,
        grounding, and escalation behavior.
      </div>
      <div style={styles.filterBar}>
        <div style={{ fontSize: '10px', color: '#e2e8f0', fontWeight: 600, textTransform: 'uppercase' }}>
          Filter by stack
        </div>
        <div style={styles.filterButtons}>
          {TAG_OPTIONS.map((option) => {
            const active = activeTags.includes(option.key);
            return (
              <button
                type="button"
                key={option.key}
                style={styles.filterButton(active)}
                onClick={() => toggleTag(option.key)}
              >
                {option.key}
              </button>
            );
          })}
        </div>
        <div style={styles.filterDescription}>
          {activeTags.length
            ? `Showing ${filteredScenarios.length} scenario${filteredScenarios.length === 1 ? '' : 's'}`
            : 'Showing all scenarios (Voice Live + Custom Cascade)'}
        </div>
      </div>
      <div style={styles.scenarioList}>
        {filteredScenarios.map(renderScenario)}
      </div>
    </div>
  );

  return (
    <div style={containerStyle} aria-live="polite">
      <style>{`
        .${PANEL_CLASSNAME}::-webkit-scrollbar { display: none; }
        .${PANEL_CLASSNAME} { scrollbar-width: none; -ms-overflow-style: none; }
      `}</style>
      {inline ? (
        <>
          <button
            type="button"
            onClick={togglePanel}
            style={toggleButtonStyle}
            aria-expanded={open}
            aria-label="Toggle demo script scenarios"
          >
            <span style={styles.iconBadge}>🎬</span>
            <span>Scenarios</span>
          </button>
          {renderPanel()}
        </>
      ) : (
        <>
          {renderPanel()}
          <button
            type="button"
            onClick={togglePanel}
            style={toggleButtonStyle}
            aria-expanded={open}
            aria-label="Toggle demo script scenarios"
          >
            <span style={styles.iconBadge}>🎬</span>
            <span>Scenarios</span>
          </button>
        </>
      )}
    </div>
  );
};

export default DemoScenariosWidget;
