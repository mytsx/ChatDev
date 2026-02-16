# MAPEG ChatDev 2.0 + Claude Code Workspace Mimarisi v2
# Legacy Migration + Cross-Access Destekli

## Proje Haritası

```
YtkService (eski backend)  ──migration──▶  mapeg (yeni backend)
MigemPortal (eski frontend) ──migration──▶  mapeg-ui (yeni frontend)
```

## Fiziksel Dizin Yapısı

```
/home/mehmet/projects/
│
│── ════════════ YENİ SİSTEM ════════════
├── mapeg/                              # Yeni Backend (Oracle DB, PL/SQL, Python API)
│   ├── .claude/
│   │   ├── settings.json
│   │   ├── skills/
│   │   │   ├── oracle-patterns/SKILL.md
│   │   │   ├── plsql-conventions/SKILL.md
│   │   │   └── api-design/SKILL.md
│   │   └── agents/
│   │       └── db-explorer.md
│   └── CLAUDE.md
│
├── mapeg-ui/                           # Yeni Frontend (React/Vue)
│   ├── .claude/
│   │   ├── settings.json
│   │   ├── skills/
│   │   │   ├── component-patterns/SKILL.md
│   │   │   ├── api-integration/SKILL.md
│   │   │   └── ui-testing/SKILL.md
│   │   └── agents/
│   │       └── style-checker.md
│   └── CLAUDE.md
│
│── ════════════ ESKİ SİSTEM (Migration Source) ════════════
├── YtkService/                         # Eski Backend (migration source)
│   ├── .claude/
│   │   └── skills/
│   │       └── ytk-legacy/SKILL.md     # Legacy yapı rehberi
│   └── CLAUDE.md                       # Eski backend yapısı dokümantasyonu
│
├── MigemPortal/                        # Eski Frontend (migration source)
│   ├── .claude/
│   │   └── skills/
│   │       └── migem-legacy/SKILL.md   # Legacy UI yapı rehberi
│   └── CLAUDE.md                       # Eski frontend yapısı dokümantasyonu
│
│── ════════════ CHATDEV WORKSPACES ════════════
├── chatdev-workspaces/
│   │
│   ├── team-lead/
│   │   └── .claude/
│   │       ├── settings.json
│   │       ├── skills/
│   │       │   ├── code-review/SKILL.md
│   │       │   ├── architecture-review/SKILL.md
│   │       │   ├── migration-tracker/SKILL.md    # Migration ilerleme takibi
│   │       │   └── task-management/SKILL.md
│   │       └── agents/
│   │           ├── frontend-reviewer.md
│   │           └── backend-reviewer.md
│   │
│   ├── backend-dev/
│   │   └── .claude/
│   │       ├── settings.json
│   │       ├── skills/
│   │       │   ├── backend-coding/SKILL.md
│   │       │   └── migration-backend/SKILL.md    # YtkService → mapeg rehberi
│   │       └── agents/
│   │           └── test-runner.md
│   │
│   ├── frontend-dev/
│   │   └── .claude/
│   │       ├── settings.json
│   │       ├── skills/
│   │       │   ├── frontend-coding/SKILL.md
│   │       │   └── migration-frontend/SKILL.md   # MigemPortal → mapeg-ui rehberi
│   │       └── agents/
│   │           └── component-tester.md
│   │
│   └── tester/
│       └── .claude/
│           ├── settings.json
│           ├── skills/
│           │   ├── test-patterns/SKILL.md
│           │   └── regression-testing/SKILL.md   # Eski vs yeni karşılaştırma
│           └── agents/
│               └── coverage-analyzer.md
│
└── chatdev-orchestrator/
    ├── config.py
    ├── hooks/
    │   ├── block-legacy-write.sh       # Eski repo'lara yazma engeli
    │   ├── block-backend-write.sh      # Frontend'in backend'e yazma engeli
    │   └── block-frontend-write.sh     # Backend'in frontend'e yazma engeli
    └── run.py
```


## Her Rolün Erişim Haritası

