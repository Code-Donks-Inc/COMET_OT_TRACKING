# COMET

**Change Operations, Management, Engineering & Threat Intelligence**

**Status:** Alpha development / proof of concept

COMET is an industrial cybersecurity, OT asset intelligence, and change management platform designed to help organizations inventory, monitor, and manage operational technology infrastructure.

The platform combines physical asset visibility, vulnerability intelligence, engineering change workflows, and auditable operational records within a centralized management environment.

COMET is being developed with particular attention to industrial environments where equipment availability, operational safety, configuration integrity, and accountability are essential.

### Current Development Status

The current development environment includes:

- A containerized Python, Streamlit, and PostgreSQL application.
- Client, site, building, cabinet, and asset inventory structures.
- Microsoft Entra ID authentication and identity validation.
- An asset assignment request preview and confirmation interface.
- Platform backup infrastructure and supporting operational records.
- Draft engineering approval, audit, and authorization designs.

**Security and release restrictions:** Client-specific authorization, restricted PostgreSQL application privileges, and engineering approval enforcement remain under development. Asset assignment request submission and approval are disabled. Migration 003 has not been applied.

COMET is not yet approved for production deployment.

## Planned Capabilities

### 1. OT Asset Inventory

Maintain a structured inventory of industrial infrastructure, including:

- Clients and organizations
- Sites and facilities
- Buildings and physical locations
- Cabinets and equipment enclosures
- Industrial controllers, drives, sensors, gateways, and other OT assets

### 2. Vulnerability Intelligence

Provide centralized vulnerability visibility for industrial assets, with future support for:

- Asset-to-vulnerability correlation
- Risk prioritization based on operational context
- Vulnerability status tracking
- Remediation planning and reporting
- Historical vulnerability assessments

### 3. Configuration and Change Management

Maintain an auditable record of configuration changes across client environments.

The planned workflow is:

1. A technician completes work and records the resulting configuration.
2. The system immediately creates an immutable completion/audit event.
3. The completed work enters a verification and approval process.
4. An approved configuration becomes the authoritative baseline.
5. When the approved configuration differs from the previous baseline, the system records an immutable differential revision.

Differential revisions will capture what changed rather than duplicating the entire configuration unnecessarily.

Rejected or corrected work must remain visible in the audit history without silently modifying previously approved records.

### 4. Platform Backup and Disaster Recovery

Provide centrally managed backups of the entire platform for disaster recovery.

The intended backup strategy includes:

- Regular full-platform backups
- A 30-day active backup retention window
- Verified monthly archives
- Three-year archive retention measured from actual archive publication
- An authoritative PostgreSQL archive registry
- Immutable archive records and protection against accidental overwrites
- Human review before any archive deletion

Client and site configuration history is a separate capability from full-platform disaster recovery.

**Automatic archive creation and deletion must remain disabled until the relevant controls have been implemented, tested, and explicitly authorized.**

### 5. Multi-Tenant Architecture

The long-term design will support multiple organizations and users, with appropriate isolation and access controls.

Planned considerations include role-based access, approval permissions, tenant isolation, auditability, and centralized scheduling of platform-wide operations.

## Current Technology Stack

- **Python** - Application logic and background processing
- **Streamlit** - Web application interface
- **PostgreSQL** - Relational data storage and audit records
- **Docker Compose** - Local service orchestration
- **Microsoft Entra ID** - Organizational authentication using OpenID Connect
- **Authlib** - OAuth 2.0 and OpenID Connect integration
- **Git and GitHub** - Version control and collaboration

The architecture and technology stack may evolve as development progresses.

**Authentication status:** Microsoft Entra ID authentication is operational in the development environment. Role-based authorization, client-specific access enforcement, and restricted database privileges are not yet implemented.

## Development Roadmap

The following represents the intended direction, not a claim that every feature is already implemented.

| Area | Direction |
|---|---|
| Foundation | Application, database, containerized services |
| Backup infrastructure | Reliable backup creation, verification, and recovery |
| Archive management | Centralized scheduling, immutable archives, and authoritative registry |
| Asset hierarchy | Clients, sites, buildings, cabinets, and devices |
| Change management | Completion events, verification, approval, and differential revisions |
| Vulnerability intelligence | Asset correlation, risk analysis, and remediation tracking |
| Access control | User roles, tenant isolation, and approval permissions |
| Reporting | Operational dashboards, audit trails, and historical analysis |

## Contributing

**Do not develop directly on `main`.**

The `main` branch is reserved for stable, reviewed, and approved changes.

All contributors must create a separate branch before making changes.

### Branch Naming

Use descriptive branch names such as:

- `feature/asset-inventory`
- `feature/change-approval`
- `fix/archive-verification`
- `docs/readme-update`
- `test/backup-worker`

### Development Workflow

1. Synchronize your local `main` branch with the remote repository.
2. Create a new branch from `main`.
3. Make your changes in that branch.
4. Test and review your changes.
5. Commit with a descriptive message.
6. Push your branch to GitHub.
7. Open a pull request targeting `main`.
8. Obtain review and approval before merging.

Example:

```bash
git switch main
git pull --ff-only origin main
git switch -c feature/my-feature
```

After completing and testing the work:

```bash
git add .
git commit -m "Add feature description"
git push -u origin feature/my-feature
```

Then open a pull request on GitHub.

### Main Branch Rules

- No direct development on `main`.
- No direct pushes to `main`.
- No force-pushing to `main`.
- No merging unreviewed or untested changes.
- Use pull requests for all changes, including documentation updates.
- Keep commits focused and descriptive.

Repository administrators should enforce these rules through GitHub branch protection or repository rulesets. Documentation alone does not technically prevent direct pushes.

## Security and Data Protection

This repository must not contain:

- Passwords, tokens, private keys, or production credentials
- `.env` files containing secrets
- PostgreSQL database dumps
- Platform backup files or archive files
- Sensitive customer or operational infrastructure data
- Real client asset inventories without explicit authorization

Use environment variables or approved secret-management mechanisms for credentials.

Use fictional or sanitized data for examples, tests, and demonstrations.

**Never delete production data, Docker volumes, database records, or backup archives as part of routine development without explicit authorization.**

## Project Maturity

This project is under active development and is not yet suitable for production deployment or reliance on as a validated industrial safety or cybersecurity control.

Features, schemas, interfaces, and deployment procedures may change.

## Project Objective

Build a scalable, auditable OT vulnerability intelligence and change-management platform that helps organizations maintain visibility, accountability, and historical integrity across industrial infrastructure.