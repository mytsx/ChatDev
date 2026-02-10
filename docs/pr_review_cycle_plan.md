# PR Review Cycle — Otomatik Code Review Döngüsü

## Context

Kullanıcı bir PR oluşturduğunda GitHub'da Gemini Code Assist otomatik olarak code review bırakıyor. Şu an bu süreç manuel yürütülüyor:

1. Gemini review bırakır
2. Kullanıcı review'ı kopyalar → Claude Code'a verir
3. Claude Code düzeltir → push eder
4. Kullanıcı "/gemini review" yazar → Gemini tekrar inceler
5. Bu döngü, Gemini yeni bulgu bulamayana kadar devam eder

**Hedef:** Bu süreci otomatikleştirmek. Gemini review geldiğinde otomatik olarak:
- Review'lar değerlendirilsin (Gemini bazen hatalı review yapıyor)
- Geçerli olanlar Claude Code'a iletilsin
- Claude Code düzeltsin, commit & push etsin
- Yapılan değişiklikler kontrol edilsin (uygulama mantığı bozulmamış mı?)
- Yeni review isteği gönderilsin
- Döngü bitene kadar tekrarlansın

**Neden ChatDev (n8n değil):**
- Claude Code **yerel** çalışıyor — n8n'den çağırmak ekstra karmaşıklık
- ChatDev zaten Claude Code provider, agent değerlendirme, human-in-the-loop, loop mekanizması var
- MCP server (`mcp-gemini-pr-reviews`) direkt Claude Code'un `--mcp-config`'ine eklenebilir
- Harici workspace (Faz 2) ile kullanıcının proje dizininde çalışabilir

## Mevcut Araçlar

| Araç | Durum | Açıklama |
|------|-------|----------|
| `mcp-gemini-pr-reviews` | Mevcut | MCP server: Gemini review'larını çeken tek tool (`get_gemini_reviews`) |
| Claude Code Provider | Mevcut | `claude_code_provider.py` — subprocess ile Claude Code çalıştırır |
| `python` node | Mevcut | GitHub API çağrıları, git komutları |
| `agent` node | Mevcut | LLM tabanlı değerlendirme |
| `human` node | Mevcut | Human-in-the-loop onayı |
| `loop_counter` node | Mevcut | İterasyon kontrolü |
| Koşullu kenarlar | Mevcut | Keyword/function bazlı dallanma |

## Workflow Tasarımı

### Genel Akış

```
[Başlat: PR URL + repo bilgisi]
         │
         ▼
┌─────────────────────────────────────┐
│  1. REVIEW FETCHER                  │  python node
│  GitHub API ile Gemini review'ları  │
│  çek (veya MCP kullan).            │
│  Çıktı: JSON review listesi        │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────┐
        │ NO_FINDINGS? │──── Evet ──→ WORKFLOW TAMAMLANDI
        └──────┬──────┘               (Gemini artık bulgu bulamadı)
               │ Hayır
               ▼
┌─────────────────────────────────────┐
│  2. REVIEW EVALUATOR                │  agent node
│  Her review'ı değerlendir:          │
│  - Geçerli mi? (kalite/güvenlik)   │
│  - Mantık değişikliği mi? (skip)   │
│  - Hatalı mı? (skip)               │
│  Çıktı: VALID_REVIEWS veya         │
│         ALL_SKIPPED                 │
└──────────────┬──────────────────────┘
               │
        ┌──────▼───────┐
        │ ALL_SKIPPED?  │──── Evet ──→ RE-REVIEW TRIGGER
        └──────┬───────┘               (atlanma nedenlerini logla)
               │ Hayır
               ▼
┌─────────────────────────────────────┐
│  3. CODE FIXER                      │  claude-code agent
│  Claude Code: geçerli review'lere   │
│  göre kodu düzelt                   │
│  - Sadece kalite iyileştirmeleri    │
│  - Mantık DEĞİŞTİRME              │
│  - Bitince commit & push            │
│  Çıktı: değişiklik özeti + diff    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  4. CHANGE VERIFIER                 │  agent node
│  Yapılan değişiklikleri kontrol et: │
│  - Uygulama akışı bozuldu mu?      │
│  - Mantık değiştirildi mi?          │
│  - Review'a uygun mu düzeltme?      │
│  Çıktı: VERIFIED veya BROKEN       │
└──────────────┬──────────────────────┘
               │
        ┌──────▼──────┐
        │   BROKEN?   │──── Evet ──→ 5. ROLLBACK NODE
        └──────┬──────┘               (git revert + human-in-the-loop)
               │ Hayır
               ▼
┌─────────────────────────────────────┐
│  6. RE-REVIEW TRIGGER               │  python node
│  GitHub API: "/gemini review"       │
│  yorumu gönder.                     │
│  Polling: Gemini'nin yeni review    │
│  oluşturmasını bekle.               │
│  Çıktı: "yeni review hazır"        │
└──────────────┬──────────────────────┘
               │
               ▼
         LOOP → 1'e dön (max N iterasyon)
```

