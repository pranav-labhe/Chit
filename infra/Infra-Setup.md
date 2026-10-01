# Chit Infrastructure Setup

## 1. Overview

Chit is currently deployed as an ARM64 container on AWS EC2.

The infrastructure path is:

```text
GitHub
   │
   │ GitHub Actions
   ▼
Amazon ECR
   │
   │ Pull ARM64 image
   ▼
AWS EC2 (ARM64)
   │
   ├── Caddy :443
   │       ├── /console → 127.0.0.1:8001 (browser console)
   │       └── other paths → 127.0.0.1:8000 (API)
   │
   └── HTTPS
          ▲
          │
api.chitt.online
```

Public API:

```text
https://api.chitt.online
```

Swagger documentation:

```text
https://api.chitt.online/docs
```

---

# 2. AWS Account / Region

| Item               | Value              |
| ------------------ | ------------------ |
| AWS Region         | `ap-south-1`       |
| Region             | Mumbai             |
| Architecture       | ARM64              |
| Container registry | Amazon ECR         |
| Compute            | EC2                |
| EC2 instance type  | `t4g.small`        |
| Storage            | 30 GiB gp3         |
| Public IPv4        | `15.252.205.123`   |
| Domain             | `chitt.online`     |
| API hostname       | `api.chitt.online` |

---

# 3. Amazon ECR

ECR repository:

```text
chit
```

Repository URI:

```text
316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit
```

Images are tagged using the GitHub Actions run number:

```text
chit:1
chit:2
chit:3
...
```

and:

```text
chit:latest
```

Example:

```text
316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit:latest
```

---

# 4. GitHub Actions

The repository uses GitHub Actions to manually build and push the Chit container image to ECR.

The workflow is intentionally:

```yaml
on:
  workflow_dispatch:
```

There is no automatic push trigger.

The branch can be selected when manually running the workflow.

## AWS authentication

GitHub Actions uses AWS OIDC.

No long-lived AWS access key or secret key is stored in GitHub.

GitHub secret:

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

AWS actions:

```yaml
aws-actions/configure-aws-credentials@v5
amazon-ecr-login@v2
```

Required permissions:

```yaml
permissions:
  id-token: write
  contents: read
```

---

# 5. ARM64 Container Build

The local development environment uses Podman, but the GitHub-hosted build uses Docker/Buildx.

The repository uses:

```text
Containerfile
```

There is no requirement for a separate `Dockerfile`.

The workflow configures QEMU and Buildx so the ARM64 image can be built on the GitHub-hosted runner.

```yaml
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3

- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
```

The image is built with:

```bash
docker build \
  --platform linux/arm64 \
  -f Containerfile \
  -t $ECR_REPOSITORY:${{ github.run_number }} \
  -t $ECR_REPOSITORY:latest \
  .
```

This produces an ARM64 Linux container suitable for the AWS `t4g.small` instance.

---

# 6. EC2 Instance

Instance:

```text
Name: chit-api
```

Architecture:

```text
ARM64 / aarch64
```

Instance type:

```text
t4g.small
```

Resources:

```text
2 vCPU
2 GiB RAM
```

Storage:

```text
30 GiB gp3
```

AMI:

```text
Amazon Linux 2023
```

Availability Zone:

```text
ap-south-1b
```

---

# 7. EC2 Networking

## Private IP

```text
172.31.25.207
```

## Elastic IP

```text
15.252.205.123
```

This Elastic IP is the current public address of the Chit EC2 instance.

The previous auto-assigned public IP:

```text
13.203.45.235
```

is no longer used.

Do not use it for DNS or API configuration.

---

# 8. VPC

VPC:

```text
vpc-0e0c60de0cee090e2
```

VPC CIDR:

```text
172.31.0.0/16
```

Subnet:

```text
subnet-060cb1848611a5837
```

Subnet CIDR:

```text
172.31.0.0/20
```

Availability Zone:

```text
ap-south-1b
```

---

# 9. Internet Routing

Route table:

```text
rtb-0f60c3e2fbfa14acf
```

Routes:

```text
172.31.0.0/16 → local
0.0.0.0/0     → Internet Gateway
```

Internet Gateway:

```text
igw-09f503223afcd70fa
```

