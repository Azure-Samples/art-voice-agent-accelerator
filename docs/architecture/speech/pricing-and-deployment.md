# Speech Services Pricing & Deployment Options

> **Last Updated:** January 2026  
> **Related:** [Streaming Modes](README.md) | [Speech Services](speech-services.md) | [Orchestration](../orchestration/README.md)

This document covers Azure Speech Services pricing tiers, container deployment options, and breakeven analysis to help you choose the right deployment model.

---

## Deployment Models Overview

| Model | Internet Required | Best For | Minimum Commitment |
|-------|-------------------|----------|-------------------|
| **Pay-as-you-go** | Yes (always) | Low/variable usage, prototyping | None |
| **Commitment Tier (Azure)** | Yes (always) | Predictable cloud workloads | Monthly |
| **Connected Containers** | Yes (billing only) | Latency-sensitive, hybrid scenarios | Monthly |
| **Disconnected Containers** | No (after license) | Air-gapped, data sovereignty, compliance | Annual |

---

## Pricing Comparison

### Speech-to-Text (STT)

| Pricing Tier | Rate | Commitment | Effective Rate | vs PAYG |
|-------------|------|------------|----------------|---------|
| **Pay-as-you-go** | $1.00/hr | None | $1.00/hr | Baseline |
| **Azure Commitment 2K** | $1,600/mo | 2,000 hrs | $0.80/hr | -20% |
| **Azure Commitment 10K** | $6,500/mo | 10,000 hrs | $0.65/hr | -35% |
| **Azure Commitment 50K** | $25,000/mo | 50,000 hrs | $0.50/hr | -50% |
| **Connected Container 2K** | $1,520/mo | 2,000 hrs | $0.76/hr | -24% |
| **Connected Container 10K** | $6,175/mo | 10,000 hrs | $0.62/hr | -38% |
| **Connected Container 50K** | $23,750/mo | 50,000 hrs | $0.48/hr | -52% |
| **Disconnected 120K** | $74,100/yr | 120,000 hrs/yr | $0.62/hr | -38% |
| **Disconnected 600K** | $285,000/yr | 600,000 hrs/yr | $0.475/hr | -52.5% |

### Neural Text-to-Speech (TTS)

| Pricing Tier | Rate | Commitment | Effective Rate | vs PAYG |
|-------------|------|------------|----------------|---------|
| **Pay-as-you-go** | $15/1M chars | None | $15/1M | Baseline |
| **Azure Commitment 80M** | $960/mo | 80M chars | $12/1M | -20% |
| **Azure Commitment 400M** | $3,900/mo | 400M chars | $9.75/1M | -35% |
| **Azure Commitment 2B** | $15,000/mo | 2,000M chars | $7.50/1M | -50% |
| **Connected Container 80M** | $912/mo | 80M chars | $11.40/1M | -24% |
| **Connected Container 400M** | $3,705/mo | 400M chars | $9.26/1M | -38% |
| **Connected Container 2B** | $14,250/mo | 2,000M chars | $7.13/1M | -52% |
| **Disconnected 4.8B** | $47,424/yr | 4.8B chars/yr | $9.88/1M | -34% |
| **Disconnected 24B** | $182,400/yr | 24B chars/yr | $7.60/1M | -49% |

---

## Disconnected Container Deep Dive

### Annual Fixed Costs

Disconnected containers are **annual commitments** with monthly quotas—no metering required after license download.

| Service | Tier | Annual Cost | Monthly Quota |
|---------|------|-------------|---------------|
| **STT Standard** | 120K hrs | $74,100 | 10,000 hrs |
| **STT Standard** | 600K hrs | $285,000 | 50,000 hrs |
| **STT Custom** | 120K hrs | $88,920 | 10,000 hrs |
| **STT Custom** | 600K hrs | $342,000 | 50,000 hrs |
| **STT Add-ons** (LID/Diarization) | 120K hrs | $22,230 | 10,000 hrs |
| **STT Add-ons** (LID/Diarization) | 600K hrs | $85,500 | 50,000 hrs |
| **TTS Neural** | 4.8B chars | $47,424 | 400M chars |
| **TTS Neural** | 24B chars | $182,400 | 2B chars |

### Pricing Structure Analysis

Disconnected container pricing includes a **fixed platform fee** plus **volume-based rate**:

**Given:**
- 120K hours = $74,100/year
- 600K hours = $285,000/year

**If purely linear:** 5× volume would be $370,500, but actual is $285,000 (volume discount).

**Decomposed pricing model:**

| Component | Value |
|-----------|-------|
| **Fixed Platform Fee** | ~$21,375/year (~$1,781/month) |
| **Variable Rate** | ~$0.44/hour |

**Verification:**

| Tier | Fixed | + Variable | = Total |
|------|-------|------------|---------|
| 120K | $21,375 | + (120,000 × $0.44) = $52,725 | $74,100 ✓ |
| 600K | $21,375 | + (600,000 × $0.44) = $263,625 | $285,000 ✓ |

### Combined STT + TTS Annual Costs

