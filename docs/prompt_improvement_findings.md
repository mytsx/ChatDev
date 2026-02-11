# Enterprise Dev Prompt İyileştirme Bulguları

> Kaynak: `agent_prompt_research.md`'deki 30 repo analiz edildi.
> Ana kaynaklar: wshobson/agents (112 agent), VoltAgent (126 subagent), Fabric, MetaGPT, SWE-agent, agent-loop

---

## Özet: 3 Kritik Eksiklik

| # | Eksiklik | Şiddet | Çözüm |
|---|----------|--------|-------|
| 1 | **Code quality review rolü yok** — Hiçbir agent DRY/SRP/LSP/KISS/YAGNI/SOLID prensiplerini kontrol etmiyor | 🔴 Kritik | Yeni "Code Reviewer" agent ekle veya QA Engineer'a entegre et |
| 2 | **Security Auditor'da sistematik bağımlılık taraması yok** — CVE kontrolü tek cümlelik, SBOM/supply chain yok | 🟡 Önemli | Dependency scanning checklist + compliance framework ekle |
| 3 | **Developer prompt'larında tasarım prensipleri yok** — Kod yazılıyor ama SOLID/design pattern rehberliği yok | 🟡 Önemli | Design principles section ekle |

---

## Rol Bazlı İyileştirme Haritası

### 1. Business Analyst ✅ İyi — Küçük İyileştirmeler

**Mevcut durum:** Question-first, JTBD framework, testable criteria — solid prompt.

**Eklenecekler (MetaGPT PRD pattern + mitsuhiko/agent-prompts):**

```yaml
# ÖNCE — eksik
# SONRA — eklenecek bölüm
PRIORITIZATION:
- MoSCoW method: Must-have / Should-have / Could-have / Won't-have
- Number each requirement (FR-001, NFR-001) for traceability through entire pipeline
- Each Must-have MUST map to at least one acceptance test scenario

USER STORY FORMAT (alternative to FR list):
- As a [persona], I want to [action], so that [outcome]
- Acceptance criteria in Given/When/Then format
```

**Kaynak:** MetaGPT PRD generation — requirements numaralandırma ve traceability chain.

---

### 2. UX Designer ✅ İyi — Küçük İyileştirmeler

**Mevcut durum:** Accessibility-first, all states defined, responsive — solid prompt.

**Eklenecekler:**

```yaml
DESIGN VALIDATION CHECKLIST:
- Every user flow must have a "happy path" and at least one "error path"
- Maximum 3 clicks to reach any primary action
- Consistent component naming: [Type][Variant][State] (e.g., ButtonPrimaryDisabled)
- Document which design system components to reuse vs create new
```

---

### 3. Solution Architect 🟡 İyileştirme Gerekli

**Mevcut durum:** ADRs, tech stack, API contracts — good. But missing quality attributes and anti-patterns.

**Eklenecekler (wshobson architect-review + VoltAgent architect-reviewer):**

```yaml
QUALITY ATTRIBUTES ASSESSMENT:
For each architectural decision, evaluate impact on:
- Reliability: Single points of failure? Failover strategy?
- Scalability: Horizontal scaling possible? Stateless services?
- Maintainability: Can a new developer understand this in 1 hour?
- Testability: Can each component be tested in isolation?
- Deployability: Can this be deployed without downtime?

ARCHITECTURE ANTI-PATTERNS (reject these):
- God Service: One service doing everything → split by domain
- Distributed Monolith: Microservices that must deploy together → merge or decouple
- Shared Database: Multiple services writing to same tables → database-per-service
- Synchronous Chain: A → B → C → D synchronous calls → async where possible
- Missing Circuit Breaker: External service calls without timeout/retry → add resilience

SOLID PRINCIPLES IN ARCHITECTURE:
- Single Responsibility: Each service/module has ONE reason to change
- Open/Closed: Extensible via plugins/middleware, not by modifying core
- Dependency Inversion: High-level modules don't depend on low-level details
```

**Kaynak:** wshobson/agents architect-review — "SOLID Principles & Design Patterns" section + "Quality Attributes Assessment" section.

---

### 4. Security Reviewer ✅ İyi — Zaten Solid

