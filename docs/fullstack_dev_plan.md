# Fullstack Dev Workflow: Backend + Frontend Sequential Pipeline

## Context

Kullanıcının iki ayrı projesi var: **mapeg** (.NET microservices) ve **mapeg-ui** (Angular). Mevcut `agile_dev.yaml` tek bir Developer node'u ile çalışıyor. Yeni workflow'da:
- Backend Developer → Frontend Developer sıralı çalışacak
- Backend: API/DB/business logic oluşturur → Frontend: API'leri consume eder
- Sadece backend veya sadece frontend görev olabilir (Architect scope evaluation ile karar verir)
- Paylaşımlı parent workspace: tüm node'lar aynı dizini kullanır, prompt ile yönlendirilir
- Tek combined review: Frontend Dev sonrası Reviewer her iki projeyi kontrol eder

---

## Akış Özeti

```
USER → Product Analyst → Architect → [Plan Approval / AUTO_APPROVE]
  → Backend Developer(s, parallel) → Frontend Developer (sequential)
  → Reviewer → QA Engineer → DevOps → Technical Writer
```

**3 bağımsız SCC:**
1. {Architect, Plan Approval, Plan Revision Counter} — plan revision (max 2)
2. {Frontend Developer, Reviewer, Review Counter} — code review (max 3)
3. {QA Engineer, QA Counter} — QA test (max 3)

**Topoloji katmanları:**
```
Layer 0: USER
Layer 1: Product Analyst
Layer 2: SCC1 (Plan Revision)
Layer 3: Backend Developer (paralel, dynamic map)
Layer 4: SCC2 (Code Review — Frontend Dev, Reviewer, Review Counter)
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

### Backend: Paralel, Frontend: Sıralı

- **Backend Developer**: Dynamic map ile `### Backend Task N:` pattern'i split → N paralel instance (max 5). .NET microservices'te her servis bağımsız çalışabilir.
- **Frontend Developer**: Dynamic map YOK, tek instance. Angular'da bileşenler birbirine bağımlı (routing, shared state, component hierarchy). Sıralı geliştirme daha güvenli.

### Dynamic Map Predecessor Gereksinimi

`_get_dynamic_config_for_node()` (graph.py:456) node'un `predecessors` listesini tarar. Predecessors sadece `trigger:true` edge'lerden oluşuyor (graph_manager.py:162). Bu yüzden:
- Backend Developer: Architect'ten `trigger:true` edge (AUTO_APPROVE) → Architect predecessor → dynamic map keşfedilir ✓
- Frontend Developer: Dynamic map yok → predecessor gereksinimi yok. Architect çıktısını basit context edge ile alır ✓

### Review Döngüsü

Review fail olduğunda → Review Counter → Frontend Developer. Frontend Dev parent workspace'e sahip, gerekirse `${BACKEND_DIR}/` dizinine gidip minimal backend fix yapabilir.

### Backend-First vs Frontend-First

- **Backend-first (varsayılan)**: Yeni API → Frontend consume eder. En yaygın senaryo.
- **Frontend-only**: UI/UX redesign, client-side validation — Architect sadece `### Frontend Task N:` oluşturur → Backend Dev scope evaluation ile skip eder.
- **Backend-only**: DB migration, business logic — Architect sadece `### Backend Task N:` oluşturur → Frontend Dev scope evaluation ile skip eder.

---

## Node Listesi (13 node)