| Usage Level | STT Cost | TTS Cost | **Total/Year** | **Monthly Equivalent** |
|-------------|----------|----------|----------------|------------------------|
| Lower tier | $74,100 | $47,424 | **$121,524** | ~$10,127 |
| Higher tier | $285,000 | $182,400 | **$467,400** | ~$38,950 |

---

## Breakeven Analysis

### When to Move from Pay-as-you-go

| Target Tier | Breakeven Usage |
|-------------|-----------------|
| Azure Commitment 2K | 1,600 hrs/month |
| Azure Commitment 10K | 6,500 hrs/month |
| Connected Container 2K | 1,520 hrs/month |
| Connected Container 10K | 6,175 hrs/month |

### Connected vs Disconnected

The key insight: **Disconnected containers are priced identically to connected containers** at equivalent volumes—you're paying for the air-gap capability, not a premium.

| Comparison | Connected (Annual) | Disconnected (Annual) | Difference |
|------------|-------------------|----------------------|------------|
| 10K hrs/month | ~$74,100 | $74,100 | **Equal** |
| 50K hrs/month | ~$285,000 | $285,000 | **Equal** |

---

## Infrastructure Costs (Container Hosting)

When self-hosting containers, add compute costs to Speech API pricing.

### Container Resource Requirements

From [Microsoft documentation](https://learn.microsoft.com/azure/ai-services/speech-service/speech-container-howto):

| Container | Minimum | Recommended | Model Memory |
|-----------|---------|-------------|--------------|
| **STT** | 4 core, 4 GB | 8 core, 8 GB | +4-8 GB |
| **Custom STT** | 4 core, 4 GB | 8 core, 8 GB | +4-8 GB |
| **Language ID** | 1 core, 1 GB | 1 core, 1 GB | — |
| **Neural TTS** | 6 core, 12 GB | 8 core, 16 GB | — |

### Estimated Azure Container Instances (ACI) Costs

| Container | CPU | Memory | Est. ACI Cost |
|-----------|-----|--------|---------------|
| STT | 8 cores | 16 GB | ~$0.15/hr |
| TTS | 8 cores | 16 GB | ~$0.15/hr |
| **Combined** | 16 cores | 32 GB | **~$0.30/hr** |

**Monthly hosting cost:** ~$220/month for 24/7 operation

This adds ~3-5% to effective Speech API costs at high volumes.

---

## Decision Framework

### Choose Pay-as-you-go when:
- Usage < 1,500 STT hours/month
- Variable or unpredictable workloads
- Prototyping or development

### Choose Commitment Tiers when:
- Usage 1,500-10,000+ hours/month
- Predictable monthly volumes
- Cloud deployment acceptable

### Choose Connected Containers when:
- Need reduced network latency
- Hybrid cloud/on-premises architecture
- Data processing locality requirements
- Cloud connectivity for billing acceptable

### Choose Disconnected Containers when:
- **Air-gapped environments** (no internet)
- **Data sovereignty requirements** (HIPAA, government, classified)
- **Regulatory compliance** mandates on-premises processing
- Usage ≥ 10,000 STT hours/month (otherwise not cost-effective)
- Existing on-premises infrastructure available

---

## Deploying Containers in This Accelerator

The accelerator includes Terraform configuration for deploying Speech containers on Azure Container Instances.

### Enable Speech Containers

```hcl
# terraform.tfvars
enable_speech_containers = true
speech_container_enable_tls = true
speech_container_external_ingress = false  # Private access only

# Resource sizing
stt_container_cpu = 8
stt_container_memory = 16
tts_container_cpu = 8
tts_container_memory = 16
```

### Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `enable_speech_containers` | `false` | Deploy STT/TTS containers |
| `speech_container_enable_tls` | `false` | Enable HTTPS/WSS via nginx sidecar |
| `speech_container_external_ingress` | `true` | Public IP (set `false` for VNet-only) |
| `speech_container_location` | — | Override region (defaults to main location) |
| `stt_container_cpu` | `8` | STT container CPU cores |
| `stt_container_memory` | `16` | STT container memory (GB) |
| `tts_container_cpu` | `8` | TTS container CPU cores |
| `tts_container_memory` | `16` | TTS container memory (GB) |

### Terraform Files

- **[`infra/terraform/speech-containers.tf`](../../../infra/terraform/speech-containers.tf)** — Container deployment, TLS termination, health probes

---

## Related Documentation

- [Streaming Modes](README.md) — SpeechCascade vs VoiceLive comparison
- [Speech Services](speech-services.md) — SDK integration reference
- [Resource Pools](resource-pools.md) — Client pooling architecture
- [Orchestration Overview](../orchestration/README.md) — Dual orchestrator architecture

---

## External References

- [Azure Speech Pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/)
- [Speech Container How-to](https://learn.microsoft.com/azure/ai-services/speech-service/speech-container-howto)
- [Disconnected Containers](https://learn.microsoft.com/azure/ai-services/containers/disconnected-containers)
- [Commitment Tiers Documentation](https://learn.microsoft.com/azure/cognitive-services/commitment-tier)