```
                 │ mapeg  │ mapeg-ui │ YtkService │ MigemPortal │ be-ws  │ fe-ws  │ test-ws │
                 │ (yeni) │ (yeni)   │ (eski)     │ (eski)      │(skills)│(skills)│(skills) │
─────────────────┼────────┼──────────┼────────────┼─────────────┼────────┼────────┼─────────┤
Team Lead        │  R/W   │   R/W    │    R       │     R       │ Görür  │ Görür  │  Görür  │
Backend Dev      │  R/W   │   R(*)   │    R       │     R(*)    │   -    │ Görür★ │   -     │
Frontend Dev     │  R(*)  │   R/W    │    R(*)    │     R       │ Görür★ │   -    │   -     │
Tester           │  R     │   R      │    R       │     R       │   -    │   -    │   -     │

R/W  = Okuma + Yazma (asıl çalışma alanı)
R    = Sadece okuma (context için)
R(*) = Okuma + hook ile yazma engelli
Görür★ = Diğer dev'in workspace skill'lerini görür (cross-context)
```


## Claude Code Başlatma Komutları

### Backend Developer
```bash
cd /home/mehmet/projects/chatdev-workspaces/backend-dev

claude -p "$TASK_PROMPT" \
  --add-dir /home/mehmet/projects/mapeg \
  --add-dir /home/mehmet/projects/YtkService \
  --add-dir /home/mehmet/projects/mapeg-ui \
  --add-dir /home/mehmet/projects/MigemPortal \
  --add-dir /home/mehmet/projects/chatdev-workspaces/frontend-dev \
  --output-format json
```

**Erişim:**
- `mapeg/` → R/W (asıl çalışma alanı, yeni backend)
- `YtkService/` → R (eski kodu okuyup yeniye taşıma)
- `mapeg-ui/` → R(*) (frontend context, hook ile yazma engelli)
- `MigemPortal/` → R(*) (eski frontend context)
- `frontend-dev/` workspace → skill'lerini görür (frontend'in ne yaptığını anlar)

### Frontend Developer
```bash
cd /home/mehmet/projects/chatdev-workspaces/frontend-dev

claude -p "$TASK_PROMPT" \
  --add-dir /home/mehmet/projects/mapeg-ui \
  --add-dir /home/mehmet/projects/MigemPortal \
  --add-dir /home/mehmet/projects/mapeg \
  --add-dir /home/mehmet/projects/YtkService \
  --add-dir /home/mehmet/projects/chatdev-workspaces/backend-dev \
  --output-format json
```

**Erişim:**
- `mapeg-ui/` → R/W (asıl çalışma alanı, yeni frontend)
- `MigemPortal/` → R (eski kodu okuyup yeniye taşıma)
- `mapeg/` → R(*) (backend API context, hook ile yazma engelli)
- `YtkService/` → R(*) (eski backend API context)
- `backend-dev/` workspace → skill'lerini görür (backend'in ne yaptığını anlar)

### Team Lead
```bash
cd /home/mehmet/projects/chatdev-workspaces/team-lead

claude -p "$TASK_PROMPT" \
  --add-dir /home/mehmet/projects/mapeg \
  --add-dir /home/mehmet/projects/mapeg-ui \
  --add-dir /home/mehmet/projects/YtkService \
  --add-dir /home/mehmet/projects/MigemPortal \
  --add-dir /home/mehmet/projects/chatdev-workspaces/backend-dev \
  --add-dir /home/mehmet/projects/chatdev-workspaces/frontend-dev \
  --add-dir /home/mehmet/projects/chatdev-workspaces/tester \
  --output-format json \
  --model opus
```

**Erişim:** Her şeye tam erişim. Review ve koordinasyon rolü.

### Tester
```bash
cd /home/mehmet/projects/chatdev-workspaces/tester

claude -p "$TASK_PROMPT" \
  --add-dir /home/mehmet/projects/mapeg \
  --add-dir /home/mehmet/projects/mapeg-ui \
  --add-dir /home/mehmet/projects/YtkService \
  --add-dir /home/mehmet/projects/MigemPortal \
  --output-format json
```

**Erişim:** Tüm repo'ları okur. Yeni vs eski karşılaştırma, regression testi.


## Hook Konfigürasyonları

### Frontend Dev — Backend'e Yazma Engeli
```json
// chatdev-workspaces/frontend-dev/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/home/mehmet/projects/chatdev-orchestrator/hooks/frontend-guard.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "npx prettier --write \"$(cat | jq -r '.tool_input.file_path // .tool_input.path // empty')\" 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

### Backend Dev — Frontend'e Yazma Engeli
```json
// chatdev-workspaces/backend-dev/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/home/mehmet/projects/chatdev-orchestrator/hooks/backend-guard.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 -m black --quiet \"$(cat | jq -r '.tool_input.file_path // empty')\" 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

### Tester — Her Yere Yazma Engeli (Sadece Okuma)
```json
// chatdev-workspaces/tester/.claude/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/home/mehmet/projects/chatdev-orchestrator/hooks/readonly-guard.sh"
          }
        ]
      }
    ]
  }
}
```