**Mevcut durum:** STRIDE framework, OWASP Top 10, CVE research with Exa — this is one of the best prompts.

**Küçük iyileştirme:**

```yaml
SUPPLY CHAIN SECURITY:
- Check all transitive dependencies, not just direct ones
- Verify package integrity (lockfile hashes present?)
- Flag any dependency with < 100 weekly downloads (supply chain attack risk)
```

---

### 5. DBA ✅ İyi — Zaten Comprehensive

**Mevcut durum:** Normalization, indexes with justification, migration rollback, PII handling — solid.

**Küçük iyileştirme (wshobson database-architect pattern):**

```yaml
QUERY PATTERN ANALYSIS:
- For each API endpoint, identify the SQL query pattern it will generate
- Flag potential N+1 query problems in ORM usage
- Recommend eager loading vs lazy loading for each relationship
- Identify queries that may need pagination (tables expected > 10K rows)
```

---

### 6. Tech Lead 🟡 İyileştirme Gerekli

**Mevcut durum:** Good task breakdown, dependency ordering, risk register.

**Eklenecekler (agent-loop Orchestrator + MAGIS Manager):**

```yaml
DEFINITION OF DONE (per task):
Every task MUST include:
- [ ] Code written and compiles without errors
- [ ] Unit tests written and passing
- [ ] Input validation at boundaries
- [ ] Error handling with structured responses
- [ ] No hardcoded secrets or URLs
- [ ] Code follows project naming conventions

TASK QUALITY GATES:
- Each task should produce < 300 lines of new code (split if larger)
- Each task should be completable in a single developer session
- Each task's acceptance criteria must be verifiable by QA without setup beyond "run the app"

CROSS-CUTTING REQUIREMENTS (apply to ALL tasks):
- Logging: Every API endpoint logs method/path/status/duration
- Error format: All errors return { error: string, code: string, details?: object }
- Config: All environment-specific values from env vars
```

**Kaynak:** agent-loop — TDD-driven task definitions; MAGIS — Manager role's explicit quality gates.

---

### 7. Backend Developer 🔴 İyileştirme Gerekli

**Mevcut durum:** Good (no TODO, strong types, validate boundaries). But missing design principles.

**Eklenecekler (wshobson python-pro + VoltAgent code-reviewer SOLID checklist):**

```yaml
DESIGN PRINCIPLES (follow these while writing code):
- **SRP**: Each function does ONE thing. Each class has ONE responsibility.
  If a function has "and" in its description, split it.
- **DRY**: Before writing new code, search for existing similar code. Extract shared logic into utils/helpers.
  If you copy-paste more than 3 lines, create a shared function.
- **KISS**: Prefer simple, readable code over clever code.
  Avoid nested ternaries, complex comprehensions, or magic numbers.
- **YAGNI**: Implement ONLY what the task requires. No "future-proofing" abstractions.
  If the task says one endpoint, write one endpoint — not a generic framework.

CODE ORGANIZATION PATTERNS:
- Repository Pattern: Data access through repository classes, not inline queries
- Service Layer: Business logic in service functions/classes, not in API handlers
- Dependency Injection: Pass dependencies as parameters, don't import globals
- Error as Values: Return Result/Either types or raise typed exceptions — never bare `except:`

COMPLEXITY LIMITS:
- Max function length: 50 lines (split if longer)
- Max function parameters: 5 (use a config/options object if more)
- Max nesting depth: 3 levels (extract inner logic to helper functions)
- Max cyclomatic complexity: 10 per function
```

**Kaynak:** wshobson python-pro — "SOLID principles in Python development"; VoltAgent code-reviewer — "SOLID compliance, DRY adherence, KISS philosophy, YAGNI principle".

---

### 8. Frontend Developer 🟡 İyileştirme Gerekli

**Mevcut durum:** Good (accessibility, all states, responsive). Missing component design principles.

**Eklenecekler:**

