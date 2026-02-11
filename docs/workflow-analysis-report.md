# Enterprise Workflow Akış Analizi: Neden Agent'lar Görevlerini Tamamlayamadı?

**Tarih:** 2026-02-11
**Session:** `996e9ca4-5329-40e4-8519-e8480eeaefe7`
**Görev:** Gelişmiş Filtreleme Sistemi
**Workflow:** `enterprise_dev.yaml`

## Context
Enterprise development workflow'u "Gelişmiş Filtreleme" görevi için çalıştırıldı. Workflow tüm node'ları başarıyla başlatıp tamamladı (hata yok, timeout yok), ancak 3 kritik agent anlamlı çıktı üretemedi. Tech Lead eksik dokümanları tespit edip akışı durdurdu.

---

## 1. Genel Akış Durumu

| Node | Süre (s) | Çıktı (char) | Tool Call | Seq. Think | Durum |
|------|----------|---------------|-----------|------------|-------|
| Business Analyst | 280 | 2,327 | 18 | 0 | ✅ Başarılı — requirements doc üretildi |
| UX Designer | 310 | 18,422 | 17 | 8 | ✅ Başarılı — kapsamlı UX spec üretildi |
| Solution Architect | 391 | **685** | **37** | **9** | ❌ Sadece ilerleme mesajları |
| Security Reviewer | 180 | **432** | **26** | **9** | ❌ Sadece ilerleme mesajları |
| DBA | 209 | **587** | **22** | **10** | ❌ Sadece ilerleme mesajları |
| Tech Lead | 89 | — | 8 | 0 | ⚠️ Eksik input ile çalıştı |

---

## 2. Temel Sorun: `--max-turns 15` Limiti

**Kök neden:** Claude Code CLI `--max-turns 15` ile çalışıyor (`claude_code_provider.py:193`). Agent'lar tüm turn bütçelerini araştırma aşamasında (dosya okuma + sequential thinking) harcadı ve **nihai dokümanı yazmak için turn kalmadı**.

### Kanıt: Agent'ların son text çıktıları hep "şimdi yapacağım" ile bitiyor

- **Solution Architect:** *"Artık tüm codebase'i kapsamlı şekilde anladım. Şimdi... analiz edeceğim."* → Analiz asla yazılmadı
- **Security Reviewer:** *"Şimdi Exa Search ile dependency CVE check yapacağım:"* → CVE check bitti ama rapor yazılmadı
- **DBA:** *"Mükemmel! Artık database architect olarak çalışmaya başlayabilirim. Sequential thinking ile analizi yapacağım:"* → Sequential thinking bitti ama schema dokümanı yazılmadı

### Turn bütçesi nasıl tükendi (Solution Architect örneği):

```
Turn  1: TodoWrite + Task(explore) başlat     → 2 tool call
Turn  2: Read(requirements.md) + Bash(find)    → 2 tool call
Turn  3: mcp_filesystem(directory_tree)        → 1 tool call (hata: çok büyük)
Turn  4: mcp_filesystem(read_text_file)        → 1 tool call (hata: erişim engeli)
Turn  5: Bash(find) + read_multiple_files      → 2 tool call
Turn  6-9: 4x read_multiple_files batches      → 8 tool call
Turn 10: TodoWrite + 6x Read                  → 7 tool call
Turn 11: ToolSearch(sequential thinking)        → 1 tool call
Turn 12-14: Sequential thinking steps 1-7      → 7 tool call (paralel olmayanlar)
Turn 15: Sequential thinking steps 8-9         → 2 tool call
→→ MAX TURNS HIT — Nihai doküman yazılamadı! ←←
```

### Neden Business Analyst ve UX Designer başardı:
- **Business Analyst:** Sequential thinking KULLANMADI (0 step). 18 tool call'ı basit dosya okuma + grep. Son turn'de nihai dokümanı yazdı + dosya oluşturdu.
- **UX Designer:** 8 sequential thinking step, ama daha az dosya okuması (9 diğer tool). Turn bütçesi yeterliydi.

---

## 3. Katkı Yapan Faktörler

### 3a. Sequential Thinking Tool Her Adımda Bir Turn Tüketiyor
Her `mcp__server-sequential-thinking__sequentialthinking` çağrısı = 1 API turn. 9-10 adımlık bir analiz tek başına turn bütçesinin %60-67'sini tüketiyor.

| Agent | Seq. Thinking Steps | Turn Bütçesi Kullanımı |
|-------|--------------------|-----------------------|
| Solution Architect | 9 step | 9/15 = %60 |
| Security Reviewer | 9 step | 9/15 = %60 |
| DBA | 10 step | 10/15 = %67 |

