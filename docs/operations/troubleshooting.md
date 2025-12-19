# :material-wrench: Troubleshooting Guide

!!! abstract "Quick Solutions for Common Issues"
    This guide provides solutions for common issues encountered with the Real-Time Voice Agent application, covering deployment, connectivity, and performance.

!!! note "Quick Reference Available"
    A condensed version of this guide is available at [TROUBLESHOOTING.md](https://github.com/Azure-Samples/art-voice-agent-accelerator/blob/main/TROUBLESHOOTING.md) in the repository root for quick GitHub access.

---

## :material-package-variant-closed: Deployment & Provisioning Issues

!!! question "Problem: `azd` authentication fails with tenant/subscription mismatch"
    **Symptoms:**
    - Error: `failed to resolve user 'admin@...' access to subscription`
    - Error: `getting tenant id for subscription ... If you recently gained access to this subscription, run azd auth login again`
    - Azure CLI shows a different user/tenant than what `azd` is trying to use

    **Solutions:**
    1.  **Check Current Azure CLI Authentication:**
        ```bash
        az account show
        ```
    2.  **Re-authenticate azd with the Correct Tenant:**
        ```bash
        # Get your tenant ID from az account show, then:
        azd auth logout
        azd auth login --tenant-id <your-tenant-id>
        ```
    3.  **Verify Subscription Access:**
        ```bash
        az account set --subscription "<subscription-id>"
        az account show
        ```
    4.  **Use Device Code Flow (if browser auth fails):**
        ```bash
        azd auth login --use-device-code
        ```

!!! question "Problem: Pre-provision script fails with Docker errors"
    **Symptoms:**
    - Pre-provision step fails intermittently
    - Docker-related errors during `azd up` or `azd provision`
    - Container build failures

    **Solutions:**
    1.  **Ensure Docker Desktop is Running:**
        - Start Docker Desktop and wait for it to fully initialize
        - Verify with: `docker ps`
    2.  **Run from Compatible Shell:**
        - On Windows, use **Git Bash** or **WSL** instead of Windows Terminal/PowerShell
        - On macOS/Linux, ensure you're in a standard terminal
    3.  **Reset Docker if Needed:**
        ```bash
        docker system prune -a
        # Restart Docker Desktop
        ```

!!! question "Problem: `jq: command not found` during provisioning"
    **Symptoms:**
    - `preprovision.sh` fails with `jq: command not found`
    - Exit code 127 during pre-provision hook

    **Solutions:**
    1.  **Install jq:**
        ```bash
        # macOS
        brew install jq
        
        # Ubuntu/Debian
        sudo apt-get install jq
        
        # Windows (winget)
        winget install jqlang.jq
        
        # Windows (chocolatey)
        choco install jq
        ```
    2.  **Verify Installation:**
        ```bash
        jq --version
        ```
    3.  **Restart Terminal:** After installation, open a new terminal session to ensure PATH is updated.

!!! question "Problem: ACS Phone Number prompt confusion"
    **Symptoms:**
    - Prompted to "enter existing phone number or skip" for `ACS_SOURCE_PHONE_NUMBER`
    - Unclear which option to choose during `azd up`

    **Solutions:**
    1.  **If You Have an Existing Phone Number:** Choose option **1** and provide your ACS phone number in E.164 format (e.g., `+15551234567`).
    2.  **Skip for Testing:** Choose option **2** if you're only testing non-telephony features or haven't provisioned a phone number yet.
    3.  **To Get a Phone Number First:**
        - Azure Portal → Communication Services → Phone numbers → **+ Get**
        - Select your country/region and number type (toll-free or geographic)
        - Complete the purchase, then re-run `azd provision` and enter the number

!!! question "Problem: MissingSubscriptionRegistration for Azure providers"
    **Symptoms:**
    - Terraform fails with `MissingSubscriptionRegistration`
    - Error: `The subscription is not registered to use namespace 'Microsoft.Communication'`
    - Similar errors for other providers like `Microsoft.App`, `Microsoft.CognitiveServices`

    **Solutions:**
    1.  **Register Required Providers:**
        ```bash
        # Register all commonly needed providers
        az provider register --namespace Microsoft.Communication
        az provider register --namespace Microsoft.App
        az provider register --namespace Microsoft.CognitiveServices
        az provider register --namespace Microsoft.DocumentDB
        az provider register --namespace Microsoft.Cache
        az provider register --namespace Microsoft.ContainerRegistry
        ```
    2.  **Check Registration Status:**
        ```bash
        az provider show --namespace Microsoft.Communication --query "registrationState"
        ```
    3.  **Wait for Registration:** Provider registration can take 1-2 minutes. Re-run `azd provision` after registration completes.

!!! question "Problem: Terraform state or backend errors"
    **Symptoms:**
    - `Error acquiring the state lock`
    - Backend configuration errors
    - State file corruption warnings

    **Solutions:**
    1.  **Force Unlock State (if stuck):**
        ```bash
        cd infra/terraform
        terraform force-unlock <lock-id>
        ```
    2.  **Reinitialize Terraform:**
        ```bash
        cd infra/terraform
        terraform init -reconfigure
        ```
    3.  **Clean and Retry:**
        ```bash
        rm -rf infra/terraform/.terraform
        rm -f infra/terraform/terraform.tfstate*
        azd provision
        ```

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
        # Reinstall dependencies with uv (recommended)
        uv sync
        
        # Or with pip in a conda environment
        conda activate audioagent
        pip install -e .[dev]
        ```
    2.  **Free Up Port:** If port `8010` is in use, find and terminate the process:
        ```bash
        # Find and kill the process on macOS or Linux
        lsof -ti:8010 | xargs kill -9
        ```
    3.  **Run with Debug Logging:**
        ```bash
        uv run uvicorn apps.artagent.backend.main:app --reload --port 8010 --log-level debug
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

## :material-rocket-launch: Container Apps & Runtime Issues

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

!!! question "Problem: Container image build or push failures"
    **Symptoms:**
    - `azd deploy` fails during image build
    - ACR push errors or authentication failures
    - Image size or timeout errors

    **Solutions:**
    1.  **Authenticate to ACR:**
        ```bash
        az acr login --name <acr-name>
        ```
    2.  **Check ACR Permissions:**
        ```bash
        # Ensure your identity has AcrPush role
        az role assignment list --scope /subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.ContainerRegistry/registries/<acr-name>
        ```
    3.  **Build Locally First to Debug:**
        ```bash
        docker build -t test-image -f apps/artagent/Dockerfile .
        ```

!!! question "Problem: Environment variables not propagating to Container Apps"
    **Symptoms:**
    - Application fails to start with missing configuration errors
    - Services can't connect to Azure resources
    - `KeyError` or `ValueError` for expected environment variables

    **Solutions:**
    1.  **Check azd Environment:**
        ```bash
        azd env get-values
        ```
    2.  **Verify Container App Configuration:**
        ```bash
        az containerapp show --name <app-name> --resource-group <rg> --query "properties.template.containers[0].env"
        ```
    3.  **Re-deploy with Updated Values:**
        ```bash
        azd env set <VAR_NAME> "<value>"
        azd deploy
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