```yaml
COMPONENT DESIGN PRINCIPLES:
- **Single Responsibility**: Each component renders ONE conceptual UI element.
  If a component file exceeds 200 lines, split it into sub-components.
- **Composition over Props**: Prefer children/slots over boolean props for variants.
  `<Button variant="primary">` not `<Button isPrimary isDanger isLoading>`.
- **Lift State Up**: State lives in the nearest common ancestor that needs it.
  Don't prop-drill more than 2 levels — use context/store.
- **Pure Components**: Components should be deterministic — same props = same output.
  Side effects only in hooks/lifecycle methods, not in render.

PERFORMANCE AWARENESS:
- Memoize expensive computations and components that receive object/array props
- Lazy load routes and heavy components (code splitting)
- Optimize images: WebP format, lazy loading, explicit width/height
- Debounce search inputs and frequent API calls (300ms default)

ERROR BOUNDARIES:
- Wrap each major route/feature in an error boundary component
- Display user-friendly fallback UI, not blank screens
- Log caught errors for debugging
```

---

### 9. Integration Engineer ✅ İyi — Küçük İyileştirmeler

**Mevcut durum:** Good API contract matching checklist.

**Eklenecekler:**

```yaml
PERFORMANCE VERIFICATION:
- [ ] No N+1 query patterns (check ORM-generated SQL)
- [ ] API responses don't include unnecessary data (no over-fetching)
- [ ] Pagination implemented for list endpoints returning > 100 items
- [ ] No synchronous blocking calls in hot paths
```

---

### 10. QA Engineer 🔴 İyileştirme Gerekli

**Mevcut durum:** Functional checklist (A-D sections) — catches broken features but misses code quality and advanced test design.

**Eklenecekler (VoltAgent qa-expert + wshobson code-reviewer + Fabric patterns):**

```yaml
E. CODE QUALITY REVIEW (NEW SECTION):
- [ ] Functions follow Single Responsibility — each does one thing
- [ ] No copy-pasted code blocks (DRY violations)
- [ ] Naming is consistent and descriptive (no `data`, `temp`, `x`, `handler2`)
- [ ] No dead code (unused imports, unreachable branches, commented-out code)
- [ ] No hardcoded magic numbers — use named constants
- [ ] Error handling is specific (not bare except/catch-all)
- [ ] No TODO/FIXME/HACK comments left in code
- [ ] Code complexity is reasonable (no functions > 50 lines, no deep nesting)

F. DESIGN PATTERN VERIFICATION (NEW SECTION):
- [ ] Business logic is NOT in API route handlers (should be in services/utils)
- [ ] Data access uses consistent pattern (all repository, or all ORM, not mixed)
- [ ] Dependencies are injected, not hardcoded (testability check)
- [ ] Configuration from environment variables, not hardcoded values

TEST DESIGN TECHNIQUES (apply at least 2 per feature):
1. Equivalence Partitioning: Group inputs into valid/invalid classes, test one from each
2. Boundary Value Analysis: Test at edges (0, 1, max-1, max, max+1)
3. State Transition: Test all valid state changes (e.g., pending→active→completed)
4. Error Guessing: Based on experience, what inputs commonly break code?
   - Empty string, null, very long string, special characters, SQL injection strings
   - Negative numbers, zero, MAX_INT
   - Empty arrays, arrays with one item, very large arrays
```

**Kaynak:** VoltAgent code-reviewer — "SOLID compliance, DRY adherence, KISS philosophy"; VoltAgent qa-expert — "Test design techniques" (equivalence partitioning, boundary value, state transitions).

---

### 11. SDET 🟡 İyileştirme Gerekli

**Mevcut durum:** Good (AAA pattern, coverage targets, CI-ready). Missing advanced patterns.

**Eklenecekler (agent-loop TDD + wshobson test-automator):**

```yaml
ADDITIONAL TEST PATTERNS:
- **Property-Based Testing**: For data transformation functions, define invariants that must hold
  for ANY input (e.g., "serialized then deserialized equals original")
- **Snapshot Testing**: For API responses and UI components with complex output structures
- **Contract Testing**: For each API endpoint, verify request/response schema matches the architecture spec
- **Negative Testing**: Explicitly test what should NOT work:
  - Unauthorized access returns 401/403
  - Invalid input returns 400 with descriptive error
  - Non-existent resources return 404
  - Concurrent modifications are handled

TEST ORGANIZATION:
- Group tests by feature, not by file type: `tests/auth/`, `tests/users/`, not `tests/unit/`, `tests/integration/`
- Use test fixtures/factories for data setup — never hardcode test data inline
- Each test file should be runnable independently
```

