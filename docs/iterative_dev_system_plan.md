# ChatDev 2.0 — İteratif Geliştirme Sistemi

## Context

Workflow sistemi şu an tek seferlik çalışma modunda: prompt ver, ekip çalışsın, çıktı alsın. Kullanıcının 3 mimari sorusu ve `dev-workflow.html` tasarımı, sistemi çok daha güçlü bir iteratif geliştirme platformuna dönüştürme fırsatı sunuyor:

1. **Mevcut bir proje üzerinde çalıştırma** — WareHouse yerine kullanıcının kendi proje dizini
2. **Devam etme kararı veren bot** — Otomatik kalite değerlendirme ve yönlendirme
3. **Spec-driven development** — Task listesi → her task için iteratif döngü

**Önemli Keşif:** Mevcut YAML graph sistemi zaten bu yeteneklerin çoğunu destekliyor:
- `human` node (human-in-the-loop)
- `loop_counter` node (iterasyon kontrolü)
- Koşullu kenarlar (keyword, function, regex)
- Subgraph kompozisyonu
- Dinamik map/tree paralel çalışma
- Reflexion pattern (iteratif iyileştirme)

Eksik parçalar: workspace override, continue/resume, ve bunları birleştiren YAML workflow.

---

## Uygulama Fazları

### Faz 1: Continue Feature (Hemen uygulanabilir)
> Önceki plan aynen geçerli — `docs/workflow_continue_plan.md`

**Özet:** "Continue" butonu ile aynı workspace'de, Claude Code'un önceki session'ını resume ederek devam etme.

**6 dosya değişikliği:**
- `claude_code_provider.py` — save/load sessions to workspace
- `server/models.py` — `previous_session_id` field
- `server/routes/execute.py` — previous_session_id iletimi
- `workflow_run_service.py` — workspace reuse logic
- `runtime/sdk.py` — save sessions before cleanup
- `LaunchView.vue` — Continue/Relaunch butonları

---

### Faz 2: Harici Workspace Desteği (Soru 1)
> "Mevcut bir proje üzerinde bunu nasıl kullandırırız?"

**Sorun:** Workspace her zaman `WareHouse/session_{id}/code_workspace/` içinde oluşturuluyor. Mevcut bir proje üzerinde çalıştıramıyoruz.

**Çözüm:** `workspace_path` parametresi ile kullanıcının kendi dizinini kullanma.

**Değişiklikler:**

| Dosya | Değişiklik |
|-------|-----------|
| `server/models.py` | `workspace_path: Optional[str] = None` ekle |
| `server/routes/execute.py` | `workspace_path` ilet |
| `workflow_run_service.py` | `workspace_path` varsa `output_root` olarak kullan, `code_workspace` alt dizin yaratma — direkt proje dizinini kullan |
| `workflow/graph_context.py` | `workspace_path` varsa `directory = workspace_path` yap |
| `workflow/runtime/runtime_builder.py` | `workspace_path` varsa `code_workspace = workspace_path` (alt dizin değil, direkt path) |
| `LaunchView.vue` | Folder picker veya text input ekle — "Workspace Path (opsiyonel)" |

**Güvenlik:** Path traversal önleme — workspace_path validate et:
- Mutlaka absolute path olmalı
- `/tmp`, `/etc` gibi sistem dizinlerine izin verme
- `.git` varsa uyar ama engelleme

**Akış:**
```
Kullanıcı: workspace_path = "/Users/mehmet/projects/my-api"
Backend:   code_workspace = "/Users/mehmet/projects/my-api" (direkt)
           output dizini = WareHouse/session_{id}/ (log, summary için)
Claude:    cwd = "/Users/mehmet/projects/my-api"
           Mevcut dosyaları görür, üzerine çalışır
```

---

### Faz 3: İteratif Dev Workflow YAML (Soru 3 + dev-workflow.html)
> "SpecKit/Kiro mantığı: task'ların her biri flow akışı olabilir mi?"

**Sorun:** Tek prompt → tek seferde çalış modeli. Karmaşık projeler için yetersiz.

**Çözüm:** 10 aşamalı iteratif workflow'u YAML olarak tanımla. Mevcut node tipleri bunu destekliyor.

**Yeni YAML:** `yaml_instance/iterative_dev_v1.yaml`

```
Akış (dev-workflow.html'den):

01. Gereksinim Analizi    [agent: Product Manager + Architect]
02. Task Planlama          [agent: Task Planner] → JSON task listesi üret
03. Plan Onayı             [human: Kullanıcı onaylar veya düzeltir]
    ↓ (onay → devam, red → 02'ye dön)
04. Geliştirme             [agent: Programmer — Claude Code provider]
05. Kod İnceleme           [agent: Reviewer]
    ↓ (başarılı → 06, başarısız → 04'e dön)
06. Test                   [agent: Tester — execute_code tool]
    ↓ (PASS → sonraki task, FAIL → 07)
07. Bug Fix                [agent: Debugger]
    ↓ (fix sonrası → 06'ya dön, max 3 deneme)
--- Task döngüsü sonu, sonraki task varsa 04'e dön ---
08. Entegrasyon Testi      [agent: QA Engineer]
    ↓ (başarılı → 09, başarısız → 07)
09. Final İnceleme         [human: Kullanıcı onaylar]
    ↓ (onay → 10, ekleme iste → 02'ye dön)
10. Teslimat               [agent: Deployer + Doc Writer]
```