### Node Detayları

#### Node 1: Review Fetcher (`python` node)

```python
# GitHub API ile Gemini review'ları çek
# Alternatif: Claude Code MCP ile de çekilebilir ama python node daha hızlı

import os, json, requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("PR_REPO", "")  # owner/repo
PR_NUMBER = os.environ.get("PR_NUMBER", "")

headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

# PR review comments (Gemini Code Assist)
reviews_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/reviews"
comments_url = f"https://api.github.com/repos/{REPO}/pulls/{PR_NUMBER}/comments"

reviews = requests.get(reviews_url, headers=headers).json()
comments = requests.get(comments_url, headers=headers).json()

# Gemini bot yorumlarını filtrele
gemini_reviews = [r for r in reviews if "gemini" in (r.get("user", {}).get("login", "")).lower()]
gemini_comments = [c for c in comments if "gemini" in (c.get("user", {}).get("login", "")).lower()]

# Son "/gemini review" yorumundan sonrakileri al
# ... (after_last_review filtreleme)

if not gemini_reviews and not gemini_comments:
    print("NO_FINDINGS")
else:
    print(json.dumps({"reviews": gemini_reviews, "comments": gemini_comments}))
```

#### Node 2: Review Evaluator (`agent` node)

**System Prompt:**
```
Sen bir code review değerlendirme uzmanısısın.

GÖREV: Gemini Code Assist'in bıraktığı code review yorumlarını değerlendir.

KURALLAR:
- Code review'in AMACI: kod kalitesi, güvenlik, best practices (KISS, SRP, DRY, SOLID)
- Uygulamanın MANTIĞI değiştirilmemeli. Sadece kalite iyileştirmeleri kabul et.
- Eğer review, uygulamanın işlevselliğini/davranışını değiştirecek bir öneri içeriyorsa → SKIP
- Eğer review, gerçek bir kalite/güvenlik iyileştirmesi öneriyorsa → VALID
- Eğer review yanlış veya alakasız ise → SKIP
- Eğer review'dan emin değilsen → SKIP (güvenli taraf)

ÇIKTI FORMATI:
Her review için bir satır:
VALID: [dosya:satır] [kısa açıklama]
SKIP: [dosya:satır] [neden atlandı]

Sonuç:
- Eğer en az bir VALID varsa → "VALID_REVIEWS" ile başla, ardından geçerli review'ları listele
- Eğer hepsi SKIP ise → "ALL_SKIPPED" yaz
```

#### Node 3: Code Fixer (`claude-code` agent)

**Prompt Template:**
```
Aşağıdaki code review bulgularına göre kodu düzelt.

KURALLAR:
- SADECE belirtilen kalite/güvenlik iyileştirmelerini yap
- Uygulamanın mantığını, akışını, davranışını DEĞİŞTİRME
- Her düzeltmeyi açıkla
- İşin bittiğinde tüm değişiklikleri commit et ve push et
- Commit mesajı: "refactor: apply code review suggestions from Gemini"

CODE REVIEW BULGULARI:
{evaluator_output}
```

**Önemli:** Claude Code'a MCP ile `mcp-gemini-pr-reviews` eklenerek review'ları doğrudan alabilmesi sağlanabilir. Ama evaluator'ün filtrelediği sonuçları vermek daha güvenli.

#### Node 4: Change Verifier (`agent` node)