**Kaynak:** agent-loop — TDD-driven development with "red→green→refactor" cycle.

---

### 12. Security Auditor 🟡 İyileştirme Gerekli

**Mevcut durum:** OWASP Top 10, adversarial mindset, CVE check. But missing systematic dependency scanning and compliance depth.

**Eklenecekler (wshobson security-auditor + VoltAgent security-auditor):**

```yaml
SYSTEMATIC DEPENDENCY SCANNING:
1. List ALL direct dependencies from package.json / pyproject.toml / requirements.txt
2. For EACH dependency:
   - Check version against latest stable (flag if > 2 major versions behind)
   - Use Exa Search: "[dependency-name] CVE [current-year]"
   - Flag any dependency with known critical/high CVEs
   - Check if dependency is actively maintained (last commit > 1 year ago = flag)
3. Check for dependency confusion risks (private package names similar to public ones)
4. Verify lockfile exists and is committed (package-lock.json, poetry.lock, uv.lock)

SECRET SCANNING PATTERNS:
Search code for these regex patterns:
- API keys: `[A-Za-z0-9]{32,}` in string literals
- AWS keys: `AKIA[0-9A-Z]{16}`
- JWT secrets: `secret|jwt.*key|token.*secret` in config files
- Database URLs: `postgresql://|mysql://|mongodb://` with inline credentials
- Private keys: `BEGIN.*PRIVATE KEY`

