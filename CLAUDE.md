# student-app-main

FastAPI CRUD application for managing student records, deployed on AWS EKS via ArgoCD and Helm.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Application | Python 3.11 / FastAPI / uvicorn |
| Database | PostgreSQL (AWS RDS) — connection injected via `POSTGRES_CONN_STR` env var |
| Container registry | AWS ECR — `308488080037.dkr.ecr.us-east-1.amazonaws.com/student-api` |
| Helm chart dependency | `application:1.0.16` — `oci://308488080037.dkr.ecr.us-east-1.amazonaws.com` |
| Deployment | ArgoCD on AWS EKS, namespace `service-workshop-control-student-api` |
| Versioning | release-please (`release-type: simple`) |
| CI/CD | GitHub Actions — `.github/workflows/ReleaseApplication.yml` |

---

## Repository Structure

```
student-app-main/
├── app/
│   ├── main.py                        # FastAPI application — all endpoints here
│   └── requirements.txt               # fastapi, uvicorn[standard], psycopg2-binary
├── helm/
│   ├── app/
│   │   └── student-api/
│   │       ├── Chart.yaml             # Chart version managed by release-please
│   │       ├── values.yaml            # Base values — ECR image, probes, service port
│   │       └── dev/
│   │           └── values.eu-west-1.dev.yaml   # Env-specific overrides — image tag, region
│   └── state/
│       └── student-api/
│           └── dev/
│               └── student-api.eu-west-1.dev.yaml  # ArgoCD Application manifest
├── Dockerfile
├── .github/workflows/ReleaseApplication.yml
├── release-please-config.json
└── .release-please-manifest.json      # Current version: 0.1.10
```

---

## Application Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check — returns `{"status": "ok"}` — used by K8s probes |
| GET | `/students` | List all students |
| POST | `/students` | Create a student |
| GET | `/students/{id}` | Get student by ID |
| PUT | `/students/{id}` | Update student |
| DELETE | `/students/{id}` | Delete student |

- Runs on port **8000**
- DB connection opened per request via `get_db_conn()` — `POSTGRES_CONN_STR` env var must be set
- No connection pooling — each request opens and closes a new connection

---

## Helm Chart

### Dependency

The chart is a thin wrapper. All Kubernetes templates (Deployment, Service, HPA, Ingress, PDB)
come from the `application` dependency chart pulled from ECR at `helm dependency update` time.

```yaml
# Chart.yaml
dependencies:
  - name: application
    version: 1.0.16
    repository: oci://308488080037.dkr.ecr.us-east-1.amazonaws.com
```

**Critical**: The repository URL must be the registry root only — do NOT add `/application`.
Helm appends the chart name automatically. Adding `/application` causes the path to double
(`…/application/application:1.0.16`) and the dependency pull fails.

### Values file layout

| File | Purpose |
|---|---|
| `values.yaml` | Base config — ECR image URL, port 8000, probe paths, disabled features |
| `dev/values.eu-west-1.dev.yaml` | Environment overrides — image tag, AWS region, env name |

### Key values decisions

**`image.repository`** — set at root `application.image.repository`, NOT under
`application.deployment.image`. The `application` chart's deployment template reads
`.Values.image.repository` directly for the container image URL.

**`image.tag`** — must be set in BOTH locations in the dev values file:
- `application.image.tag` — used by the deployment template for the actual container image
- `application.deployment.image.tag` — used by label helpers (`application.version`)

**Service port 8000** — the `application` chart derives container port from
`service.ports[0].port`. Setting `service.ports[0].port: 8000` controls both the
service and container port.

**Disabled features** — these are explicitly disabled to avoid dependency on operators/resources
not present in the cluster:
- `externalSecrets.enabled: false` — External Secrets Operator not installed
- `ingressInternal.enabled: false` — internal ALB ingress not required

### Known issues in the `application` dependency chart

The `application` chart (`helm-common-main`) has bugs. Work around them in values:

| Bug | Workaround in this repo |
|---|---|
| `imagePullSecrets` not rendered in pod spec | Secret must be attached to service account or patched separately until chart is fixed |
| `podSecurityContext` / `containerSecurityContext` not rendered | Security context is not applied — track in backlog |
| Probe `enabled` field leaks into K8s spec | No workaround needed — probe `enabled` field renders as an unknown field; Kubernetes ignores unknown fields in practice |
| `startupProbe` not rendered | Covered by `livenessProbe` with `initialDelaySeconds` |
| `ingressPublic.hosts` ignored — host and path hardcoded in template | `ingressPublic` is enabled but the configured path (`/student-api`) has no effect until the chart bug is fixed |

Full bug list documented in `helm-common-main/CLAUDE.md`.

---

## ArgoCD Deployment