**System Prompt:**
```
Sen bir değişiklik doğrulama uzmanısısın.

GÖREV: Code review'e istinaden yapılan değişiklikleri kontrol et.

GİRDİ:
- Orijinal code review bulguları
- Yapılan değişikliklerin diff'i (git diff)

KONTROL ET:
1. Uygulamanın akışı bozulmuş mu? (fonksiyon çağrıları, veri akışı, API endpoint'ler)
2. İşlevsellik değiştirilmiş mi? (davranış, return değerleri, side effect'ler)
3. Review'a uygun düzeltme yapılmış mı? (istenen değişiklik gerçekten yapıldı mı)
4. Yeni bug oluşturulmuş mu? (null reference, type error, import eksik)
5. Gereksiz değişiklik var mı? (review'da olmayan dosyalar değişmiş mi)

ÇIKTI:
- "VERIFIED" — değişiklikler temiz, uygulama mantığı korunmuş
- "BROKEN: [detaylı neden]" — sorun var, rollback gerekli
```

#### Node 5: Rollback (`python` node + `human` node)

```python
# git revert ile son commit'i geri al
import subprocess
result = subprocess.run(["git", "revert", "--no-commit", "HEAD"], capture_output=True, text=True)
if result.returncode == 0:
    subprocess.run(["git", "commit", "-m", "revert: rollback broken code review changes"])
    subprocess.run(["git", "push"])
    print("ROLLBACK_DONE")
else:
    print(f"ROLLBACK_FAILED: {result.stderr}")
```

Rollback sonrası `human` node devreye girer: kullanıcıya durum bildirilir, devam mı yoksa durdur mu kararı alınır.

#### Node 6: Re-review Trigger (`python` node)

```python
# "/gemini review" yorumu gönder
import os, requests, time

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ.get("PR_REPO", "")
PR_NUMBER = os.environ.get("PR_NUMBER", "")

headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
url = f"https://api.github.com/repos/{REPO}/issues/{PR_NUMBER}/comments"

# Trigger review
requests.post(url, headers=headers, json={"body": "/gemini review"})

# Gemini'nin review oluşturmasını bekle (polling)
MAX_WAIT = 300  # 5 dakika
POLL_INTERVAL = 15  # 15 saniye

for _ in range(MAX_WAIT // POLL_INTERVAL):
    time.sleep(POLL_INTERVAL)
    # Son yorumları kontrol et
    comments = requests.get(url, headers=headers).json()
    gemini_comments = [c for c in comments if "gemini" in c.get("user", {}).get("login", "").lower()]
    if gemini_comments:
        last = gemini_comments[-1]
        # "/gemini review" yorumundan sonra mı?
        # ... timestamp karşılaştırması
        print("NEW_REVIEW_READY")
        break
else:
    print("TIMEOUT_NO_REVIEW")
```

### Edge Conditions

```yaml
# Custom edge condition functions (functions/edge/conditions.py)

def no_findings(data: str) -> bool:
    """Review fetcher'dan bulgu yok."""
    return "NO_FINDINGS" in data

def has_findings(data: str) -> bool:
    """Review fetcher'dan bulgu var."""
    return "NO_FINDINGS" not in data

def all_skipped(data: str) -> bool:
    """Evaluator tüm review'ları atladı."""
    return "ALL_SKIPPED" in data

def has_valid_reviews(data: str) -> bool:
    """Evaluator geçerli review buldu."""
    return "VALID_REVIEWS" in data

def change_verified(data: str) -> bool:
    """Verifier değişiklikleri onayladı."""
    return "VERIFIED" in data

def change_broken(data: str) -> bool:
    """Verifier değişikliklerde sorun buldu."""
    return "BROKEN" in data
```

### YAML Taslağı

