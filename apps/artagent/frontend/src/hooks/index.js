/**
 * Custom React Hooks for Real-Time Voice Agent
 * 
 * Collection of reusable hooks for state management and effects
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { API_BASE_URL, WS_URL } from '../config/constants';

/**
 * Hook for managing application state
 */
export const useAppState = () => {
  const [recording, setRecording] = useState(false);
  const [messages, setMessages] = useState([]);
  const [backendStats, setBackendStats] = useState(null);
  const [showBackendStats, setShowBackendStats] = useState(false);
  const [debugInfo, setDebugInfo] = useState({});
  const [lastError, setLastError] = useState(null);
  const [connectionState, setConnectionState] = useState('disconnected');
  const [callActive, setCallActive] = useState(false);
  const [showPhoneInput, setShowPhoneInput] = useState(false);
  const [targetPhoneNumber, setTargetPhoneNumber] = useState('');
  const [amplitude, setAmplitude] = useState(0);

  return {
    recording, setRecording,
    messages, setMessages,
    backendStats, setBackendStats,
    showBackendStats, setShowBackendStats,
    debugInfo, setDebugInfo,
    lastError, setLastError,
    connectionState, setConnectionState,
    callActive, setCallActive,
    showPhoneInput, setShowPhoneInput,
    targetPhoneNumber, setTargetPhoneNumber,
    amplitude, setAmplitude
  };
};

/**
 * Hook for managing WebSocket connection
 */
export const useWebSocket = (setConnectionState, setLastError, setDebugInfo) => {
  const ws = useRef(null);
  const mediaRecorder = useRef(null);
  const audioContext = useRef(null);
  const workletNode = useRef(null);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');
    ws.current = new WebSocket(WS_URL);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setConnectionState('connected');
      setLastError(null);
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      setConnectionState('disconnected');
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
      setLastError('WebSocket connection failed');
      setConnectionState('error');
    };

    return ws.current;
  }, [setConnectionState, setLastError]);

  const disconnect = useCallback(() => {
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  const sendMessage = useCallback((message) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  }, []);

  return {
    ws: ws.current,
    mediaRecorder,
    audioContext,
    workletNode,
    connect,
    disconnect,
    sendMessage
  };
};

/**
 * Hook for managing audio recording
 */
export const useAudioRecording = () => {
  const [isSupported, setIsSupported] = useState(false);
  const [permissionGranted, setPermissionGranted] = useState(false);

  useEffect(() => {
    const checkSupport = async () => {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        setIsSupported(true);
        
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          setPermissionGranted(true);
          stream.getTracks().forEach(track => track.stop());
        } catch (error) {
          console.log('Microphone permission not yet granted');
        }
      }
    };

    checkSupport();
  }, []);

  const requestPermission = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        }
      });
      setPermissionGranted(true);
      return stream;
    } catch (error) {
      console.error('Failed to get microphone permission:', error);
      throw error;
    }
  }, []);

  return {
    isSupported,
    permissionGranted,
    requestPermission
  };
};

/**
 * Hook for handling backend API calls
 */
export const useBackendAPI = () => {
  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      if (response.ok) {
        return await response.json();
      }
      throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      console.error('Failed to fetch backend stats:', error);
      throw error;
    }
  }, []);

  const makeCall = useCallback(async (phoneNumber) => {
    try {
      const response = await fetch(`${API_BASE_URL}/call`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          phoneNumber: phoneNumber,
          callbackUrl: `${window.location.origin}/webhook/callback`
        }),
      });

      if (response.ok) {
        return await response.json();
      }
      throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      console.error('Failed to initiate call:', error);
      throw error;
    }
  }, []);

  const endCall = useCallback(async (callId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/call/${callId}/end`, {
        method: 'POST',
      });

      if (response.ok) {
        return await response.json();
      }
      throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      console.error('Failed to end call:', error);
      throw error;
    }
  }, []);

  return {
    fetchStats,
    makeCall,
    endCall
  };
};

/**
 * Hook for managing auto-scroll behavior
 */
export const useAutoScroll = (dependency) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [dependency]);

  return scrollRef;
};
