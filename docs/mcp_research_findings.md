# MCP Araştırma Bulguları — Agent Tooling Güçlendirme

> `prompt_improvement_findings.md` bulgularına istinaden hazırlandı.
> Amaç: Prompt iyileştirmeleri uygulandıktan sonra, agent'lara gerçek araç desteği sağlayacak MCP server'ları belirlemek.

---

## Mevcut MCP Envanteri

Şu anda `enterprise_dev.yaml`'da 6 MCP server kullanılıyor:

| # | MCP Server | Tür | Amaç | Kullanan Agent'lar |
|---|-----------|-----|------|-------------------|
| 1 | `@modelcontextprotocol/server-sequential-thinking` | npx | Reasoning/planlama | Neredeyse tüm agent'lar |
| 2 | `@upstash/context7-mcp` | npx | Framework/kütüphane dokümantasyonu | Architect, Security, DBA, Dev'ler, QA, SDET, DevOps, SRE |
| 3 | `https://mcp.deepwiki.com/mcp` | SSE | GitHub repo dokümantasyonu | Architect, Security, DBA, Dev'ler, QA Bug Fixer |
| 4 | `https://mcp.exa.ai/mcp` | SSE | Web search, CVE araştırması | BA, UX, Architect, Security, Dev'ler, Security Auditor |
| 5 | `@modelcontextprotocol/server-filesystem` | npx | Dosya okuma/yazma | Dev'ler, QA, SDET, Security, DevOps, SRE |
| 6 | `mcp-server-fetch` | uvx | Web sayfası çekme | BA, UX, Dev'ler, DevOps, Tech Writer |

---

## Gap → MCP Eşleştirmesi

Prompt improvement findings'deki 3 kritik eksiklik ve MCP çözümleri:

| Eksiklik | Prompt Çözümü | MCP Araç Desteği |
|----------|--------------|-----------------|
| 🔴 Kod kalite review yok | Code Reviewer agent + QA'ya E/F bölümleri | **SonarQube MCP** + **Codacy MCP** |
| 🟡 Security'de bağımlılık taraması zayıf | Systematic dependency scanning checklist | **Snyk MCP** + **OSV MCP** + **Semgrep MCP** |
| 🟡 Developer'larda design principles yok | SOLID/DRY/KISS/YAGNI sections | **SonarQube MCP** (code smell detection) |

---

## Önerilen Yeni MCP Server'lar

### 1. SonarQube MCP Server ⭐ Öncelik: P1

- **Repo:** `SonarSource/sonarqube-mcp-server` (Official)
- **Stars:** 377 | **Dil:** Java | **Lisans:** SONAR Source-Available License v1.0
- **Docker:** `mcp/sonarqube`

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `analyze_code_snippet` | Kod parçasını SonarQube analyzer'larla analiz et — code smell, bug, vulnerability |
| `search_sonar_issues_in_projects` | Proje genelinde kalite sorunlarını filtrele (severity, category, language) |
| `get_component_measures` | ncloc, complexity, violations, coverage metrikleri |
| `get_project_quality_gate_status` | Quality Gate durumu (PASS/FAIL) |
| `search_dependency_risks` | SCA — bağımlılık risk analizi (Enterprise) |
| `get_duplications` | Kod tekrarı tespiti (DRY ihlalleri) |
| `list_quality_gates` | Kalite geçitleri listesi |
| `show_rule` | SonarQube kural detayları |

**Yapılandırma:**
```json
{
  "command": "docker",
  "args": ["run", "-i", "--rm", "-e", "SONARQUBE_TOKEN", "-e", "SONARQUBE_URL", "mcp/sonarqube"],
  "env": {
    "SONARQUBE_TOKEN": "$ENV{SONARQUBE_TOKEN}",
    "SONARQUBE_URL": "$ENV{SONARQUBE_URL}"
  }
}
```

