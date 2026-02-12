# Agile Dev Workflow: Enterprise'ın Çevik Versiyonu

## Context

Mevcut `enterprise_dev.yaml` 26 node, 55 edge, 17 agent ile kapsamlı ama hantal. Her review aşamasında ayrı "Bug Fixer" node'ları var (Code Review Bug Fixer, QA Bug Fixer, Security Bug Fixer, Final Bug Fixer = 4 fixer). Bu, küçük-orta projeler için gereksiz karmaşıklık. Kullanıcı 5-10 agent ile çevik, efektif bir versiyon istiyor.

**Yaklaşım:** Rolleri birleştir, fixer'ları ortadan kaldır, her agent'a daha kapsamlı prompt ver.

---

## Ekip Tasarımı: 7 Agent

| # | Agent | Birleştirdiği Enterprise Roller | Model |
|---|-------|-------------------------------|-------|
| 1 | **Product Analyst** | Business Analyst + UX Designer | sonnet |
| 2 | **Architect** | Solution Architect + Security Reviewer + DBA + Tech Lead | opus |
| 3 | **Developer** | Backend Dev + Frontend Dev + Integration Engineer | opus |
| 4 | **Reviewer** | Code Reviewer + Security Auditor (+ tüm fixer'lar) | opus |
| 5 | **QA Engineer** | QA Engineer + SDET (bug fix dahil) | sonnet |
| 6 | **DevOps** | DevOps Engineer + SRE | sonnet |
| 7 | **Technical Writer** | Technical Writer + Delivery Manager | haiku |

**Neden bu roller?**
- **Product Analyst**: Requirements + UX tek kişide. Çünkü küçük ekipte ayrı UX designer lüks.
- **Architect**: Architecture + Security Design + DB + Task Planning tek kişide. Agile'da Tech Lead = Architect.
- **Developer**: Full-stack. Backend/Frontend ayrımı küçük ekipte gereksiz. Dynamic map ile paralel task'lar.
- **Reviewer**: Code review + Security audit tek geçişte. Fixer yok — FAIL olursa Developer'a geri döner.
- **QA Engineer**: Test + bug fix tek kişide. Bulduğu bug'ları kendisi düzeltir.
- **DevOps**: CI/CD + monitoring tek kişide.
- **Technical Writer**: Docs + delivery summary tek kişide.

---

## Node Envanteri (12 node)

| Node | Type | Açıklama |
|------|------|----------|
| USER | passthrough | Giriş noktası |
| Product Analyst | agent | Gereksinim + UX analizi |
| Architect | agent | Mimari + güvenlik + DB + task planlama |
| Plan Approval | human | Kullanıcı plan onayı |
| Plan Revision Counter | loop_counter | Max 2 revizyon |
| Developer | agent | Full-stack geliştirme (dynamic map) |
| Reviewer | agent | Kod + güvenlik inceleme |
| Review Counter | loop_counter | Max 3 review döngüsü |
| QA Engineer | agent | Test + bug fix |
| QA Counter | loop_counter | Max 3 QA döngüsü |
| DevOps | agent | CI/CD + monitoring |
| Technical Writer | agent | Dokümantasyon + teslimat |

**Toplam:** 7 agent + 1 passthrough + 1 human + 3 loop_counter = 12 node

---

## Akış Diyagramı

```
USER ──→ Product Analyst ──→ Architect ──→ Plan Approval
                                              │
                              ┌────────────── ├── [approve] ──→ Developer (x5 parallel)
                              │               └── [reject]  ──→ Plan Revision Counter
                              │                                      │
                              │               ┌── [not exhausted] ←──┘
                              │               └── [exhausted] ──→ Developer
                              │
                              └── Architect ──(context, dynamic map)──→ Developer
                                                                          │
                                                                          ▼
Developer ──→ Reviewer ──→ [REVIEW_PASS] ──→ QA Engineer ──→ [QA_PASS] ──→ DevOps ──→ Technical Writer
                │                                │
                └── [REVIEW_FAIL]                └── [QA_FAIL]
                     │                                │
                Review Counter                   QA Counter
                     │                                │
                     └── Developer                    └── QA Engineer (kendisi fix'ler)
```

## SCC Analizi (Bağımsız Döngüler)

| SCC | Node'lar | Max İterasyon |
|-----|----------|---------------|
| SCC 1 | Architect ↔ Plan Revision Counter (Plan Approval üzerinden) | 2 |
| SCC 2 | Developer ↔ Review Counter ↔ Reviewer | 3 |
| SCC 3 | QA Engineer ↔ QA Counter | 3 |

**Mega-SCC riski YOK** — QA failures Developer'a geri dönmüyor (QA kendisi fix'liyor), DevOps/Writer'dan geri döngü yok.

---

## Edge Listesi (~22 edge)

### Context Propagation (trigger: false)
| Source | Target | keep_message | dynamic | Amaç |
|--------|--------|-------------|---------|------|
| USER | Architect | true | - | Orijinal isteği Architect'e aktar |
| USER | QA Engineer | true | - | Orijinal isteği QA'e aktar |
| USER | Technical Writer | true | - | Orijinal isteği Writer'a aktar |
| Product Analyst | Architect | false (trigger edge) | - | - |
| Architect | Developer | true | **DYNAMIC MAP** | Task planını paralel Developer instance'larına dağıt |

