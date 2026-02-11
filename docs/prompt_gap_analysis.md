# Enterprise Workflow Prompt Gap Analizi

> Tarih: 2026-02-11
> Karşılaştırma kaynakları: wshobson/agents, VoltAgent/awesome-claude-code-subagents, danielmiessler/Fabric, mitsuhiko/agent-prompts

---

## Mevcut Prompt Durumu Özeti

| Node | Prompt Uzunluğu | Durum |
|---|---|---|
| Business Analyst | ~2500 char | Var |
| UX Designer | ~2200 char | Var |
| Solution Architect | ~2800 char | Var |
| Security Reviewer | ~2500 char | Var |
| DBA | ~2300 char | Var |
| Tech Lead | ~3500 char | Var |
| Backend Developer | ~2470 char | Var |
| Frontend Developer | ~2570 char | Var |
| Integration Engineer | ~1800 char | Var |
| QA Engineer | ~2250 char | Var |
| QA Bug Fixer | ~1500 char | Var |
| SDET | ~2150 char | Var |
| Security Auditor | ~2850 char | Var |
| Security Bug Fixer | ~1810 char | Var |
| DevOps Engineer | ~2000 char | Var |
| SRE | ~2100 char | Var |
| **Final Review** | **0 char** | **BOŞ — KRİTİK** |
| Final Bug Fixer | ~760 char | Kısa |
| Technical Writer | ~1800 char | Var |
| Delivery Manager | ~1500 char | Var |

---

## 1. Kod Kalitesi Prensipleri — Gap Analizi

