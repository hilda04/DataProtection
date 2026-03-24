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
VITE_API_BASE_URL=https://abc123.execute-api.us-east-1.amazonaws.com/dev-sam
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
