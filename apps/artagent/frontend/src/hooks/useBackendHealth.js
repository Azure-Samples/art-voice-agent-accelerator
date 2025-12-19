import { useCallback, useEffect, useMemo, useState } from 'react';
import logger from '../utils/logger.js';

export const useBackendHealth = (url, { intervalMs = 30000 } = {}) => {
  const [isConnected, setIsConnected] = useState(null);
  const [readinessData, setReadinessData] = useState(null);
  const [agentsData, setAgentsData] = useState(null);
  const [healthData, setHealthData] = useState(null);
  const [error, setError] = useState(null);

  const checkReadiness = useCallback(async () => {
    try {
      const response = await fetch(`${url}/api/v1/readiness`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data.status && data.checks && Array.isArray(data.checks)) {
        setReadinessData(data);
        setIsConnected(data.status !== 'unhealthy');
        setError(null);
      } else {
        throw new Error('Invalid response structure');
      }
    } catch (err) {
      logger.error('Readiness check failed:', err);
      setIsConnected(false);
      setError(err.message);
      setReadinessData(null);
    }
  }, [url]);

  const checkAgents = useCallback(async () => {
    try {
      const response = await fetch(`${url}/api/v1/agents`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (!data || typeof data !== 'object') {
        setAgentsData(null);
        return;
      }
      const agentsArray =
        (Array.isArray(data.agents) && data.agents) ||
        (Array.isArray(data.summaries) && data.summaries) ||
        (Array.isArray(data.agent_summaries) && data.agent_summaries) ||
        [];

      setAgentsData({ ...data, agents: agentsArray });
    } catch (err) {
      logger.error('Agents check failed:', err);
      setAgentsData(null);
    }
  }, [url]);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${url}/api/v1/health`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      if (data.status) {
        setHealthData(data);
      } else {
        throw new Error('Invalid health response structure');
      }
    } catch (err) {
      logger.error('Health check failed:', err);
      setHealthData(null);
    }
  }, [url]);

  useEffect(() => {
    checkReadiness();
    checkAgents();
    checkHealth();
    const interval = setInterval(() => {
      checkReadiness();
      checkAgents();
      checkHealth();
    }, intervalMs);
    return () => clearInterval(interval);
  }, [checkReadiness, checkAgents, checkHealth, intervalMs]);

  const statusInfo = useMemo(() => {
    const readinessChecks = readinessData?.checks ?? [];
    const unhealthyChecks = readinessChecks.filter((c) => c.status === 'unhealthy');
    const degradedChecks = readinessChecks.filter((c) => c.status === 'degraded');
    const acsOnlyIssue =
      unhealthyChecks.length > 0 &&
      degradedChecks.length === 0 &&
      unhealthyChecks.every((c) => c.component === 'acs_caller') &&
      readinessChecks
        .filter((c) => c.component !== 'acs_caller')
        .every((c) => c.status === 'healthy');

    const getOverallStatus = () => {
      if (!readinessData?.checks) {
        if (isConnected === null) return 'checking';
        if (!isConnected) return 'unhealthy';
        return 'checking';
      }
      if (acsOnlyIssue) return 'degraded';
      if (unhealthyChecks.length > 0) return 'unhealthy';
      if (degradedChecks.length > 0) return 'degraded';
      return 'healthy';
    };

    return {
      acsOnlyIssue,
      overallStatus: getOverallStatus(),
      readinessChecks,
      unhealthyChecks,
      degradedChecks,
    };
  }, [isConnected, readinessData]);

  return {
    isConnected,
    readinessData,
    agentsData,
    healthData,
    error,
    ...statusInfo,
    refresh: {
      checkReadiness,
      checkAgents,
      checkHealth,
    },
  };
};

export default useBackendHealth;