### Mevcut Durum
Pipeline'da **hiçbir node** aşağıdaki prensipleri değerlendirmiyor:
- SOLID (SRP, OCP, LSP, ISP, DIP)
- DRY (Don't Repeat Yourself)
- KISS (Keep It Simple, Stupid)
- YAGNI (You Aren't Gonna Need It)
- Clean Code prensipleri
- Cyclomatic complexity limitleri
- Code coverage hedefleri

### Referans: wshobson/agents — code-reviewer

```
Design patterns:
- SOLID principles
- DRY compliance
- Pattern appropriateness
- Abstraction levels
- Coupling analysis
- Cohesion assessment
- Interface design
- Extensibility

Best practices enforcement:
- Clean code principles
- SOLID compliance
- DRY adherence
- KISS philosophy
- YAGNI principle
- Defensive programming
- Fail-fast approach
- Documentation standards

Code review checklist:
- Zero critical security issues verified
- Code coverage > 80% confirmed
- Cyclomatic complexity < 10 maintained
- No high-priority vulnerabilities found
- Documentation complete and clear
- No significant code smells detected
- Performance impact validated thoroughly
- Best practices followed consistently
```

### Referans: VoltAgent — architect-reviewer

```
Architectural principles:
- Separation of concerns
- Single responsibility
- Interface segregation
- Dependency inversion
- Open/closed principle
- Don't repeat yourself
- Keep it simple
- You aren't gonna need it

Technical debt assessment:
- Architecture smells
- Outdated patterns
- Technology obsolescence
- Complexity metrics
- Maintenance burden
- Risk assessment
- Remediation priority
- Modernization roadmap
```

### Referans: Fabric — review_code

```
ROLE AND GOAL:
You are a Principal Software Engineer, renowned for your meticulous attention
to detail and your ability to provide clear, constructive, and educational
code reviews.

STEPS:
1. Understand the Context
2. Systematic Analysis across dimensions:
   - Correctness
   - Security
   - Performance
   - Readability
   - Best practices
   - Error handling
```

### Etkilenen Node'lar
- **Final Review** (boş prompt — en kritik)
- **QA Engineer** (sadece fonksiyonel test yapıyor, kod kalitesi bakmıyor)
- **Integration Engineer** (entegrasyon kontrolü var, kalite kontrolü yok)

---

## 2. Güvenlik — Güncel Açıklar & Tooling — Gap Analizi

### Mevcut Durum
- OWASP Top 10 checklist var (Security Auditor'da)
- STRIDE framework var (Security Reviewer'da)
- "Exa Search ile CVE ara" talimatı var ama genel
- Eksikler: SAST/DAST tool referansları, supply chain security, container security, zero-trust

### Referans: wshobson/agents — security-auditor

```
DevSecOps & Security Automation:
- SAST/DAST/IAST/dependency scanning in CI/CD
- Shift-left security
- Policy as Code with OPA
- Container security
- Supply chain security (SLSA/SBOM)
- Secrets management (Vault, cloud secret managers)

Application Security Testing:
- SAST (SonarQube, Checkmarx, Veracode, Semgrep, CodeQL)
- DAST (OWASP ZAP, Burp Suite, Nessus)
- IAST
- Dependency scanning (Snyk, WhiteSource)
- Container scanning (Twistlock, Aqua, Anchore)
- Infrastructure scanning

Cloud Security:
- AWS Security Hub, Azure Security Center, GCP Security Command Center
- IAM policies
- Data protection (encryption at rest/transit)
- Serverless security
- K8s Pod Security Standards
- Multi-cloud security

Compliance & Governance:
- GDPR, HIPAA, PCI-DSS, SOC 2, ISO 27001, NIST CSF
- Compliance automation
- Data governance
- Security metrics/KPIs
- Incident response (NIST framework)
```

### Referans: VoltAgent — penetration-tester

```
Web application testing:
- OWASP Top 10
- Injection attacks
- Authentication bypass
- Session management
- Access control
- Security misconfiguration
- XSS vulnerabilities
- CSRF attacks

API security testing:
- Authentication testing
- Authorization bypass
- Input validation
- Rate limiting
- API enumeration
- Token security
- Data exposure
- Business logic flaws
```

### Referans: Fabric — create_stride_threat_model

```
STEPS:
- Create a section called ASSETS, determine what data or assets need protection
- Create a section called TRUST BOUNDARIES
- Create a section called DATA FLOWS, mark data flows crossing trust boundaries
- Create a section called THREAT MODEL with STRIDE per element threats

Table columns: THREAT ID, COMPONENT NAME, THREAT NAME, STRIDE CATEGORY,
WHY APPLICABLE, HOW MITIGATED, MITIGATION, LIKELIHOOD EXPLANATION,
IMPACT EXPLANATION, RISK SEVERITY
```

### Etkilenen Node'lar
- **Security Reviewer** (mimari aşaması — SAST/DAST tool önerileri eksik)
- **Security Auditor** (kod aşaması — supply chain, container security eksik)
- **Security Bug Fixer** (remediation pattern'ler var ama sığ)
- **DevOps Engineer** (güvenlik entegrasyonu eksik)

---

## 3. Güncel Dokümantasyon Araştırması — Gap Analizi

### Mevcut Durum
- Backend Developer: "Use Context7 to verify correct API usage for EVERY library you use" ✓
- Frontend Developer: "Use Context7 to verify correct component/hook/directive usage" ✓
- Eksikler: Breaking changes kontrolü, deprecation uyarıları, version pinning, progressive implementation

### Referans: mitsuhiko/agent-prompts — implementation_agent

```
Implementation Process:
1. Plan review — understand objective, deliverables, steps
2. Environment preparation — verify prerequisites, check dependencies, validate previous tasks
3. Sequential implementation — one step at a time, follow exact specs, proper error handling
4. Continuous validation — run validation after each step, test before integration, fix before proceeding
5. Integration and testing — run all tests, verify integration
6. Documentation and cleanup — comments, clean up, follow conventions

Key guidelines:
- Follow plan systematically: Complete each step before next; resolve failures before continuing
- Write high-quality code: Conventions, error handling, meaningful comments, consistent naming, security best practices
- Test incrementally: After each step
- Maintain working state: Existing functionality must continue working; roll back if breaks
```

### Referans: mitsuhiko/agent-prompts — software_architect_agent

```
Implementation Guidelines:
- Maintain proper implementation order:
  Project layout → Framework layer → Database models → API endpoints → Testing → Frontend → Integration
- Backend-first approach: Always complete backend before frontend.
  Database schema first, then API endpoints, then business logic, then frontend.
- Progressive implementation: Build and test incrementally.
  Maintain working system at each stage.
```

### Referans: VoltAgent — backend-developer

```
Backend development checklist:
- RESTful API design with proper HTTP semantics
- Database schema optimization and indexing
- Authentication and authorization implementation
- Caching strategy for performance
- Error handling and structured logging
- API documentation with OpenAPI spec
- Security measures following OWASP guidelines
- Test coverage exceeding 80%

Performance optimization techniques:
- Response time under 100ms p95
- Database query optimization
- Caching layers (Redis, Memcached)
- Connection pooling strategies
- Asynchronous processing for heavy tasks
```

### Etkilenen Node'lar
- **Backend Developer** (implementation order, progressive build eksik)
- **Frontend Developer** (backend-first dependency, breaking changes kontrolü eksik)
- **Integration Engineer** (entegrasyon doğrulama sırası eksik)
- **Tech Lead** (task sıralama kuralları eksik)

---

## 4. Quantitative Targets — Gap Analizi

### Mevcut Durum
Pipeline'da **hiçbir sayısal hedef** tanımlı değil.

### Referans Repolardan Toplanan Hedefler

| Metrik | Kaynak | Hedef |
|---|---|---|
| Code coverage | wshobson, VoltAgent | > 80% (backend), > 85% (frontend) |
| Cyclomatic complexity | wshobson | < 10 |
| p95 response time | VoltAgent | < 100ms |
| Service availability | VoltAgent | > 99.9% |
| MTTR | VoltAgent | < 30 minutes |
| Toil ratio | VoltAgent | < 50% |
| Test automation | VoltAgent | > 70% |
| Infrastructure automation | VoltAgent | 100% |
| Mean time to production | VoltAgent | < 1 day |
| Database uptime | VoltAgent | 99.99% |
| RTO | VoltAgent | < 1 hour |
| RPO | VoltAgent | < 5 minutes |
| Readability score (docs) | VoltAgent | > 60 |
| Technical accuracy (docs) | VoltAgent | 100% |

### Etkilenen Node'lar
- **SDET** (coverage ve complexity hedefleri eksik)
- **DevOps Engineer** (deployment metrikleri eksik)
- **SRE** (SLO/SLI, MTTR, uptime hedefleri eksik)
- **DBA** (uptime, RTO, RPO hedefleri eksik)
- **Technical Writer** (readability hedefi eksik)

---

## 5. Eksik Prompt Pattern'ler

### 5a. Structured Output Format (Fabric pattern)

Bizim prompt'larda output format var ama tutarsız. Fabric'in **IDENTITY/PURPOSE/STEPS/OUTPUT** yapısı daha standart:

```
# IDENTITY and PURPOSE
You are a [role] specializing in [domain].

# STEPS
1. [Specific action]
2. [Specific action]
...

# OUTPUT INSTRUCTIONS
- Output in valid Markdown
- [Specific format rules]

# OUTPUT FORMAT
[Exact template]
```

### 5b. Progressive Implementation (mitsuhiko pattern)

Developer prompt'larında eksik:

```
Implementation Order (STRICT):
1. Project layout & environment setup
2. Framework layer & database configuration
3. Database models & migrations
4. API endpoints & business logic
5. Testing (backend)
6. Frontend development (ONLY after backend complete)
7. Integration testing & deployment
```

### 5c. Constructive Feedback Pattern (wshobson pattern)

Review node'larında eksik:

```
Constructive feedback:
- Specific examples
- Clear explanations
- Alternative solutions
- Learning resources
- Positive reinforcement
- Priority indication (P1/P2/P3)
- Action items
- Follow-up plans
```

### 5d. Tool Usage Strategy (mitsuhiko pattern)

Tüm agent'larda eksik:

```
Tool usage strategy:
- File operations (Read, Write, Edit) — for code changes
- Directory operations (Glob) — for project structure discovery
- Command execution (Bash) — for deps, tests, builds ONLY
- Search (Grep) — for finding existing patterns
- Research (Context7, DeepWiki) — BEFORE every library usage
- Web Search (Exa) — for current CVEs, breaking changes, deprecations
```

### 5e. Research-Before-Code Pattern

Developer prompt'larında eksik:

```
BEFORE writing ANY code that uses a library/framework:
1. Use Context7 to check latest stable version and API
2. Use DeepWiki to read the framework's migration guide
3. Check for breaking changes between versions
4. Verify deprecated APIs are not used
5. Confirm the library is actively maintained (last commit < 6 months)
```

---

## 6. Öncelik Matrisi

### P1 — Kritik (Pipeline'ı zayıflatan boşluklar)

| # | Eksik | Etkilenen Node'lar | Referans |
|---|---|---|---|
| 1 | **Final Review prompt'u tamamen boş** | Final Review | wshobson/code-reviewer |
| 2 | **SOLID/DRY/KISS/YAGNI prensipleri yok** | Final Review, QA Engineer | VoltAgent/architect-reviewer |
| 3 | **Kod kalitesi metrikleri yok** (complexity, coverage) | SDET, QA Engineer | wshobson (complexity < 10, coverage > 80%) |
| 4 | **Implementation order yok** | Backend Dev, Frontend Dev | mitsuhiko (backend-first, progressive) |

### P2 — Önemli (Kaliteyi artıracak iyileştirmeler)

| # | Eksik | Etkilenen Node'lar | Referans |
|---|---|---|---|
| 5 | SAST/DAST tool referansları eksik | Security Reviewer, Auditor | wshobson (SonarQube, CodeQL, Semgrep) |
| 6 | Supply chain security eksik | Security Auditor | wshobson (SLSA/SBOM) |
| 7 | Research-before-code pattern eksik | Backend Dev, Frontend Dev | mitsuhiko (validate previous, check deps) |
| 8 | Quantitative targets eksik | SDET, DevOps, SRE, DBA | VoltAgent (p95 < 100ms, uptime > 99.9%) |
| 9 | Compliance detayı sığ | Security Reviewer | wshobson (SOC2, ISO 27001, NIST detaylı) |

### P3 — İyileştirme (Nice-to-have)

| # | Eksik | Etkilenen Node'lar | Referans |
|---|---|---|---|
| 10 | Breaking changes / deprecation kontrolü | Backend Dev, Frontend Dev | Yok (bizim eklememiz) |
| 11 | Technical debt tracking | QA Engineer, Final Review | wshobson, VoltAgent |
| 12 | Constructive feedback pattern | Final Review, QA Engineer | wshobson |
| 13 | Tool usage strategy section | Tüm agent'lar | mitsuhiko |
| 14 | Readability/doc quality metrics | Technical Writer | VoltAgent (score > 60) |

---

## 7. Referans Repo Prompt Yapıları (Karşılaştırma)

### wshobson/agents Yapısı
```
Identity Statement: "You are a [senior role] with expertise in..."
Capabilities: 10-12 kategorize bölüm (bulleted lists)
Behavioral Traits: Karar verme prensipleri
Response Approach: 9-10 adımlı süreç
Model: opus (review), sonnet (execution)
```

### VoltAgent Yapısı
```
YAML frontmatter: name, description, tools, model
Identity: "You are a senior [role]..."
Invocation Steps: 4 adımlı başlatma süreci
Checklist: Quantitative thresholds
Domain Sections: Bulleted topic lists
Tools: Read-only (reviewers) vs Read/Write (developers)
```

### Fabric Yapısı
```
IDENTITY and PURPOSE: 1-3 cümle persona
STEPS: Sequenced instructions
OUTPUT INSTRUCTIONS: Format kuralları
OUTPUT FORMAT: Exact template
```

### mitsuhiko Yapısı
```
Identity: "You are an expert [role]..."
Process: 6-7 numbered phases
Guidelines: Key principles (bold)
Output: Structured format specification
Delegation: Subagent instructions (orchestrator only)
```

### Bizim Mevcut Yapı
```
Identity: "You are a [Role]. Your goal is to..."
Downstream awareness: "Your output goes to → [next node]"
Tools: AVAILABLE TOOLS listesi
Process: Numbered steps
Output: FORMAT bölümü
Constraints: CRITICAL RULES
Decision: Keyword (QA_PASS/QA_FAIL, SEC_PASS/SEC_FAIL)
```

**Bizim avantajımız:** Downstream awareness (çıktının kime gittiği) ve keyword-based routing. Diğer repolarda bu yok.
**Bizim eksikimiz:** Quantitative thresholds, architectural principles, structured checklist'ler.

---

## 8. Kaynak Repo Linkleri

| Repo | Stars | Ana Değer |
|---|---|---|
| [wshobson/agents](https://github.com/wshobson/agents) | ~700 | 112 agent prompt, preset team workflows |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | ~2k | 100+ subagent, quantitative targets |
| [danielmiessler/Fabric](https://github.com/danielmiessler/Fabric) | ~30k | IDENTITY/PURPOSE/STEPS/OUTPUT pattern |
| [mitsuhiko/agent-prompts](https://github.com/mitsuhiko/agent-prompts) | ~600 | Progressive implementation, backend-first |
| [x1xhlol/system-prompts-and-models-of-ai-tools](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools) | ~15k | Production tool system prompts |
| [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | ~56k | Document-driven communication |
| [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | ~30k | Phase-based chat chain |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | ~44k | YAML role + backstory + goal |
