# Agent Prompt Araştırma Kaynakları

Enterprise workflow'daki 18 agent rolünün prompt'larını iyileştirmek için araştırılan GitHub repoları ve kaynaklar.

## Daha Önce Kullanılan Kaynaklar (d4048f9 commit)

| Repo | Stars | Kullanılan Pattern |
|---|---|---|
| [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | ~30k | Chat chain paradigm, phase-based conversations |
| [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | ~56k | Document-driven communication, SOP-based roles |
| engineering-team-agents (tam repo bilinmiyor) | — | — |

---

## Kategori 1: Multi-Agent Yazılım Geliştirme Framework'leri

### 1. MetaGPT
- **URL:** [github.com/FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) (~56k stars)
- **Roller:** Product Manager, Architect, Project Manager, Engineer, QA Engineer
- **Pattern:** Agents arası iletişim yapısal dokümanlarla (PRD, design doc, task list). Her rol SOP takip eder.
- **Hedef roller:** Business Analyst, Solution Architect, Tech Lead, QA Engineer

### 2. ChatDev
- **URL:** [github.com/OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) (~30k stars)
- **Roller:** CEO, CTO, CPO, Programmer, Code Reviewer, Tester, Art Designer
- **Pattern:** Chat chain + functional seminars (Design, Coding, Testing, Documentation)
- **Hedef roller:** Solution Architect, Backend/Frontend Developer, QA Engineer, Technical Writer

### 3. Agyn
- **URL:** [arxiv.org/abs/2602.01465](https://arxiv.org/abs/2602.01465) (Şubat 2025)
- **Roller:** Analysis, task specification, PR creation, iterative review
- **Pattern:** SWE-bench'te %72.4 — workflow design ve responsibility separation first-class
- **Hedef roller:** Tech Lead, Backend Developer, QA Engineer

### 4. MAGIS (NeurIPS 2024)
- **URL:** [github.com/co-evolve-lab/magis](https://github.com/co-evolve-lab/magis)
- **Roller:** Manager, Repository Custodian, Developer, QA Engineer
- **Pattern:** Temiz sorumluluk ayrımı — Manager plan yapar, Custodian dosya bulur, Dev implement eder, QA review eder
- **Hedef roller:** Tech Lead, Backend Developer, QA Engineer

### 5. DevOpsGPT
- **URL:** [github.com/kuafuai/DevOpsGPT](https://github.com/kuafuai/DevOpsGPT) (~8.5k stars)
- **Roller:** Requirements Clarifier, Interface Designer, Developer, DevOps operator
- **Pattern:** Full deployment lifecycle — requirements'tan CI/CD'ye
- **Hedef roller:** DevOps Engineer, SRE, Integration Engineer

### 6. AgentVerse (OpenBMB)
- **URL:** [github.com/OpenBMB/AgentVerse](https://github.com/OpenBMB/AgentVerse) (~4.5k stars)
- **Roller:** Configurable — Software Designer, DBA, Professor+Students
- **Pattern:** Dynamic agent team composition, simulation framework
- **Hedef roller:** Solution Architect, DBA, UX Designer

---

## Kategori 2: Genel Multi-Agent Framework'leri

### 7. CrewAI
- **URL:** [github.com/crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) (~44k stars)
- **Pattern:** YAML-based role definition (role, backstory, goal, tools). Sequential/hierarchical process orchestration.
- **Hedef roller:** Tüm roller (YAML config pattern'i bizimkine çok benzer)

### 8. AutoGen (Microsoft)
- **URL:** [github.com/microsoft/autogen](https://github.com/microsoft/autogen) (~54k stars)
- **Pattern:** Structured multi-agent conversations, function-calling agents
- **Hedef roller:** Tüm roller (conversational scaffolding pattern)

### 9. CAMEL-AI
- **URL:** [github.com/camel-ai/camel](https://github.com/camel-ai/camel) (~7.5k stars)
- **Pattern:** Role-playing paradigm — iki agent paired roller alıp collaborate eder. Role flipping, termination condition handling.
- **Hedef roller:** Dev+QA pairs, Security Reviewer+Bug Fixer pairs

### 10. PraisonAI
- **URL:** [github.com/MervinPraison/PraisonAI](https://github.com/MervinPraison/PraisonAI) (~3.5k stars)
- **Pattern:** YAML agent definitions (role, instructions, backstory, goal, tasks, tools). planning_llm, reasoning, memory config.
- **Hedef roller:** Tüm roller (YAML pattern transferable)

### 11. EvoAgentX
- **URL:** [github.com/EvoAgentX/EvoAgentX](https://github.com/EvoAgentX/EvoAgentX) (~1.2k stars)
- **Pattern:** Self-evolving agent prompts — TextGrad/MIPRO ile iteratif feedback loops ile otomatik prompt optimizasyonu
- **Hedef roller:** Tüm roller (meta-optimization)

---

## Kategori 3: AI Coding Agent'lar (Zengin Prompt Pattern'ler)

### 12. OpenHands (formerly OpenDevin)
- **URL:** [github.com/OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) (~65k stars)
- **Pattern:** AgentHub, hierarchical delegation, standardized vocabulary
- **Hedef roller:** Backend/Frontend Developer, Integration Engineer, SDET

### 13. SWE-agent (Princeton, NeurIPS 2024)
- **URL:** [github.com/SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) (~18k stars)
- **Pattern:** Agent-Computer Interface (ACI) — file navigation, editing, testing için custom commands
- **Hedef roller:** Backend/Frontend Developer, QA Bug Fixer, Security Bug Fixer

### 14. Aider
- **URL:** [github.com/Aider-AI/aider](https://github.com/Aider-AI/aider) (~30k stars)
- **Pattern:** Modular coder personas, repository map concept (codebase awareness)
- **Hedef roller:** Backend/Frontend Developer, Solution Architect

### 15. Goose (Block)
- **URL:** [github.com/block/goose](https://github.com/block/goose) (~17k stars)
- **Pattern:** MCP-based tool integration, extensible agent
- **Hedef roller:** DevOps Engineer, Integration Engineer, SRE

---

## Kategori 4: Prompt Koleksiyonları & Agent Skill Libraries

### 16. VoltAgent/awesome-claude-code-subagents ★★★
- **URL:** [github.com/VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) (~2k stars)
- **Pattern:** 100+ specialized subagents — core development, infrastructure, quality/security, data/AI kategorilerinde
- **Hedef roller:** **TÜM 18 ROL** — her rolün doğrudan analog'u var

### 17. wshobson/agents ★★★
- **URL:** [github.com/wshobson/agents](https://github.com/wshobson/agents) (~700 stars)
- **Pattern:** 112 specialized agents, 16 multi-agent orchestrators, 146 agent skills. Preset teams: review, debug, feature, fullstack, security, migration. Workflow: `backend-architect → database-architect → frontend-developer → test-automator → security-auditor → deployment-engineer → observability-engineer`
- **Hedef roller:** **TÜM 18 ROL** — neredeyse birebir pipeline eşleşmesi

### 18. Miaoge-Ge/coding-agent-skills
- **URL:** [github.com/Miaoge-Ge/coding-agent-skills](https://github.com/Miaoge-Ge/coding-agent-skills) (~200 stars)
- **Pattern:** Expert system prompts — Architecture, Deep Learning, Git/CI-CD workflows
- **Hedef roller:** Solution Architect, DevOps Engineer, Backend Developer

### 19. mitsuhiko/agent-prompts (Armin Ronacher - Flask yaratıcısı)
- **URL:** [github.com/mitsuhiko/agent-prompts](https://github.com/mitsuhiko/agent-prompts) (~600 stars)
- **Pattern:** Problem Analysis → Architecture Design → Task Breakdown → Detailed Planning pipeline
- **Hedef roller:** Solution Architect, Tech Lead, Business Analyst

### 20. Saik0s/agent-loop
- **URL:** [github.com/Saik0s/agent-loop](https://github.com/Saik0s/agent-loop) (~500 stars)
- **Pattern:** Orchestrator delegates to Architect, Builder, Tester. "think → think harder → ultrathink" progression. TDD-driven development.
- **Hedef roller:** Tech Lead, Backend Developer, SDET, QA Engineer

### 21. jwadow/agentic-prompts
- **URL:** [github.com/jwadow/agentic-prompts](https://github.com/jwadow/agentic-prompts) (~200 stars)
- **Pattern:** Project Orchestrator, Technical Leader, Expert Developer, Critic/Challenger. "Cynical agent" for challenging complexity.
- **Hedef roller:** Delivery Manager, Solution Architect, Security Reviewer

### 22. danielmiessler/Fabric ★★★
- **URL:** [github.com/danielmiessler/Fabric](https://github.com/danielmiessler/Fabric) (~30k stars)
- **Pattern:** IDENTITY/PURPOSE/STEPS prompt yapısı. Chain of Thought + Chain of Draft. Security analysis, code review, documentation pattern'leri.
- **Hedef roller:** Security Auditor, Technical Writer, QA Engineer

---

## Kategori 5: Üretim Araçları System Prompt'ları

### 23. x1xhlol/system-prompts-and-models-of-ai-tools ★★★
- **URL:** [github.com/x1xhlol/system-prompts-and-models-of-ai-tools](https://github.com/x1xhlol/system-prompts-and-models-of-ai-tools) (~15k stars)
- **İçerik:** Claude Code, Cursor, Devin AI, Augment Code, Windsurf, Replit, VSCode Agent, Kiro, Junie, Lovable, Manus tam system prompt'ları
- **Hedef roller:** Tüm roller (production-grade prompt patterns)

### 24. tallesborges/agentic-system-prompts
- **URL:** [github.com/tallesborges/agentic-system-prompts](https://github.com/tallesborges/agentic-system-prompts) (~500 stars)
- **İçerik:** Production AI coding agent system prompt'ları, tool documentation yapısı

### 25. EliFuzz/awesome-system-prompts
- **URL:** [github.com/EliFuzz/awesome-system-prompts](https://github.com/EliFuzz/awesome-system-prompts) (~300 stars)
- **İçerik:** Claude Code, Cursor, Devin, Kiro, Gemini, Codex system prompt'ları

---

## Kategori 6: Akademik Kaynaklar

### 26. FudanSELab/Agent4SE-Paper-List
- **URL:** [github.com/FudanSELab/Agent4SE-Paper-List](https://github.com/FudanSELab/Agent4SE-Paper-List)
- **İçerik:** 106 paper — requirements engineering, code generation, testing, debugging

### 27. kyegomez/awesome-multi-agent-papers
- **URL:** [github.com/kyegomez/awesome-multi-agent-papers](https://github.com/kyegomez/awesome-multi-agent-papers)
- **İçerik:** DyLAN (Dynamic LLM-Agent Networks), collaboration mechanisms

### 28. LLM-Based Multi-Agent Systems for SE
- **URL:** [arxiv.org/abs/2404.04834](https://arxiv.org/html/2404.04834v2)
- **İçerik:** Agent orchestration, communication, planning teorik framework'ü

---

## Kategori 7: Meta-Kaynaklar

### 29. e2b-dev/awesome-ai-agents
- **URL:** [github.com/e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents) (~12k stars)

### 30. e2b-dev/awesome-devins
- **URL:** [github.com/e2b-dev/awesome-devins](https://github.com/e2b-dev/awesome-devins) (~3k stars)

---

## Rol Bazlı Öncelik Matrisi

| Rol | En Faydalı Kaynaklar |
|---|---|
| **Business Analyst** | MetaGPT (PRD generation), mitsuhiko/agent-prompts (Problem Analysis) |
| **UX Designer** | AgentVerse (simulation), Fabric (pattern structure) |
| **Solution Architect** | MetaGPT (architecture docs), mitsuhiko/agent-prompts, coding-agent-skills |
| **Security Reviewer** | wshobson/agents (security-scanning), Fabric (security analysis) |
| **DBA** | AgentVerse (DBA demo), wshobson/agents (database-architect) |
| **Tech Lead** | Agyn (responsibility separation), MAGIS (Manager role), agent-loop (Orchestrator) |
| **Backend Developer** | VoltAgent subagents, OpenHands, SWE-agent (ACI patterns) |
| **Frontend Developer** | VoltAgent subagents, wshobson/agents (frontend-developer) |
| **Integration Engineer** | Goose (MCP extensibility), DevOpsGPT |
| **QA Engineer** | MAGIS (QA Agent), CAMEL-AI (role-playing), MetaGPT |
| **QA Bug Fixer** | SWE-agent (auto-fix), OpenHands (bug resolution) |
| **SDET** | agent-loop (TDD patterns), wshobson/agents (test-automator) |
| **Security Auditor** | wshobson/agents (security-auditor), Fabric (security patterns) |
| **Security Bug Fixer** | SWE-agent (fix patterns), OpenHands |
| **DevOps Engineer** | DevOpsGPT, wshobson/agents (kubernetes-ops), Goose |
| **SRE** | wshobson/agents (observability-engineer), Goose (MCP monitoring) |
| **Technical Writer** | ChatDev (documentation phase), Fabric (documentation patterns) |
| **Delivery Manager** | Agyn (organizational structure), MetaGPT (PM role), agentic-prompts |

---

## Çıkarılacak Temel Prompt Pattern'ler

1. **Document-driven communication** (MetaGPT): Yapısal artifact alışverişi, free-form chat değil
2. **IDENTITY/PURPOSE/STEPS yapısı** (Fabric): Net persona, hedef, execution steps bölümleri
3. **Role-playing with termination conditions** (CAMEL-AI): Paired agent etkileşim yönetimi
4. **Responsibility separation as first-class design** (Agyn): Açık rol sınırları
5. **Structured thinking progression** (agent-loop): "think → think harder → ultrathink"
6. **Agent-Computer Interface** (SWE-agent): Tool command tanımları
7. **Preset team workflows** (wshobson/agents): Önceden yapılandırılmış pipeline'lar
8. **YAML role definitions with backstory** (CrewAI, PraisonAI): Role + backstory + goal + tools
9. **Critic/Challenger pattern** (agentic-prompts): Cynical agent for complexity challenging
10. **Self-evolving prompts** (EvoAgentX): Otomatik prompt optimizasyonu
