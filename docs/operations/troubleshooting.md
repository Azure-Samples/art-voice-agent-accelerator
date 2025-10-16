# :material-wrench: Troubleshooting Guide

!!! abstract "Quick Solutions for Common Issues"
    This guide provides solutions for common issues encountered with the Real-Time Voice Agent application, covering deployment, connectivity, and performance.

---

## :material-phone: ACS & WebSocket Issues

!!! question "Problem: ACS is not making outbound calls or audio quality is poor"
    **Symptoms:**
    - Call fails to initiate or no audio connection is established.
    - ACS callback events are not received.
    - Audio quality is choppy or has high latency.

    **Solutions:**
    1.  **Check Container App Logs:**
        ```bash
        # Monitor backend logs for errors
        make monitor_backend_deployment
        # Or directly query Azure Container Apps
        az containerapp logs show --name <your-app-name> --resource-group <rg-name>
        ```
    2.  **Verify Webhook Accessibility:** Ensure your webhook URL is public and uses `https`. For local development, use a tunnel:
        ```bash
        # Use devtunnel for local development
        devtunnel host -p 8010 --allow-anonymous
        ```
    3.  **Test WebSocket Connectivity:**
        ```bash
        # Install wscat (npm install -g wscat) and test the connection
        wscat -c wss://your-domain.com/ws/call/{callConnectionId}
        ```
    4.  **Check ACS & Speech Resources:** Verify that your ACS connection string and Speech service keys are correctly configured in your environment variables.

!!! question "Problem: WebSocket connection fails or drops frequently"
    **Symptoms:**
    - `WebSocket connection failed` errors in the browser console.
    - Frequent reconnections or missing real-time updates.

    **Solutions:**
    1.  **Test WebSocket Endpoint Directly:**
        ```bash
        wscat -c wss://<backend-domain>/api/v1/media/stream
        ```
    2.  **Check CORS Configuration:** Ensure your frontend's origin is allowed in the backend's CORS settings, especially for WebSocket upgrade headers.
    3.  **Monitor Connection Lifecycle:** Review backend logs for WebSocket connection and disconnection events to identify patterns.

---

## :material-api: Backend & API Issues

!!! question "Problem: FastAPI server won't start or endpoints return 500 errors"
    **Symptoms:**
    - Import errors, "port already in use," or environment variable errors on startup.
    - API endpoints respond with `500 Internal Server Error`.

    **Solutions:**
    1.  **Check Python Environment & Dependencies:**
        ```bash
        # Ensure you are in the correct conda environment
        conda activate audioagent
        # Reinstall dependencies
        pip install -r requirements.txt
        ```
    2.  **Free Up Port:** If port `8010` is in use, find and terminate the process:
        ```bash
        # Find and kill the process on macOS or Linux
        lsof -ti:8010 | xargs kill -9
        ```
    3.  **Run with Debug Logging:**
        ```bash
        uvicorn apps.rtagent.backend.main:app --reload --port 8010 --log-level debug
        ```
    4.  **Verify Environment File (`.env`):** Ensure the file exists and all required variables for Azure, Redis, and OpenAI are correctly set.

---

## :material-cloud-alert: Azure AI & Redis Issues

!!! question "Problem: Speech-to-Text or OpenAI API errors"
    **Symptoms:**
    - Transcription is not appearing or is inaccurate.
    - AI-generated responses are missing or failing.
    - `401 Unauthorized` or `429 Too Many Requests` errors.

    **Solutions:**
    1.  **Check Keys and Endpoints:** Verify that `AZURE_COGNITIVE_SERVICES_KEY`, `AZURE_OPENAI_ENDPOINT`, and other related variables are correct.
    2.  **Test Service Connectivity Directly:**
        ```bash
        # Test Azure Speech API (replace with a valid audio file)
        curl -X POST "https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1" \
          -H "Ocp-Apim-Subscription-Key: {key}" -H "Content-Type: audio/wav" --data-binary @test.wav

        # Test OpenAI API
        curl -X GET "{endpoint}/openai/deployments?api-version=2023-12-01-preview" -H "api-key: {key}"
        ```
    3.  **Check Quotas and Model Names:** Ensure your service quotas have not been exceeded and that the model deployment names in your code match those in the Azure portal.

!!! question "Problem: Redis connection timeouts or failures"
    **Symptoms:**
    - High latency in agent responses.
    - Errors related to reading or writing session state.
    - `ConnectionTimeoutError` in backend logs.

    **Solutions:**
    1.  **Test Redis Connectivity:**
        ```bash
        # Use redis-cli to ping the server
        redis-cli -u $REDIS_URL ping
        ```
    2.  **Verify Configuration:** For Azure Cache for Redis, check the connection string, firewall rules, and whether SSL/TLS is required.

---

## :material-rocket-launch: Deployment & Performance

!!! question "Problem: `azd` deployment fails or containers won't start"
    **Symptoms:**
    - `azd up` or `azd provision` command fails with an error.
    - Container Apps show a status of "unhealthy" or are stuck in a restart loop.

    **Solutions:**
    1.  **Check Azure Authentication & Permissions:**
        ```bash
        # Ensure you are logged into the correct account
        az account show
        # Verify you have Contributor/Owner rights on the subscription
        ```
    2.  **Review Deployment Logs:**
        ```bash
        # Use the 'logs' command for detailed output
        azd logs
        # For container-specific issues
        az containerapp logs show --name <app-name> --resource-group <rg-name> --follow
        ```
    3.  **Purge and Redeploy:** As a last resort, a clean deployment can resolve state issues:
        ```bash
        azd down --force --purge
        azd up
        ```

!!! question "Problem: High latency or memory usage"
    **Symptoms:**
    - Slow audio processing or delayed AI responses.
    - Backend container memory usage grows over time and leads to restarts.

    **Solutions:**
    1.  **Monitor Resources:** Use `htop` or `docker stats` locally, and Application Insights in Azure to monitor CPU and memory usage.
    2.  **Profile Memory Usage:** Add lightweight profiling to your Python code to track object allocation and identify potential leaks.
        ```python
        import psutil
        process = psutil.Process()
        print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")
        ```
    3.  **Check for Connection Leaks:** Ensure that database and WebSocket connections are properly closed and managed.

---

## :material-toolbox-outline: Debugging Tools & Commands

!!! tip "Essential Commands for Quick Diagnostics"

    - **Health Check:**
      ```bash
      make health_check
      ```
    - **Monitor Backend Deployment:**
      ```bash
      make monitor_backend_deployment
      ```
    - **View Logs:**
      ```bash
      tail -f logs/app.log
      ```
    - **Test WebSocket Connection:**
      ```bash
      wscat -c ws://localhost:8010/ws/call/test-id
      ```
    - **Check Network Connectivity:**
      ```bash
      curl -v http://localhost:8010/health
      ```

!!! info "Log Locations"
    - **Backend:** Container logs in Azure or `logs/app.log` locally.
    - **Frontend:** Browser developer console (F12).
    - **Azure Services:** Azure Monitor and Application Insights.
