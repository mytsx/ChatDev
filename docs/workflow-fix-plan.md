# Workflow Akış Sorunları: Kök Neden Analizi ve Düzeltme Planı (v2)

> **Revizyon notu**: Gerçek YAML ve Python kodu satır satır doğrulandı.
> Orijinal plandaki yanlışlıklar düzeltildi, 3 yeni keşif eklendi.

## Context

Enterprise workflow (`enterprise_dev.yaml`) gerçek bir görevde (Flutter gelişmiş filtreleme) çalıştırıldı. Phase 2 agentları (Solution Architect, Security Reviewer, DBA) `max-turns` limitine takıldı — tüm turlarını araştırmaya harcadı, deliverable yazmaya turn kalmadı. Tech Lead bu eksik çıktıları alınca "doküman bulunamadı" diyerek akışı durdurdu.

## Kök Nedenler (doğrulanmış)

| # | Sorun | Etki | Konum |
|---|---|---|---|
| **1** | `--max-turns 15/20` tüm agentlar için hardcoded | SA (40 tool call), SR (25), DBA (21) araştırmada bitti, deliverable üretmedi | `claude_code_provider.py:191-193` |
| **2** | DBA→Tech Lead edge'de `keep_message: true` eksik | Tech Lead `context_window: 0` — DBA çıktısı context'e girmiyor | `enterprise_dev.yaml:2352-2356` |
| **3** | Security Reviewer→Tech Lead `trigger: false` | DBA önce biterse Tech Lead SR çıktısı olmadan başlar (race condition) | `enterprise_dev.yaml:2344-2349` |
| **4** | ⚠️ **YENİ** — Plan Revision Counter→Tech Lead'de `keep_message: true` eksik | Revision loop'ta Tech Lead, ret gerekçesini context'te görmüyor | `enterprise_dev.yaml:2403-2413` |

## Tech Lead'e Gelen TÜM Edge'ler (doğrulanmış harita)

| # | From | trigger | keep_message | Durum |
|---|---|---|---|---|
| 1 | USER | false | **true** ✓ | OK |
| 2 | Solution Architect | false | **true** ✓ | OK |
| 3 | Business Analyst | false | **true** ✓ | OK |
| 4 | Security Reviewer | false | **true** ✓ | Race condition riski (Fix 3) |
| 5 | DBA | **true** | **EKSİK** ✗ | Fix 2 gerekli |
| 6 | Plan Revision Counter | **true** | **EKSİK** ✗ | Fix 4 gerekli (yeni keşif!) |

> **Not**: Tech Lead'in `context_window: 0` — önceki invocation'lardan hiçbir şey tutmuyor.
> `keep_message: true` olan edge'ler mevcut invocation'ın context'ine girer.
> `keep_message` olmayan edge'lerin mesajları context'e girmez.

---

## Fix 1: YAML'da node başına `max_turns` desteği [KRİTİK]

### 1a. `AgentConfig`'e `max_turns` field ekle

**Dosya: `entity/configs/node/agent.py`**

`AgentConfig` dataclass'a (satır 322, `skip_memory`'den sonra) ekle:
```python
max_turns: int | None = None  # Max agentic turns for Claude Code CLI
```

`from_dict()` içinde (satır 400-402 civarı, `skip_memory` parse'ından sonra) ekle:
```python
# Max turns configuration
max_turns_raw = mapping.get("max_turns")
max_turns = None
if max_turns_raw is not None:
    max_turns = _coerce_positive_int(max_turns_raw, field_path=extend_path(path, "max_turns"), minimum=1)
```

`return cls(...)` bloğuna `max_turns=max_turns,` ekle.

`FIELD_SPECS` dict'ine (`skip_memory`'den sonra) ekle:
```python
"max_turns": ConfigFieldSpec(
    name="max_turns",
    display_name="Max Turns",
    type_hint="int",
    required=False,
    description="Maximum agentic turns for Claude Code CLI (overrides provider default)",
    advance=True,
),
```

### 1b. Provider'da config'den oku

