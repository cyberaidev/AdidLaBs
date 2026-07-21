# AdidLaBs — LiteLLM Gateway

> **Concept demo — no affiliation with adidas AG. All products fictional.**

The **model-access tier** for AdidLaBs. LiteLLM is exposed as an
**OpenAI-compatible endpoint** (`LITELLM_URL`) running on **AWS Lambda** behind the
**AWS Lambda Web Adapter**, with an **IAM-auth function URL**. Idle cost is **$0** —
no Fargate, no Postgres, no always-on compute. All model spend is per-token only.

Every agent and Lambda in the system talks to Bedrock **only through this gateway**,
and only by **route name** — never a raw model id. There are **exactly two routes**:

| Route name | Target (APAC cross-region inference profile) | Used by |
|---|---|---|
| `nova-pro`  | `bedrock/apac.amazon.nova-pro-v1:0`                          | Orchestrator only |
| `haiku-4.5` | `bedrock/au.anthropic.claude-haiku-4-5-20251001-v1:0`     | Weather + all 6 category agents |

Region is pinned to **`ap-southeast-2` (Sydney)** in `config.yaml`
(`aws_region_name: ap-southeast-2`), and `drop_params: true` is set so OpenAI-only
parameters the agents may send are silently dropped rather than erroring on Bedrock.

---

## Files

```
gateway/
├── config.yaml            # the two routes (the whole contract). drop_params + region here.
├── run_local.sh           # start LiteLLM locally, prove BOTH routes resolve. Run before any deploy.
├── README.md              # this file
└── lambda/
    ├── bootstrap                # LWA exec wrapper — cold-start entry (Handler = "bootstrap")
    ├── gateway_app.py           # starts LiteLLM's OpenAI-compatible server on 127.0.0.1:$PORT
    ├── requirements.txt         # pinned deps (litellm[proxy], uvicorn, boto3)
    ├── build_zip.sh             # vendors deps for the Lambda platform → gateway/dist/gateway-lambda.zip
    ├── resolve_lwa_layer_arn.sh # prints the current LWA layer ARN (no hardcoded version)
    └── Dockerfile               # container-image alternative to the layer path
```

`build_zip.sh` emits **`gateway/dist/gateway-lambda.zip`** — that is the artifact **infra**
consumes to create the Lambda.

---

## How agents point at the gateway

Agents use any OpenAI-compatible client and set the base URL to `LITELLM_URL`. They pass
the **route name** as `model`. No model id, no region — those live only in `config.yaml`.

```python
# Example: a category agent using the OpenAI SDK against LITELLM_URL.
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["LITELLM_URL"],   # IAM-auth function URL of this gateway
    api_key="not-used-in-demo",           # no master key in the demo (see below)
)

resp = client.chat.completions.create(
    model="haiku-4.5",                    # ROUTE NAME — never a raw model id
    messages=[{"role": "user", "content": "Pick a rain-ready jacket."}],
)
```

The orchestrator is identical except `model="nova-pro"`.

> **IAM auth on the function URL.** Because the function URL is `AuthType=AWS_IAM`, callers
> must **SigV4-sign** requests to it (service `lambda`). Inside AWS — the AgentCore Runtime
> execution role and the `api-handler` Lambda — this is handled by the caller's role holding
> `lambda:InvokeFunctionUrl` on the URL (see the IAM posture in `docs/architecture.md §6`).
> Plain OpenAI SDK calls as shown above are for **local/dev** against a non-IAM endpoint; in
> AWS, wrap the request with SigV4 (e.g. `botocore.auth.SigV4Auth`) or route through a
> caller that signs for you. The route names and payloads are unchanged either way.

---

## Local testing — prove both routes before you deploy

`run_local.sh` starts the exact same LiteLLM server the Lambda runs, then:

1. asserts `/v1/models` exposes **exactly** `nova-pro` and `haiku-4.5` (and nothing else),
2. calls `POST /chat/completions` on **each** route and asserts a non-empty completion.

```bash
# Prereqs: Python 3.12, `pip install 'litellm[proxy]==1.61.20' boto3`,
#          AWS creds with Bedrock access in ap-southeast-2, and model access
#          enabled for Nova Pro + Claude Haiku 4.5 in Sydney.
export AWS_REGION=ap-southeast-2
cd gateway
./run_local.sh
# → "[run_local] SUCCESS: both routes resolved and returned valid responses."
```