| # | ID | Type | Model | Turns | Not |
|---|-----|------|-------|-------|-----|
| 1 | USER | passthrough | — | — | Entry point |
| 2 | Product Analyst | agent | sonnet | 45 | agile_dev.yaml'dan kopyala |
| 3 | Architect | agent | opus | 50 | Task format değişikliği: Backend/Frontend Task |
| 4 | Plan Approval | human | — | — | agile_dev.yaml'dan kopyala |
| 5 | Plan Revision Counter | loop_counter | — | max 2 | agile_dev.yaml'dan kopyala |
| 6 | Backend Developer | agent | opus | 50 | YENİ: .NET odaklı, `${BACKEND_DIR}/` scope |
| 7 | Frontend Developer | agent | opus | 50 | YENİ: Angular odaklı, `${FRONTEND_DIR}/` scope |
| 8 | Reviewer | agent | opus | 40 | Güncellendi: dual-project review |
| 9 | Review Counter | loop_counter | — | max 3 | agile_dev.yaml'dan kopyala |
| 10 | QA Engineer | agent | sonnet | 45 | Güncellendi: integrated testing |
| 11 | QA Counter | loop_counter | — | max 3 | agile_dev.yaml'dan kopyala |
| 12 | DevOps | agent | sonnet | 35 | Güncellendi: dual-project deployment |
| 13 | Technical Writer | agent | haiku | 25 | Güncellendi: dual-project docs |

---

## Edge Listesi (25 edge: 19 trigger + 6 context)

### Trigger Edges (19)

| # | From | To | Condition | Not |
|---|------|----|-----------|-----|
| 1 | USER | Product Analyst | true | |
| 2 | Product Analyst | Architect | true | |
| 3 | Architect | Plan Approval | none: [AUTO_APPROVE] | Karmaşık görevler |
| 4 | Architect | Backend Developer | any: [AUTO_APPROVE] | Basit görevler bypass |
| 5 | Plan Approval | Backend Developer | any: [approve, onay, tamam] | İnsan onayı |
| 6 | Plan Approval | Plan Revision Counter | none: [approve, onay, tamam] | Revizyon |
| 7 | Plan Revision Counter | Architect | none: [LOOP_EXIT] | Loop devam |
| 8 | Plan Revision Counter | Backend Developer | any: [LOOP_EXIT] | Loop bitti |
| 9 | Backend Developer | Frontend Developer | true, carry_data | Sıralı: backend → frontend |
| 10 | Frontend Developer | Reviewer | true, carry_data | Review'a gönder (clear_context YOK) |
| 11 | Reviewer | QA Engineer | any: [REVIEW_PASS], clear_context | Geçti |
| 12 | Reviewer | Review Counter | none: [REVIEW_PASS] | Kaldı |
| 13 | Review Counter | Frontend Developer | none: [LOOP_EXIT] | Retry |
| 14 | Review Counter | QA Engineer | any: [LOOP_EXIT], clear_context | Loop bitti |
| 15 | QA Engineer | DevOps | any: [QA_PASS] | Geçti |
| 16 | QA Engineer | QA Counter | none: [QA_PASS] | Kaldı |
| 17 | QA Counter | QA Engineer | none: [LOOP_EXIT] | Retry |
| 18 | QA Counter | DevOps | any: [LOOP_EXIT] | Loop bitti |
| 19 | DevOps | Technical Writer | true | |

### Context Edges (6, trigger: false)

| # | From | To | Not |
|---|------|----|-----|
| 20 | USER | Architect | keep_message — orijinal istek |
| 21 | USER | QA Engineer | keep_message — gereksinim referansı |
| 22 | USER | Technical Writer | keep_message — dokümantasyon referansı |
| 23 | Architect | Backend Developer | **dynamic map**: regex `### Backend Task \d+:`, max_parallel: 5, on_no_match: pass |
| 24 | Architect | Frontend Developer | keep_message, carry_data — tam plan (dynamic map YOK) |
| 25 | Backend Developer | Reviewer | keep_message, carry_data — Backend çıktısı review için |

---

## Prompt Değişiklikleri (agile_dev.yaml'dan farklar)

### Architect — Task Format

Mevcut `### Task N:` formatı yerine:

```
## TASK FORMAT

You MUST organize tasks using these EXACT section headers:

### Backend Task N: [Title] — Size: [S/M/L]
**What**: [Specific backend deliverable]
**Files**: [Paths relative to ${BACKEND_DIR}/]
**Dependencies**: [Other task dependencies]

### Frontend Task N: [Title] — Size: [S/M/L]
**What**: [Specific frontend deliverable]
**Files**: [Paths relative to ${FRONTEND_DIR}/]
**Dependencies**: [Other task dependencies, including backend APIs to consume]

SPECIAL CASES:
- Backend-only: Create only "### Backend Task N:" sections
- Frontend-only: Create only "### Frontend Task N:" sections
- Fullstack: Backend tasks FIRST, frontend tasks reference backend API contracts
```

### Backend Developer — Yeni Node

```
═══ WORKSPACE SCOPE ═══

You work EXCLUSIVELY in the ${BACKEND_DIR}/ subdirectory.
This is a .NET microservices project.
NEVER modify files outside ${BACKEND_DIR}/.

═══ SCOPE EVALUATION (do this FIRST) ═══

If you receive NO "### Backend Task" assignments, output:
"SCOPE: No backend tasks assigned. Passing through to Frontend Developer."
Then stop immediately without making any code changes.

═══ SCOPE BOUNDARY ═══

[agile_dev.yaml Developer'ın scope boundary kuralları]

═══ ROLE ═══

You are a Senior Backend Developer specializing in .NET/C# microservices.
You receive: Architect's backend task assignments.
Your output goes to → Frontend Developer (who will build the UI consuming your APIs).

Implementation order:
1. Database models/migrations (Entity Framework)
2. Business logic / domain services
3. API controllers + DTOs
4. Unit tests (xUnit/NUnit)

CRITICAL: Document your API endpoints clearly at the end of your output.
Frontend Developer needs this information to consume your APIs.
Format: "## API Summary\n- [METHOD] /api/path — description"
```

### Frontend Developer — Yeni Node

```
═══ WORKSPACE SCOPE ═══

You work primarily in the ${FRONTEND_DIR}/ subdirectory.
This is an Angular project.
If the Reviewer found backend issues, you MAY navigate to ${BACKEND_DIR}/
for MINIMAL targeted fixes only. Document any backend changes you make.

═══ SCOPE EVALUATION (do this FIRST) ═══

If you receive NO "### Frontend Task" assignments AND the Backend Developer
output contains no API changes that require frontend updates, output:
"SCOPE: No frontend tasks assigned. Skipping frontend development."
Then stop immediately without making any code changes.

═══ SCOPE BOUNDARY ═══

[agile_dev.yaml Developer'ın scope boundary kuralları]

═══ ROLE ═══

You are a Senior Frontend Developer specializing in Angular.
You receive: Backend Developer's output (API endpoints, data models) +
Architect's frontend task assignments.
Your output goes to → Reviewer (who will audit both backend and frontend code).

Implementation order:
1. Models/interfaces matching backend DTOs
2. Services (HttpClient calls to backend APIs)
3. Components (smart + dumb pattern)
4. Routing + guards
5. Unit tests (Jasmine/Karma) + e2e specs
```

### Reviewer — Güncellendi

```
═══ MULTI-PROJECT REVIEW ═══

You are reviewing a fullstack system with two projects:
1. ${BACKEND_DIR}/ — .NET microservices (Backend)
2. ${FRONTEND_DIR}/ — Angular application (Frontend)

Review checklist:
- Backend: API contracts, data access, security, error handling, SOLID
- Frontend: Component quality, state management, API integration, RxJS patterns
- Integration: Frontend correctly consumes backend APIs, CORS config,
  auth token handling, error propagation, DTO alignment
- Cross-cutting: Naming consistency, shared models match between projects
```

### QA Engineer — Güncellendi