**Dosya: `runtime/node/agent/providers/claude_code_provider.py`**

**Satır 188-193** (ana çağrı):
```python
# Eski (hardcoded):
if existing_session:
    cmd.extend(["--max-turns", "20"])
else:
    cmd.extend(["--max-turns", "15"])

# Yeni (configurable, daha yüksek default'lar):
configured_turns = getattr(self.config, "max_turns", None)
if existing_session:
    turns = configured_turns or 40
else:
    turns = configured_turns or 30
cmd.extend(["--max-turns", str(turns)])
```

**Satır 243** (retry bloğu):
```python
# Eski:
cmd_retry.extend(["--max-turns", "15"])

# Yeni:
configured_turns = getattr(self.config, "max_turns", None)
cmd_retry.extend(["--max-turns", str(configured_turns or 30)])
```

> **Neden `self.config`?** Provider'ın `__init__`'i `AgentConfig`'i `self.config` (parent'tan `self._agent_config`) olarak tutuyor.
> Ama dikkat: base class'taki attribute ismi `config` mı `_agent_config` mı? Doğrulanmalı.
> Güvenli versiyon: `getattr(self.config, "max_turns", None)` — attribute yoksa `None` döner.

### 1c. YAML'da node'lara max_turns ata

**Dosya: `yaml_instance/enterprise_dev.yaml`** — 20 agent node var (21 değil!)

Her agent node'un `config:` bloğuna `max_turns:` ekle:

| Tier | Node'lar | max_turns | Gerekçe |
|---|---|---|---|
| **Araştırma** | Solution Architect, Security Reviewer, DBA | **50** | SA: 40+ tool call gözlemlendi, deliverable yazma dahil |
| **Planlama** | Tech Lead | **45** | Çoklu girdi analizi + detaylı task breakdown |
| **Kod yazma** | Backend Developer, Frontend Developer, Integration Engineer | **50** | Yoğun kod üretimi + test çalıştırma |
| **Review** | Code Reviewer | **40** | Çoklu dosya analizi + detaylı rapor |
| **Analiz (Phase 1)** | Business Analyst, UX Designer | **40** | Gereksinim analizi + doküman üretimi |
| **Test/QA** | QA Engineer, SDET | **40** | Test yazma + çalıştırma + analiz |
| **Security** | Security Auditor | **40** | Güvenlik taraması + rapor |
| **Ops** | DevOps Engineer, SRE | **35** | CI/CD + monitoring konfigürasyonu |
| **Bug fix** | Code Review/QA/Security/Final Bug Fixer | **30** | Hedefli düzeltme (daha dar scope) |
| **Özet** | Technical Writer, Delivery Manager | **25** | Doküman derleme + özet rapor |

**Provider default'lar** (YAML'da `max_turns` belirtilmemişse):
- Yeni session: **30** (eskisi: 15)
- Mevcut session (resume): **40** (eskisi: 20)

---

## Fix 2: DBA→Tech Lead edge'e `keep_message` ekle [KRİTİK]

**Dosya: `enterprise_dev.yaml` satır 2352-2356**

```yaml
# Eski
- from: DBA
  to: Tech Lead
  trigger: true
  condition: 'true'
  carry_data: true

# Yeni
- from: DBA
  to: Tech Lead
  trigger: true
  condition: 'true'
  carry_data: true
  keep_message: true   # ← EKSİKTİ — DBA çıktısı Tech Lead context'ine girmiyordu
```

---

## Fix 3: Security Reviewer→Tech Lead'i `trigger: true` yap [KRİTİK]

**Dosya: `enterprise_dev.yaml` satır 2344-2349**

**Mevcut durum**: SA→SR ve SA→DBA paralel tetikleniyor. DBA→Tech Lead `trigger:true`, SR→Tech Lead `trigger:false`. DBA önce biterse Tech Lead SR'ı beklemeden başlıyor.