**YAML Entegrasyonu:**
```yaml
- type: mcp_local
  prefix: sonarqube
  config:
    command: "docker"
    args: ["run", "-i", "--rm", "-e", "SONARQUBE_TOKEN", "-e", "SONARQUBE_URL", "mcp/sonarqube"]
    env:
      SONARQUBE_TOKEN: "$ENV{SONARQUBE_TOKEN}"
      SONARQUBE_URL: "$ENV{SONARQUBE_URL}"
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Code Reviewer** (yeni) | Ana kullanıcı — `analyze_code_snippet` + `search_sonar_issues_in_projects` + `get_duplications` |
| **QA Engineer** | `get_project_quality_gate_status` + `search_sonar_issues_in_projects` (E/F bölümleriyle) |
| **Tech Lead** | `get_component_measures` — task quality gate doğrulama |
| **Delivery Manager** | `get_project_quality_gate_status` — final rapor kalite kontrolü |

---

### 2. Snyk Studio MCP Server ⭐ Öncelik: P1

- **Repo:** `snyk/studio-mcp` (Official)
- **Stars:** 19 | **Dil:** Go | **Lisans:** Apache-2.0
- **Gereksinim:** Snyk CLI + Auth token

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `snyk_sca_scan` | Open Source bağımlılık taraması — bilinen CVE'ler |
| `snyk_code_scan` | SAST — statik kod analizi (güvenlik açıkları) |
| `snyk_iac_scan` | Infrastructure as Code taraması (Dockerfile, K8s YAML, Terraform) |
| `snyk_container_scan` | Container image güvenlik taraması |
| `snyk_sbom_scan` | SBOM (Software Bill of Materials) oluşturma |
| `snyk_aibom` | AI BOM — AI model bağımlılık listesi |
| `snyk_trust` | Paket güvenilirlik skoru |

**Yapılandırma:**
```json
{
  "command": "snyk-mcp-server",
  "args": ["stdio"],
  "env": {
    "SNYK_TOKEN": "$ENV{SNYK_TOKEN}"
  }
}
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Security Auditor** | `snyk_sca_scan` + `snyk_code_scan` — sistematik bağımlılık + kod taraması |
| **Security Bug Fixer** | `snyk_sca_scan` — düzeltme sonrası yeniden tarama |
| **DevOps Engineer** | `snyk_iac_scan` + `snyk_container_scan` — CI/CD Security Gates |
| **DBA** | `snyk_sca_scan` — database driver/ORM bağımlılık güvenliği |

---

### 3. Semgrep MCP Server ⭐ Öncelik: P2

- **Repo:** `semgrep/semgrep` (artık ana Semgrep repo'sunda)
- **Stars:** 634 (eski ayrı repo) | **Dil:** Python | **Lisans:** MIT
- **Kurulum:** `uvx semgrep-mcp` veya hosted `mcp.semgrep.ai`

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `security_check` | Hızlı güvenlik taraması |
| `semgrep_scan` | Tam Semgrep analizi (SAST) |
| `semgrep_scan_with_custom_rule` | Özel kural ile tarama (proje-spesifik pattern'ler) |
| `get_abstract_syntax_tree` | AST çıktısı — kod yapısı analizi |
| `semgrep_findings` | Önceki tarama sonuçlarını getir |

**Yapılandırma Seçenekleri:**

A) Hosted (auth gerekmez):
```yaml
- type: mcp_sse
  prefix: semgrep
  config:
    url: "https://mcp.semgrep.ai/mcp"
```

B) Local (daha hızlı):
```yaml
- type: mcp_local
  prefix: semgrep
  config:
    command: "uvx"
    args: ["semgrep-mcp"]
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Security Auditor** | `semgrep_scan` — SAST taraması, OWASP pattern'leri |
| **Security Bug Fixer** | `semgrep_scan` — fix sonrası tekrar tarama |
| **Code Reviewer** (yeni) | `semgrep_scan_with_custom_rule` — code quality pattern'leri |

---

### 4. OSV MCP Server ⭐ Öncelik: P2

- **Repo:** `StacklokLabs/osv-mcp`
- **Stars:** 26 | **Dil:** Go | **Lisans:** Apache-2.0
- **Auth:** Gerekmez (ücretsiz, açık veritabanı)

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `query_vulnerability` | Paket/versiyon/commit/purl ile zafiyet sorgula |
| `query_vulnerabilities_batch` | Toplu paket sorgulama (tüm dependency listesi) |
| `get_vulnerability` | CVE ID ile detaylı bilgi getir |

**Avantajı:** Ücretsiz, auth token gerektirmez, npm/PyPI/Go/Maven/NuGet/CRAN/Packagist destekler.

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: osv
  config:
    command: "osv-mcp-server"
    args: ["--transport", "stdio"]
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Security Auditor** | `query_vulnerabilities_batch` — tüm bağımlılıkları toplu tarama |
| **Security Reviewer** | `get_vulnerability` — tasarım aşamasında bağımlılık CVE kontrolü |

---

### 5. Codacy MCP Server ⭐ Öncelik: P2

- **Repo:** `codacy/codacy-mcp-server`
- **Stars:** 55 | **Dil:** TypeScript | **Lisans:** MIT
- **Kurulum:** `npx -y @codacy/codacy-mcp@latest`
- **Gereksinim:** Codacy Account Token

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `codacy_list_repository_issues` | Kod kalitesi sorunları — best practices, performance, complexity, style |
| `codacy_search_repository_srm_items` | Güvenlik sorunları — SAST, Secrets, SCA, IaC, CICD, DAST |
| `codacy_get_file_coverage` | Dosya bazında coverage bilgisi |
| `codacy_get_file_clones` | Kod tekrarı (DRY ihlalleri) tespiti |
| `codacy_get_file_with_analysis` | Grade, Issues, Duplication, Complexity, Coverage metrikleri |
| `codacy_list_pull_request_issues` | PR'daki yeni/düzeltilen sorunlar |
| `codacy_cli_analyze` | Yerel dosya analizi (Codacy CLI ile) |

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: codacy
  config:
    command: "npx"
    args: ["-y", "@codacy/codacy-mcp@latest"]
    env:
      CODACY_ACCOUNT_TOKEN: "$ENV{CODACY_ACCOUNT_TOKEN}"
```

