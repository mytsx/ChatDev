# Fullstack Dev Workflow: Backend + Frontend Parallel Pipeline

## Context

Kullanıcının iki ayrı projesi var: **mapeg** (.NET microservices) ve **mapeg-ui** (Angular). Mevcut `agile_dev.yaml` tek bir Developer node'u ile çalışıyor. Yeni workflow'da:
- Backend Developer ve Frontend Developer **paralel** çalışacak
- Her iki developer da aynı layer'da — birbirini beklemiyor
- Sadece backend, sadece frontend veya fullstack görev olabilir (scope evaluation ile karar)
- Paylaşımlı parent workspace: tüm node'lar aynı dizini kullanır, prompt ile yönlendirilir
- Tek combined review: Her iki developer bittikten sonra Reviewer kontrol eder (AND-join)
- Review fix'leri yeni "Code Fixer" node'u ile — enterprise_dev'deki pattern

---

## Akış Özeti

```
USER → Product Analyst → Architect → [Plan Approval / AUTO_APPROVE]
  → Backend Developer (paralel, dynamic map)  ─┐
  → Frontend Developer (tek instance)          ─┤→ AND-join
  ──────────────────────────────────────────────┘
  → Reviewer → [Code Fixer loop] → QA Engineer → DevOps → Technical Writer
```

**3 bağımsız SCC:**
1. {Architect, Plan Approval, Plan Revision Counter} — plan revision (max 2)
2. {Code Fixer, Reviewer, Review Counter} — code review (max 3)
3. {QA Engineer, QA Counter} — QA test (max 3)

**Topoloji katmanları:**
```
Layer 0: USER
Layer 1: Product Analyst
Layer 2: SCC1 (Plan Revision)
Layer 3: Backend Developer + Frontend Developer (PARALEL — aynı layer)
Layer 4: SCC2 (Code Review — Code Fixer, Reviewer, Review Counter)
Layer 5: SCC3 (QA)
Layer 6: DevOps
Layer 7: Technical Writer
```

---

## Dosya Değişiklikleri

**Tek dosya oluşturulacak:**
- `yaml_instance/fullstack_dev.yaml` — agile_dev.yaml baz alınarak

**Engine değişikliği YOK.** Mevcut engine kapasitesi yeterli.

---

## Tasarım Kararları

### Neden Paralel?

**Eski tasarım (sıralı)**: Backend Dev → Frontend Dev trigger edge → Frontend Dev HER ZAMAN Backend Dev'in bitmesini bekler. Frontend-only görevlerde bile ~15-20s boşa harcanır.

**Yeni tasarım (paralel)**: Her iki developer SCC1'den bağımsız tetiklenir. Topoloji builder (topology_builder.py:76-93) sadece `trigger:true` edge'lerden super-node bağımlılığı çıkarır. İki developer arasında trigger edge olmadığı için aynı layer'a düşer.

**Topoloji doğrulama:**
- Backend Dev predecessors (trigger): {SCC1 super-node}
- Frontend Dev predecessors (trigger): {SCC1 super-node}
- İkisi de sadece SCC1'e bağlı → aynı layer (Layer 3) ✓
- SCC2 predecessors: {Backend Dev super-node, Frontend Dev super-node} → Layer 4 ✓

### Üç Senaryo

| Senaryo | Backend Dev | Frontend Dev | Davranış |
|---------|------------|--------------|----------|
| **Fullstack** | Backend task'ları implement eder | Frontend task'ları implement eder | Paralel çalışır, Reviewer AND-join ile her ikisini bekler |
| **Backend-only** | Backend task'ları implement eder | Scope eval skip (~15s) | Paralel — skip çok hızlı, overhead yok |
| **Frontend-only** | Scope eval skip (~15s) | Frontend task'ları implement eder | Paralel — skip çok hızlı, overhead yok |

Scope evaluation skip paralel çalıştığı için **takvim süresine sıfır eklenti** yapar. Uzun süren developer çalışırken, diğeri skip'i çoktan bitirmiş olur.

### Fullstack'te API Contract Yönetimi

Paralel çalışmada Frontend Dev, Backend Dev'in gerçek çıktısını görmez. Bunun yerine:
1. **Architect** API contract'ları detaylı tanımlar (endpoint path, request/response DTO, status codes)
2. **Frontend Dev** bu contract'lara göre implement eder
3. **Backend Dev** aynı contract'ları implement eder
4. **Reviewer** iki projenin contract uyumunu kontrol eder
5. Uyumsuzluk varsa → **Code Fixer** düzeltir (review loop)