**YAML Tasarımı:**
- Fazlar 04-07 bir **subgraph** içinde: `subgraphs/task_iteration.yaml`
- Bu subgraph, Faz 02'nin ürettiği her task için **dynamic map** ile çalıştırılır
- `loop_counter` nodları: Review retry (max 3), Test retry (max 3)
- `human` nodları: Faz 03 (plan onayı), Faz 09 (final review)
- Koşullu kenarlar: `code_pass`/`code_fail` fonksiyonları, keyword tespiti

**Önemli:** Bu YAML'i yazmak için yeni kod yazmaya GEREK YOK — mevcut node tipleri ve edge mekanizmaları yeterli. Sadece yeni YAML dosyaları oluşturulacak.

---

### Faz 4: Kalite Kapısı / Evaluator Pattern (Soru 2)
> "Continue edip etmeyeceğine karar veren bir bot mu olsa?"

**Sorun:** Şu an döngülerde sadece `loop_counter` (sabit iterasyon sayısı) veya basit keyword koşulları var. Gerçek bir "kalite değerlendirmesi" yok.

**Çözüm:** "Evaluator" agent pattern'i — LLM tabanlı kalite kapısı.

**Yaklaşım A — Mevcut Yapıda (YAML-only, kod değişikliği yok):**
Evaluator'ü normal bir `agent` node olarak tanımla:
```yaml
- id: Quality Gate
  type: agent
  config:
    provider: openai
    name: gpt-4o
    role: |
      Sen bir kalite değerlendirme uzmanısısın.
      Önceki aşamanın çıktısını incele ve PASS veya FAIL kararını ver.
      PASS ise: "QUALITY_PASS" yaz
      FAIL ise: "QUALITY_FAIL: [neden]" yaz
```
Kenarlar keyword koşuluyla yönlendirilir:
```yaml
edges:
  - from: Quality Gate
    to: Next Phase
    condition: { type: keyword, config: { any: ["QUALITY_PASS"] } }
  - from: Quality Gate
    to: Fix Phase
    condition: { type: keyword, config: { any: ["QUALITY_FAIL"] } }
```

**Bu yaklaşım SIFIR kod değişikliği gerektirir** — tamamen YAML tabanlı.

**Yaklaşım B — Opsiyonel Gelişmiş (Faz 4+):**
Yeni bir `evaluator` node tipi ekle:
- Puanlama sistemi (0-100)
- Eşik değeri (threshold) config'den
- Otomatik retry yönlendirmesi
- Değerlendirme log'u

Bu opsiyonel — Yaklaşım A yeterli olabilir.

---

## Öncelik ve Sıralama

```
Faz 1: Continue Feature        → Hemen uygulanabilir (6 dosya)
Faz 2: Harici Workspace         → Continue'dan sonra (6 dosya)
Faz 3: İteratif Dev YAML        → Sadece YAML dosyaları (kod değişikliği yok)
Faz 4: Evaluator Pattern        → Yaklaşım A: YAML-only, Yaklaşım B: yeni node tipi
```

**Tavsiye:** Faz 1 + Faz 3 paralel başlanabilir çünkü Faz 3 sadece YAML.

---

## Mimari Özet

```
                    ┌─────────────────────────────────────┐
                    │         dev-workflow.html            │
                    │    (10-aşamalı iteratif model)       │
                    └──────────────┬──────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            │                      │                      │
     ┌──────▼──────┐    ┌─────────▼────────┐   ┌────────▼────────┐
     │   Faz 1     │    │     Faz 2        │   │    Faz 3        │
     │  Continue   │    │ Harici Workspace │   │ İteratif YAML   │
     │  Feature    │    │    Desteği       │   │   Workflow      │
     └──────┬──────┘    └─────────┬────────┘   └────────┬────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │     Faz 4       │
                          │   Evaluator     │
                          │   (Kalite Bot)  │
                          └─────────────────┘
```

## Mevcut YAML Yetenekleri (Referans)

| Yetenek | Node/Edge Tipi | Örnek Dosya |
|---------|---------------|-------------|
| LLM Agent | `type: agent` | Tüm workflow'lar |
| Human-in-the-Loop | `type: human` | `demo_human.yaml` |
| Döngü Kontrolü | `type: loop_counter` | `demo_loop_counter.yaml` |
| Alt Workflow | `type: subgraph` | `demo_sub_graph.yaml`, `react.yaml` |
| Koşullu Dallanma | `condition: keyword/function` | `ChatDev_v1.yaml` |
| Paralel Çalışma | `dynamic: map/tree` | `demo_dynamic.yaml` |
| Bellek Sistemi | `memory: blackboard/simple` | `reflexion_product.yaml` |
| Kod Çalıştırma | `type: python` | `demo_python.yaml` |
| Çoğunluk Oylaması | `is_majority_voting: true` | `demo_majority_voting.yaml` |
| Kenar Dönüşümü | `process: regex_extract` | `demo_edge_transform.yaml` |