**Not:** SonarQube ile alternatif/tamamlayıcı olarak kullanılabilir. SonarQube self-hosted tercih ediliyorsa SonarQube, cloud tercih ediliyorsa Codacy seçilebilir. İkisinin birlikte kullanımı gereksiz olabilir.

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Code Reviewer** (yeni) | `codacy_list_repository_issues` + `codacy_get_file_clones` |
| **QA Engineer** | `codacy_get_file_with_analysis` — quality gate kontrolü |
| **Security Auditor** | `codacy_search_repository_srm_items` — güvenlik sorunları |

---

### 6. GitHub MCP Server ⭐ Öncelik: P2

- **Repo:** `github/github-mcp-server` (Official)
- **Stars:** 26.8K | **Dil:** Go | **Lisans:** MIT
- **Docker:** `ghcr.io/github/github-mcp-server`
- **Remote:** `https://api.githubcopilot.com/mcp/` (OAuth)

**Sağladığı Toolset'ler:**

| Toolset | Açıklama | Agent İlgisi |
|---------|---------|-------------|
| `repos` | Repository browse, code search, file content | Architect, Dev'ler |
| `issues` | Issue yönetimi — create, update, list | Tech Lead, Delivery Manager |
| `pull_requests` | PR operations — create, review, merge | Code Reviewer, Dev'ler |
| `actions` | GitHub Actions workflow yönetimi — run, monitor | DevOps Engineer |
| `code_security` | Code scanning alerts, Dependabot | Security Auditor |
| `dependabot` | Dependabot alert/PR yönetimi | Security Auditor, DevOps |
| `secret_protection` | Secret scanning alerts | Security Auditor |
| `security_advisories` | Security advisory yönetimi | Security Reviewer |

**Yapılandırma:**

A) Remote (OAuth — en kolay):
```yaml
- type: mcp_sse
  prefix: github
  config:
    url: "https://api.githubcopilot.com/mcp/"
```

