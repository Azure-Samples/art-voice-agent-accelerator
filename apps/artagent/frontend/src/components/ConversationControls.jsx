import React, { useCallback, useState } from 'react';
import { IconButton } from '@mui/material';
import MicNoneRoundedIcon from '@mui/icons-material/MicNoneRounded';
import MicOffRoundedIcon from '@mui/icons-material/MicOffRounded';
import RecordVoiceOverRoundedIcon from '@mui/icons-material/RecordVoiceOverRounded';
import StopCircleRoundedIcon from '@mui/icons-material/StopCircleRounded';
import PhoneDisabledRoundedIcon from '@mui/icons-material/PhoneDisabledRounded';
import PhoneRoundedIcon from '@mui/icons-material/PhoneRounded';
import RestartAltRoundedIcon from '@mui/icons-material/RestartAltRounded';
import ChatBubbleOutlineRoundedIcon from '@mui/icons-material/ChatBubbleOutlineRounded';
import AutoGraphRoundedIcon from '@mui/icons-material/AutoGraphRounded';
import NotificationsNoneRoundedIcon from '@mui/icons-material/NotificationsNoneRounded';
import { styles } from '../styles/voiceAppStyles.js';

const ConversationControls = React.memo(({
  recording,
  callActive,
  isCallDisabled,
  onResetSession,
  onMicToggle,
  onPhoneButtonClick,
  phoneButtonRef,
  micButtonRef,
  micMuted,
  onMuteToggle,
  mainView,
  onMainViewChange,
}) => {
  const [resetHovered, setResetHovered] = useState(false);
  const [micHovered, setMicHovered] = useState(false);
  const [phoneHovered, setPhoneHovered] = useState(false);
  const [muteHovered, setMuteHovered] = useState(false);
  const [showResetTooltip, setShowResetTooltip] = useState(false);
  const [showMicTooltip, setShowMicTooltip] = useState(false);
  const [showPhoneTooltip, setShowPhoneTooltip] = useState(false);
  const [showMuteTooltip, setShowMuteTooltip] = useState(false);
  const [phoneDisabledPos, setPhoneDisabledPos] = useState(null);
  const [resetTooltipPos, setResetTooltipPos] = useState(null);
  const [micTooltipPos, setMicTooltipPos] = useState(null);
  const [phoneTooltipPos, setPhoneTooltipPos] = useState(null);
  const [muteTooltipPos, setMuteTooltipPos] = useState(null);
  const [hatHovered, setHatHovered] = useState(false);

  // Lift the mini view toggle when the inline text input is visible (e.g., recording)
  const hatOffset = recording ? -78 : -42;

  const handlePhoneMouseEnter = useCallback((event) => {
    setShowPhoneTooltip(true);
    const target = phoneButtonRef?.current || event?.currentTarget;
    if (target) {
      const rect = target.getBoundingClientRect();
      setPhoneTooltipPos({
        top: rect.bottom + 12,
        left: rect.left + rect.width / 2,
      });
      setPhoneDisabledPos({
        top: rect.bottom + 12,
        left: rect.left + rect.width / 2,
      });
    }
    if (!isCallDisabled) {
      setPhoneHovered(true);
    }
  }, [isCallDisabled, phoneButtonRef]);

  const handlePhoneMouseLeave = useCallback(() => {
    setShowPhoneTooltip(false);
    setPhoneHovered(false);
    setPhoneDisabledPos(null);
    setPhoneTooltipPos(null);
  }, []);

  return (
    <div style={styles.controlSection}>
      {/* Mini view toggle "hat" above the main control cluster (non-intrusive) */}
      {typeof onMainViewChange === "function" && (
        <div
          onMouseEnter={() => setHatHovered(true)}
          onMouseLeave={() => setHatHovered(false)}
          style={{
            position: "absolute",
            top: `${hatOffset}px`,
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "2px 0",
            zIndex: 12,
            pointerEvents: "auto",
            opacity: hatHovered ? 1 : 0.45,
            transition: "opacity 0.18s ease",
          }}
        >
          {[
            { mode: "chat", icon: <ChatBubbleOutlineRoundedIcon fontSize="small" /> },
            { mode: "graph", icon: <AutoGraphRoundedIcon fontSize="small" /> },
            { mode: "timeline", icon: <NotificationsNoneRoundedIcon fontSize="small" /> },
          ].map(({ mode, icon }) => {
            const active = mainView === mode;
            return (
              <button
                key={mode}
                type="button"
                aria-label={`Switch to ${mode}`}
                style={{
                  pointerEvents: "auto",
                  width: 36,
                  height: 36,
                  borderRadius: 12,
                  border: '1px solid rgba(226,232,240,0.6)',
                  background: active
                    ? 'linear-gradient(145deg, rgba(248,250,252,0.98), rgba(241,245,249,0.95))'
                    : 'linear-gradient(145deg, #ffffff, #fafbfc)',
                  color: active ? '#6366f1' : '#64748b',
                  cursor: "pointer",
                  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: active
                    ? '0 2px 8px rgba(99,102,241,0.12), inset 0 1px 0 rgba(255,255,255,0.8)'
                    : '0 2px 6px rgba(15,23,42,0.06), inset 0 1px 0 rgba(255,255,255,0.8)',
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                onClick={() => onMainViewChange(mode)}
              >
                {icon}
              </button>
            );
          })}
        </div>
      )}

      <div style={styles.controlContainer}>
        {/* Reset */}
        <div style={{ position: 'relative' }}>
          <IconButton
            disableRipple
            aria-label="Reset session"
            sx={styles.resetButton(resetHovered)}
            onMouseEnter={(event) => {
              setShowResetTooltip(true);
              setResetHovered(true);
              const rect = event.currentTarget.getBoundingClientRect();
              setResetTooltipPos({
                top: rect.bottom + 12,
                left: rect.left + rect.width / 2,
              });
            }}
            onMouseLeave={() => {
              setShowResetTooltip(false);
              setResetHovered(false);
              setResetTooltipPos(null);
            }}
            onClick={onResetSession}
          >
            <RestartAltRoundedIcon fontSize="medium" />
          </IconButton>
          {showResetTooltip && resetTooltipPos && (
            <div
              style={{
                ...styles.buttonTooltip,
                top: resetTooltipPos.top,
                left: resetTooltipPos.left,
                ...(showResetTooltip ? styles.buttonTooltipVisible : {}),
              }}
            >
              Reset conversation & start fresh
            </div>
          )}
        </div>

        {/* Mute */}
        <div
          style={{ position: 'relative' }}
          onMouseEnter={(event) => {
            const target = event.currentTarget.querySelector('button') ?? event.currentTarget;
            const rect = target.getBoundingClientRect();
            setMuteTooltipPos({
              top: rect.bottom + 12,
              left: rect.left + rect.width / 2,
            });
            setShowMuteTooltip(true);
            if (recording) {
              setMuteHovered(true);
            }
          }}
          onMouseLeave={() => {
            setShowMuteTooltip(false);
            setMuteHovered(false);
            setMuteTooltipPos(null);
          }}
        >
          <IconButton
            disableRipple
            aria-label={micMuted ? "Unmute microphone" : "Mute microphone"}
            sx={styles.muteButton(micMuted, muteHovered, !recording)}
            disabled={!recording}
            onClick={() => {
              if (!recording) {
                return;
              }
              onMuteToggle();
            }}
          >
            {micMuted ? (
              <MicOffRoundedIcon fontSize="medium" />
            ) : (
              <MicNoneRoundedIcon fontSize="medium" />
            )}
          </IconButton>
          {showMuteTooltip && muteTooltipPos && (
            <div
              style={{
                ...styles.buttonTooltip,
                top: muteTooltipPos.top,
                left: muteTooltipPos.left,
                ...(showMuteTooltip ? styles.buttonTooltipVisible : {}),
              }}
            >
              {recording
                ? micMuted
                  ? "Resume sending microphone audio"
                  : "Temporarily mute your microphone"
                : "Start the microphone to enable mute"}
            </div>
          )}
        </div>

        {/* Mic */}
        <div style={{ position: 'relative' }}>
          <IconButton
            disableRipple
            aria-label={recording ? "End conversation with agent" : "Start talking to agent"}
            sx={styles.micButton(recording, micHovered)}
            ref={micButtonRef}
            onMouseEnter={(event) => {
              setShowMicTooltip(true);
              setMicHovered(true);
              const rect = event.currentTarget.getBoundingClientRect();
              setMicTooltipPos({
                top: rect.bottom + 12,
                left: rect.left + rect.width / 2,
              });
            }}
            onMouseLeave={() => {
              setShowMicTooltip(false);
              setMicHovered(false);
              setMicTooltipPos(null);
            }}
            onClick={onMicToggle}
          >
            {recording ? (
              <StopCircleRoundedIcon fontSize="medium" />
            ) : (
              <RecordVoiceOverRoundedIcon fontSize="medium" />
            )}
          </IconButton>
          {showMicTooltip && micTooltipPos && (
            <div
              style={{
                ...styles.buttonTooltip,
                top: micTooltipPos.top,
                left: micTooltipPos.left,
                ...(showMicTooltip ? styles.buttonTooltipVisible : {}),
              }}
            >
              {recording ? "End the conversation" : "Start talking to the agent"}
            </div>
          )}
        </div>

        {/* Call */}
        <div
          style={{ position: 'relative' }}
          onMouseEnter={handlePhoneMouseEnter}
          onMouseLeave={handlePhoneMouseLeave}
        >
          <IconButton
            ref={phoneButtonRef}
            disableRipple
            aria-label={callActive ? "Hang up call" : "Place call"}
            sx={styles.phoneButton(callActive, phoneHovered, isCallDisabled)}
            disabled={isCallDisabled && !callActive}
            onClick={onPhoneButtonClick}
          >
            {callActive ? (
              <PhoneDisabledRoundedIcon fontSize="medium" sx={{ transform: 'rotate(135deg)', transition: 'transform 0.3s ease' }} />
            ) : (
              <PhoneRoundedIcon fontSize="medium" />
            )}
          </IconButton>
          {!isCallDisabled && showPhoneTooltip && phoneTooltipPos && (
            <div
              style={{
                ...styles.buttonTooltip,
                top: phoneTooltipPos.top,
                left: phoneTooltipPos.left,
                ...(showPhoneTooltip ? styles.buttonTooltipVisible : {}),
              }}
            >
              {callActive ? "End the conversation" : "Start a conversation"}
            </div>
          )}
        </div>
      </div>

      {typeof onMainViewChange === "function" && (
        null
      )}

      {isCallDisabled && showPhoneTooltip && phoneDisabledPos && (
        <div
          style={{
            ...styles.phoneDisabledDialog,
            top: phoneDisabledPos.top,
            left: phoneDisabledPos.left,
          }}
        >
          ⚠️ Outbound calling is disabled. Update backend .env with Azure Communication Services settings (ACS_CONNECTION_STRING, ACS_SOURCE_PHONE_NUMBER, ACS_ENDPOINT) to enable this feature.
        </div>
      )}
    </div>
  );
});

export default React.memo(ConversationControls);