### Trigger Edges
| Source | Target | Condition | clear_context | Amaç |
|--------|--------|-----------|---------------|------|
| USER | Product Analyst | - | - | Workflow başlat |
| Product Analyst | Architect | - | - | Gereksinimleri ilet |
| Architect | Plan Approval | - | - | Planı onaya sun |
| Plan Approval | Developer | keyword: approve/onay/tamam | - | Onaylanan planla geliştir |
| Plan Approval | Plan Revision Counter | keyword: NOT approve | - | Revizyon döngüsü |
| Plan Revision Counter | Architect | NOT LOOP_EXIT, keep_message | - | Revize et |
| Plan Revision Counter | Developer | LOOP_EXIT | - | Maks revizyon, devam et |
| Developer | Reviewer | - | true | Kodu incele |
| Reviewer | QA Engineer | REVIEW_PASS | true | QA'e geç |
| Reviewer | Review Counter | NOT REVIEW_PASS | - | Review döngüsü |
| Review Counter | Developer | NOT LOOP_EXIT | - | Developer düzeltsin |
| Review Counter | QA Engineer | LOOP_EXIT | true | Maks review, devam et |
| QA Engineer | DevOps | QA_PASS | true | DevOps'a geç |
| QA Engineer | QA Counter | NOT QA_PASS | - | QA döngüsü |
| QA Counter | QA Engineer | NOT LOOP_EXIT | - | QA tekrar test+fix |
| QA Counter | DevOps | LOOP_EXIT | true | Maks QA, devam et |
| DevOps | Technical Writer | - | - | Dokümantasyona geç |

---

## Agent Prompt Tasarımı

Her agent'ın prompt'u, birleştirdiği tüm rollerin sorumluluklarını kapsar. Enterprise'daki 5 ayrı prompt → 1 kapsamlı prompt.

### Prompt Özeti
| Agent | Prompt Kapsamı | Tahmini Uzunluk |
|-------|---------------|-----------------|
| Product Analyst | Stakeholder analizi, fonksiyonel/non-fonksiyonel gereksinimler, kullanıcı personaları, user flow, kabul kriterleri, MoSCoW | ~800 kelime |
| Architect | System architecture, ADR, tech stack, API contract, DB schema, security threat model, task breakdown | ~1200 kelime |
| Developer | Full-stack implementation, unit test, API + UI, SOLID, clean code | ~600 kelime |
| Reviewer | SOLID review, OWASP Top 10, design patterns, security vulns, REVIEW_PASS/FAIL | ~800 kelime |
| QA Engineer | Functional test, integration test, automated tests, bug fix, QA_PASS/FAIL | ~800 kelime |
| DevOps | Dockerfile, docker-compose, CI/CD, health check, logging, monitoring | ~600 kelime |
| Technical Writer | README, API docs, CHANGELOG, architecture summary, delivery metrics | ~500 kelime |

---

## MCP Tooling Dağılımı

| Agent | Tooling |
|-------|---------|
| Product Analyst | sequential-thinking, exa-search, web-fetch, filesystem |
| Architect | sequential-thinking, context7, deepwiki, exa-search, filesystem |
| Developer | context7, deepwiki, exa-search, filesystem, stackoverflow |
| Reviewer | sequential-thinking, context7, filesystem |
| QA Engineer | sequential-thinking, context7, filesystem |
| DevOps | sequential-thinking, context7, filesystem |
| Technical Writer | filesystem |

---

## Dynamic Map (Paralel Task Dağılımı)

Architect → Developer edge'inde dynamic map:
```yaml
dynamic:
  type: map
  split:
    type: regex
    config:
      pattern: "### Task \\d+:.*?(?=### Task \\d+:|$)"
      dotall: true
      on_no_match: pass
  config:
    max_parallel: 5
```

Architect'in task planı `### Task 1:`, `### Task 2:` formatında olacak. Her task bağımsız bir Developer instance'ına dağıtılacak.

---

## Dosya Değişiklikleri

| # | Değişiklik | Dosya |
|---|-----------|-------|
| 1 | Yeni `agile_dev.yaml` oluştur | `yaml_instance/agile_dev.yaml` |

**Kod değişikliği SIFIR** — engine tüm bu özellikleri zaten destekliyor.

---

## Enterprise vs Agile Karşılaştırma

| Metrik | Enterprise | Agile |
|--------|-----------|-------|
| Agent sayısı | 17 | 7 |
| Toplam node | 26 | 12 |
| Edge sayısı | 55 | ~22 |
| SCC sayısı | 5 | 3 |
| Fixer node'ları | 4 | 0 |
| Human gate'ler | 2 | 1 |
| Dynamic map | 2 (backend + frontend ayrı) | 1 (unified task) |
| Model tier | opus + sonnet + haiku | opus + sonnet + haiku |
| Tahmini süre | ~2-3 saat | ~45-90 dakika |

---

## Doğrulama

1. YAML syntax: `uv run python -c "import yaml; yaml.safe_load(open('yaml_instance/agile_dev.yaml'))"`
2. Workflow parse: `uv run python -c "from workflow.parser import WorkflowParser; p = WorkflowParser(); p.parse_file('yaml_instance/agile_dev.yaml'); print('OK')"`
3. Frontend render: Workflow'u UI'da açıp node/edge bağlantılarını görsel doğrula
4. Manuel test: Basit bir proje ile workflow'u çalıştır, tüm agent'ların doğru çalıştığını kontrol et
