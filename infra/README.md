# AdidLaBs — `infra/`

> **Concept demo — no affiliation with adidas AG. All products fictional.**

One CloudFormation template (`template.yaml`) that assembles the whole durable,
serverless AdidLaBs stack in **`ap-southeast-2` (Sydney)**. Everything it
provisions is request-scoped or storage-priced, so a deployed-but-idle stack
costs effectively nothing. The only piece created outside this template is the
Bedrock Knowledge Base — because Amazon **S3 Vectors is preview** and not a
stable CloudFormation resource type yet (see [Why the KB is script-created](#why-the-kb-is-created-by-a-script-not-cloudformation)).

- `template.yaml` — the single CloudFormation template (the entire module).
- `params.json` — optional parameter file for manual `aws cloudformation` runs.
- `README.md` — this file.

---

## What the template provisions

| Area | Resources |
|---|---|
| **Static site** | Private `AWS::S3::Bucket` + `AWS::CloudFront::Distribution` fronted by **Origin Access Control** (`AWS::CloudFront::OriginAccessControl`, never legacy OAI). `index.html` is the default root object; 403/404 rewrite to `/index.html` for the SPA. The bucket policy grants `s3:GetObject` **only** to this distribution via `AWS:SourceArn`. |
| **KB corpus** | Private `AWS::S3::Bucket` (`adidlabs-kb-corpus-…`) that `data/seed_catalog.py` / `data/setup_kb.py` write the RAG markdown corpus into. |
| **Identity** | `AWS::Cognito::UserPool` (email sign-up, auto-verify) + `AWS::Cognito::UserPoolClient` (public SPA client, **no secret**). Backs AgentCore Identity and authorizes the API. |
| **API** | `AWS::ApiGatewayV2::Api` (HTTP API) with a **JWT authorizer** bound to the Cognito pool, plus one Lambda per route: `GET /api/session`, `GET /api/weather`, `GET/POST/DELETE /api/bag`, `POST /api/chat`, `GET /api/agents`. |
| **MCP tools** | `adidlabs-tools` Lambda (`get_catalog`, `get_deals`, `bag_add`, `bag_get`, `search_lab_knowledge`, `search_web`). Also the host for the **FAISS-in-Lambda KB fallback**. |
| **Models** | `adidlabs-litellm` Lambda behind an `AWS::Lambda::Url` with `AuthType: AWS_IAM`. Routes `nova-pro` / `haiku-4.5` → APAC inference profiles. |
| **Data** | `adidlabs-catalog` (pk `item_id`) and `adidlabs-bag` (pk `user_id`, sk `item_id`) DynamoDB tables, both `PAY_PER_REQUEST`. |
| **IAM** | Six least-privilege roles (below) — five Lambda roles plus the Bedrock KB service role. No shared god-role, no resource wildcards on data/model actions. |

All 7 Lambdas are **Python 3.12**. The LiteLLM function can also run as a
container image (`PackageType: Image`) when you pass `LiteLlmImageUri`.

---

## Stack outputs

The five required by the module contract, the alternate spellings the
`deploy.sh` / `teardown.sh` orchestration reads, and the ids those scripts need
for post-deploy steps — all resolve from one deploy.

| Output | Purpose |
|---|---|
| `CloudFrontURL` / `CloudFrontUrl` | Public site URL (raw CloudFront domain). |
| `ApiUrl` / `ApiBaseUrl` | HTTP API base URL. |
| `LiteLlmUrl` / `LiteLLMUrl` | LiteLLM function URL (AWS_IAM). |
| `UserPoolId` | Cognito user pool id. |
| `UserPoolClientId` | Cognito app client id. |
| `SiteBucketName` | Site bucket (`deploy.sh` syncs `frontend/dist` here). |
| `CloudFrontDistributionId` | Distribution id (`deploy.sh` invalidates it). |
| `KbCorpusBucketName` | KB corpus bucket (seed + `setup_kb.py` target). |
| `KbRoleArn` | Bedrock KB **service-role** ARN. `deploy.sh` reads it (`cfn_output KbRoleArn`) and hands it to `setup_kb.py` as the role the KB assumes (Titan embed + corpus read + S3 Vectors). Falls back to a `KB_ROLE_ARN` env if absent. |
| `ApiHandlerFunctionName` | Chat function name (`deploy.sh` pushes `KB_ID` here). |
| `ToolsFunctionName` | Tools function name (`deploy.sh` pushes `KB_ID` here). |
| `AgentRuntimeArn` | Echoes the `AgentCoreAgentArn` parameter (empty until agents deploy). |
| `KbId` | Echoes the `KbId` parameter (set by `setup_kb.py`). |
| `UserPoolProviderUrl`, `CatalogTableName`, `BagTableName` | Convenience for the frontend / agents config. |

Both output spellings (`CloudFrontURL` and `CloudFrontUrl`, etc.) point at the
same value, so the module contract and the repo scripts are both satisfied.

---

## Parameters

| Parameter | Default | Notes |
|---|---|---|
| `DemoMode` | `true` | Sets `DEMO_MODE`; `true` makes `/api/chat` return the canned stylist reply. |
| `CatalogTable` / `BagTable` | `adidlabs-catalog` / `adidlabs-bag` | DynamoDB table names. |
| `AgentCoreAgentArn` | `""` | AgentCore Runtime ARN for `/api/chat` (provisioned outside CFN). |
| `KbId` | `""` | Bedrock KB id from `setup_kb.py`; empty at first deploy. |
| `TavilyApiKey` | `""` (NoEcho) | Optional; enables Tavily for `search_web`. |
| `LiteLlmImageUri` | `""` | Optional ECR image for the LiteLLM container path. |
| `ArtifactsBucket` + `ApiCodeS3Key` / `ToolsCodeS3Key` | `""` | Point the Lambdas at the real sibling code zips (below). |
| `LambdaMemoryMb` / `LiteLlmMemoryMb` | `256` / `1024` | Function memory. |

`deploy.sh` passes `DemoMode`, `CatalogTable`, and `BagTable` via
`--parameter-overrides`; the rest take their defaults unless you override them.
`params.json` mirrors the defaults for a manual
`aws cloudformation create-stack --parameters file://infra/params.json` run.

---

## Deploy

The repo's `deploy.sh` runs the full ordered pipeline (frontend build → this
template → asset sync → seed → KB → agents → gateway) and reads the outputs
above. To deploy this template alone:

```bash
aws cloudformation deploy \
  --region ap-southeast-2 \
  --stack-name adidlabs \
  --template-file infra/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides DemoMode=true CatalogTable=adidlabs-catalog BagTable=adidlabs-bag
```

`CAPABILITY_NAMED_IAM` is required because the roles have explicit names
(`adidlabs-*-role-<stack>-<region>`). After the stack is up, `deploy.sh` syncs
`frontend/dist` to `SiteBucketName`, invalidates the distribution, seeds the
catalog, runs `setup_kb.py`, and pushes the resulting `KB_ID` onto the chat and
tools Lambdas.

### Running two stacks in one region (name scoping)

Every resource with an explicit physical name is **stack-scoped** with
`${AWS::StackName}` — the IAM roles (`adidlabs-*-role-<stack>-<region>`), the
seven Lambdas (`adidlabs-*-<stack>`), the HTTP API (`adidlabs-http-api-<stack>`),
the Cognito pool/client (`adidlabs-users-<stack>` / `adidlabs-web-<stack>`), and
the CloudFront OAC (`adidlabs-site-oac-<stack>-<account>-<region>`). So a second
stack (e.g. `--stack-name adidlabs-staging`) can stand up in `ap-southeast-2`
alongside the first without a `CREATE_FAILED: name already exists`. The S3
buckets already embed `${AWS::AccountId}-${AWS::Region}` and are account-unique.

The **only** names not stack-scoped by default are the two DynamoDB tables:
their `CatalogTable` / `BagTable` parameters default to the contract-fixed
literals `adidlabs-catalog` / `adidlabs-bag` (the data seed, agents, and tools
read them from `CATALOG_TABLE` / `BAG_TABLE`, and the frontend contract names
them). For a second concurrent stack, override them —
`--parameter-overrides CatalogTable=adidlabs-catalog-staging BagTable=adidlabs-bag-staging`
— since DynamoDB table names are account+region unique. This keeps the single
demo stack on its contract names while making a multi-stack deploy collision-free.

### Packaging: inline bootstrap vs. real sibling code

`deploy.sh` runs `aws cloudformation deploy` **without** a separate `package`
step, so the template ships each Python Lambda with an **inline `Code.ZipFile`
bootstrap** that returns the real endpoint shapes. The site works end-to-end in
`DEMO_MODE` immediately — no artifact staging, no container build.

To run the full sibling implementations (`backend/*.py` + `backend/common/`, and
`mcp-tools/server.py`), stage their zips and pass the code parameters:

```bash
ART=adidlabs-artifacts-$(aws sts get-caller-identity --query Account --output text)
aws s3 mb "s3://$ART" --region ap-southeast-2

# Backend API zip (all handlers + the common/ package at the archive root).
( cd backend && zip -r /tmp/api.zip . -x 'tests/*' 'pytest.ini' >/dev/null )
aws s3 cp /tmp/api.zip "s3://$ART/api.zip"

# MCP tools zip (install deps into the archive so `mcp`, `ddgs` are importable).
( cd mcp-tools && pip install -r requirements.txt -t build >/dev/null \
  && cp server.py register_gateway.py build/ && cd build && zip -r /tmp/tools.zip . >/dev/null )
aws s3 cp /tmp/tools.zip "s3://$ART/tools.zip"

aws cloudformation deploy --region ap-southeast-2 --stack-name adidlabs \
  --template-file infra/template.yaml --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides DemoMode=false \
    ArtifactsBucket="$ART" ApiCodeS3Key=api.zip ToolsCodeS3Key=tools.zip
```

When `ArtifactsBucket` + the matching `*S3Key` are set, the function's `Handler`
switches to the real module entry point (`session.handler`, `weather.handler`,
`bag.handler`, `chat.handler`, `agents.handler`, `server.handler`) and its code
loads from S3 instead of the inline bootstrap.

For **LiteLLM as a container** (the production path with the
`aws-lambda-web-adapter` layer and `gateway/config.yaml`), build and push the
image, then pass `LiteLlmImageUri=<account>.dkr.ecr.ap-southeast-2.amazonaws.com/adidlabs-litellm:latest`.
Without it, the LiteLLM function uses an inline OpenAI-compatible shim over
`bedrock-runtime` Converse so the two routes resolve for the demo.

---

## Teardown

`teardown.sh` deletes the out-of-band KB first, empties the S3 buckets, then
deletes the stack. Manually:

```bash
python3 data/setup_kb.py --teardown           # KB + S3 Vectors index (outside CFN)
aws s3 rm "s3://$(aws cloudformation describe-stacks --stack-name adidlabs \
  --region ap-southeast-2 --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" \
  --output text)" --recursive
aws s3 rm "s3://$(aws cloudformation describe-stacks --stack-name adidlabs \
  --region ap-southeast-2 --query "Stacks[0].Outputs[?OutputKey=='KbCorpusBucketName'].OutputValue" \
  --output text)" --recursive
aws cloudformation delete-stack --stack-name adidlabs --region ap-southeast-2
```

The buckets carry `DeletionPolicy: Delete`, so once emptied the stack removes
them; the DynamoDB tables and Cognito pool are also `Delete` on stack removal.
Idle cost after teardown is zero.

---

## Why the KB is created by a script, not CloudFormation

The RAG store is a **Bedrock Knowledge Base over Amazon S3 Vectors**. S3 Vectors
is in **preview** and is **not yet a stable CloudFormation resource type**, so
the KB, its vector index, and the S3 data source wiring are provisioned by
`data/setup_kb.py` (boto3) rather than this template. That script creates the
index, points the KB at the corpus bucket this template provisions
(`KbCorpusBucketName`), triggers ingestion with **Titan Text Embeddings v2**
(`amazon.titan-embed-text-v2:0`), and prints the resulting **`KB_ID`**.
`deploy.sh` then sets `KB_ID` on the chat and tools Lambdas
(`ApiHandlerFunctionName`, `ToolsFunctionName`). S3 Vectors was chosen over
OpenSearch Serverless precisely to keep idle cost near zero — OpenSearch's
~$90+/mo floor would break the budget.

Even though the KB itself is script-created, **the IAM service-role it assumes is
durable infra and lives in this template** (`KbServiceRole`, exposed as the
`KbRoleArn` output) for a clean cross-module handoff. `create_knowledge_base`
takes a `roleArn`; `deploy.sh` reads `cfn_output KbRoleArn` and passes it to
`setup_kb.py` (falling back to a `KB_ROLE_ARN` env when the output is absent).
The role trusts `bedrock.amazonaws.com` (guarded by `aws:SourceAccount` +
`aws:SourceArn` so only this account's knowledge bases can assume it) and is
scoped to exactly what a VECTOR KB over S3 Vectors needs: `bedrock:InvokeModel`
on the one Titan v2 model, `s3:GetObject`/`ListBucket` on the corpus bucket, and
the `s3vectors:*` index operations on `adidlabs-kb-vectors-<account>`. The
sibling AgentCore **gateway id** is deliberately *not* exposed here — it belongs
to the `gateway/` module and `deploy.sh` already falls back to `GATEWAY_ID` / a
stable default when that output is missing.

### FAISS-in-Lambda fallback

Because S3 Vectors is preview, the design carries a fallback that needs **no new
always-on infrastructure** and keeps the `search_lab_knowledge` signature
unchanged:

1. Embed the same corpus offline with Titan v2 and build a **FAISS** index; store
   the index file as an object in the KB corpus bucket (this template grants the
   tools role `s3:GetObject` on that bucket for exactly this).
2. On cold start, the `adidlabs-tools` Lambda loads the FAISS index from S3 and
   caches it for the container's warm lifetime, serving nearest-neighbour queries
   in-process.
3. At **query time** the fallback embeds the incoming question with Titan v2 in
   the tools Lambda before the FAISS similarity search. The tools role therefore
   also carries `bedrock:InvokeModel` scoped to **exactly**
   `amazon.titan-embed-text-v2:0` (`tools-embed-titan`). This grant is **dormant
   for the shipped code** — `mcp-tools/server.py`'s `search_lab_knowledge` only
   calls `bedrock-agent-runtime` Retrieve and degrades to `search_web` — but it
   exists so the documented query-time-embedding path does **not** hit
   `AccessDenied` if it is ever wired.
4. `search_lab_knowledge` keeps the same inputs/outputs, so agents are unaffected
   by the swap. The KB tool in `mcp-tools/server.py` already degrades gracefully
   to `search_web` when `KB_ID` is unset or the retrieve call fails, so a
   half-configured environment still answers.

This preserves the near-zero-idle property: the index is a single S3 object and
search runs only inside a request-scoped Lambda — never a standing vector service.

---

## IAM posture (least privilege)

Six roles, each scoped to exactly what its function needs — no wildcards on data
or model actions:

- **Stateless role** (`session`, `weather`, `agents`): CloudWatch Logs only. These
  handlers make outbound HTTPS (Open-Meteo / geolocation) and touch no AWS data.
- **Bag role** (`bag`): `dynamodb:GetItem/PutItem/UpdateItem/DeleteItem/Query` on
  the **bag table ARN only**.
- **Chat role** (`chat`, the api-handler): `lambda:InvokeFunctionUrl` (scoped to
  the LiteLLM function ARN, conditioned on `FunctionUrlAuthType = AWS_IAM`) so the
  handler can SigV4-call the model gateway when it needs a direct completion; plus
  `bedrock-agentcore:InvokeAgentRuntime` bounded to this account/region's runtimes
  (added only once `AgentCoreAgentArn` is set; omitted at the first empty deploy).
  No `bedrock:InvokeModel` — all model traffic goes through LiteLLM. The
  identity-policy grant here is paired with the `LiteLlmUrlInvokePermission`
  resource policy on the function; an `AWS_IAM` function URL needs **both**.
- **Tools role** (`tools`): DynamoDB item/query/scan on the **two table ARNs**,
  `bedrock:Retrieve` bounded to this account/region's knowledge bases,
  `s3:GetObject` on the KB corpus bucket, and `bedrock:InvokeModel` scoped to
  **exactly** `amazon.titan-embed-text-v2:0` — the last two solely for the
  FAISS-in-Lambda fallback (dormant for the shipped Retrieve-only code; see
  [FAISS-in-Lambda fallback](#faiss-in-lambda-fallback)).
- **LiteLLM role** (`litellm`): `bedrock:InvokeModel` /
  `InvokeModelWithResponseStream` on **exactly the two APAC inference profiles**
  (`au.anthropic.claude-haiku-4-5-20251001-v1:0`, `apac.amazon.nova-pro-v1:0`)
  plus the foundation-model ARNs those cross-region profiles fan out to. Nothing
  else.
- **KB service role** (`kb`, assumed by **Bedrock**, not a Lambda): trusts
  `bedrock.amazonaws.com` with `aws:SourceAccount` / `aws:SourceArn` confused-
  deputy guards; grants `bedrock:InvokeModel` on the one Titan v2 embedding model,
  `s3:GetObject`/`ListBucket` on the corpus bucket, and the `s3vectors:*` index
  ops on `adidlabs-kb-vectors-<account>`. Exposed as `KbRoleArn` for the
  out-of-band `setup_kb.py` KB creation.

Edge/auth posture: the site bucket is **private** (OAC only, no public access, no
ACLs); the HTTP API's `bag` and `chat` routes require a **Cognito JWT** and derive
`user_id` from the token `sub`, never the request body; and the LiteLLM function
URL is **`AWS_IAM`**, so only principals holding the explicit invoke grant reach it
— never public.

**CORS is configured in exactly one place** — the HTTP API's `CorsConfiguration`
(`AllowOrigins: ["*"]`, methods `GET/POST/DELETE/OPTIONS`). API Gateway injects the
`Access-Control-Allow-Origin` header onto every proxy response, so the Lambda
handlers deliberately do **not** set any `Access-Control-*` header. Emitting it in
both places would send a duplicated ACAO header, which browsers reject — blocking
the CloudFront-origin SPA → `execute-api` calls the whole app depends on.

---

## No circular reference (design note)

The classic trap here is: the API Lambda needs the LiteLLM URL, and if LiteLLM
referenced the API Lambda you'd get a cycle. This template avoids it by declaring
**LiteLLM first** and passing its URL **one-way** into the chat Lambda via a single
`Fn::GetAtt LiteLlmUrl.FunctionUrl` (env) and a one-way `Fn::GetAtt
LiteLlmFunction.Arn` in the chat role's invoke grant. The AgentCore Runtime ARN
arrives via the `AgentCoreAgentArn` **parameter**, not a resource reference.
Dependency chain: `ChatFunction / ChatLambdaRole → LiteLlmUrl / LiteLlmFunction →
LiteLlmLambdaRole` — strictly acyclic (LiteLLM never references anything named
`Chat*`), verified with a graph cycle check.

---

*Concept demo — no affiliation with adidas AG. All products fictional.*