```
═══ INTEGRATED TESTING ═══

Test the COMPLETE system across both projects:
1. ${BACKEND_DIR}/ — Run .NET tests (dotnet test), verify API endpoints
2. ${FRONTEND_DIR}/ — Run Angular tests (ng test), verify components
3. Integration — Frontend calls backend APIs correctly, data flows end-to-end
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

SCC #2: {Frontend Developer, Reviewer, Review Counter}
  Back-edge: Review Counter → Frontend Developer
  Exits: → QA Engineer (2 yol: REVIEW_PASS, LOOP_EXIT)

SCC #3: {QA Engineer, QA Counter}
  Back-edge: QA Counter → QA Engineer
  Exits: → DevOps (2 yol: QA_PASS, LOOP_EXIT)

Backend Developer: SCC dışı, Layer 3 (SCC1 ile SCC2 arasında)
```

---

## Uygulama Adımları

1. `agile_dev.yaml`'ı `fullstack_dev.yaml` olarak kopyala
2. `vars:` bölümüne `BACKEND_DIR` ve `FRONTEND_DIR` ekle
3. Mevcut Developer node'unu Backend Developer olarak yeniden adlandır + prompt güncelle
4. Yeni Frontend Developer node'u ekle
5. Architect prompt'unu `### Backend Task N:` / `### Frontend Task N:` formatına güncelle
6. Dynamic map regex'ini backend-specific pattern'e güncelle
7. Yeni context edge ekle: Architect → Frontend Developer (dynamic map yok, keep_message)
8. Yeni trigger edge ekle: Backend Developer → Frontend Developer (true, carry_data)
9. Review Counter → Developer edge'ini Review Counter → Frontend Developer olarak güncelle
10. Reviewer, QA, DevOps, TW prompt'larını dual-project için güncelle
11. Edge listesindeki tüm "Developer" referanslarını "Backend Developer" olarak güncelle (Plan Approval → BD, Plan Rev Counter → BD, etc.)
12. Backend Developer → Reviewer context edge ekle (keep_message, carry_data)

---

## Ek Hususlar ve Riskler

### 1. Dynamic Map Çıktı Aggregasyonu

Engine'in dynamic map davranışı:
- N paralel Backend Developer instance'ı → N ayrı çıktı mesajı üretir
- `carry_data: true` ile her bir çıktı **ayrı ayrı** Frontend Developer'a iletilir (birleştirilmez)
- Frontend Developer giriş kuyruğunda N ayrı mesaj alır

**Risk**: Frontend Developer N ayrı Backend çıktısı alırsa, her birini ayrı ayrı işlemesi gerekir. Eğer context_window=0 ise sadece son mesajı görür.

**Çözüm**: Frontend Developer'ın `context_window: -1` (unlimited) olması gerekir — böylece tüm N Backend çıktısını görebilir. Plan zaten bunu karşılıyor ama YAML'da explicit belirtmeli.

### 2. Keyword Matching SUBSTRING Bazlı

`keyword_manager.py` Python'un `in` operatörünü kullanıyor — exact match DEĞİL substring match:
```python
if keyword and keyword in haystack:  # substring!
```

**Risk örnekleri**:
- `any: [PASS]` → "PASSPORT validation" mesajında da eşleşir
- `any: [REVIEW_PASS]` → "REVIEW_PASSED_RATE: 85%" mesajında da eşleşir
- `none: [LOOP_EXIT]` → "LOOP_EXIT_CONDITION" mesajında da tetiklenir

**Çözüm**: Keyword'lere delimiter ekle. Mevcut engine'deki pattern: `LOOP_EXIT:` (iki nokta ile biter). Biz de:
- `REVIEW_PASS` → güvenli (yeterince spesifik)
- `QA_PASS` → güvenli
- `AUTO_APPROVE` → güvenli (yeterince spesifik)

### 3. SCOPE Skip Mesajları Downstream'e Yayılıyor

