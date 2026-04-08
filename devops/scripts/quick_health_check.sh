#!/bin/bash
# Quick Health Check - Tests all ARTagent health endpoints
# Usage: ./quick_health_check.sh [environment]

ENV=${1:-contoso}
azd env select "$ENV" > /dev/null 2>&1
BACKEND="https://$(azd env get-value BACKEND_CONTAINER_APP_FQDN 2>/dev/null)"

echo "📊 Quick Health Check - ARTagent ($ENV)"
echo "========================================="
echo ""

# 1. Basic Health
echo "1. Basic Health:"
curl -s --max-time 5 "${BACKEND}/api/v1/health" | jq -c '{status, active_sessions}' || echo "FAILED"
echo ""

# 2. Readiness
echo "2. Readiness (Dependencies):"
curl -s --max-time 10 "${BACKEND}/api/v1/readiness" | jq -c '{status, response_time_ms, checks: [.checks[] | {component, status, check_time_ms}]}' || echo "FAILED"
echo ""

# 3. Pools
echo "3. Resource Pools:"
curl -s --max-time 5 "${BACKEND}/api/v1/pools" | jq -c '{status, pools: (.pools | to_entries | map({name: .key, ready: .value.ready, warm: .value.warm_pool_size, active: .value.active_sessions}))}' || echo "FAILED"
echo ""

# 4. Metrics
echo "4. Session Metrics:"
curl -s --max-time 5 "${BACKEND}/api/v1/metrics/summary" | jq -c '{active_connections, browser_sessions, total_connected, total_disconnected}' || echo "FAILED"
echo ""

# 5. Agents
echo "5. Agents:"
curl -s --max-time 5 "${BACKEND}/api/v1/agents" | jq -c '{agents_count, start_agent, agents: [.agents[0:3] | .[] | .name]}' || echo "FAILED"
echo ""

echo "✅ Quick health check complete"