B) Local (PAT ile):
```yaml
- type: mcp_local
  prefix: github
  config:
    command: "docker"
    args: ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "$ENV{GITHUB_PAT}"
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Toolset | Kullanım Amacı |
|-------|---------|---------------|
| **Security Auditor** | `code_security`, `dependabot`, `secret_protection` | GitHub native güvenlik taraması |
| **DevOps Engineer** | `actions` | CI/CD workflow yönetimi |
| **Tech Lead** | `issues` | Task/issue takibi |
| **Code Reviewer** (yeni) | `pull_requests` | PR review desteği |
| **Delivery Manager** | `issues`, `pull_requests` | Proje durumu takibi |

---

### 7. Docker MCP Server ⭐ Öncelik: P3

- **Repo:** `ckreiling/mcp-server-docker`
- **Stars:** 675 | **Dil:** Python | **Lisans:** GPL-3.0
- **Kurulum:** `uvx mcp-server-docker`

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `list_containers` | Container listesi |
| `create_container` / `run_container` | Container oluşturma/çalıştırma |
| `fetch_container_logs` | Container logları |
| `stop_container` / `remove_container` | Container durdurma/silme |
| `list_images` / `pull_image` / `build_image` | Image yönetimi |
| `list_networks` / `create_network` | Network yönetimi |
| `list_volumes` / `create_volume` | Volume yönetimi |

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: docker
  config:
    command: "uvx"
    args: ["mcp-server-docker"]
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **DevOps Engineer** | Container/image yönetimi, deployment |
| **SRE** | Container monitoring, log inspeksiyonu |

---

### 8. Kubernetes MCP Server ⭐ Öncelik: P3

- **Repo:** `rohitg00/kubectl-mcp-server`
- **Stars:** 816 | **Dil:** Python | **Lisans:** MIT
- **Kurulum:** `npx -y kubectl-mcp-server` veya `pip install kubectl-mcp-server`

**253 MCP Tool** — Başlıca kategoriler:

| Kategori | Örnek Tool'lar |
|----------|---------------|
| Pods | `get_pods`, `get_logs`, `diagnose_pod_crash`, `check_pod_health` |
| Deployments | `create_deployment`, `scale_deployment`, `restart_deployment` |
| Helm | `helm_list`, `helm_status`, `install_helm_chart`, `helm_rollback` |
| Security | `audit_rbac_permissions`, `check_secrets_security`, `get_pod_security_info` |
| Cost | `get_resource_recommendations`, `get_idle_resources`, `get_cost_analysis` |
| Networking | `diagnose_network_connectivity`, `check_dns_resolution`, `trace_service_chain` |
| GitOps | `gitops_apps_list`, `gitops_app_sync`, `gitops_app_status` |

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: kubernetes
  config:
    command: "npx"
    args: ["-y", "kubectl-mcp-server"]
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **DevOps Engineer** | Deployment, Helm, CI/CD — ana kullanıcı |
| **SRE** | Pod diagnostics, health checks, resource monitoring |

---

### 9. Grafana MCP Server ⭐ Öncelik: P3

- **Repo:** `grafana/mcp-grafana` (Official)
- **Stars:** 2.3K | **Dil:** Go | **Lisans:** Apache-2.0
- **Kurulum:** Binary, Docker, veya Helm chart

**Sağladığı Araçlar (Kategoriler):**

| Kategori | Tool'lar | Açıklama |
|----------|---------|---------|
| Dashboards | `search_dashboards`, `get_dashboard_summary`, `update_dashboard` | Dashboard yönetimi |
| Prometheus | `query_prometheus`, `list_prometheus_metric_names`, `query_prometheus_histogram` | PromQL sorguları |
| Loki | `query_loki_logs`, `query_loki_patterns` | Log sorguları (LogQL) |
| Alerting | `list_alert_rules`, `create_alert_rule`, `list_contact_points` | Alert yönetimi |
| Incidents | `list_incidents`, `create_incident`, `add_activity_to_incident` | Incident yönetimi |
| OnCall | `list_oncall_schedules`, `get_current_oncall_users`, `list_alert_groups` | On-call yönetimi |
| Annotations | `create_annotation`, `get_annotations` | Dashboard annotation'ları |

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: grafana
  config:
    command: "mcp-grafana"
    args: ["--disable-write"]
    env:
      GRAFANA_URL: "$ENV{GRAFANA_URL}"
      GRAFANA_SERVICE_ACCOUNT_TOKEN: "$ENV{GRAFANA_TOKEN}"
```

**Not:** `--disable-write` flag'i ile read-only mod kullanılabilir (güvenli).

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **SRE** | Ana kullanıcı — PromQL, Loki logları, alert yönetimi, incident'lar |
| **DevOps Engineer** | Deployment sonrası dashboard kontrolü |

---

### 10. Sentry MCP Server ⭐ Öncelik: P3

- **Repo:** `getsentry/sentry-mcp` (Official)
- **Stars:** 551 | **Dil:** TypeScript | **Lisans:** Custom
- **Kurulum:** `npx @sentry/mcp-server@latest`
- **Remote:** `https://mcp.sentry.dev`

**Sağladığı Yetenekler:**
- Error/issue takibi ve analizi
- Trace/performance debugging
- AI-powered event search (`search_events`, `search_issues`)
- Release ve deployment tracking

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: sentry
  config:
    command: "npx"
    args: ["@sentry/mcp-server@latest"]
    env:
      SENTRY_ACCESS_TOKEN: "$ENV{SENTRY_TOKEN}"
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **SRE** | Error tracking, performance monitoring |
| **QA Bug Fixer** | Sentry error'larından bug analizi |