### 3b. Solution Architect Çok Fazla Dosya Okudu
Solution Architect `opus` model ile çalıştığı için (input_size=24,889 char), kapsamlı araştırma yaptı:
- `mcp__filesystem__read_multiple_files` x10 batch (tüm Flutter dosyaları)
- Ayrı ayrı 9x `Read` tool call
- 1x `Task` sub-agent (explore)
- 1x `Bash(find)` + 1x `Glob`

Toplam 28 non-sequential tool call + 9 sequential thinking = 37 tool call = 15 turn bütçesi fazlasıyla aşıldı.

### 3c. Agent'lar Turn Bütçesinden Habersiz
Agent prompt'larında turn limiti hakkında bilgi yok. Agent'lar sınırsız turn'leri varmış gibi davranıyor — önce tüm araştırmayı yapıp sonra yazmayı planlıyor, ama yazma aşamasına hiç ulaşamıyor.

### 3d. DBA Yanlış Dosya Ekledi
DBA'nın output'unda attachment olarak `.claude_sessions.json` gönderilmiş. Bu, Claude Code CLI'ın session tracking dosyası — workspace diff mekanizması bu dosyayı "yeni oluşturulmuş" olarak algılayıp attach etti. Gerçek database schema dokümanı hiç yazılmadı.

---

## 4. Downstream Etki Zinciri

```
Solution Architect (685 char ilerleme mesajı) ──→ Tech Lead'e context olarak gitti
Security Reviewer (432 char ilerleme mesajı)  ──→ Tech Lead'e context olarak gitti
DBA (587 char ilerleme mesajı)                ──→ Tech Lead'i TETİKLEDİ (trigger:true)

Tech Lead 5 input aldı:
  ✅ Input 0: USER task (294 char)
  ✅ Input 1: Business Analyst requirements (2327 char + dosya)
  ❌ Input 2: Solution Architect → 685 char ilerleme mesajı (mimari yok)
  ❌ Input 3: Security Reviewer → 432 char ilerleme mesajı (güvenlik analizi yok)
  ❌ Input 4: DBA → 587 char ilerleme mesajı + yanlış dosya (schema yok)

→ Tech Lead doğru bir şekilde eksikleri tespit edip uyarı verdi
→ Plan Approval'da akış durdu (kullanıcıya eksiklik bildirildi)
```

---

## 5. Önerilen Düzeltmeler

### Kısa Vadeli (Hızlı Çözüm)
1. **`max_turns` artır**: `claude_code_provider.py:193` → 15'ten 25-30'a çıkar
2. **Agent prompt'larına turn uyarısı ekle**: "En fazla 15 turn'ünüz var. Araştırmaya max 8-10 turn, nihai doküman yazmaya min 3-5 turn ayırın."
3. **Sequential thinking step sayısını sınırla**: Prompt'ta "Maximum 5 sequential thinking step kullanın" yönergesi ekle

### Orta Vadeli (Yapısal İyileştirme)
4. **Output validation**: Node tamamlandığında `output_size` minimum eşiği kontrol et (ör. architecture node için min 2000 char). Eşik altındaysa uyarı log'la veya session resume ile devam ettir.
5. **Turn budget tracking**: Claude Code provider'a turn sayacı ekle, kalan turn bilgisini agent'a ilet
6. **Session resume for incomplete outputs**: Eğer output_size < threshold ise, mevcut session_id ile `--resume` yaparak agent'ı devam ettir

### Uzun Vadeli (Mimari)
7. **Two-phase execution**: Araştırma fazı (dosya okuma, seq thinking) ve yazım fazı (doküman oluşturma) ayrı CLI invocation'ları olarak çalıştır
8. **Smart tool budgeting**: Agent'ın prompt'una dinamik olarak "N tool call hakkınız kaldı" bilgisi ekle

---

## Özet

| Sorun | Etki | Şiddet |
|-------|------|--------|
| max_turns=15 yetersiz | 3 agent doküman üretemedi | **Kritik** |
| Sequential thinking turn-hog | 9-10 step = bütçenin %60-67'si | **Yüksek** |
| Turn bütçesi farkındalığı yok | Agent'lar plansız harcıyor | **Orta** |
| DBA yanlış dosya attach | .claude_sessions.json → schema yerine | **Düşük** |
| Output validation yok | Boş çıktılar algılanmıyor | **Orta** |

---

## Referans Dosyalar
- Session log: `logs/session_996e9ca4-5329-40e4-8519-e8480eeaefe7.log`
- Claude Code provider: `runtime/node/agent/providers/claude_code_provider.py` (satır 193: max_turns)
- Enterprise workflow: `yaml_instance/enterprise_dev.yaml`