Bu, gerçek yazılım ekiplerinin çalışma şeklini yansıtır: frontend ve backend geliştiriciler API contract'ları üzerinden paralel çalışır.

### Review Loop: Code Fixer Pattern

Review fail olduğunda loop Frontend Dev'e değil, **Code Fixer** node'una gider. Neden?

Eğer `Review Counter → Frontend Dev` (trigger:true) olsaydı:
- Frontend Dev SCC2'nin içine girerdi
- SCC2 = {Frontend Dev, Reviewer, Review Counter}
- SCC2'nin external predecessor'ı: Backend Dev (trigger edge Backend Dev → Reviewer)
- SCC2, Backend Dev'den SONRA gelen layer'a düşerdi
- Ama Frontend Dev SCC2'de olduğundan, ilk çalışmada da Backend Dev'i beklerdi
- **Sonuç: Frontend Dev yine Backend Dev'in arkasında!**

Code Fixer ile:
- SCC2 = {Code Fixer, Reviewer, Review Counter} — ne Backend Dev ne Frontend Dev içeride
- Backend Dev ve Frontend Dev Layer 3'te paralel kalır
- Code Fixer hem `${BACKEND_DIR}/` hem `${FRONTEND_DIR}/` erişimine sahip — her iki projede fix yapabilir

Bu, enterprise_dev.yaml'daki "dedicated fixer node" pattern'i ile aynıdır (bkz. MEMORY.md: "Never route a late-stage retry loop back into an earlier independent cycle").

### Dynamic Map: Sadece Backend

- **Backend Developer**: Dynamic map ile `### Backend Task N:` pattern split → N paralel instance (max 5). .NET microservices'te her servis bağımsız.
- **Frontend Developer**: Dynamic map YOK, tek instance. Angular bileşenleri birbirine bağımlı (routing, shared state, component hierarchy).

### Dynamic Map Predecessor Gereksinimi

`_get_dynamic_config_for_node()` (graph.py:456) node'un `predecessors` listesini tarar. Predecessors sadece `trigger:true` edge'lerden oluşuyor (graph_manager.py:162).

- Backend Developer: Architect'ten `trigger:true` edge (AUTO_APPROVE) → Architect predecessor → Architect'in context edge'indeki dynamic map keşfedilir ✓
- Frontend Developer: Dynamic map yok → predecessor gereksinimi yok ✓

---

## Node Listesi (14 node)

| # | ID | Type | Model | Turns | Not |
|---|-----|------|-------|-------|-----|
| 1 | USER | passthrough | — | — | Entry point |
| 2 | Product Analyst | agent | sonnet | 45 | agile_dev.yaml'dan kopyala |
| 3 | Architect | agent | opus | 50 | Task format: Backend/Frontend Task + API contracts |
| 4 | Plan Approval | human | — | — | agile_dev.yaml'dan kopyala |
| 5 | Plan Revision Counter | loop_counter | — | max 2 | agile_dev.yaml'dan kopyala |
| 6 | Backend Developer | agent | opus | 50 | .NET odaklı, `${BACKEND_DIR}/` scope |
| 7 | Frontend Developer | agent | opus | 50 | Angular odaklı, `${FRONTEND_DIR}/` scope |
| 8 | Code Fixer | agent | opus | 50 | **YENİ**: Dual-project fix, review loop içinde |
| 9 | Reviewer | agent | opus | 40 | Güncellendi: dual-project review |
| 10 | Review Counter | loop_counter | — | max 3 | agile_dev.yaml'dan kopyala |
| 11 | QA Engineer | agent | sonnet | 45 | Güncellendi: integrated testing |
| 12 | QA Counter | loop_counter | — | max 3 | agile_dev.yaml'dan kopyala |
| 13 | DevOps | agent | sonnet | 35 | Güncellendi: dual-project deployment |
| 14 | Technical Writer | agent | haiku | 25 | Güncellendi: dual-project docs |

---

## Edge Listesi (28 edge: 23 trigger + 5 context)

### Trigger Edges (23)