---

### 11. BoostSecurity MCP ⭐ Öncelik: P3

- **Repo:** `boost-community/boost-mcp`
- **Amaç:** Güvensiz bağımlılıkları validate etme, alternatif önerme
- **Desteklenen Ekosistemler:** Python/PyPI, Go, JS/npm, Java/Maven, C#/NuGet

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|---------|
| `validate_package` | Paketin güvenli olup olmadığını kontrol et, güvensizse alternatif öner |

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Security Auditor** | Bağımlılık güvenlik validasyonu |
| **Backend Developer** | Yeni paket eklerken güvenlik kontrolü |

---

## Sorun Çözümü & Q&A MCP Server'ları

Agent'ların hata mesajları, stack trace'ler ve kodlama sorunları için cevap arayabileceği bilgi tabanı MCP'leri. Mevcut `exa` (web search) genel arama yaparken, bu MCP'ler doğrudan Stack Overflow, Hacker News gibi yapılandırılmış Q&A veritabanlarına erişir.

### 12. Stack Overflow MCP Server ⭐ Öncelik: P2

- **Repo:** `gscalzo/stackoverflow-mcp`
- **Stars:** 56 | **Dil:** TypeScript | **Lisans:** MIT
- **Kurulum:** `npx -y @gscalzo/stackoverflow-mcp`
- **Auth:** Opsiyonel — Stack Overflow API Key (rate limit artırır, zorunlu değil)

**Sağladığı Araçlar:**

| Tool | Açıklama | Parametre |
|------|---------|----------|
| `search_by_error` | Hata mesajı ile Stack Overflow'da çözüm ara | `errorMessage`, `language?`, `technologies?`, `minScore?` |
| `search_by_tags` | Tag'lere göre soru ara (örn: python + pandas + dataframe) | `tags[]`, `minScore?`, `limit?` |
| `analyze_stack_trace` | Stack trace'i analiz edip ilgili çözümleri bul | `stackTrace`, `language`, `limit?` |

**Neden Exa'dan farklı?**
- `exa` genel web araması yapar — sonuçlar blog, doküman, video olabilir
- Stack Overflow MCP: doğrudan upvote'lu cevaplara + kabul edilen çözümlere erişir
- `minScore` filtresi ile düşük kaliteli cevaplar atlanır
- `includeComments` ile cevap altındaki tartışmalar da alınır
- `analyze_stack_trace` hatayı parsing edip en alakalı SO sorularını bulur

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: stackoverflow
  config:
    command: "npx"
    args: ["-y", "@gscalzo/stackoverflow-mcp"]
    env:
      STACKOVERFLOW_API_KEY: "$ENV{STACKOVERFLOW_API_KEY}"  # opsiyonel
```

**Kullanım Örneği:**
```json
{
  "name": "search_by_error",
  "arguments": {
    "errorMessage": "TypeError: Cannot read property 'length' of undefined",
    "language": "javascript",
    "technologies": ["react"],
    "minScore": 5,
    "includeComments": true,
    "responseFormat": "markdown",
    "limit": 3
  }
}
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Backend Developer** | Runtime hata çözümü, library kullanım sorunları |
| **Frontend Developer** | UI framework hataları, browser uyumluluk sorunları |
| **QA Bug Fixer** | Test sırasında karşılaşılan hataların çözüm araştırması |
| **Integration Engineer** | API entegrasyon hataları, protobuf/gRPC sorunları |
| **SDET** | Test framework sorunları, CI/CD test hataları |
| **Security Bug Fixer** | Güvenlik fix'i sonrası oluşan edge-case hataları |

---

### 13. Hacker News MCP Server ⭐ Öncelik: P3

- **Repo:** `erithwik/mcp-hn`
- **Stars:** 62 | **Dil:** Python | **Lisans:** MIT
- **Kurulum:** `uvx mcp-hn`
- **Auth:** Gerekmez

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|----------|
| `get_stories` | Top/new/ask/show HN hikayelerini getir |
| `get_story_info` | Hikaye detayları + yorumlar |
| `search_stories` | Sorgu ile arama (örn: "kubernetes memory leak") |
| `get_user_info` | Kullanıcı profili ve aktivitesi |

