# DataProtection MVP foundation

## Proposed folder structure

- `frontend/` React + Vite application for authentication, onboarding, dashboard, wizard, findings, and report summary pages.
- `backend/` Python AWS Lambda handlers, assessment services, and automated tests.
- `frameworks/` JSON framework definitions that keep sections, controls, questions, scoring, and legal mapping configurable.
- `docs/` product and architecture reference material for the MVP.

## DynamoDB single-table schema

### Table
- Table name: `DataProtection`
- Partition key: `PK`
- Sort key: `SK`
- Recommended GSIs:
  - `GSI1PK` / `GSI1SK` for cross-entity lookups by tenant and type.
  - `GSI2PK` / `GSI2SK` for workflow queries such as assessments by status or reports by date.

### Entity patterns

| Entity | PK | SK | Notes |
| --- | --- | --- | --- |
| Tenant | `TENANT#{tenantId}` | `META` | Root tenant record with organisation profile and privacy profile summary. |
| User | `TENANT#{tenantId}` | `USER#{userId}` | Keeps users grouped within tenant for future multi-user support. |
| Framework | `FRAMEWORK#{frameworkId}` | `META` | Global framework metadata, versioning, and jurisdiction. |
| Section | `FRAMEWORK#{frameworkId}` | `SECTION#{sectionId}` | Reusable structure across regulations. |
| Control | `FRAMEWORK#{frameworkId}` | `CONTROL#{sectionId}#{controlId}` | Weighted compliance controls with legal references. |
| Question | `FRAMEWORK#{frameworkId}` | `QUESTION#{sectionId}#{questionId}` | Plain-language questions linked to controls. |
| Assessment | `TENANT#{tenantId}` | `ASSESSMENT#{assessmentId}` | Tenant-scoped assessment shell with framework version and status. |
| Response | `TENANT#{tenantId}` | `ASSESSMENT#{assessmentId}#RESPONSE#{questionId}` | Stores maturity score, notes, and timestamps per question. |
| Evidence | `TENANT#{tenantId}` | `ASSESSMENT#{assessmentId}#EVIDENCE#{evidenceId}` | Metadata for S3 evidence objects and linkage to controls. |
| Finding | `TENANT#{tenantId}` | `ASSESSMENT#{assessmentId}#FINDING#{findingId}` | Generated findings with risk, legal mapping, and action plan. |
| Report | `TENANT#{tenantId}` | `REPORT#{reportId}` | Report manifest and S3 export location. |

### GSI suggestions
- `GSI1PK = TENANT#{tenantId}#TYPE#{entityType}` with `GSI1SK` values such as status, created date, or user email for tenant-specific filtered lists.
- `GSI2PK = FRAMEWORK#{frameworkId}#VERSION#{version}` with `GSI2SK` values for ordered sections, controls, and questions.

### Tenant isolation model
- Every customer-owned item is written under `PK = TENANT#{tenantId}`.
- Cognito tokens should carry `tenantId`, `organizationId`, and `role` claims.
- API Gateway authorizers and Lambda handlers use the token tenant claim to derive allowed partition keys.
- No API route accepts arbitrary tenant IDs from the client; handlers resolve tenant context from the authenticated principal.
- S3 object keys should include the tenant prefix, for example `tenant/{tenantId}/reports/{reportId}.json`, and access should be enforced with IAM policy conditions.

## API route design

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/onboarding/organizations` | Create the tenant and organisation profile. |
| `GET` | `/api/frameworks` | List frameworks available to the tenant. |
| `POST` | `/api/assessments` | Start a new assessment for a chosen framework version. |
| `GET` | `/api/assessments/{assessmentId}` | Retrieve assessment metadata and completion progress. |
| `GET` | `/api/assessments/{assessmentId}/sections` | Fetch ordered sections and questions for the wizard. |
| `PUT` | `/api/assessments/{assessmentId}/responses/{questionId}` | Save or update a maturity response and notes. |
| `POST` | `/api/assessments/{assessmentId}/score` | Calculate weighted section and overall scores. |
| `POST` | `/api/assessments/{assessmentId}/findings` | Generate findings and recommended actions from responses. |
| `GET` | `/api/assessments` | List past assessments for the tenant workspace. |
| `POST` | `/api/assessments/{assessmentId}/reports` | Prepare structured report payload data and export metadata. |

## AWS hosting direction
- Frontend can be deployed to S3 + CloudFront or AWS Amplify Hosting.
- API Gateway fronts Lambda handlers for tenant-scoped REST APIs.
- Amazon Cognito manages authentication and future invitation flows.
- DynamoDB stores tenant, framework, and assessment data in a single-table design.
- Amazon S3 stores report exports and uploaded evidence.