It exits non-zero if either route fails, so it doubles as a CI gate. Full LiteLLM
output is written to `/tmp/adidlabs-litellm.log`.

---

## Deploy on Lambda — the layer path (recommended)

The zip is deployed as a **Python 3.12 / x86_64** Lambda with the public
**AWS Lambda Web Adapter** layer attached.

### 1. Build the artifact

```bash
cd gateway
./lambda/build_zip.sh          # → gateway/dist/gateway-lambda.zip
```

Dependencies are installed for the **Lambda platform** (`manylinux2014_x86_64`, `cp312`),
so the zip builds correctly even on an Apple-silicon/macOS dev machine.

### 2. The LWA layer ARN — `ap-southeast-2`, x86_64

The layer ARN has this shape (region + account + name are fixed; **only the
trailing version varies**):

```
arn:aws:lambda:ap-southeast-2:753240598075:layer:LambdaAdapterLayerX86:<VERSION>
```

- Account `753240598075` is the public account hosting the adapter layers in all
  commercial regions.
- **Do not hardcode a version number.** The adapter bumps the version on every
  release, and this public account does **not** grant `ListLayerVersions`, so any
  `:NN` written into a doc cannot be trusted to still be valid — attaching a stale
  or wrong version makes the layer attach fail. **Resolve it at deploy time:**

  ```bash
  # Prints the current x86_64 layer ARN for ap-southeast-2 (nothing else):
  LAYER_ARN="$(gateway/lambda/resolve_lwa_layer_arn.sh)"
  echo "$LAYER_ARN"
  # arm64 variant:      ARCH=arm64 gateway/lambda/resolve_lwa_layer_arn.sh
  # pin a known version: LWA_LAYER_VERSION=28 gateway/lambda/resolve_lwa_layer_arn.sh
  ```

  The resolver uses `get-layer-version-by-arn` (needs only the public
  `GetLayerVersion` permission, not `ListLayerVersions`) to find the highest
  version that actually exists in-region. `infra` calls it so the deployed value
  is always live, not copied from here.