**Neden Faydalı?**
- HN yorumları genellikle üst düzey mühendislerin (ex-FAANG, OSS maintainer) teknik tartışmalarını içerir
- Yeni teknoloji/araç değerlendirmesi için topluluk görüşleri
- `search_stories` ile spesifik teknik konularda tartışma bulma
- Blog post'ların altındaki HN yorumları genellikle post'un kendisinden daha değerli bilgi içerir

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: hackernews
  config:
    command: "uvx"
    args: ["mcp-hn"]
```

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Solution Architect** | Teknoloji seçimi — topluluk geri bildirimi araştırması |
| **Tech Lead** | Teknoloji kararları için HN tartışmaları |
| **DevOps Engineer** | Yeni araç/platform değerlendirmesi (CI/CD, container, K8s) |

---

### 14. Discourse MCP Server ⭐ Öncelik: P3

- **Repo:** `discourse/discourse-mcp` (Official — Discourse.org)
- **Stars:** 40 | **Dil:** TypeScript | **Lisans:** MIT
- **Kurulum:** `npx -y @discourse/mcp@latest`
- **Auth:** Opsiyonel (read-only mod auth gerektirmez)

**Sağladığı Araçlar:**

| Tool | Açıklama |
|------|----------|
| `discourse_select_site` | Discourse sitesi seç (birden fazla forum destekler) |
| `discourse_search` | Forum içinde arama |
| `discourse_read_topic` | Topic detayları + post'lar |
| `discourse_read_post` | Tekil post okuma |
| `discourse_filter_topics` | Gelişmiş filtreleme (tag, category, status, date) |
| `discourse_list_user_posts` | Kullanıcının post'ları |

**Neden Stack Overflow'dan farklı?**
- Birçok büyük OSS projesi kendi Discourse forumunu kullanır:
  - `discuss.python.org` — Python topluluğu
  - `users.rust-lang.org` — Rust topluluğu
  - `discuss.emberjs.com` — Ember.js
  - `discourse.julialang.org` — Julia
  - `forum.vuejs.org` — Vue.js
  - `community.render.com` — Render hosting
  - Birçok Kubernetes, Docker, DevOps topluluğu
- Stack Overflow genel "en iyi cevap" formatında, Discourse uzun tartışma formatında
- Framework-spesifik sorunlar için SO'dan daha derin bilgi içerebilir
- AI birden fazla Discourse sitesine bağlanabilir

**Yapılandırma:**
```yaml
- type: mcp_local
  prefix: discourse
  config:
    command: "npx"
    args: ["-y", "@discourse/mcp@latest", "--site", "https://discuss.python.org"]