## Guard Hook Scripts

### frontend-guard.sh
```bash
#!/bin/bash
# Frontend dev: SADECE mapeg-ui/ altına yazabilir
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

# Boş path → izin ver (dosya dışı işlem)
[ -z "$FILE_PATH" ] && exit 0

# mapeg-ui/ altına yazma → İZİN VER
echo "$FILE_PATH" | grep -q "mapeg-ui/" && exit 0

# chatdev-workspaces/frontend-dev/ altına yazma → İZİN VER (kendi workspace'i)
echo "$FILE_PATH" | grep -q "chatdev-workspaces/frontend-dev/" && exit 0

# Diğer her yer → ENGELLE
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Frontend developer SADECE mapeg-ui/ altina yazabilir. Bu dosya baska bir repo'da. Degisiklik gerekiyorsa task ciktisinda rapor et."
  }
}
EOF
exit 0
```

### backend-guard.sh
```bash
#!/bin/bash
# Backend dev: SADECE mapeg/ altına yazabilir (mapeg-ui/ hariç)
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

[ -z "$FILE_PATH" ] && exit 0

# mapeg-ui/ veya MigemPortal/ → ENGELLE (frontend repo'ları)
if echo "$FILE_PATH" | grep -qE "(mapeg-ui/|MigemPortal/)"; then
  cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Backend developer frontend repo'larina yazamaz (mapeg-ui/, MigemPortal/). Degisiklik gerekiyorsa task ciktisinda rapor et."
  }
}
EOF
  exit 0
fi

# YtkService/ → ENGELLE (eski repo'ya yazma yok, sadece okuma)
if echo "$FILE_PATH" | grep -q "YtkService/"; then
  cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Eski sisteme (YtkService/) yazma yasak. Sadece okuyup yeni sisteme (mapeg/) tasima yapilmali."
  }
}
EOF
  exit 0
fi

# mapeg/ altına yazma → İZİN VER
echo "$FILE_PATH" | grep -q "mapeg/" && exit 0

# Kendi workspace'i → İZİN VER
echo "$FILE_PATH" | grep -q "chatdev-workspaces/backend-dev/" && exit 0

# Diğer → ENGELLE
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Backend developer SADECE mapeg/ altina yazabilir."
  }
}
EOF
exit 0
```

### readonly-guard.sh
```bash
#!/bin/bash
# Tester: HİÇBİR YERE yazamaz (test dosyaları hariç)
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

[ -z "$FILE_PATH" ] && exit 0

# Test dosyalarına yazma → İZİN VER
if echo "$FILE_PATH" | grep -qE "(\.test\.|\.spec\.|__tests__|/tests/)"; then
  exit 0
fi

# Kendi workspace'i → İZİN VER
echo "$FILE_PATH" | grep -q "chatdev-workspaces/tester/" && exit 0

# Diğer her şey → ENGELLE
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Tester rolu sadece test dosyalarini (*.test.*, *.spec.*, __tests__/) yazabilir. Diger dosyalara mudahale yasak."
  }
}
EOF
exit 0
```

### legacy-guard.sh (Tüm roller için ortak — eski repo'lara yazma engeli)
```bash
#!/bin/bash
# HİÇBİR ROL eski repo'lara (YtkService, MigemPortal) yazamaz
# Bu script diğer guard'lardan ÖNCE çağrılabilir veya içlerine gömülebilir
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

[ -z "$FILE_PATH" ] && exit 0

if echo "$FILE_PATH" | grep -qE "(YtkService/|MigemPortal/)"; then
  cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Eski sisteme (YtkService/MigemPortal) yazma YASAK. Bu repolar sadece migration kaynak olarak okunur. Yeni kodu mapeg/ veya mapeg-ui/ altina yaz."
  }
}
EOF
  exit 0
fi

exit 0
```


## Migration Skill Örnekleri

