import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook to monitor backend health and readiness status
 * Provides real-time health monitoring with configurable intervals
 */
export const useHealthMonitor = ({
  baseUrl,
  healthInterval = 30000,    // 30 seconds for basic health
  readinessInterval = 10000, // 10 seconds for detailed readiness
  enableAutoRefresh = true,
}) => {
  const [healthStatus, setHealthStatus] = useState({
    isHealthy: null,
    lastChecked: null,
    error: null,
  });

  const [readinessStatus, setReadinessStatus] = useState({
    status: null,
    timestamp: null,
    responseTime: null,
    checks: [],
    lastChecked: null,
    error: null,
  });

  const healthIntervalRef = useRef(null);
  const readinessIntervalRef = useRef(null);
  const mountedRef = useRef(true);

  // Check basic health endpoint
  const checkHealth = useCallback(async () => {
    try {
      const startTime = performance.now();
      const response = await fetch(`${baseUrl}/health`);
      const endTime = performance.now();
      
      if (!mountedRef.current) return;

      const isHealthy = response.ok;
      setHealthStatus({
        isHealthy,
        lastChecked: new Date().toISOString(),
        responseTime: Math.round(endTime - startTime),
        error: isHealthy ? null : `HTTP ${response.status}`,
      });
    } catch (error) {
      if (!mountedRef.current) return;
      
      setHealthStatus({
        isHealthy: false,
        lastChecked: new Date().toISOString(),
        responseTime: null,
        error: error.message,
      });
    }
  }, [baseUrl]);

  // Check detailed readiness endpoint
  const checkReadiness = useCallback(async () => {
    try {
      const response = await fetch(`${baseUrl}/readiness`);
      
      if (!mountedRef.current) return;

      if (response.ok) {
        const data = await response.json();
        setReadinessStatus({
          status: data.status,
          timestamp: data.timestamp,
          responseTime: data.response_time_ms,
          checks: data.checks || [],
          lastChecked: new Date().toISOString(),
          error: null,
        });
      } else {
        setReadinessStatus(prev => ({
          ...prev,
          status: 'unhealthy',
          lastChecked: new Date().toISOString(),
          error: `HTTP ${response.status}`,
        }));
      }
    } catch (error) {
      if (!mountedRef.current) return;
      
      setReadinessStatus(prev => ({
        ...prev,
        status: 'error',
        lastChecked: new Date().toISOString(),
        error: error.message,
      }));
    }
  }, [baseUrl]);

  // Manual refresh function
  const refresh = useCallback(async () => {
    await Promise.all([checkHealth(), checkReadiness()]);
  }, [checkHealth, checkReadiness]);

  // Setup intervals
  useEffect(() => {
    if (!enableAutoRefresh) return;

    // Initial checks
    checkHealth();
    checkReadiness();

    // Setup intervals
    healthIntervalRef.current = setInterval(checkHealth, healthInterval);
    readinessIntervalRef.current = setInterval(checkReadiness, readinessInterval);

    return () => {
      clearInterval(healthIntervalRef.current);
      clearInterval(readinessIntervalRef.current);
    };
  }, [checkHealth, checkReadiness, healthInterval, readinessInterval, enableAutoRefresh]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      mountedRef.current = false;
      clearInterval(healthIntervalRef.current);
      clearInterval(readinessIntervalRef.current);
    };
  }, []);

  // Derived state for overall system status
  const overallStatus = {
    isHealthy: healthStatus.isHealthy && readinessStatus.status === 'ready',
    hasWarnings: readinessStatus.checks.some(check => check.status !== 'healthy'),
    criticalErrors: readinessStatus.checks.filter(check => check.status === 'unhealthy'),
  };

  return {
    healthStatus,
    readinessStatus,
    overallStatus,
    refresh,
    actions: {
      startMonitoring: () => {
        checkHealth();
        checkReadiness();
        if (healthIntervalRef.current) clearInterval(healthIntervalRef.current);
        if (readinessIntervalRef.current) clearInterval(readinessIntervalRef.current);
        healthIntervalRef.current = setInterval(checkHealth, healthInterval);
        readinessIntervalRef.current = setInterval(checkReadiness, readinessInterval);
      },
      stopMonitoring: () => {
        clearInterval(healthIntervalRef.current);
        clearInterval(readinessIntervalRef.current);
      },
    },
  };
};
