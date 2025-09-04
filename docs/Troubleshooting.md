# Troubleshooting Guide

This guide provides quick solutions for common issues with the Real-Time Audio Agent application.

## Table of Contents

- [ACS (Azure Communication Services) Issues](#acs-azure-communication-services-issues)
- [WebSocket Connection Issues](#websocket-connection-issues)
- [Networking & Connectivity](#networking--connectivity)
- [Backend API Issues](#backend-api-issues)
- [Frontend Issues](#frontend-issues)
- [Azure AI Services Issues](#azure-ai-services-issues)
- [Redis Connection Issues](#redis-connection-issues)
- [Deployment Issues](#deployment-issues)
- [Performance Issues](#performance-issues)
- [Debugging Tools](#debugging-tools)

---

## ACS (Azure Communication Services) Issues

### Problem: ACS not making outbound calls

**Symptoms:**
- Call fails to initiate
- No audio connection established
- ACS callback events not received

**Solutions:**
1. **Check App Service Logs:**
   ```bash
   make monitor_backend_deployment
   # Or check Azure Container Apps logs
   az containerapp logs show --name <your-app-name> --resource-group <rg-name>
   ```

2. **Verify Webhook URL is publicly accessible:**
   - Must use HTTPS (not HTTP)
   - Use devtunnel for local development:
     ```bash
     devtunnel host -p 8010 --allow-anonymous
     ```
   - Or use ngrok:
     ```bash
     ngrok http 8010
     ```

3. **Test WebSocket connectivity:**
   ```bash
   # Install wscat if not available
   npm install -g wscat
   
   # Test WebSocket connection
   wscat -c wss://your-domain.com/ws/call/{callConnectionId}
   ```

4. **Check ACS Resource Configuration:**
   - Verify ACS connection string in environment variables
   - Ensure phone number is properly configured
   - Check PSTN calling is enabled

### Problem: Audio quality issues or dropouts

**Solutions:**
1. Check network latency to Azure region
2. Verify TTS/STT service health
3. Monitor Redis connection stability
4. Check container resource limits

---

## WebSocket Connection Issues

### Problem: WebSocket connection fails or drops frequently

**Symptoms:**
- `WebSocket connection failed` errors
- Frequent reconnections
- Missing real-time updates

**Solutions:**
1. **Test WebSocket endpoint directly:**
   ```bash
   wscat -c wss://<backend-domain>:8010/call/stream
   ```

2. **Check CORS configuration:**
   - Verify frontend origin is allowed
   - Ensure WebSocket upgrade headers are supported

3. **Monitor connection lifecycle:**
   ```bash
   # Check backend logs for WebSocket events
   tail -f logs/app.log | grep -i websocket
   ```

4. **Verify environment variables:**
   ```bash
   # Check if required vars are set
   echo $AZURE_ACS_CONNECTION_STRING
   echo $REDIS_URL
   ```

---

## Networking & Connectivity

### Problem: Cannot access application from external networks

**Solutions:**
1. **For local development:**
   ```bash
   # Start devtunnel
   devtunnel host -p 8010 --allow-anonymous
   
   # Or use ngrok
   ngrok http 8010
   ```

2. **Check firewall rules:**
   - Ensure ports 8010 (backend) and 5173 (frontend) are open
   - Verify Azure NSG rules if deployed

3. **Verify DNS resolution:**
   ```bash
   nslookup your-domain.com
   dig your-domain.com
   ```

### Problem: SSL/TLS certificate issues

**Solutions:**
1. **For development with self-signed certs:**
   ```bash
   # Accept self-signed certificates in browser
   # Or configure proper SSL certificates
   ```

2. **Check certificate validity:**
   ```bash
   openssl s_client -connect your-domain.com:443 -servername your-domain.com
   ```

---

## Backend API Issues

### Problem: FastAPI server won't start

**Symptoms:**
- Import errors
- Port already in use
- Environment variable errors

**Solutions:**
1. **Check Python environment:**
   ```bash
   conda activate audioagent
   pip install -r requirements.txt
   ```

2. **Kill processes using port 8010:**
   ```bash
   lsof -ti:8010 | xargs kill -9
   ```

3. **Run with detailed logging:**
   ```bash
   uvicorn apps.rtagent.backend.main:app --reload --port 8010 --log-level debug
   ```

4. **Check environment file:**
   ```bash
   # Ensure .env file exists and has required variables
   cat .env | grep -E "(AZURE_|REDIS_|OPENAI_)"
   ```

### Problem: API endpoints returning 500 errors

**Solutions:**
1. **Check backend logs:**
   ```bash
   tail -f logs/app.log
   ```

2. **Test individual endpoints:**
   ```bash
   curl -X GET http://localhost:8010/health
   curl -X POST http://localhost:8010/api/v1/calls/start -H "Content-Type: application/json" -d '{}'
   ```

3. **Verify database connections:**
   ```bash
   # Test Redis connection
   redis-cli -u $REDIS_URL ping
   ```

---

## Frontend Issues

### Problem: React app won't start or compile errors

**Solutions:**
1. **Clear node modules and reinstall:**
   ```bash
   cd apps/rtagent/frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

2. **Check Node.js version:**
   ```bash
   node --version  # Should be >= 18
   npm --version
   ```

3. **Start with verbose logging:**
   ```bash
   npm run dev -- --verbose
   ```

### Problem: Frontend can't connect to backend

**Solutions:**
1. **Check proxy configuration in vite.config.js**
2. **Verify backend is running:**
   ```bash
   curl http://localhost:8010/health
   ```

3. **Check network tab in browser dev tools**
4. **Verify CORS settings in backend**

---

## Azure AI Services Issues

### Problem: Speech-to-Text not working

**Solutions:**
1. **Check Azure Cognitive Services key:**
   ```bash
   echo $AZURE_COGNITIVE_SERVICES_KEY
   echo $AZURE_COGNITIVE_SERVICES_REGION
   ```

2. **Test STT service directly:**
   ```bash
   # Use curl to test Azure Speech API
   curl -X POST "https://$AZURE_COGNITIVE_SERVICES_REGION.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1" \
     -H "Ocp-Apim-Subscription-Key: $AZURE_COGNITIVE_SERVICES_KEY" \
     -H "Content-Type: audio/wav" \
     --data-binary @test.wav
   ```

3. **Check service quotas and limits**
4. **Verify region availability for your subscription**

### Problem: OpenAI API errors

**Solutions:**
1. **Check API key and endpoint:**
   ```bash
   echo $AZURE_OPENAI_ENDPOINT
   echo $AZURE_OPENAI_API_KEY
   ```

2. **Test API connectivity:**
   ```bash
   curl -X GET "$AZURE_OPENAI_ENDPOINT/openai/deployments?api-version=2023-12-01-preview" \
     -H "api-key: $AZURE_OPENAI_API_KEY"
   ```

3. **Verify model deployment names match configuration**

---

## Redis Connection Issues

### Problem: Redis connection timeouts or failures

**Solutions:**
1. **Test Redis connectivity:**
   ```bash
   redis-cli -u $REDIS_URL ping
   redis-cli -u $REDIS_URL info server
   ```

2. **Check Redis configuration:**
   ```bash
   # For local Redis
   redis-server --version
   
   # Check if Redis is running
   ps aux | grep redis
   ```

3. **For Azure Redis Cache:**
   - Verify connection string format
   - Check firewall rules
   - Ensure SSL is enabled if required

---

## Deployment Issues

### Problem: azd deployment fails

**Solutions:**
1. **Check Azure authentication:**
   ```bash
   az account show
   az account list-locations
   ```

2. **Verify subscription and resource group:**
   ```bash
   azd env get-values
   ```

3. **Check deployment logs:**
   ```bash
   azd logs
   ```

4. **Common fixes:**
   ```bash
   # Clean and redeploy
   azd down --force --purge
   azd up
   ```

### Problem: Container deployment issues

**Solutions:**
1. **Check container logs:**
   ```bash
   az containerapp logs show --name <app-name> --resource-group <rg-name> --follow
   ```

2. **Verify container registry access:**
   ```bash
   az acr repository list --name <registry-name>
   ```

3. **Check resource quotas:**
   ```bash
   az vm list-usage --location <region>
   ```

---

## Performance Issues

### Problem: High latency in audio processing

**Solutions:**
1. **Monitor resource usage:**
   ```bash
   # Check CPU and memory
   top
   htop  # if available
   ```

2. **Check Azure region proximity**
3. **Monitor Redis performance**
4. **Review container resource limits**

### Problem: Memory leaks or high memory usage

**Solutions:**
1. **Profile Python memory usage:**
   ```python
   # Add to your code for debugging
   import psutil
   process = psutil.Process()
   print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")
   ```

2. **Check for connection leaks**
3. **Monitor WebSocket connections**

---

## Debugging Tools

### Essential Commands

```bash
# Check all services health
make health_check

# Monitor backend deployment
make monitor_backend_deployment

# View logs
tail -f logs/app.log

# Test WebSocket connection
wscat -c ws://localhost:8010/ws/call/test-id

# Check network connectivity
curl -v http://localhost:8010/health

# Monitor system resources
htop
iotop  # for disk I/O
```

### Log Locations

- **Backend logs:** container logs
- **Frontend logs:** Browser console (F12)
- **Azure logs:** Azure Monitor / Application Insights
- **System logs:** `/var/log/` (Linux) or Console.app (macOS)

---

## Getting Help

If you're still experiencing issues:

1. **Check GitHub Issues:** Look for similar problems in the repository
2. **Enable debug logging:** Set `LOG_LEVEL=DEBUG` in your environment
3. **Collect logs:** Gather relevant logs before reporting issues
4. **Test with minimal setup:** Try with basic configuration first
5. **Check Azure service health:** Visit Azure status page
