# Deployment and environment configuration

## Frontend runtime config

The frontend must use `VITE_API_BASE_URL` from environment variables rather than a hardcoded API Gateway URL.

Use the backend stack output as the source of truth after each deploy:

```bash
aws cloudformation describe-stacks \
  --stack-name dataprotection-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text
```

Set that value in frontend environments:

- Local: `frontend/.env.local`
- Amplify Hosting: App settings → Environment variables

Example:

```bash
VITE_API_BASE_URL=<paste ApiUrl stack output here>
```

## Backend deploy checks

Validate and deploy:

```bash
cd backend
sam validate
sam deploy --config-env default
```

Verify routes after deploy:

```bash
API_URL="$(aws cloudformation describe-stacks \
  --stack-name dataprotection-backend \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text)"

curl -i "${API_URL}/health"
```

`/health` should return HTTP 200 with JSON body containing `ok: true`.

## Framework content source of truth

- `GET /frameworks` is served from the backend framework registry (`backend/src/services/framework_registry.py`) through `DataStore.list_frameworks`.
- Assessment questions are snapshotted into each assessment record at creation/restart time (`assessmentSections` in DynamoDB).
- Report recommendations/evidence for new assessments are resolved from question metadata fields first:
  - `recommendation`
  - `evidence_required`
  Legacy `guidance` is used only as a backward-compatible fallback.

Operationally, this means framework JSON updates appear immediately for new assessments, while older assessments keep their original snapshot unless explicitly migrated.