| # | From | To | Condition | Not |
|---|------|----|-----------|-----|
| 1 | USER | Product Analyst | true | |
| 2 | Product Analyst | Architect | true | |
| 3 | Architect | Plan Approval | none: [AUTO_APPROVE] | Karmaşık görevler |
| 4 | Architect | Backend Developer | any: [AUTO_APPROVE] | Basit — backend bypass |
| 5 | Architect | Frontend Developer | any: [AUTO_APPROVE] | Basit — frontend bypass |
| 6 | Plan Approval | Backend Developer | any: [approve, onay, tamam] | İnsan onayı → backend |
| 7 | Plan Approval | Frontend Developer | any: [approve, onay, tamam] | İnsan onayı → frontend |
| 8 | Plan Approval | Plan Revision Counter | none: [approve, onay, tamam] | Revizyon |
| 9 | Plan Revision Counter | Architect | none: [LOOP_EXIT] | Loop devam |
| 10 | Plan Revision Counter | Backend Developer | any: [LOOP_EXIT] | Loop bitti → backend |
| 11 | Plan Revision Counter | Frontend Developer | any: [LOOP_EXIT] | Loop bitti → frontend |
| 12 | Backend Developer | Reviewer | true | Backend çıktısı → review |
| 13 | Frontend Developer | Reviewer | true, clear_context | Frontend çıktısı → review |
| 14 | Reviewer | QA Engineer | any: [REVIEW_PASS], clear_context | Geçti |
| 15 | Reviewer | Review Counter | none: [REVIEW_PASS] | Kaldı |
| 16 | Review Counter | Code Fixer | none: [LOOP_EXIT] | Fix retry |
| 17 | Review Counter | QA Engineer | any: [LOOP_EXIT], clear_context | Loop bitti |
| 18 | Code Fixer | Reviewer | true | Fix sonrası re-review |
| 19 | QA Engineer | DevOps | any: [QA_PASS] | Geçti |
| 20 | QA Engineer | QA Counter | none: [QA_PASS] | Kaldı |
| 21 | QA Counter | QA Engineer | none: [LOOP_EXIT] | Retry |
| 22 | QA Counter | DevOps | any: [LOOP_EXIT] | Loop bitti |
| 23 | DevOps | Technical Writer | true | |

### Context Edges (5, trigger: false)

| # | From | To | Not |
|---|------|----|-----|
| 24 | USER | Architect | keep_message — orijinal istek |
| 25 | USER | QA Engineer | keep_message — gereksinim referansı |
| 26 | USER | Technical Writer | keep_message — dokümantasyon referansı |
| 27 | Architect | Backend Developer | **dynamic map**: regex `### Backend Task \d+:`, max_parallel: 5, on_no_match: pass |
| 28 | Architect | Frontend Developer | keep_message, carry_data — tam plan (dynamic map YOK) |

### AND-join Davranışı