Backend Developer "SCOPE: No backend tasks assigned" çıktısı verdiğinde:
- Bu mesaj `carry_data: true` ile Frontend Developer'a iletilir
- Frontend Developer bu mesajı gerçek bir Backend çıktısı olarak yorumlayabilir

**Çözüm seçenekleri**:
- **A)** Frontend Developer prompt'una explicit "SCOPE mesajlarını yoksay" talimatı ekle (mevcut planda var ✓)
- **B)** Backend Developer → Frontend Developer edge'ine keyword condition ekle: `none: [SCOPE:]` — Backend skip mesajını Frontend'e iletme
- **C)** Backend Developer skip mesajında Frontend Dev'i trigger etmek yerine doğrudan Reviewer'a yönlendir

**Önerilen**: Seçenek A yeterli. Frontend Developer zaten prompt'unda "If you receive NO frontend task assignments AND no API changes" kontrolü yapıyor. SCOPE mesajı API değişikliği içermediği için Frontend de skip eder.

### 4. Dynamic Map + on_no_match: pass Davranışı

Architect sadece Frontend Task oluşturduğunda (Backend Task yok):
1. Dynamic map regex `### Backend Task \d+:` eşleşmez
2. `on_no_match: pass` → tüm mesaj tek birim olarak Backend Developer'a geçer
3. Backend Developer tüm Architect çıktısını alır ama "### Backend Task" bulamaz
4. Backend Developer SCOPE evaluation ile "No backend tasks" der ve skip eder

**Risk**: Gereksiz bir Backend Developer instance'ı başlatılmış olur (kaynak israfı ama mantık doğru).

**Kabul**: Bu beklenen davranış. Backend Dev SCOPE evaluation hızlıca skip eder (~1 turn). Engine seviyesinde pre-filter eklemek karmaşıklık getirir.

### 5. Review Counter → Frontend Developer (Backend Bug Riski)

Review fail olduğunda sadece Frontend Developer yeniden çalışır. Eğer bug Backend'de ise:
- Frontend Dev'in prompt'u "MAY navigate to ${BACKEND_DIR}/ for MINIMAL targeted fixes" diyor
- Ama karmaşık backend bug'ları için Frontend Dev yetersiz kalabilir

**Risk**: Backend'deki ciddi bug'lar düzeltilemez, review döngüsü max_count'a kadar tekrarlar ve LOOP_EXIT ile çıkar.

**Çözüm**: Reviewer prompt'una explicit talimat ekle:
```
If the bug is EXCLUSIVELY in backend code and requires deep .NET expertise,
mention "BACKEND_ONLY_FIX_NEEDED" in your review. Frontend Developer will
forward this to the appropriate handler.
```
Bu V2 için düşünülebilir — şimdilik Frontend Dev'in minimal backend fix yapabilmesi yeterli.

### 6. Backend Developer'a Oracle MCP Eklenmeli

Kullanıcının Oracle DB'si var ve `mapeg-oracle-db` MCP server'ı aktif. Backend Developer'ın DB schema'sını okuyabilmesi ve sorgu test edebilmesi için MCP tooling eklemeli:

```yaml
tooling:
  - type: mcp_local
    config:
      command: "uvx"
      args: ["mcp-server-fetch"]
  # Oracle MCP — Backend Developer'ın DB erişimi için
  # NOT: MCP config'i kullanıcının lokal .env'sinden gelecek
```

**Dikkat**: Oracle MCP server config'i şu an IDE seviyesinde tanımlı. YAML'dan CLI provider'a forward edilmesi için `mcp_local` olarak tanımlanmalı. Bu, kullanıcının Oracle MCP binary'sinin path'ini bilmemizi gerektirir.

### 7. Frontend Developer → Reviewer Edge'de clear_context

Plan'daki edge #10:
```
Frontend Developer → Reviewer (true, clear_context)
```

`clear_context: true` ile Reviewer'ın önceki context'i temizlenir. Ama Reviewer'ın Backend Developer çıktısını da görmesi gerekiyor (dual-project review için).