```yaml
# Eski (race condition)
- from: Security Reviewer
  to: Tech Lead
  trigger: false        # ← DBA önce biterse SR çıktısı olmadan başlar
  condition: 'true'
  carry_data: true
  keep_message: true

# Yeni (AND-join: DBA + SR tamamlanınca tetiklenir)
- from: Security Reviewer
  to: Tech Lead
  trigger: true          # ← Artık Tech Lead hem DBA hem SR'ı bekler
  condition: 'true'
  carry_data: true
  keep_message: true
```

**Topoloji etkisi**: Tech Lead artık 2 trigger edge'e sahip → AND-join davranışı → her iki source tamamlanmadan başlamaz. Bu doğru davranış.

> **Dikkat**: Plan Revision Counter→Tech Lead de trigger:true. Ama bu farklı bir akış yolu (revision loop) — AND-join'e dahil edilmemeli. Çalışma zamanında Plan Revision Counter yalnızca approval reject edildiğinde tetiklenir, normal akışta DBA+SR→Tech Lead AND-join'i çalışır.

---

## Fix 4: Plan Revision Counter→Tech Lead'e `keep_message` ekle [YENİ — KRİTİK]

**Dosya: `enterprise_dev.yaml` satır 2403-2413**

Bu keşif orijinal planda yoktu. Revision loop'ta kullanıcı planı reddedip revizyon istediğinde, Counter'ın çıktısı (ret gerekçesini içerir) Tech Lead'in context'ine girmiyordu.

```yaml
# Eski
- from: Plan Revision Counter
  to: Tech Lead
  trigger: true
  condition:
    type: keyword
    config:
      any: []
      none: [LOOP_EXIT]
      regex: []
      case_sensitive: true
  carry_data: true

# Yeni
- from: Plan Revision Counter
  to: Tech Lead
  trigger: true
  condition:
    type: keyword
    config:
      any: []
      none: [LOOP_EXIT]
      regex: []
      case_sensitive: true
  carry_data: true
  keep_message: true   # ← Ret gerekçesi Tech Lead'in context'ine girsin
```

---

## Düşünülmesi Gereken Ek Konular

### 5. `carry_data` vs `keep_message` — Sistematik Tutarsızlık

**Bulgu**: Workflow'da **46 trigger:true edge** `carry_data: true` ama `keep_message` yok. Bu tasarım gereği mi, yoksa yaygın bir bug mu?

**Analiz**:
- `carry_data: true` → mesaj edge üzerinden hedefe taşınır
- `keep_message: true` → mesaj hedef node'un context buffer'ında tutulur
- `context_window: 0` node'larda `keep_message` olmadan mesaj context'e girmez
- `context_window: -1` node'larda (Code Reviewer, QA, Bug Fixers) tüm history tutulur → `keep_message` daha az kritik

**Kontrol edilmesi gereken edge'ler** (trigger:true, hedef context_window:0, keep_message yok):
- BA → SA (trigger:true via UX path?)
- SA → SR (trigger:true, no keep_message) → SR context_window:0
- SA → DBA (trigger:true, no keep_message) → DBA context_window:0
- Plan Approval → Backend/Frontend Dev (trigger:true, no keep_message)
- Ve daha fazlası...

**Soru**: Bu edge'lerin hepsine keep_message eklenmeli mi, yoksa trigger:true edge'lerde carry_data zaten yeterli mi? Davranışı test etmeliyiz.

### 6. Prompt'larda "Turn Budget" Farkındalığı

Agentlar max_turns limitinden habersiz. SA 40 turn boyunca araştırma yapıp deliverable yazmaya başlayamıyor.

**Potansiyel çözümler**:
1. **Statik prompt yönergesi**: System prompt'a "Toplam turn bütçen sınırlı. İlk %60'ını araştırmaya, son %40'ını deliverable yazmaya ayır." gibi genel kural
2. **Dinamik enjeksiyon**: Provider'da kalan turn sayısını prompt'a ekle (Claude Code CLI bunu expose etmiyor — uygulanması zor)
3. **İki aşamalı çalıştırma**: Aynı agent'ı iki kez çağır — ilk sefer araştırma, ikinci sefer deliverable yazma (persistent session ile)