```

**Çoklu Site Kullanımı:**
Birden fazla Discourse forumuna erişmek için `discourse_select_site` tool'u kullanılır. Agent session başında hangi foruma bağlanacağını seçer.

**Hangi Agent'lara Eklenmeli:**

| Agent | Kullanım Amacı |
|-------|---------------|
| **Backend Developer** | Python/Rust/Go framework forumlarında sorun çözümü |
| **Frontend Developer** | Vue/Ember/React topluluk forumlarında sorun çözümü |
| **DevOps Engineer** | K8s/Docker/Terraform topluluk forumları |

---

## Agent Bazlı Yeni MCP Ataması Özeti

Mevcut 6 MCP'ye ek olarak, her agent'a atanması önerilen yeni MCP'ler:

| Agent | Mevcut MCP'ler | + Yeni MCP Önerileri |
|-------|---------------|---------------------|
| **Business Analyst** | seq-thinking, exa, fetch | — (değişiklik yok) |
| **UX Designer** | seq-thinking, exa, fetch | — (değişiklik yok) |
| **Solution Architect** | seq-thinking, context7, deepwiki, exa, filesystem | + GitHub (repos, security_advisories), + Hacker News MCP (teknoloji değerlendirmesi) |
| **Security Reviewer** | seq-thinking, context7, deepwiki, exa, filesystem | + OSV, + GitHub (security_advisories) |
| **DBA** | seq-thinking, context7, deepwiki, filesystem | + Snyk (sca_scan — DB driver güvenliği) |
| **Tech Lead** | seq-thinking, filesystem | + SonarQube (measures, quality gates), + GitHub (issues) |
| **Backend Developer** | seq-thinking, context7, deepwiki, exa, filesystem, fetch | + BoostSecurity (validate_package), + **Stack Overflow MCP** (hata çözümü), + Discourse MCP (forum araştırması) |
| **Frontend Developer** | seq-thinking, context7, deepwiki, exa, filesystem, fetch | + **Stack Overflow MCP** (hata çözümü), + Discourse MCP (forum araştırması) |
| **Integration Engineer** | seq-thinking, filesystem | + **Stack Overflow MCP** (API entegrasyon hataları) |
| **Code Reviewer** (YENİ) | seq-thinking, filesystem | + SonarQube, + Semgrep, + Codacy (veya SonarQube/Codacy'den biri) |
| **QA Engineer** | seq-thinking, context7, filesystem | + SonarQube (quality gate kontrolü) |
| **QA Bug Fixer** | seq-thinking, context7, deepwiki, filesystem | + Sentry (error analizi), + **Stack Overflow MCP** (hata çözümü) |
| **SDET** | seq-thinking, context7, filesystem | + **Stack Overflow MCP** (test framework sorunları) |
| **Security Auditor** | seq-thinking, context7, exa, filesystem | + **Snyk** (SCA+SAST), + **Semgrep** (SAST), + **OSV** (CVE DB), + GitHub (code_security, dependabot, secret_protection) |
| **Security Bug Fixer** | seq-thinking, context7, filesystem | + Snyk (fix sonrası re-scan), + Semgrep (fix doğrulama), + **Stack Overflow MCP** (edge-case hata çözümü) |
| **DevOps Engineer** | seq-thinking, context7, filesystem, fetch | + Snyk (iac_scan, container_scan), + Docker MCP, + Kubernetes MCP, + GitHub (actions), + Hacker News MCP (araç değerlendirmesi) |
| **SRE** | seq-thinking, context7, filesystem | + Grafana MCP, + Docker MCP, + Kubernetes MCP, + Sentry |
| **Technical Writer** | seq-thinking, filesystem, fetch | — (değişiklik yok) |
| **Delivery Manager** | seq-thinking, filesystem | + SonarQube (quality gate raporu), + GitHub (issues, PRs) |

---

## Uygulama Öncelik Sırası

Prompt improvement bulguları ile paralel sıralama:

| Sıra | MCP Server | İlgili Prompt Gap | Etki | Zorluk |
|------|-----------|-------------------|------|--------|
| **P1-1** | **SonarQube MCP** | 🔴 Kod kalite review yok | Çok Yüksek | Orta (SonarQube instance gerekli) |
| **P1-2** | **Snyk MCP** | 🟡 Bağımlılık taraması zayıf | Yüksek | Düşük (Snyk free tier mevcut) |
| **P2-1** | **Semgrep MCP** | 🟡 SAST eksik | Yüksek | Düşük (hosted + ücretsiz) |
| **P2-2** | **OSV MCP** | 🟡 CVE database erişimi | Orta | Çok Düşük (auth gerektirmez) |
| **P2-3** | **GitHub MCP** | DevOps + Security | Orta | Düşük (official, iyi dokümante) |
| **P2-4** | **Codacy MCP** | 🔴 Kod kalite (SonarQube alternatifi) | Yüksek | Düşük (cloud-based) |
| **P3-1** | **Grafana MCP** | SRE monitoring/alerting | Orta | Orta (Grafana instance gerekli) |
| **P3-2** | **Docker MCP** | DevOps container yönetimi | Düşük-Orta | Çok Düşük |
| **P3-3** | **Kubernetes MCP** | DevOps/SRE cluster yönetimi | Düşük-Orta | Düşük (npx ile) |
| **P3-4** | **Sentry MCP** | QA/SRE error tracking | Düşük | Düşük (Sentry hesabı gerekli) |
| **P2-5** | **Stack Overflow MCP** | Q&A sorun çözümü — tüm developer'lar | Yüksek | Çok Düşük (auth gerekmez, npx) |
| **P3-5** | **BoostSecurity MCP** | Bağımlılık validasyonu | Düşük | Çok Düşük |
| **P3-6** | **Hacker News MCP** | Teknoloji değerlendirmesi, topluluk görüşleri | Düşük | Çok Düşük (auth gerekmez) |
| **P3-7** | **Discourse MCP** | Framework-spesifik forum araştırması | Düşük | Düşük (site URL gerekli) |

---

## Minimum Viable Tooling (MVP) Önerisi

Eğer tüm MCP'ler aynı anda eklenemeyecekse, en yüksek etkili kombine:

### Tier 1 — Hemen Ekle (3 MCP)
1. **Snyk MCP** → Security Auditor + DevOps (bağımlılık + IaC + container taraması)
2. **SonarQube MCP** veya **Codacy MCP** → Code Reviewer + QA (kod kalitesi)
3. **OSV MCP** → Security Auditor (ücretsiz CVE database — auth gerekmez)

### Tier 2 — Kısa Vadede Ekle (4 MCP)
4. **Stack Overflow MCP** → Tüm Developer'lar + QA Bug Fixer (hata çözümü)
5. **Semgrep MCP** → Security Auditor + Code Reviewer (SAST)
6. **GitHub MCP** → DevOps + Security + Delivery Manager
7. **Grafana MCP** → SRE (monitoring)

### Tier 3 — Orta Vadede Ekle (5 MCP)
8. **Docker MCP** → DevOps + SRE
9. **Kubernetes MCP** → DevOps + SRE
10. **Sentry MCP** → SRE + QA Bug Fixer
11. **Hacker News MCP** → Architect + Tech Lead (teknoloji araştırması)
12. **Discourse MCP** → Developer'lar (framework-spesifik forum Q&A)

---

## SonarQube vs Codacy Karşılaştırması

İkisi de kod kalitesi analizi yapar. Birini seçmek yeterlidir:

| Özellik | SonarQube MCP | Codacy MCP |
|---------|--------------|------------|
| **Şirket** | SonarSource (official) | Codacy (official) |
| **Hosting** | Self-hosted veya Cloud | Cloud-only (+ CLI) |
| **Dil** | Java | TypeScript (npx) |
| **Kurulum** | Docker image (JDK 21+) | `npx -y @codacy/codacy-mcp` |
| **Code Quality** | ✅ Issues, complexity, duplication | ✅ Issues, complexity, duplication, coverage |
| **Security** | ✅ Vulnerability detection | ✅ SAST, Secrets, SCA, IaC, CICD, DAST |
| **Coverage** | ✅ (CI integration gerekli) | ✅ Built-in |
| **PR Analysis** | ✅ Quality Gate | ✅ PR issues, diff coverage |
| **CLI Analysis** | ❌ (server-only tools) | ✅ `codacy_cli_analyze` (yerel analiz) |
| **Dependency Risks** | ✅ (Enterprise only) | ✅ SRM items |
| **Ücretsiz Tier** | Community Edition | Free plan mevcut |
| **Stars** | 377 | 55 |
| **Öneri** | Self-hosted istiyorsan | Cloud-first istiyorsan |

**Karar:** Self-hosted altyapı varsa **SonarQube**, yoksa **Codacy** tercih edilmeli. İkisini birden kullanmak ekstra fayda sağlamaz.

---

## Context Window Etkisi Analizi

Her eklenen MCP, agent'ın tool listesini büyütür ve context window'u tüketir. Dikkat edilmesi gerekenler:

| Endişe | Çözüm |
|--------|-------|
| Çok fazla tool = LLM kararsızlık | Agent başına max 3-4 MCP server (mevcut + yeni) |
| Tool açıklamaları context yer | `SONARQUBE_TOOLSETS` gibi filtreleme destekleyen MCP'leri yapılandır |
| Gereksiz tool çağrıları | Prompt'ta hangi MCP tool'larını ne zaman kullanacağını açıkça belirt |
| Startup süresi | Docker-based MCP'leri önceden başlat (warm container) |

**Önerilen Agent Başına MCP Limiti:**

| Agent Tipi | Max MCP Sayısı | Mantık |
|-----------|---------------|--------|
| Developer (Backend/Frontend) | 6-7 | Geniş araç seti gerekiyor |
| Security (Auditor/Fixer) | 6-8 | Çok boyutlu tarama gerekiyor |
| QA/SDET | 5-6 | Test + kalite araçları |
| DevOps/SRE | 6-8 | İnfra + monitoring + deployment |
| Design/Planning (BA, UX, Architect) | 4-5 | Araştırma odaklı |
| Management (Tech Lead, Delivery) | 4-5 | Rapor/tracking odaklı |

---

## Sonraki Adımlar

1. **P1 MCP'leri seçip YAML'a entegre et** (Snyk + SonarQube/Codacy + OSV)
2. **Her MCP için gerekli env variable'ları `.env` dosyasına ekle**
3. **Code Reviewer agent'ı oluşturulursa** MCP tooling'ini bu dokümana göre yapılandır
4. **Test:** Her MCP'yi tek tek test edip tool listelerinin doğru yüklendiğini doğrula
5. **Context window monitoring:** Agent'lara MCP ekledikçe performans etkisini ölç