### backend-dev migration skill
```yaml
# chatdev-workspaces/backend-dev/.claude/skills/migration-backend/SKILL.md
---
name: migration-backend
description: >
  YtkService'ten mapeg'e backend migration rehberi.
  YtkService/ altindaki dosyalari okuyup mapeg/ altina yeni yapiyla tasima.
  SADECE migration task'larinda kullan.
---

# YtkService → mapeg Migration Rehberi

## Klasör Eşleştirmesi
- YtkService/Controllers/ → mapeg/src/api/routes/
- YtkService/Models/ → mapeg/src/models/
- YtkService/DAL/ → mapeg/src/database/
- YtkService/Services/ → mapeg/src/services/

## Migration Kuralları
1. Eski kodu ASLA kopyala-yapıştır yapma
2. Eski kodu oku, mantığını anla, yeni pattern'e uygun yeniden yaz
3. Oracle stored procedure'leri: YtkService/SQL/ → mapeg/sql/
4. Her migration'da test yaz
5. Eski endpoint → yeni endpoint mapping'ini mapeg/docs/migration-map.md'ye kaydet

## Dikkat
- YtkService .NET/C# tabanlı, mapeg Python tabanlı — direkt çeviri YAPMA
- İş mantığını koru, implementasyonu yeniden tasarla
- Oracle connection string'leri, tablo isimleri değişmiş olabilir, CLAUDE.md'yi kontrol et
```

### frontend-dev migration skill
```yaml
# chatdev-workspaces/frontend-dev/.claude/skills/migration-frontend/SKILL.md
---
name: migration-frontend
description: >
  MigemPortal'dan mapeg-ui'a frontend migration rehberi.
  MigemPortal/ altindaki dosyalari okuyup mapeg-ui/ altina yeni yapiyla tasima.
  SADECE migration task'larinda kullan.
---

# MigemPortal → mapeg-ui Migration Rehberi

## Klasör Eşleştirmesi
- MigemPortal/Views/ → mapeg-ui/src/pages/
- MigemPortal/Scripts/ → mapeg-ui/src/utils/
- MigemPortal/Content/css/ → mapeg-ui/src/styles/
- MigemPortal/Models/ViewModels/ → mapeg-ui/src/types/

## Migration Kuralları
1. MigemPortal Razor/jQuery tabanlı, mapeg-ui React/Vue — direkt çeviri YAPMA
2. UI davranışını koru, component yapısını yeniden tasarla
3. Her sayfa migration'ında eski-yeni ekran karşılaştırması yap
4. API endpoint'leri değiştiyse mapeg/docs/migration-map.md'yi kontrol et
5. mapeg/ altındaki yeni API şemasına uygun service layer yaz
```


## Skill Karışma Kontrolü — description Stratejisi

```yaml
# mapeg/.claude/skills/oracle-patterns/SKILL.md
---
name: oracle-patterns
description: >
  Oracle PL/SQL query patterns for MAPEG NEW backend.
  ONLY activate when working on Python files in mapeg/src/database/ or mapeg/sql/.
  NEVER activate for frontend, UI, JavaScript, or React work.
  NEVER activate for YtkService or MigemPortal legacy code.
disable-model-invocation: true
---
```

```yaml
# mapeg-ui/.claude/skills/component-patterns/SKILL.md
---
name: component-patterns
description: >
  React/Vue component patterns for MAPEG-UI NEW frontend.
  ONLY activate when working on files in mapeg-ui/src/.
  NEVER activate for backend, database, PL/SQL, or Python work.
  NEVER activate for YtkService or MigemPortal legacy code.
disable-model-invocation: true
---
```

```yaml
# YtkService/.claude/skills/ytk-legacy/SKILL.md
---
name: ytk-legacy
description: >
  Legacy YtkService (.NET/C#) codebase structure reference.
  ONLY activate during migration tasks reading from YtkService/.
  This is READ-ONLY reference. Never suggest writing to YtkService.
disable-model-invocation: true
---
```

```yaml
# MigemPortal/.claude/skills/migem-legacy/SKILL.md
---
name: migem-legacy
description: >
  Legacy MigemPortal (ASP.NET MVC/Razor/jQuery) structure reference.
  ONLY activate during migration tasks reading from MigemPortal/.
  This is READ-ONLY reference. Never suggest writing to MigemPortal.
disable-model-invocation: true
---
```


## ChatDev Orkestratör Konfigürasyonu

