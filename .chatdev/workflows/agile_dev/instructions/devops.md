# DevOps Engineer Guidelines

## Scope Evaluation
Before creating deployment config:
- If project already has adequate config, just provide a brief status summary
- Match deployment complexity to project size (simple API != Kubernetes)

## Containerization Standards
- Multi-stage Dockerfile (builder -> runtime)
- Non-root user in runtime stage
- .dockerignore for build context
- Health check instruction
- Minimal base image (alpine/slim)

## CI/CD Pipeline Stages
1. Install dependencies
2. Lint / format check
3. Run unit tests
4. Run integration tests
5. Security scan (dependency audit)
6. Build container image

## Security Gates
- No secrets in Dockerfile or docker-compose
- Dependency vulnerability scan
- Secret detection (no hardcoded credentials)

## Health Endpoints
- `/health` — liveness check (actual dependency checks, not just 200)
- `/ready` — readiness check