**Çözüm**: `clear_context` KULLANMA. Bunun yerine:
- Backend Developer → Reviewer: `carry_data: true` (context edge veya trigger)
- Frontend Developer → Reviewer: `carry_data: true` (trigger edge, clear_context YOK)
- Architect → Reviewer: `keep_message: true, trigger: false` (plan referansı)

Bu şekilde Reviewer tüm context'i görebilir. **Plan güncellenmeli.**

### 8. Backend Developer'dan Reviewer'a Doğrudan Edge Gerekli

Mevcut plan'da Backend Developer → Frontend Developer → Reviewer akışı var. Ama Reviewer'ın Backend çıktısını da görmesi gerekiyor.

**Çözüm**: Context edge ekle:
```yaml
- from: Backend Developer
  to: Reviewer
  trigger: false
  keep_message: true
  carry_data: true
```

Bu, Backend Developer çıktısını Reviewer'ın context'ine ekler (trigger etmeden). Reviewer hem Backend hem Frontend çıktısını görerek dual-project review yapabilir.

**Edge sayısı güncellenmeli**: 24 → 25 (1 ek context edge)

### 9. Paralel Backend Instance'ları Arasında Workspace Çakışması

N paralel Backend Developer instance'ı **aynı** `${BACKEND_DIR}/` dizininde çalışır. İki instance aynı dosyayı aynı anda değiştirirse çakışma olur.

**Risk**: İki microservice aynı shared model/config dosyasını değiştirmeye çalışabilir.

**Azaltma**:
- Architect'in task plan'ında her task'ın "Files" bölümünü net belirtmesi gerekiyor
- Backend Developer prompt'una ekle: "If you detect file conflicts with other parallel tasks, document the conflict but do NOT modify shared files."
- Pratikte .NET microservices'te servisler genelde farklı dizinlerde — risk düşük

### 10. Her İki Dev "SCOPE Skip" Yapması Senaryosu

Hem Backend Dev hem Frontend Dev skip ederse:
- Reviewer iki SCOPE mesajı alır, review edecek kod yok
- QA, DevOps, TW boşuna çalışır

**Risk**: Düşük — Architect en az bir task oluşturmalı. Ama SCOPE EVALUATION'ı yanlış yorumlama mümkün.

**Çözüm V2**: Reviewer'a SCOPE detection ekle:
```
If ALL developer outputs contain "SCOPE: No ... tasks assigned",
output: "REVIEW_PASS — No code changes to review."
```
Bu, boş döngüyü hızla geçirir.

### 11. Kaynak Maliyeti ve Performans

- N paralel Backend Dev (opus, 50 turns) = N × opus maliyeti
- max_parallel: 5 → tek makinede 5 eşzamanlı Claude Code process
- Her process ~500MB RAM + CPU → toplam ~2.5GB ek yük

**Öneri**: Backend Developer'ı `sonnet` ile çalıştırmayı düşünebiliriz. Opus daha yüksek kalite verir ama maliyet 5x'tir. İlk versiyonda sonnet ile başlayıp, kalite yetersizse opus'a geçilebilir.

### 12. Dynamic Map Config Keşfi: Doğrulandı ✓

`_get_dynamic_config_for_node()` (graph.py:456) incelendi:
1. `node.predecessors` üzerinden dolaşır (graph build time'da eklenir, sadece trigger:true)
2. Her predecessor'ın **TÜM** outgoing edge'lerini tarar (trigger:true + trigger:false)
3. Context edge'deki dynamic map config'i de bulur

Architect → Backend Developer:
- Edge #4 (AUTO_APPROVE, trigger:true) → Architect'i predecessor yapar
- Edge #23 (context, trigger:false, dynamic map) → dynamic config keşfedilir ✓

Bu yapısal (graph build time) — runtime'da edge fire olup olmadığına bağlı değil.

---

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
"
```