### Application manifest

`helm/state/student-api/dev/student-api.eu-west-1.dev.yaml` — apply this to create the ArgoCD app:

```bash
kubectl apply -f helm/state/student-api/dev/student-api.eu-west-1.dev.yaml
```

| Field | Value |
|---|---|
| ArgoCD app name | `svc-student-api-dev-euw1` |
| ArgoCD project | `default` |
| Target cluster | `in-cluster` |
| Target namespace | `service-workshop-control-student-api` |
| Git source path | `./helm/app/student-api` |
| Value files | `values.yaml` + `dev/values.eu-west-1.dev.yaml` |
| Helm release name | `svc-student-api-dev-euw1` |

### ArgoCD repositories required

Both must be registered in **ArgoCD → Settings → Repositories** before the application can sync:

| Type | URL | Notes |
|---|---|---|
| Git | `https://github.com/unixbps/student-app` | Source repo |
| Helm (OCI) | `308488080037.dkr.ecr.us-east-1.amazonaws.com` | Enable OCI checkbox — no `oci://` prefix |

### ECR token rotation

ECR tokens expire every **12 hours**. Two credentials need rotating:

1. **ArgoCD OCI Helm repo** — update via CLI:
   ```bash
   argocd repo add 308488080037.dkr.ecr.us-east-1.amazonaws.com \
     --type helm --name ecr-helm-use1 --enable-oci \
     --username AWS \
     --password $(aws ecr get-login-password --region us-east-1) \
     --upsert
   ```

2. **`ecr-pull-secret`** — for pod image pulls in the target namespace:
   ```bash
   kubectl create secret docker-registry ecr-pull-secret \
     --namespace service-workshop-control-student-api \
     --docker-server=308488080037.dkr.ecr.us-east-1.amazonaws.com \
     --docker-username=AWS \
     --docker-password=$(aws ecr get-login-password --region us-east-1) \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

---

## Versioning and CI/CD

### How versioning works

1. Merge a commit to `main` with a conventional commit prefix (`feat:`, `fix:`, etc.)
2. `release-please` opens a PR bumping the version in:
   - `.release-please-manifest.json`
   - `helm/app/student-api/Chart.yaml` (version + appVersion)
   - `helm/app/student-api/dev/values.eu-west-1.dev.yaml` (image.tag + deployment.image.tag)
3. Merging the release PR triggers the `build-and-push-ecr` job
4. Docker image is pushed to ECR with the new version tag
5. ArgoCD detects the Git change and syncs (if auto-sync is enabled) or requires manual sync

### CI/CD pipeline

`.github/workflows/ReleaseApplication.yml`:

| Job | Trigger | What it does |
|---|---|---|
| `Release.Please` | Push to `main` or `workflow_dispatch` | Creates/updates release PR, outputs version tag |
| `Docker.Build.Publish` | Release created or manual dispatch | Builds Docker image, pushes to ECR with version tag |

**Secrets required in GitHub:**
- `PAT_TOKEN` — GitHub Personal Access Token for release-please to open PRs
- `AWS_ACCESS_KEY_ID` — for ECR push
- `AWS_SECRET_ACCESS_KEY` — for ECR push

**Variables required:**
- `AWS_ACCOUNT_ID` — used to construct ECR repository URL

The `trigger-deployment` job is commented out — ArgoCD sync is triggered manually or via
auto-sync policy, not by the pipeline.

---

## Local Development

```bash
# Run with Docker
docker build -t student-api .
docker run -p 8000:8000 -e POSTGRES_CONN_STR="postgresql://user:pass@host:5432/db" student-api

# Test health endpoint
curl http://localhost:8000/health

# API docs (auto-generated by FastAPI)
open http://localhost:8000/docs
```

---

## Do's and Don'ts

DO:
- Add the `/health` endpoint first in `main.py` — probes depend on it returning 200
- Set both `image.tag` and `deployment.image.tag` in the env-specific values file when updating
  the image tag manually
- Run `helm dependency update helm/app/student-api` locally to verify the OCI chart pulls before
  pushing to Git
- Use conventional commits (`feat:`, `fix:`, `chore:`) — release-please parses them for versioning

DO NOT:
- Add `/application` to the `repository` URL in `Chart.yaml` — Helm appends the chart name and
  the path will double, breaking dependency resolution
- Set `externalSecrets.enabled: true` unless External Secrets Operator is installed in the cluster
- Change `service.ports[0].port` without also verifying probe port name `http` still resolves —
  the chart derives container port from service port
- Store `POSTGRES_CONN_STR` in plaintext — inject via Kubernetes Secret and reference in
  `deployment.secrets` once `imagePullSecrets` / secrets rendering is fixed in the dependency chart