This allows the EC2 instance to communicate with the public Internet.

---

# 10. Elastic IP

Elastic IP:

```text
15.252.205.123
```

Allocation:

```text
eipalloc-0e9d8333082c70e63
```

Association:

```text
eipassoc-0cd5e5d53f2f5922a
```

The Elastic IP is associated with:

```text
172.31.25.207
```

The Elastic IP should remain attached because DNS points to it.

---

# 11. EC2 IAM Role

IAM role:

```text
ChitEC2ECRPullRole
```

Purpose:

```text
Allow EC2 to pull container images from Amazon ECR.
```

The role only requires ECR read/pull permissions.

The EC2 instance does not require EC2-management permissions for the Chit deployment.

---

# 12. Security Group

Current Security Group:

```text
sg-0d22a3430547766ff
```

Security Group name:

```text
launch-wizard-1
```

## Intended final inbound rules

| Port | Protocol | Source      | Purpose              |
| ---: | -------- | ----------- | -------------------- |
|   22 | TCP      | Your IP     | SSH / administration |
|   80 | TCP      | `0.0.0.0/0` | HTTP / Caddy         |
|  443 | TCP      | `0.0.0.0/0` | HTTPS / Caddy        |

Port `8000` should **not** be publicly exposed in the final configuration.

During initial troubleshooting, port `8000` was temporarily opened to:

```text
0.0.0.0/0
```

This was used to prove that:

```text
Internet → AWS → EC2 → Docker → Chit
```

was working.

After HTTPS/reverse proxy setup was confirmed, public port `8000` should be removed.

---

# 13. Chit Container

The Chit image is pulled from ECR.

Example:

```bash
docker pull 316672688107.dkr.ecr.ap-south-1.amazonaws.com/chit:latest
```

The container listens internally on:

```text
8000 (API) and 8001 (browser console)
```

The current container was verified as healthy.

Health endpoint:

```text
/health
```

The application currently reports:

```json
{
  "status": "no_model",
  "version": "0.2.0",
  "model_loaded": false,
  "error": "checkpoint not found: checkpoints/latest.pt (train first)",
  "training_job": null
}
```

This is an application/model-state issue, not an infrastructure/networking failure.

---

# 14. Docker Port

During initial deployment, Docker exposed:

```text
0.0.0.0:8000 → container:8000
```

This allowed direct testing:

```bash
curl http://15.252.205.123:8000/health
```

The test succeeded from the laptop.

This proved that the EC2 public networking, Security Group, Docker port mapping and Chit API were functioning.

The final configuration should avoid exposing this port publicly.

Caddy should be the public entry point instead.

---

# 15. Caddy

Caddy is installed as a standalone ARM64 binary.

Version currently installed:

```text
v2.11.4
```

Binary:

```text
/usr/local/bin/caddy
```

Configuration:

```text
/etc/caddy/Caddyfile
```

Caddy is managed by systemd:

```text
/etc/systemd/system/caddy.service
```

---

# 16. Caddy Configuration

Current Caddyfile:

```caddyfile
api.chitt.online {
    @console path /console /console/*
    handle @console {
        uri strip_prefix /console
        reverse_proxy 127.0.0.1:8001
    }
    handle {
        reverse_proxy 127.0.0.1:8000
    }
}
```

This means:

```text
https://api.chitt.online
        ↓
      Caddy
        ↓
127.0.0.1:8000
        ↓
      Chit API (port 8000)
```

The browser console is available at `https://api.chitt.online/console`. The deploy workflow binds its
port 8001 to the EC2 loopback interface; Caddy routes `/console` to it. Do not open port 8001 in the
EC2 security group. After changing the Caddyfile, validate and reload Caddy:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy automatically handles HTTPS certificates for the domain.

Caddy also automatically redirects HTTP requests to HTTPS.

---

# 17. Caddy Service

Caddy is enabled through systemd:

```bash
sudo systemctl enable --now caddy
```

Service:

```text
caddy.service
```

Check status:

```bash
sudo systemctl status caddy --no-pager
```

Expected:

```text
Active: active (running)
```

Validate configuration:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

Expected:

```text
Valid configuration
```

---

# 18. DNS

Domain registrar / DNS provider:

```text
GoDaddy
```