- If you must confirm by hand, the
  [aws-lambda-web-adapter README](https://github.com/awslabs/aws-lambda-web-adapter#lambda-functions-packaged-as-zip-packagetypezip)
  lists the current version; then pass it as `LWA_LAYER_VERSION=<n>`.
- arm64 equivalent (if you switch architecture): `...:layer:LambdaAdapterLayerArm64:<VERSION>`
  via `ARCH=arm64 gateway/lambda/resolve_lwa_layer_arn.sh` (also update
  `build_zip.sh`'s `--platform` to `manylinux2014_aarch64`).

### 3. Function configuration (infra sets these)

| Setting | Value |
|---|---|
| Runtime | `python3.12` |
| Architecture | `x86_64` |
| **Handler** | `bootstrap` (the LWA wrapper execs this script) |
| Layers | `arn:aws:lambda:ap-southeast-2:753240598075:layer:LambdaAdapterLayerX86:<VERSION>` — resolve via `lambda/resolve_lwa_layer_arn.sh`; never a hardcoded `:NN` |
| Env `AWS_LAMBDA_EXEC_WRAPPER` | `/opt/bootstrap` (activates the adapter's wrapper) |
| Env `AWS_LWA_PORT` | `8000` |
| Env `PORT` | `8000` |
| Timeout | ≥ 60s (Bedrock calls); 120s recommended |
| Memory | 1024–1536 MB (LiteLLM import + one in-flight request) |
| Function URL | **`AuthType=AWS_IAM`** — never public |

**How the pieces fit on cold start:** the layer installs the adapter as a Lambda
**extension** plus a wrapper at `/opt/bootstrap`. Setting
`AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap` tells Lambda to launch through that wrapper,
which execs the function **Handler (`bootstrap`)** as a shell command. Our `bootstrap`
then runs `python -m gateway_app`, which starts LiteLLM's FastAPI server on
`127.0.0.1:$PORT`. The adapter proxies the incoming function-URL event to that port and
returns the HTTP response. Result: the same OpenAI-compatible server locally and in Lambda.

`bootstrap` pins `PYTHONPATH="${LAMBDA_TASK_ROOT}:${LAMBDA_TASK_ROOT}/python"` so
**both** the entrypoint (`gateway_app.py`, at the package root) and the vendored deps
(under `python/`) resolve explicitly — the `-m gateway_app` import does not rely on
Lambda's default cwd being `LAMBDA_TASK_ROOT`. The container path sets the equivalent
`PYTHONPATH=${LAMBDA_TASK_ROOT}` in the Dockerfile.

### 4. IAM (summary — full policy lives in `infra`)

- **This function's role:** `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`
  scoped to the two APAC inference-profile ARNs (Nova Pro, Haiku 4.5) and the foundation-model
  ARNs they route to. Nothing else.
- **Callers** (AgentCore Runtime role, `api-handler` role) need `lambda:InvokeFunctionUrl`
  on this function URL. The URL's `AWS_IAM` auth guarantees only those principals reach it.

---

## Deploy on Lambda — the container alternative

If you prefer a container image over the zip+layer, use `lambda/Dockerfile`. It copies the
Web Adapter in from `public.ecr.aws/awsguru/aws-lambda-adapter` instead of attaching the
layer; the config, entrypoint, and IAM-auth function URL are identical.

```bash
cd gateway
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=${ACCOUNT}.dkr.ecr.ap-southeast-2.amazonaws.com/adidlabs-litellm
aws ecr create-repository --repository-name adidlabs-litellm --region ap-southeast-2 || true
aws ecr get-login-password --region ap-southeast-2 \
  | docker login --username AWS --password-stdin ${ACCOUNT}.dkr.ecr.ap-southeast-2.amazonaws.com
docker build --platform linux/amd64 -f lambda/Dockerfile -t ${REPO}:latest .
docker push ${REPO}:latest
# Create the Lambda with PackageType=Image → ${REPO}:latest, Function URL AuthType=AWS_IAM.
```

Choose **one** path. The zip+layer path is the default because it has no image build/push and
a smaller cold start.

---

## Flipping routes / adding a model

Everything is a `config.yaml` edit — no code changes, no agent changes.

- **Swap the model behind a route** (one line): change the `model:` under the route. E.g. to
  point `haiku-4.5` at a different profile, edit only that `litellm_params.model`. Agents keep
  sending `model="haiku-4.5"`.
- **Add a new route:** append another `- model_name: <name>` block with its own
  `litellm_params.model` + `aws_region_name`. Then reference `<name>` from an agent. (The demo
  intentionally ships exactly two; `run_local.sh` asserts that count, so update the assertion if
  you deliberately add routes.)
- **Change region:** update `aws_region_name` on each route (kept explicit per-route on purpose).

After any edit, run `./run_local.sh` to confirm the routes still resolve, rebuild with
`./lambda/build_zip.sh`, and redeploy the zip.

---

## No master key in the demo (and how to add one)

The demo runs LiteLLM **without a master key**. Access is controlled at the network edge by
the function URL's **`AWS_IAM`** auth — only principals with the explicit
`lambda:InvokeFunctionUrl` grant can invoke it, so an unauthenticated caller never reaches the
proxy. This keeps the demo simple and avoids shipping a secret to agents.

To require an application-level key as well (defence in depth, or for a non-IAM deployment):

1. In `config.yaml`, uncomment under `general_settings`:
   ```yaml
   general_settings:
     master_key: os.environ/LITELLM_MASTER_KEY
   ```
2. Set `LITELLM_MASTER_KEY` on the Lambda (inject via infra as an environment secret; do not
   commit it).
3. Have every caller send `Authorization: Bearer $LITELLM_MASTER_KEY`. With the OpenAI SDK,
   pass it as `api_key=os.environ["LITELLM_MASTER_KEY"]` instead of the placeholder.
4. **Prove auth works locally** by exporting `LITELLM_MASTER_KEY` before running the smoke
   test:
   ```bash
   cd gateway
   LITELLM_MASTER_KEY='sk-demo-local' ./run_local.sh
   # → "[run_local] SUCCESS: both routes resolved AND master-key auth was accepted ..."
   ```
   When `LITELLM_MASTER_KEY` is set, `run_local.sh` **enables `master_key` for the run**
   (on a throwaway copy of the config — your committed `config.yaml` is untouched) **and
   sends `Authorization: Bearer $LITELLM_MASTER_KEY` on every `/v1/models` and
   `/chat/completions` call.** Because those routes now require the key, a green run is a
   genuine end-to-end proof that the token is accepted; a wrong/missing key makes the proxy
   return 401 and the script fails. With no `LITELLM_MASTER_KEY` exported it runs keyless,
   exactly as the demo default. After it passes, rebuild and redeploy.

The master key and the IAM-auth function URL are independent layers; you can run either or both.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*
*MIT © cyberaidev · github.com/cyberaidev/AdidLaBs*