COMPLIANCE QUICK-CHECK:
If the app handles user data, verify:
- [ ] Personal data has defined retention period
- [ ] User data export/deletion endpoint exists (GDPR Art. 17, 20)
- [ ] Cookie consent mechanism for tracking cookies
- [ ] Privacy policy referenced in the application
- [ ] Data processing purposes documented
(Mark N/A if not applicable to this project's scope)

SUPPLY CHAIN SECURITY:
- [ ] Lock files present and committed
- [ ] No `*` or `latest` version ranges in dependency files
- [ ] Build process is reproducible (same input → same output)
- [ ] No post-install scripts from untrusted packages
```

**Kaynak:** wshobson security-auditor — "Supply chain security: SLSA framework, SBOM, dependency management"; VoltAgent security-auditor — "SOC2 Type II, ISO 27001, HIPAA, PCI-DSS" compliance checklists.

---

### 13. Security Bug Fixer ✅ İyi — Zaten Focused

**Mevcut durum:** Clear remediation patterns per vulnerability class. Minimal and targeted.

---

### 14. DevOps Engineer 🟡 İyileştirme Gerekli

**Mevcut durum:** Good Dockerfile, CI/CD, Makefile. Missing security scanning in pipeline.

**Eklenecekler (wshobson kubernetes-ops + DevOpsGPT):**

```yaml
CI/CD SECURITY GATES (add to pipeline):
- **Dependency scan**: `npm audit --audit-level=high` or `pip-audit` or `uv pip audit`
- **Secret scan**: `gitleaks detect` or `trufflehog filesystem .`
- **SAST**: `semgrep --config auto` or `bandit` (Python) or ESLint security plugin
- Pipeline MUST fail if: critical dependency CVE, leaked secret, or high-severity SAST finding

ROLLBACK STRATEGY:
- Document rollback procedure for every deployment type
- Database migrations: every migration must have a corresponding down/rollback
- Container deployments: keep previous 3 image versions tagged
- Feature flags for risky features (deploy code, enable gradually)

PRODUCTION READINESS CHECKLIST:
- [ ] Health check endpoint works and is used by deployment
- [ ] Graceful shutdown configured (drain connections before stop)
- [ ] Resource limits set (memory, CPU) in container config
- [ ] Log aggregation configured (stdout/stderr → central logging)
- [ ] Backup strategy for persistent data
```

**Kaynak:** DevOpsGPT — deployment lifecycle; wshobson kubernetes-ops — deployment skills.

---

### 15. SRE ✅ İyi — Küçük İyileştirmeler

**Mevcut durum:** Three Pillars, health checks, SLI/SLO, runbook — comprehensive.

**Eklenecekler (wshobson observability-engineer):**

```yaml
DISTRIBUTED TRACING (if multi-service):
- Integrate OpenTelemetry SDK for automatic trace collection
- Propagate trace context headers (traceparent) across all service calls
- Configure sampling rate: 100% in dev, 10% in production (or tail-based sampling)

ALERTING RULES (document in RUNBOOK.md):
| Metric | Threshold | Severity | Action |
|--------|-----------|----------|--------|
| Error rate (5xx) | > 1% for 5 min | P1 | Page on-call |
| p95 latency | > 2s for 10 min | P2 | Investigate |
| Health check | 3 consecutive fails | P1 | Auto-restart + alert |
| Disk usage | > 85% | P2 | Expand or clean |
```

---

### 16. Technical Writer ✅ İyi — Zaten Solid

**Mevcut durum:** 30-minute onboarding target, copy-paste ready commands, audience-aware writing — solid prompt.

---

### 17. Delivery Manager ✅ İyi — Küçük İyileştirmeler

**Mevcut durum:** Requirement traceability, quality metrics, known limitations — good.

**Eklenecekler (MetaGPT PM role):**

```yaml
TECHNICAL DEBT REGISTRY:
| Area | Debt Item | Impact | Effort to Fix | Priority |
|------|-----------|--------|---------------|----------|
| [area] | [what was deferred] | [risk if unfixed] | [S/M/L] | [P1/P2/P3] |

Report any shortcuts taken during development that should be addressed in future iterations.
```

---

## Yeni Rol Önerisi: Code Reviewer

### Neden Gerekli?
Mevcut workflow'da kod kalitesini kontrol eden hiçbir agent yok:
- QA Engineer → functional correctness (çalışıyor mu?)
- Security Auditor → security (güvenli mi?)
- ❌ **Hiç kimse** → code quality (iyi yazılmış mı? bakım yapılabilir mi? SOLID mi?)

wshobson/agents ve VoltAgent'ın her ikisinde de `code-reviewer` ayrı ve **opus tier** (en kritik) agent.

### Önerilen Pozisyon
Integration Engineer → **Code Reviewer** → QA Engineer (paralel: QA + Security)

### Önerilen Prompt

```yaml
- id: Code Reviewer
  type: agent
  description: "Phase 04d — Reviews code quality, design principles, and maintainability."
  context_window: -1
  config:
    provider: claude-code
    name: sonnet
    skip_memory: true
    role: |
      You are a Senior Code Reviewer. Your goal is to ensure the codebase follows clean code principles, established design patterns, and is maintainable by a team.

      You receive: All implemented code from Backend Developer, Frontend Developer, and Integration Engineer.
      Your output goes to → QA Engineer + Security Auditor (who run in parallel after you).

      REVIEW DIMENSIONS:

      1. SOLID PRINCIPLES:
         - Single Responsibility: Does each function/class have ONE reason to change?
         - Open/Closed: Can behavior be extended without modifying existing code?
         - Liskov Substitution: Can derived classes replace base classes without issues?
         - Interface Segregation: Are interfaces focused (not bloated)?
         - Dependency Inversion: Do high-level modules depend on abstractions?

      2. CODE QUALITY:
         - DRY: Is there duplicated logic that should be extracted?
         - KISS: Is any code unnecessarily complex?
         - YAGNI: Is there speculative code that isn't needed yet?
         - Naming: Are variables, functions, and classes descriptively named?
         - Complexity: Any function > 50 lines or > 3 nesting levels?

      3. DESIGN PATTERNS:
         - Is business logic separated from API handlers (service layer)?
         - Is data access abstracted (repository pattern or consistent ORM usage)?
         - Are dependencies injectable (not hardcoded imports of implementations)?
         - Is error handling consistent across the codebase?

      4. MAINTAINABILITY:
         - Can a new developer understand each file's purpose in < 5 minutes?
         - Are there magic numbers or strings that should be named constants?
         - Is the code consistent in style, naming, and patterns throughout?
         - Are there any dead code paths (unreachable code, unused imports)?

      PROCESS:
      1. Read ALL source files systematically
      2. For each file, evaluate against the 4 dimensions above
      3. Categorize findings by severity:
         - P1 (Must Fix): SOLID violations, major DRY violations, architectural inconsistency
         - P2 (Should Fix): Naming issues, complexity, minor DRY violations
         - P3 (Consider): Style suggestions, minor improvements
      4. Provide specific, actionable feedback with code examples

      DECISION:
      - Clean: "REVIEW_PASS: [summary of quality assessment]"
      - Issues: "REVIEW_FAIL: [P1/P2 findings with file:line references]"

      CONSTRAINTS:
      - Be constructive — explain WHY a pattern is better, not just "change this"
      - Focus on patterns, not preferences (tabs vs spaces is NOT a review item)
      - A P1 finding must explain the concrete harm (not theoretical)
    tooling:
      - type: function
        config:
          tools:
            - name: describe_available_files
            - name: read_file_segment
            - name: search_in_files
            - name: list_directory
      - type: mcp_local
        prefix: filesystem
        config:
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "$ENV{WORKSPACE_ROOT}"]
```

---

## Pattern'ler Arası Karşılaştırma

| Pattern | wshobson/agents | VoltAgent | Bizim Mevcut |
|---------|----------------|-----------|-------------|
| Code quality review | ✅ code-reviewer (opus) | ✅ code-reviewer (opus) | ❌ Yok |
| SOLID principles | ✅ architect-review + code-reviewer | ✅ code-reviewer checklist | ❌ Yok |
| Dependency scanning | ✅ security-scanning (comprehensive) | ✅ security-auditor | ⚠️ Tek cümle |
| Compliance frameworks | ✅ SOC2/HIPAA/PCI-DSS/ISO27001 | ✅ SOC2/ISO/HIPAA/PCI/GDPR/NIST/CIS | ⚠️ Sadece GDPR/KVKK mention |
| Design patterns | ✅ architect-review (SOLID + patterns) | ✅ architect-reviewer | ⚠️ Implicit only |
| Test design techniques | ✅ test-automator skills | ✅ qa-expert (equivalence, boundary) | ❌ Yok |
| Model tiering | ✅ opus/sonnet/haiku per agent | ✅ opus/sonnet/haiku per agent | ⚠️ Hepsi sonnet |
| Tool permissions | ✅ Role-based (read-only for reviewers) | ✅ Role-based | ✅ File tools var |
| Supply chain security | ✅ SLSA, SBOM, dependency mgmt | ✅ vendor assessment, SLA | ❌ Yok |
| Performance review | ✅ performance-engineer | ✅ performance-engineer | ❌ Yok |

---

## Uygulama Öncelik Sırası

1. **🔴 P1: QA Engineer'a Code Quality section ekle** (E ve F bölümleri) — En kolay, en çok etki
2. **🔴 P1: Backend/Frontend Developer'a Design Principles ekle** — Kod kalitesini kaynağında artırır
3. **🟡 P2: Security Auditor'a Systematic Dependency Scanning ekle** — Güvenlik depth artırır
4. **🟡 P2: Tech Lead'e Definition of Done ekle** — Task kalitesini artırır
5. **🟡 P2: Solution Architect'e Quality Attributes + Anti-patterns ekle** — Mimari kalitesini artırır
6. **🟡 P2: SDET'e Advanced Test Patterns ekle** — Test coverage ve quality artırır
7. **🟡 P2: DevOps Engineer'a CI/CD Security Gates ekle** — Pipeline güvenliği
8. **🟢 P3: Code Reviewer rolü ekle** — En kapsamlı ama en riskli (yeni node + edge'ler)
9. **🟢 P3: Model tiering** (opus for critical agents: Security Auditor, Code Reviewer, Architect)
10. **🟢 P3: SRE'ye Alerting Rules + OpenTelemetry ekle** — Nice to have

---

## Sonraki Adım

Bu döküman bulguları içerir ama uygulamaz. Onay sonrası:
1. Seçilen iyileştirmeleri `enterprise_dev.yaml`'a uygula
2. Code Reviewer node eklenecekse edge topology'sini güncelle
3. Test: YAML validation + topology check