```yaml
version: 0.4.0
graph:
  id: pr_review_cycle
  description: Automated PR code review cycle with Gemini + Claude Code

  start:
    - Review Fetcher
  end:
    - Completed

  nodes:
    - id: Review Fetcher
      type: python
      config:
        # GitHub API ile Gemini review'ları çek

    - id: Review Evaluator
      type: agent
      config:
        provider: openai
        name: gpt-4o
        role: "Code review değerlendirme uzmanı..."

    - id: Code Fixer
      type: agent
      config:
        provider: claude-code
        # Claude Code ile review'lere göre düzelt + commit & push

    - id: Change Verifier
      type: agent
      config:
        provider: openai
        name: gpt-4o
        role: "Değişiklik doğrulama uzmanı..."

    - id: Rollback
      type: python
      config:
        # git revert

    - id: Human Decision
      type: human
      config:
        description: "Değişiklikler geri alındı. Devam mı, dur mu?"

    - id: Re-review Trigger
      type: python
      config:
        # "/gemini review" yorumu gönder + polling

    - id: Loop Gate
      type: loop_counter
      config:
        max_iterations: 10  # Maksimum 10 döngü
        reset_on_emit: false

    - id: Completed
      type: literal
      config:
        content: "PR Review Cycle tamamlandı. Gemini artık bulgu bulamadı."

  edges:
    # Fetcher → condition check
    - from: Review Fetcher
      to: Completed
      condition: { type: function, config: { name: no_findings } }

    - from: Review Fetcher
      to: Review Evaluator
      condition: { type: function, config: { name: has_findings } }

    # Evaluator → condition check
    - from: Review Evaluator
      to: Re-review Trigger
      condition: { type: function, config: { name: all_skipped } }

    - from: Review Evaluator
      to: Code Fixer
      condition: { type: function, config: { name: has_valid_reviews } }

    # Code Fixer → Change Verifier
    - from: Code Fixer
      to: Change Verifier

    # Verifier → condition check
    - from: Change Verifier
      to: Re-review Trigger
      condition: { type: function, config: { name: change_verified } }

    - from: Change Verifier
      to: Rollback
      condition: { type: function, config: { name: change_broken } }

    # Rollback → Human Decision
    - from: Rollback
      to: Human Decision

    # Human → devam veya dur
    - from: Human Decision
      to: Review Fetcher  # Tekrar dene
      condition: { type: keyword, config: { any: ["CONTINUE"] } }

    - from: Human Decision
      to: Completed
      condition: { type: keyword, config: { any: ["STOP"] } }

    # Re-review → Loop Gate → Review Fetcher (döngü)
    - from: Re-review Trigger
      to: Loop Gate

    - from: Loop Gate
      to: Review Fetcher  # Döngü devam

    - from: Loop Gate
      to: Completed  # Maksimum iterasyona ulaşıldı
```

## Bağımlılıklar

Bu workflow'un çalışması için gerekli ön koşullar:

| Bağımlılık | Durum | Açıklama |
|-----------|-------|----------|
| **Faz 2: Harici Workspace** | Gerekli | PR'ın repo'sunda çalışmak için `workspace_path` desteği |
| **Custom edge conditions** | Yeni | `no_findings`, `has_valid_reviews` vb. fonksiyonlar |
| **GitHub Token** | Mevcut | `.env`'de `GITHUB_TOKEN` |
| **Claude Code** | Mevcut | Provider zaten entegre |
| **mcp-gemini-pr-reviews** | Opsiyonel | MCP ile review çekme (python node da yapabilir) |

## Trigger Mekanizması

### Opsiyon A: Manuel Başlatma (İlk Aşama)

UI'dan workflow'u seç, PR bilgilerini gir:
```
Task Prompt: "Review cycle for https://github.com/mytsx/my-project/pull/42"
Workspace Path: /Users/mehmet/projects/my-project
```

### Opsiyon B: Webhook Listener (Gelecek)

```python
# Basit Flask/FastAPI webhook endpoint
# GitHub PR review event geldiğinde ChatDev workflow trigger et
@app.post("/github/webhook")
async def github_webhook(payload: dict):
    if payload.get("action") == "submitted" and "pull_request" in payload:
        # POST /api/workflow/execute ile ChatDev workflow başlat
        pass
```

### Opsiyon C: Polling Script (Orta Yol)

```python
# Cron veya daemon: her N dakikada açık PR'ları kontrol et
# Yeni review varsa ChatDev workflow başlat
```

## Doğrulama Senaryosu

1. Test repo'da bir PR oluştur (kasıtlı olarak kötü kod ile)
2. Gemini review bırakmasını bekle
3. "PR Review Cycle" workflow'unu başlat
4. İzle:
   - Review Fetcher Gemini yorumlarını çekiyor mu?
   - Evaluator geçerli/geçersiz ayrımı yapıyor mu?
   - Claude Code düzeltmeleri uyguluyor mu?
   - Verifier değişiklikleri kontrol ediyor mu?
   - Re-review trigger çalışıyor mu?
   - Döngü doğru bitiyor mu?
5. Edge case: Gemini hatalı review → Evaluator SKIP'liyor mu?
6. Edge case: Claude Code mantık bozuyor → Verifier BROKEN → Rollback çalışıyor mu?