Route 53 hosted-zone creation was not used.

The DNS record for the API is:

| Type | Name  | Value            | TTL      |
| ---- | ----- | ---------------- | -------- |
| A    | `api` | `15.252.205.123` | 1/2 Hour |

Therefore:

```text
api.chitt.online
        ↓
15.252.205.123
```

DNS was verified using both Google DNS and Cloudflare DNS.

Google DNS:

```bash
nslookup api.chitt.online 8.8.8.8
```

Result:

```text
Address: 15.252.205.123
```

Cloudflare DNS:

```bash
nslookup api.chitt.online 1.1.1.1
```

Result:

```text
Address: 15.252.205.123
```

---

# 19. HTTPS Verification

The public HTTPS endpoint is working:

```text
https://api.chitt.online/docs
```

FastAPI Swagger UI is accessible through the domain.

The final request path is:

```text
Client
  ↓
HTTPS
  ↓
api.chitt.online
  ↓
15.252.205.123
  ↓
EC2 :443
  ↓
Caddy
  ↓
127.0.0.1:8000
  ↓
Chit container
```

---

# 20. Verification Commands

## DNS

```bash
nslookup api.chitt.online
```

or:

```bash
nslookup api.chitt.online 8.8.8.8
```

## Chit directly

Temporary/debugging only:

```bash
curl http://15.252.205.123:8000/health
```

## Public HTTPS API

```bash
curl https://api.chitt.online/health
```

## Swagger

Open:

```text
https://api.chitt.online/docs
```

## Caddy status

```bash
sudo systemctl status caddy --no-pager
```

## Caddy logs

```bash
sudo journalctl -u caddy -n 50 --no-pager
```

## Caddy configuration validation

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
```

---

# 21. Current Infrastructure Status

| Component                | Status             |
| ------------------------ | ------------------ |
| Chit repository          | ✅                  |
| `Containerfile`          | ✅                  |
| ARM64 GitHub build       | ✅                  |
| GitHub Actions           | ✅                  |
| GitHub OIDC → AWS        | ✅                  |
| ECR repository           | ✅                  |
| ARM64 ECR image          | ✅                  |
| EC2 ARM64                | ✅                  |
| EC2 `t4g.small`          | ✅                  |
| Elastic IP               | ✅                  |
| GoDaddy DNS              | ✅                  |
| `api.chitt.online`       | ✅                  |
| Caddy                    | ✅                  |
| Automatic HTTPS          | ✅                  |
| Reverse proxy            | ✅                  |
| Swagger `/docs`          | ✅                  |
| Chit container           | ✅                  |
| Model checkpoint         | ⏳ Not deployed yet |
| Public port 8000 removal | ⏳ Final cleanup    |

---

# 22. Final Target

The intended production-style public architecture is:

```text
                         INTERNET
                            │
                            ▼
                  api.chitt.online
                            │
                          HTTPS
                            │
                            ▼
                 Elastic IP
               15.252.205.123
                            │
                            ▼
                     AWS EC2
                    t4g.small
                     ARM64
                            │
                            ▼
                       Caddy
                       :443
                            │
                            ▼
                  ┌─────────┴─────────┐
                  ▼                   ▼
             127.0.0.1:8000     127.0.0.1:8001
               Chit API          Browser console
                  │                   │
                  └─────────┬─────────┘
                            ▼
                    Chit Container
                            │
                            ▼
                     Chit Runtime
```

Only Caddy should be publicly exposed for the application.

Ports `8000` (API) and `8001` (browser console) are internal application ports.

---

# 23. Important Infrastructure Principles

### Stable public address

Always use:

```text
15.252.205.123
```

rather than the old auto-assigned address.

### DNS

The API hostname is:

```text
api.chitt.online
```

DNS is managed through GoDaddy.

### HTTPS

Public API access should use:

```text
https://api.chitt.online
```

not direct HTTP on port `8000`.

### Reverse proxy

Caddy is the public-facing reverse proxy.

Chit itself remains behind Caddy.

### Container

The Chit container does not need to know about the public domain or TLS.

Caddy handles that infrastructure responsibility.

### Security

Public access should ultimately be limited to:

```text
80
443
```

with SSH restricted to the administrator's IP where practical.

Port `8000` should remain private.