**Reviewer (Edge #12 + #13)**: İki trigger predecessor — Backend Dev ve Frontend Dev. Engine her ikisinin de bitmesini bekler (AND-join). Scope eval skip paralel çalıştığı için ek bekleme yok.

**İlk iterasyon**: Reviewer, Backend Dev + Frontend Dev çıktılarını alır.
**Cycle retry**: Review Counter → Code Fixer → Reviewer. Cycle executor sadece SCC-internal predecessor'lara bakar — external (Backend Dev, Frontend Dev) zaten tamamlanmış, tekrar beklenmez.

---

## Prompt Değişiklikleri (agile_dev.yaml'dan farklar)

### Architect — Task Format + API Contracts

Mevcut `### Task N:` formatı yerine:

```
## TASK FORMAT

You MUST organize tasks using these EXACT section headers:

### Backend Task N: [Title] — Size: [S/M/L]
**What**: [Specific backend deliverable]
**Files**: [Paths relative to ${BACKEND_DIR}/]
**API Contract**: [Method, path, request/response DTO schema if this creates/modifies an API]
**Dependencies**: [Other task dependencies]

### Frontend Task N: [Title] — Size: [S/M/L]
**What**: [Specific frontend deliverable]
**Files**: [Paths relative to ${FRONTEND_DIR}/]
**Consumes API**: [Reference to Backend Task's API contract if applicable]
**Dependencies**: [Other task dependencies]

SPECIAL CASES:
- Backend-only: Create only "### Backend Task N:" sections
- Frontend-only: Create only "### Frontend Task N:" sections
- Fullstack: Backend tasks + Frontend tasks. Frontend tasks reference backend API contracts.

IMPORTANT: For fullstack tasks, define API contracts precisely in Backend Tasks.
Frontend Developer will implement against these contracts IN PARALLEL with Backend Developer.
Both developers will NOT see each other's output. API contracts are the shared interface.
```

### Backend Developer — Yeni Node

```
═══ WORKSPACE SCOPE ═══

You work EXCLUSIVELY in the ${BACKEND_DIR}/ subdirectory.
This is a .NET microservices project.
NEVER modify files outside ${BACKEND_DIR}/.

═══ SCOPE EVALUATION (do this FIRST) ═══

If you receive NO "### Backend Task" assignments, output:
"SCOPE: No backend tasks assigned. Skipping backend development."
Then stop immediately without making any code changes.

═══ SCOPE BOUNDARY ═══

[agile_dev.yaml Developer'ın scope boundary kuralları]

═══ ROLE ═══

You are a Senior Backend Developer specializing in .NET/C# microservices.
You receive: Architect's backend task assignments with API contracts.
Frontend Developer works IN PARALLEL with you — you will not see each other's output.
The Reviewer will check both projects for contract alignment.

Implementation order:
1. Database models/migrations (Entity Framework)
2. Business logic / domain services
3. API controllers + DTOs (MUST match Architect's API contracts exactly)
4. Unit tests (xUnit/NUnit)

CRITICAL: Implement API endpoints EXACTLY as specified in the Architect's API contracts.
Frontend Developer is building against the same contracts simultaneously.
```

### Frontend Developer — Yeni Node

```
═══ WORKSPACE SCOPE ═══

You work EXCLUSIVELY in the ${FRONTEND_DIR}/ subdirectory.
This is an Angular project.
NEVER modify files outside ${FRONTEND_DIR}/.

═══ SCOPE EVALUATION (do this FIRST) ═══

If you receive NO "### Frontend Task" assignments, output:
"SCOPE: No frontend tasks assigned. Skipping frontend development."
Then stop immediately without making any code changes.

═══ SCOPE BOUNDARY ═══

[agile_dev.yaml Developer'ın scope boundary kuralları]

═══ ROLE ═══

You are a Senior Frontend Developer specializing in Angular.
You receive: Architect's frontend task assignments with API contract references.
Backend Developer works IN PARALLEL with you — you will not see each other's output.
The Reviewer will check both projects for contract alignment.

Implementation order:
1. Models/interfaces matching Architect's API contract DTOs
2. Services (HttpClient calls to API endpoints as defined in contracts)
3. Components (smart + dumb pattern)
4. Routing + guards
5. Unit tests (Jasmine/Karma) + e2e specs

CRITICAL: Implement API calls EXACTLY as specified in the Architect's API contracts.
Backend Developer is building the same endpoints simultaneously.
```

### Code Fixer — Yeni Node

```
═══ WORKSPACE SCOPE ═══

You have access to BOTH projects:
1. ${BACKEND_DIR}/ — .NET microservices (Backend)
2. ${FRONTEND_DIR}/ — Angular application (Frontend)

═══ ROLE ═══

You are a Senior Fullstack Developer who fixes code review issues.
You receive: Reviewer's feedback identifying problems in backend, frontend, or both.
Your output goes to → Reviewer (who will re-audit the fixes).

Fix ONLY the specific issues identified by the Reviewer.
Do NOT refactor, optimize, or add features beyond what the Reviewer requested.

═══ SCOPE BOUNDARY ═══

[agile_dev.yaml Developer'ın scope boundary kuralları]

For each fix, clearly document:
1. What was the issue (from Reviewer's feedback)
2. What file(s) you changed
3. What the fix does
```

### Reviewer — Güncellendi

```
═══ MULTI-PROJECT REVIEW ═══

You are reviewing a fullstack system with two projects:
1. ${BACKEND_DIR}/ — .NET microservices (Backend)
2. ${FRONTEND_DIR}/ — Angular application (Frontend)

NOTE: If a developer output contains "SCOPE: No ... tasks assigned",
that project was not modified. Focus your review only on the project(s)
that were actually changed.

Review checklist:
- Backend: API contracts match Architect's spec, data access, security, error handling, SOLID
- Frontend: Component quality, state management, API integration, RxJS patterns
- Contract alignment: Frontend service calls match backend API endpoints exactly
  (paths, methods, request/response schemas, status codes)
- Cross-cutting: Naming consistency, shared models match between projects, CORS config
```

### QA Engineer — Güncellendi

```
═══ INTEGRATED TESTING ═══

Test the COMPLETE system across both projects:
1. ${BACKEND_DIR}/ — Run .NET tests (dotnet test), verify API endpoints
2. ${FRONTEND_DIR}/ — Run Angular tests (ng test), verify components
3. Integration — Frontend calls backend APIs correctly, data flows end-to-end

NOTE: If a project was not modified (developer scope eval skip),
you may skip testing for that project.
```

### DevOps — Güncellendi

```
═══ MULTI-PROJECT DEPLOYMENT ═══

Create deployment config for BOTH projects:
1. ${BACKEND_DIR}/ — .NET microservice Dockerfiles, docker-compose
2. ${FRONTEND_DIR}/ — Angular build + nginx/static serve
3. Shared: docker-compose.yml orchestrating both services, CI/CD pipeline
```

---

## YAML vars

```yaml
vars:
  BACKEND_DIR: mapeg
  FRONTEND_DIR: mapeg-ui
```

Kullanıcı bu değerleri `.env` veya YAML `vars:` bölümünden override edebilir.

---

## Dynamic Map Regex

Backend Developer context edge:
```yaml
dynamic:
  type: map
  split:
    type: regex
    config:
      pattern: "### Backend Task \\d+:.*?(?=### (?:Backend |Frontend )Task \\d+:|$)"
      dotall: true
      on_no_match: pass
  config:
    max_parallel: 5
```

`on_no_match: pass` davranışı (splitter.py:84-87): Regex eşleşmezse tam mesaj tek birim olarak geçer → Backend Dev scope evaluation "No backend tasks" diyerek skip eder.

---

## SCC Doğrulama

```
Trigger edges → Tarjan SCC (trigger:true only):

SCC #1: {Architect, Plan Approval, Plan Revision Counter}
  Back-edge: Plan Revision Counter → Architect
  Exits: → Backend Developer (3 yol: AUTO_APPROVE, approve, LOOP_EXIT)
          → Frontend Developer (3 yol: AUTO_APPROVE, approve, LOOP_EXIT)

SCC #2: {Code Fixer, Reviewer, Review Counter}
  Back-edge: Code Fixer → Reviewer → Review Counter → Code Fixer
  External predecessors: Backend Developer, Frontend Developer (AND-join)
  Exits: → QA Engineer (2 yol: REVIEW_PASS, LOOP_EXIT)

SCC #3: {QA Engineer, QA Counter}
  Back-edge: QA Counter → QA Engineer
  Exits: → DevOps (2 yol: QA_PASS, LOOP_EXIT)

Backend Developer: SCC dışı, Layer 3 (SCC1 sonrası, SCC2 öncesi)
Frontend Developer: SCC dışı, Layer 3 (Backend Dev ile AYNI layer — paralel)
Code Fixer: SCC2 içinde, Layer 4
```

---

## Eski vs Yeni Karşılaştırma

| Özellik | Eski (Sıralı) | Yeni (Paralel) |
|---------|---------------|----------------|
| Developer ilişkisi | Backend → Frontend (sıralı) | Aynı layer (paralel) |
| Frontend-only overhead | ~15-20s (Backend scope eval skip + sıralı bekleme) | ~0s (skip paralel çalışır) |
| Backend-only overhead | ~15-20s (Frontend scope eval skip) | ~0s (skip paralel çalışır) |
| Fullstack API bilgisi | Frontend, Backend'in gerçek çıktısını görür | Her iki dev Architect's contract'tan çalışır |
| Fullstack entegrasyon riski | Düşük (sıralı) | Orta (contract mismatch olabilir → Reviewer yakalar) |
| Node sayısı | 13 | 14 (+Code Fixer) |
| Edge sayısı | 24 (19+5) | 28 (23+5) |
| SCC2 üyeleri | {Frontend Dev, Reviewer, Review Counter} | {Code Fixer, Reviewer, Review Counter} |
| Review fix yapan | Frontend Developer | Code Fixer (her iki projeye erişim) |

---

## Uygulama Adımları

1. `agile_dev.yaml`'ı `fullstack_dev.yaml` olarak kopyala
2. `vars:` bölümüne `BACKEND_DIR` ve `FRONTEND_DIR` ekle
3. Mevcut Developer node'unu Backend Developer olarak yeniden adlandır + prompt güncelle
4. Yeni Frontend Developer node'u ekle
5. Yeni Code Fixer node'u ekle
6. Architect prompt'unu `### Backend Task N:` / `### Frontend Task N:` + API contracts formatına güncelle
7. Dynamic map regex'ini backend-specific pattern'e güncelle
8. SCC1 çıkışlarını duplicate et: her exit hem Backend Dev hem Frontend Dev'e gitsin
   - Architect → Backend Dev (AUTO_APPROVE) + Architect → Frontend Dev (AUTO_APPROVE)
   - Plan Approval → Backend Dev (approve) + Plan Approval → Frontend Dev (approve)
   - Plan Revision Counter → Backend Dev (LOOP_EXIT) + Plan Revision Counter → Frontend Dev (LOOP_EXIT)
9. Backend Dev → Reviewer (trigger:true) edge ekle
10. Frontend Dev → Reviewer (trigger:true, clear_context) edge ekle
11. Review Counter → Code Fixer (none: [LOOP_EXIT]) edge ekle
12. Code Fixer → Reviewer (trigger:true) edge ekle
13. Eski edge'leri kaldır: Backend Dev → Frontend Dev, Review Counter → Frontend Dev
14. Yeni context edge ekle: Architect → Frontend Developer (keep_message, carry_data)
15. Reviewer, QA, DevOps, TW prompt'larını dual-project için güncelle

## Doğrulama

```bash
# 1. YAML syntax
uv run python -c "import yaml; yaml.safe_load(open('yaml_instance/fullstack_dev.yaml')); print('YAML OK')"

# 2. SCC topoloji (trigger:true only Tarjan)
uv run python -c "
import yaml
from collections import defaultdict

with open('yaml_instance/fullstack_dev.yaml') as f:
    config = yaml.safe_load(f)

edges = [(e['from'], e['to']) for e in config['graph']['edges'] if e.get('trigger', True)]
graph = defaultdict(list)
nodes = set()
for s, d in edges:
    graph[s].append(d)
    nodes.add(s); nodes.add(d)

# Tarjan SCC
idx = [0]; stack = []; low = {}; ix = {}; on = {}; sccs = []
def sc(v):
    ix[v]=idx[0]; low[v]=idx[0]; idx[0]+=1; stack.append(v); on[v]=True
    for w in graph.get(v,[]):
        if w not in ix: sc(w); low[v]=min(low[v],low[w])
        elif on.get(w): low[v]=min(low[v],ix[w])
    if low[v]==ix[v]:
        scc=[]
        while True:
            w=stack.pop(); on[w]=False; scc.append(w)
            if w==v: break
        if len(scc)>1: sccs.append(scc)
for n in sorted(nodes):
    if n not in ix: sc(n)
print('SCCs:', sccs)
assert len(sccs) == 3, f'Expected 3 SCCs, got {len(sccs)}'
print('Topology OK')
"

# 3. Edge count
uv run python -c "
import yaml
with open('yaml_instance/fullstack_dev.yaml') as f:
    config = yaml.safe_load(f)
edges = config['graph']['edges']
trigger = [e for e in edges if e.get('trigger', True)]
context = [e for e in edges if not e.get('trigger', True)]
print(f'Total: {len(edges)} (trigger: {len(trigger)}, context: {len(context)})')
assert len(trigger) == 23, f'Expected 23 trigger, got {len(trigger)}'
assert len(context) == 5, f'Expected 5 context, got {len(context)}'
"

# 4. Parallelism check (Backend Dev and Frontend Dev in same layer)
uv run python -c "
import yaml
with open('yaml_instance/fullstack_dev.yaml') as f:
    config = yaml.safe_load(f)

# Build trigger predecessor map
preds = {}
for node in config['graph']['nodes']:
    nid = node['id']
    preds[nid] = set()

for edge in config['graph']['edges']:
    if edge.get('trigger', True):
        preds[edge['to']].add(edge['from'])

# Check Backend Dev and Frontend Dev have same predecessors (both from SCC1 only)
bd_preds = preds.get('Backend Developer', set())
fd_preds = preds.get('Frontend Developer', set())
print(f'Backend Dev predecessors: {bd_preds}')
print(f'Frontend Dev predecessors: {fd_preds}')
assert bd_preds == fd_preds, f'Predecessors differ! BD={bd_preds}, FD={fd_preds}'
print('Parallel check OK — same predecessors, same layer')
"
```