**Öneri**: Seçenek 1 en kolay, hemen uygulanabilir. System prompt'lara eklenmeli.

### 7. Turn Tükendiğinde Graceful Degradation

Şu an agent max_turns'e ulaşınca yarım/eksik çıktı dönüyor.

**Sorular**:
- Claude Code CLI `--max-turns` aşıldığında exit code ne? Normal mi, hata mı?
- `result` event'inde "max turns reached" gibi bir sinyal var mı?
- Provider bu durumu yakalayıp "tamamlanmamış çıktı" olarak flag'leyebilir mi?

**Potansiyel**: Provider'da response'u kontrol et — kısa/eksik ise `[INCOMPLETE: max_turns reached]` prefix ekle → downstream node'lar buna göre davranabilir.

### 8. Retry/Bug-Fix Loop'larında Turn Çarpanı

Bug fixer node'lar retry loop'ta birden fazla kez çalışıyor:
- Code Review Bug Fixer: max 3 iterasyon × 30 turn = 90 turn
- QA Bug Fixer: max 3 iterasyon × 30 turn = 90 turn
- Security Bug Fixer: max 2 iterasyon × 30 turn = 60 turn
- Final Bug Fixer: max 2 iterasyon × 30 turn = 60 turn

**Toplam potansiyel**: 300 turn sadece bug fix loop'larında.

**Soru**: Persistent session kullanılıyorsa her iterasyon resume üzerinden gidiyor — context korunuyor, sadece yeni talimat ekleniyor. Bu durumda max_turns her seferinde yeniden mi başlıyor, yoksa toplam mı?

### 9. Paralel Node'ların Toplam Maliyet Etkisi

Phase 2'de SA + SR + DBA paralel → 50 × 3 = 150 eşzamanlı turn
Phase 4'te Backend + Frontend paralel → 50 × 2 = 100 eşzamanlı turn

Max subscription rate limit'leri bunu kaldırıyor mu? Claude Code'un eşzamanlı session limiti var mı?

### 10. `iterative_dev_v1.yaml`'a da `max_turns` Eklenmeli mi?

Enterprise workflow'da çıkan sorunlar iterative_dev_v1'de de geçerli. 12 node, 23 edge — daha basit ama aynı provider hardcoded limit'lerini kullanıyor.

**Öneri**: Provider default'ları yükseltmek (30/40) her iki workflow'u da iyileştirir. YAML-level override ihtiyaç halinde eklenebilir.

### 11. Tech Lead'in Eksik Girdiyi Handle Etmesi

Tech Lead'in prompt'u şu an eksik girdiyle başa çıkamıyor — "doküman bulunamadı" diyor.