```python
# chatdev-orchestrator/config.py

import os
import subprocess
import json

BASE = "/home/mehmet/projects"

REPOS = {
    # Yeni sistem
    "mapeg":       f"{BASE}/mapeg",
    "mapeg-ui":    f"{BASE}/mapeg-ui",
    # Eski sistem (migration source)
    "YtkService":  f"{BASE}/YtkService",
    "MigemPortal": f"{BASE}/MigemPortal",
}

WORKSPACES = f"{BASE}/chatdev-workspaces"

ROLES = {
    "team-lead": {
        "cwd": f"{WORKSPACES}/team-lead",
        "add_dirs": [
            REPOS["mapeg"],
            REPOS["mapeg-ui"],
            REPOS["YtkService"],
            REPOS["MigemPortal"],
            f"{WORKSPACES}/backend-dev",
            f"{WORKSPACES}/frontend-dev",
            f"{WORKSPACES}/tester",
        ],
        "model": "opus",
        "env": {
            "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1",
        },
    },
    "backend-dev": {
        "cwd": f"{WORKSPACES}/backend-dev",
        "add_dirs": [
            REPOS["mapeg"],          # Asıl çalışma alanı (R/W)
            REPOS["YtkService"],     # Eski backend (R, migration source)
            REPOS["mapeg-ui"],       # Frontend context (R, hook engelli)
            REPOS["MigemPortal"],    # Eski frontend context (R)
            f"{WORKSPACES}/frontend-dev",  # Frontend dev'in skill'lerini gör
        ],
        "model": "sonnet",
        "env": {},
    },
    "frontend-dev": {
        "cwd": f"{WORKSPACES}/frontend-dev",
        "add_dirs": [
            REPOS["mapeg-ui"],       # Asıl çalışma alanı (R/W)
            REPOS["MigemPortal"],    # Eski frontend (R, migration source)
            REPOS["mapeg"],          # Backend API context (R, hook engelli)
            REPOS["YtkService"],     # Eski backend context (R)
            f"{WORKSPACES}/backend-dev",   # Backend dev'in skill'lerini gör
        ],
        "model": "sonnet",
        "env": {},
    },
    "tester": {
        "cwd": f"{WORKSPACES}/tester",
        "add_dirs": [
            REPOS["mapeg"],
            REPOS["mapeg-ui"],
            REPOS["YtkService"],
            REPOS["MigemPortal"],
        ],
        "model": "sonnet",
        "env": {},
    },
}


def build_claude_command(role: str, task: str) -> tuple[list, str, dict]:
    """Claude CLI komutunu oluşturur."""
    cfg = ROLES[role]

    cmd = [
        "claude", "-p", task,
        "--output-format", "json",
        "--model", cfg.get("model", "sonnet"),
    ]

    for d in cfg.get("add_dirs", []):
        cmd.extend(["--add-dir", d])

    return cmd, cfg["cwd"], cfg.get("env", {})


def run_role(role: str, task: str) -> dict:
    """Bir ChatDev rolünü Claude Code session'ı olarak çalıştırır."""
    cmd, cwd, env = build_claude_command(role, task)

    full_env = {**os.environ, **env}

    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=600,  # 10 dakika timeout
    )

    return {
        "role": role,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
```


## Akış Özeti

```
ChatDev Orkestratör
│
├─▶ Team Lead session
│   │  CWD: team-lead/        (kendi hooks: review-focused)
│   │  --add-dir: mapeg, mapeg-ui, YtkService, MigemPortal + tüm workspace'ler
│   │  Görev: Task planla, review yap, migration ilerlemesini takip et
│   │
│   ├─▶ Backend Dev session
│   │   │  CWD: backend-dev/   (kendi hooks: backend-guard.sh → mapeg/ dışına yazma yasak)
│   │   │  --add-dir: mapeg(R/W), YtkService(R), mapeg-ui(R), MigemPortal(R), frontend-dev/(skills)
│   │   │  Görev: YtkService'ten oku → mapeg'e yeni backend yaz
│   │   │
│   │   └─ Sub-agents: db-explorer (Oracle şema keşfi), test-runner
│   │
│   ├─▶ Frontend Dev session
│   │   │  CWD: frontend-dev/  (kendi hooks: frontend-guard.sh → mapeg-ui/ dışına yazma yasak)
│   │   │  --add-dir: mapeg-ui(R/W), MigemPortal(R), mapeg(R), YtkService(R), backend-dev/(skills)
│   │   │  Görev: MigemPortal'dan oku → mapeg-ui'a yeni frontend yaz
│   │   │
│   │   └─ Sub-agents: component-tester, style-checker
│   │
│   └─▶ Tester session
│       │  CWD: tester/        (kendi hooks: readonly-guard.sh → test dosyaları hariç yazma yasak)
│       │  --add-dir: mapeg(R), mapeg-ui(R), YtkService(R), MigemPortal(R)
│       │  Görev: Eski vs yeni davranış karşılaştırma, regression test
│       │
│       └─ Sub-agents: coverage-analyzer
│
└─▶ ChatDev: Roller arası iletişim, review döngüleri, task yönlendirme
```