**Çözüm önerileri**:
1. Tech Lead prompt'una fallback yönergesi ekle: "Eğer SA/SR/DBA çıktılarından biri eksikse, mevcut bilgilerle devam et ve eksik noktaları [TBD] olarak işaretle"
2. Edge condition'larda timeout/failure handling ekle
3. Veya yukarıdaki Fix 2-4 ile bu sorun zaten çözülüyor (mesajlar artık context'e girecek)

### 12. Monitoring — max_turns Tüketim Alerting

**Potansiyel iyileştirme** (şu an için low priority):
- Provider'da `raw_response`'a "turns_used" / "max_turns_reached" bilgisi ekle
- WebSocket üzerinden UI'a `NODE_MAX_TURNS_REACHED` event'i emit et
- Session log'larına turn kullanım istatistikleri yaz

---

## Uygulama Sırası

| Sıra | Fix | Süre | Risk |
|---|---|---|---|
| 1 | **Fix 1a** — AgentConfig'e `max_turns` field | Düşük | Yok (backward compatible, None default) |
| 2 | **Fix 1b** — Provider'da config'den oku + default'ları yükselt | Düşük | Yok (sadece CLI flag değişiyor) |
| 3 | **Fix 2** — DBA→Tech Lead `keep_message: true` | Trivial | Yok |
| 4 | **Fix 3** — SR→Tech Lead `trigger: true` | Trivial | Topoloji değişikliği — test gerekli |
| 5 | **Fix 4** — Plan Rev Counter→Tech Lead `keep_message: true` | Trivial | Yok |
| 6 | **Fix 1c** — YAML'da 20 agent'a max_turns ata | Orta | Yok (yeni field, default'lar çalışır) |
| 7 | **Testler** | — | Mevcut testlerin geçtiğini doğrula |
| 8 | **Ek konular** (5-12) | — | Tartışılarak prioritize edilecek |

---

## Doğrulama Adımları

```bash
# 1. YAML parse — node/edge sayısı doğru mu?
uv run python -c "
import yaml
d = yaml.safe_load(open('yaml_instance/enterprise_dev.yaml'))
g = d['graph']
nodes = g['nodes']
edges = g['edges']
agent_nodes = [n for n in nodes if n.get('type') == 'agent']
print(f'{len(nodes)} nodes, {len(edges)} edges, {len(agent_nodes)} agents')
for n in agent_nodes:
    mt = n.get('config', {}).get('max_turns', 'NOT SET')
    print(f'  {n[\"id\"]}: max_turns={mt}')
"

# 2. AgentConfig parse — max_turns field çalışıyor mu?
uv run python -c "
from entity.configs.node.agent import AgentConfig
c = AgentConfig.from_dict({'provider':'claude-code','name':'sonnet','max_turns':50}, path='test')
print(f'max_turns={c.max_turns}')  # → 50
c2 = AgentConfig.from_dict({'provider':'claude-code','name':'sonnet'}, path='test')
print(f'max_turns={c2.max_turns}')  # → None
"

# 3. Mevcut testler
uv run pytest tests/ -x -q

# 4. Edge doğrulama — Tech Lead'e gelen tüm edge'lerde keep_message var mı?
uv run python -c "
import yaml
d = yaml.safe_load(open('yaml_instance/enterprise_dev.yaml'))
edges = d['graph']['edges']
tl_edges = [e for e in edges if e.get('to') == 'Tech Lead']
for e in tl_edges:
    km = e.get('keep_message', 'NOT SET')
    tr = e.get('trigger', 'NOT SET')
    print(f'{e[\"from\"]} → Tech Lead | trigger={tr} | keep_message={km}')
"

# 5. Topoloji — SR→Tech Lead trigger:true ile SCC yapısı bozulmuyor mu?
# (SR ve DBA ayrı SCC'lerde kalmalı, mega-SCC oluşmamalı)
```

---

## Kritik Dosyalar

| Dosya | Değişiklik Özeti |
|---|---|
| `entity/configs/node/agent.py` | `max_turns` field + `from_dict` parse + `FIELD_SPECS` |
| `runtime/node/agent/providers/claude_code_provider.py` | Config'den `max_turns` oku, default 30/40, retry bloğu |
| `yaml_instance/enterprise_dev.yaml` | 3 edge fix + 20 agent node'a `max_turns` değeri |

---

## Orijinal Plandaki Düzeltmeler

| Orijinal plan | Gerçek durum |
|---|---|
| "21 agent node" | **20 agent node** (doğrulandı) |
| USER→Tech Lead `keep_message` eksik | **Yanlış** — USER→Tech Lead zaten `keep_message: true` (satır 2217) |
| SA→Tech Lead `keep_message` eksik olabilir | **Yanlış** — SA→Tech Lead zaten `keep_message: true` (satır 2243) |
| Provider'da `self._agent_config` kullan | **Doğrulanmalı** — base class attribute ismi `self.config` (`super().__init__(config)`) |
| Provider default 20/25 önerilmişti | **Daha yüksek gerekli** — 30/40 daha uygun (kullanıcı talebi + gözlem) |
| Plan Revision Counter→Tech Lead sorunu yoktu | **YENİ BUG** — `keep_message: true` eksik (satır 2413) |
