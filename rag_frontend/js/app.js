/* ============================================================
   FMEA 风险智能台 · KG-RAG Console
   Frontend application logic
   ============================================================ */

const RPN_BUCKETS = [
    { label: '1-25', min: 1, max: 25, level: 'low' },
    { label: '26-50', min: 26, max: 50, level: 'low' },
    { label: '51-75', min: 51, max: 75, level: 'mid' },
    { label: '76-100', min: 76, max: 100, level: 'mid' },
    { label: '101-125', min: 101, max: 125, level: 'elevated' },
    { label: '126-150', min: 126, max: 150, level: 'elevated' },
    { label: '151-200', min: 151, max: 200, level: 'high' },
    { label: '200+', min: 201, max: Infinity, level: 'high' },
];

const RISK_COLORS = {
    low: 'var(--risk-low)',
    mid: 'var(--risk-mid)',
    elevated: 'var(--risk-elevated)',
    high: 'var(--risk-high)',
};

const GAUGE_MAX = 250;

class FmeaRagApp {
    constructor() {
        this.storageKey = 'fmeaKgRagConsole.v3';
        this.sessions = {};
        this.currentSessionId = null;
        this.activeAnswerTab = 'summary';
        this.activeQueryMode = '标准检索';
        this.config = {
            topK: 3,
            csvPath: '',
            defaultCsvPath: '',
            fmeaApiBase: '',
            theme: '',
            sidebarCollapsed: false,
        };
        this.isSending = false;
        this.isBuilding = false;

        this.quickPromptGroups = [
            {
                title: '高 RPN 故障查询',
                prompts: [
                    'RPN 排名前五的失效模式有哪些？',
                    'RPN 值超过 100 的失效模式有哪些？',
                    '根据 RPN 数值，目前风险最高的失效模式是什么？',
                ],
            },
            {
                title: '严重度分析',
                prompts: [
                    '严重度最高的失效模式有哪些？',
                    '动力电池对应的潜在失效模式是什么？',
                    '比较"动力电池"和"电池组箱体"的平均 RPN。',
                ],
            },
            {
                title: '措施推荐',
                prompts: [
                    '文档中提到的现行预防性设计控制主要类型有哪些？',
                    '针对 RPN 最高的失效模式，其临时采取的措施是什么？',
                    '哪些失效原因属于设计缺陷？',
                ],
            },
        ];

        this.navMeta = {
            overview: { title: '风险概览', subtitle: 'DFMEA 知识图谱检索问答工作台' },
            evidence: { title: '证据链', subtitle: '检索上下文与图谱证据溯源' },
            graph: { title: '图谱管理', subtitle: 'FMEA 知识图谱构建与维护' },
        };

        this.initElements();
        this.initTheme();
        this.bindEvents();
        this.loadFromStorage();
        this.applySidebarState();
        this.renderQuickPrompts();
        this.renderHistory();
        this.renderRpnBars([]);
        this.renderGauge(null);
        this.renderCurrentSession();
        this.loadStatus();
    }

    initElements() {
        const $ = (id) => document.getElementById(id);
        this.app = $('app');
        this.sidebar = $('sidebar');
        this.newChatBtn = $('newChatBtn');
        this.collapseSidebarBtn = $('collapseSidebarBtn');
        this.openSidebarBtn = $('openSidebarBtn');
        this.navStack = $('navStack');
        this.chatHistory = $('chatHistory');
        this.historyCount = $('historyCount');
        this.quickPrompts = $('quickPrompts');
        this.serviceStatus = $('serviceStatus');
        this.serviceStatusText = $('serviceStatusText');

        this.pageTitle = $('pageTitle');
        this.pageSubtitle = $('pageSubtitle');
        this.datasetChip = $('datasetChip');
        this.defaultCsvLabel = $('defaultCsvLabel');
        this.topKInput = $('topKInput');
        this.topKMinus = $('topKMinus');
        this.topKPlus = $('topKPlus');
        this.saveTopKBtn = $('saveTopKBtn');
        this.themeToggle = $('themeToggle');
        this.toggleInspectorBtn = $('toggleInspectorBtn');

        this.riskOverview = $('riskOverview');
        this.metricMaxRpn = $('metricMaxRpn');
        this.metricMaxRpnLabel = $('metricMaxRpnLabel');
        this.metricHighRisk = $('metricHighRisk');
        this.metricHighRiskLabel = $('metricHighRiskLabel');
        this.metricAvgRpn = $('metricAvgRpn');
        this.overviewEvidenceCount = $('overviewEvidenceCount');
        this.rpnBars = $('rpnBars');
        this.riskGauge = $('riskGauge');
        this.metrics = document.querySelector('.metrics');

        this.questionForm = $('questionForm');
        this.messageInput = $('messageInput');
        this.sendBtn = $('sendBtn');
        this.modeChips = $('modeChips');
        this.currentModeLabel = $('currentModeLabel');

        this.answerTabs = $('answerTabs');
        this.copyAnswerBtn = $('copyAnswerBtn');
        this.exportAnswerBtn = $('exportAnswerBtn');
        this.chatContainer = $('chatContainer');
        this.answerPanel = document.querySelector('.answer');
        this.composer = document.querySelector('.composer');

        this.inspector = $('inspector');
        this.closeInspectorBtn = $('closeInspectorBtn');
        this.evidencePanel = $('evidencePanel');
        this.evidenceCount = $('evidenceCount');
        this.graphStateLabel = $('graphStateLabel');
        this.graphPanel = $('graphPanel');
        this.csvPathInput = $('csvPathInput');
        this.resetCsvPathBtn = $('resetCsvPathBtn');
        this.buildGraphBtn = $('buildGraphBtn');
        this.clearGraphBtn = $('clearGraphBtn');
        this.apiBaseLabel = $('apiBaseLabel');
        this.inspectorCsvLabel = $('inspectorCsvLabel');
        this.rawContextPanel = $('rawContextPanel');

        this.confirmClearModal = $('confirmClearModal');
        this.clearConfirmCheck = $('clearConfirmCheck');
        this.confirmClearBtn = $('confirmClearBtn');
        this.cancelClearBtn = $('cancelClearBtn');
        this.cancelClearIcon = $('cancelClearIcon');

        this.scrim = $('scrim');
        this.toastStack = $('toastStack');
    }

    /* ---------- Theme ---------- */
    initTheme() {
        let theme = '';
        try {
            const raw = localStorage.getItem(this.storageKey);
            if (raw) theme = (JSON.parse(raw).config || {}).theme || '';
        } catch (_) { /* ignore */ }
        if (!theme) {
            theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        this.config.theme = theme;
        document.documentElement.dataset.theme = theme;
    }

    toggleTheme() {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        this.config.theme = next;
        this.saveToStorage();
        // re-render gauge so it picks up themed colors
        const message = this.latestAssistant();
        this.renderGauge(this.computeStats(message).max);
    }

    /* ---------- Events ---------- */
    bindEvents() {
        this.newChatBtn.addEventListener('click', () => this.createNewSession(true));
        this.collapseSidebarBtn.addEventListener('click', () => this.toggleSidebarCollapse());
        this.openSidebarBtn.addEventListener('click', () => this.toggleSidebar());

        this.navStack.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-nav-target]');
            if (btn) this.handleNav(btn.dataset.navTarget);
        });

        this.questionForm.addEventListener('submit', (e) => { e.preventDefault(); this.sendQuestion(); });
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendQuestion(); }
        });
        this.messageInput.addEventListener('input', () => { this.autoResize(); this.updateSendState(); });

        this.chatHistory.addEventListener('click', (e) => {
            const item = e.target.closest('[data-session-id]');
            if (!item) return;
            if (e.target.closest('[data-delete-session]')) { this.deleteSession(item.dataset.sessionId); return; }
            this.selectSession(item.dataset.sessionId);
            this.closeMobileSidebar();
        });

        this.quickPrompts.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-prompt]');
            if (btn) { this.usePrompt(btn.dataset.prompt); this.closeMobileSidebar(); }
        });

        this.answerTabs.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-answer-tab]');
            if (!btn) return;
            this.activeAnswerTab = btn.dataset.answerTab;
            this.renderCurrentSession();
        });

        this.modeChips.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-query-mode]');
            if (!btn) return;
            this.activeQueryMode = btn.dataset.queryMode;
            this.syncModeChips();
            this.showToast(`查询模式：${this.activeQueryMode}`, 'info');
            this.saveToStorage();
        });

        this.copyAnswerBtn.addEventListener('click', () => this.copyLatestAnswer());
        this.exportAnswerBtn.addEventListener('click', () => this.exportLatestAnswer());

        this.resetCsvPathBtn.addEventListener('click', () => {
            this.csvPathInput.value = this.config.defaultCsvPath || 'data/dfmea_final.csv';
            this.saveConfigFromInputs();
            this.showToast('已恢复默认 CSV 路径', 'success');
        });
        this.buildGraphBtn.addEventListener('click', () => this.createGraph());
        this.clearGraphBtn.addEventListener('click', () => this.showClearConfirm());
        this.cancelClearBtn.addEventListener('click', () => this.hideClearConfirm());
        this.cancelClearIcon.addEventListener('click', () => this.hideClearConfirm());
        this.clearConfirmCheck.addEventListener('change', () => { this.confirmClearBtn.disabled = !this.clearConfirmCheck.checked; });
        this.confirmClearBtn.addEventListener('click', () => this.clearGraph());
        this.confirmClearModal.addEventListener('click', (e) => { if (e.target === this.confirmClearModal) this.hideClearConfirm(); });

        this.topKMinus.addEventListener('click', () => this.bumpTopK(-1));
        this.topKPlus.addEventListener('click', () => this.bumpTopK(1));
        this.saveTopKBtn.addEventListener('click', () => this.applyTopK());
        this.topKInput.addEventListener('change', () => this.saveConfigFromInputs());
        this.csvPathInput.addEventListener('change', () => this.saveConfigFromInputs());

        this.serviceStatus.addEventListener('click', () => this.loadStatus());
        this.datasetChip.addEventListener('click', () => this.openInspector('graph'));
        this.themeToggle.addEventListener('click', () => this.toggleTheme());
        this.toggleInspectorBtn.addEventListener('click', () => this.toggleInspector());
        this.closeInspectorBtn.addEventListener('click', () => this.closeInspector());

        this.metrics.addEventListener('click', (e) => {
            const tile = e.target.closest('[data-metric-action]');
            if (tile) this.handleMetricAction(tile.dataset.metricAction);
        });
        this.rpnBars.addEventListener('click', (e) => {
            const bar = e.target.closest('[data-bucket]');
            if (bar) this.handleRpnRange(bar);
        });

        this.scrim.addEventListener('click', () => { this.closeMobileSidebar(); this.closeInspector(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { this.hideClearConfirm(); this.closeInspector(); this.closeMobileSidebar(); }
        });
        window.addEventListener('resize', () => this.syncOverlays());
    }

    /* ---------- Navigation / layout ---------- */
    handleNav(target) {
        this.setActiveNav(target);
        const meta = this.navMeta[target];
        if (meta) { this.pageTitle.textContent = meta.title; this.pageSubtitle.textContent = meta.subtitle; }
        if (target === 'overview') {
            document.querySelector('.content').scrollTo({ top: 0, behavior: 'smooth' });
            this.flash(this.riskOverview);
        } else if (target === 'evidence') {
            this.activeAnswerTab = 'evidence';
            this.renderCurrentSession();
            this.openInspector('evidence');
        } else if (target === 'graph') {
            this.openInspector('graph');
        }
        this.closeMobileSidebar();
    }

    setActiveNav(target) {
        this.navStack.querySelectorAll('[data-nav-target]').forEach((b) => b.classList.toggle('is-active', b.dataset.navTarget === target));
    }

    toggleSidebarCollapse() {
        this.config.sidebarCollapsed = !this.config.sidebarCollapsed;
        this.applySidebarState();
        this.saveToStorage();
    }
    applySidebarState() {
        this.app.classList.toggle('sidebar-collapsed', !!this.config.sidebarCollapsed);
    }
    toggleSidebar() {
        if (window.innerWidth <= 1024) {
            this.app.classList.contains('sidebar-open') ? this.closeMobileSidebar() : this.openMobileSidebar();
        } else {
            this.toggleSidebarCollapse();
        }
    }
    openMobileSidebar() { this.app.classList.remove('sidebar-collapsed'); this.app.classList.add('sidebar-open'); this.syncOverlays(); }
    closeMobileSidebar() { this.app.classList.remove('sidebar-open'); this.syncOverlays(); }

    toggleInspector() { this.inspector.classList.contains('is-collapsed') ? this.openInspector() : this.closeInspector(); }
    openInspector(focus = 'evidence') {
        this.inspector.classList.remove('is-collapsed');
        this.toggleInspectorBtn.classList.add('icon-btn');
        if (focus === 'graph') {
            this.setActiveNav('graph');
            this.flash(this.graphPanel);
            this.csvPathInput.focus();
        } else {
            this.flash(this.evidencePanel);
        }
        this.syncOverlays();
    }
    closeInspector() { this.inspector.classList.add('is-collapsed'); this.syncOverlays(); }

    syncOverlays() {
        const mobile = window.innerWidth <= 1024;
        const sidebarOpen = this.app.classList.contains('sidebar-open');
        const inspectorOpen = !this.inspector.classList.contains('is-collapsed');
        const showScrim = sidebarOpen || (inspectorOpen && mobile);
        this.scrim.hidden = !showScrim;
        requestAnimationFrame(() => this.scrim.classList.toggle('is-visible', showScrim));
    }

    flash(el) {
        if (!el) return;
        el.classList.remove('focus-pulse');
        void el.offsetWidth;
        el.classList.add('focus-pulse');
        setTimeout(() => el.classList.remove('focus-pulse'), 1200);
    }

    handleMetricAction(action) {
        if (action === 'evidence') {
            this.activeAnswerTab = 'evidence';
            this.renderCurrentSession();
            this.openInspector('evidence');
            return;
        }
        this.activeAnswerTab = 'data';
        this.renderCurrentSession();
        this.scrollAnswerIntoView();
        if (action === 'high-risk' || action === 'max-risk') this.showToast('已切换到数据视图，便于查看高风险项', 'info');
    }

    handleRpnRange(bar) {
        this.rpnBars.querySelectorAll('[data-bucket]').forEach((b) => b.classList.toggle('is-active', b === bar));
        const { label, min, max } = bar.dataset;
        const rangeText = max && max !== 'Infinity' ? `${min} 到 ${max}` : `${min} 以上`;
        const prompt = `列出 RPN 在 ${rangeText} 区间的失效模式，并说明对应项目、主要原因和建议措施。`;
        this.fillPrompt(prompt);
        this.setActiveNav('overview');
        this.scrollComposerIntoView();
        this.showToast(`已选择 RPN 区间：${label}，可直接发送查询`, 'info');
    }

    scrollAnswerIntoView() { this.answerPanel?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    scrollComposerIntoView() { this.composer?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }

    fillPrompt(prompt) {
        this.messageInput.value = prompt;
        this.autoResize();
        this.updateSendState();
        this.messageInput.focus();
    }

    /* ---------- Status / storage ---------- */
    async loadStatus() {
        this.setServiceState('checking', '检查服务中');
        try {
            const data = await this.fetchJson('/api/status');
            this.config.fmeaApiBase = data.fmeaApiBase || this.config.fmeaApiBase;
            this.config.defaultCsvPath = data.defaultCsvPath || this.config.defaultCsvPath;
            if (!this.config.csvPath) this.config.csvPath = this.config.defaultCsvPath;
            this.csvPathInput.value = this.config.csvPath || this.config.defaultCsvPath || '';
            this.topKInput.value = this.config.topK;
            this.apiBaseLabel.textContent = this.compactPath(this.config.fmeaApiBase, 30);
            this.apiBaseLabel.title = this.config.fmeaApiBase;
            this.defaultCsvLabel.textContent = this.basename(this.config.defaultCsvPath) || '—';
            this.defaultCsvLabel.title = this.config.defaultCsvPath;
            this.inspectorCsvLabel.textContent = this.compactPath(this.config.defaultCsvPath, 28);
            this.inspectorCsvLabel.title = this.config.defaultCsvPath;
            this.setServiceState('ready', '服务连接正常');
            this.saveToStorage();
        } catch (error) {
            this.setServiceState('error', '服务未连接');
            this.showToast(error.message || '无法读取服务状态', 'error');
        }
    }

    loadFromStorage() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            if (!raw) { this.topKInput.value = this.config.topK; return; }
            const parsed = JSON.parse(raw);
            this.sessions = parsed.sessions || {};
            this.currentSessionId = parsed.currentSessionId || null;
            this.activeAnswerTab = parsed.activeAnswerTab || 'summary';
            this.activeQueryMode = parsed.activeQueryMode || this.activeQueryMode;
            this.config = { ...this.config, ...(parsed.config || {}) };
            this.topKInput.value = this.config.topK || 3;
            this.csvPathInput.value = this.config.csvPath || '';
            this.syncModeChips();
        } catch (error) { console.warn('无法加载本地状态', error); }
    }

    saveToStorage() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify({
                sessions: this.sessions,
                currentSessionId: this.currentSessionId,
                activeAnswerTab: this.activeAnswerTab,
                activeQueryMode: this.activeQueryMode,
                config: this.config,
            }));
        } catch (error) { console.warn('无法保存本地状态', error); }
    }

    saveConfigFromInputs() {
        this.config.topK = this.getTopK();
        this.config.csvPath = this.csvPathInput.value.trim();
        this.saveToStorage();
    }

    /* ---------- Sessions ---------- */
    createNewSession(select = false) {
        const id = `session_${Date.now()}`;
        this.sessions[id] = { id, title: '新的 DFMEA 分析', messages: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() };
        if (select) { this.currentSessionId = id; this.activeAnswerTab = 'summary'; this.renderCurrentSession(); }
        this.renderHistory();
        this.saveToStorage();
        this.closeMobileSidebar();
        return this.sessions[id];
    }
    currentSession() {
        if (this.currentSessionId && this.sessions[this.currentSessionId]) return this.sessions[this.currentSessionId];
        const list = Object.values(this.sessions).sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
        if (list[0]) { this.currentSessionId = list[0].id; return list[0]; }
        return null;
    }
    selectSession(id) {
        if (!this.sessions[id]) return;
        this.currentSessionId = id;
        this.activeAnswerTab = 'summary';
        this.renderHistory();
        this.renderCurrentSession();
        this.saveToStorage();
    }
    deleteSession(id) {
        const session = this.sessions[id];
        if (!session) return;
        if (!window.confirm(`删除分析记录"${session.title}"？`)) return;
        delete this.sessions[id];
        if (this.currentSessionId === id) this.currentSessionId = null;
        this.renderHistory();
        this.renderCurrentSession();
        this.saveToStorage();
    }

    renderHistory() {
        const list = Object.values(this.sessions).sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
        this.historyCount.textContent = String(list.length);
        if (!list.length) { this.chatHistory.innerHTML = '<div class="empty empty--sm">暂无分析记录</div>'; return; }
        this.chatHistory.innerHTML = list.map((s) => {
            const active = s.id === this.currentSessionId ? 'is-active' : '';
            const last = [...s.messages].reverse().find((m) => m.role === 'assistant' || m.role === 'user');
            const subtitle = last ? this.truncate(last.content, 40) : '尚未提问';
            return `
                <div class="history-item ${active}" data-session-id="${s.id}">
                    <div class="history-item__row">
                        <strong>${this.escapeHtml(s.title)}</strong>
                        <button class="history-del" data-delete-session type="button" title="删除">×</button>
                    </div>
                    <span>${this.escapeHtml(subtitle)}</span>
                </div>`;
        }).join('');
    }

    renderQuickPrompts() {
        this.quickPrompts.innerHTML = this.quickPromptGroups.map((g) => `
            <div class="prompt-group">
                <div class="prompt-group__title">${this.escapeHtml(g.title)}</div>
                ${g.prompts.map((p) => `
                    <button class="prompt-btn" type="button" data-prompt="${this.escapeHtml(p)}">
                        <span>${this.escapeHtml(p)}</span><em>运行</em>
                    </button>`).join('')}
            </div>`).join('');
    }

    /* ---------- Render current session ---------- */
    latestAssistant() {
        const session = this.currentSession();
        return session ? [...session.messages].reverse().find((m) => m.role === 'assistant') || null : null;
    }

    renderCurrentSession() {
        this.syncTabs();
        const session = this.currentSession();
        const latest = this.latestAssistant();
        this.renderEvidence(latest);
        this.renderDashboard(latest);

        if (!session || session.messages.length === 0) { this.renderWelcome(); this.saveToStorage(); return; }

        if (this.activeAnswerTab === 'evidence') {
            this.chatContainer.innerHTML = this.evidenceSheet(latest);
        } else if (this.activeAnswerTab === 'data') {
            this.chatContainer.innerHTML = this.dataSheet(latest);
        } else if (this.activeAnswerTab === 'raw') {
            this.chatContainer.innerHTML = this.rawSheet(latest);
        } else {
            this.chatContainer.innerHTML = `<div class="answer-flow" style="display:flex;flex-direction:column;gap:16px">${session.messages.map((m, i) => this.messageTemplate(m, i)).join('')}</div>`;
            this.bindCopyButtons();
        }
        this.scrollChatToBottom();
        this.saveToStorage();
    }

    syncTabs() {
        this.answerTabs.querySelectorAll('[data-answer-tab]').forEach((b) => b.classList.toggle('is-active', b.dataset.answerTab === this.activeAnswerTab));
        this.syncModeChips();
    }
    syncModeChips() {
        this.modeChips.querySelectorAll('[data-query-mode]').forEach((b) => b.classList.toggle('is-active', b.dataset.queryMode === this.activeQueryMode));
        if (this.currentModeLabel) this.currentModeLabel.textContent = this.activeQueryMode;
    }

    renderWelcome() {
        const top = this.quickPromptGroups.flatMap((g) => g.prompts).slice(0, 5);
        this.chatContainer.innerHTML = `
            <div class="welcome">
                <div class="welcome__hero">
                    <span class="welcome__badge">READY FOR QUERY</span>
                    <h3>选择一个风险查询模板，或直接输入 DFMEA 问题开始分析</h3>
                    <p>默认呈现摘要与证据链。需要时可切换到"数据"或"原始"，查看结构化表格与图谱返回。</p>
                </div>
                <div class="flow">
                    <span>提出问题</span><button class="flow__arrow" type="button" tabindex="-1">→</button>
                    <span>图谱检索</span><button class="flow__arrow" type="button" tabindex="-1">→</button>
                    <span>证据链</span><button class="flow__arrow" type="button" tabindex="-1">→</button>
                    <span>措施建议</span>
                </div>
                <div class="welcome__list">
                    ${top.map((p, i) => `
                        <button class="welcome__row" type="button" data-welcome-prompt="${this.escapeHtml(p)}">
                            <span>${String(i + 1).padStart(2, '0')}</span><strong>${this.escapeHtml(p)}</strong>
                        </button>`).join('')}
                </div>
            </div>`;
        this.chatContainer.querySelectorAll('[data-welcome-prompt]').forEach((b) => b.addEventListener('click', () => this.usePrompt(b.dataset.welcomePrompt)));
    }

    messageTemplate(message, index) {
        const isUser = message.role === 'user';
        const kind = isUser ? 'is-user' : (message.error ? 'is-assistant is-error' : 'is-assistant');
        const meta = this.messageMeta(message);
        const answerFile = !isUser && message.answerFile ? `
            <div class="answer-file" title="${this.escapeHtml(message.answerFile)}">
                <span>结果文件</span><strong>${this.escapeHtml(this.compactPath(message.answerFile, 48))}</strong>
            </div>` : '';
        const actions = isUser ? '' : `
            <div class="bubble-actions"><button class="bubble-action" type="button" data-copy-message="${index}">复制</button></div>`;
        return `
            <article class="message ${kind}">
                <div class="message__meta">
                    <span class="message__who">${isUser ? 'USER' : 'FMEA · RAG'}</span>
                    <time>${this.formatTime(message.timestamp)}</time>
                    ${meta ? `<em>${this.escapeHtml(meta)}</em>` : ''}
                </div>
                <div class="bubble">${this.formatContent(message.content)}${answerFile}${actions}</div>
            </article>`;
    }
    messageMeta(m) {
        if (m.error && m.status) return `HTTP ${m.status}`;
        if (m.elapsedMs) return `${(m.elapsedMs / 1000).toFixed(1)}s`;
        return '';
    }

    evidenceSheet(message) {
        const evidence = this.normalizeEvidence(message?.context);
        if (!message) return '<div class="empty">暂无回答，尚未生成证据链。</div>';
        if (!evidence.length) return '<div class="empty">本次回答没有返回额外证据。</div>';
        return `
            <div class="sheet">
                <div class="sheet__title"><strong>检索证据链</strong><span>${evidence.length} 条上下文</span></div>
                <div>${evidence.map((it, i) => this.disclosure(it, i, i === 0)).join('')}</div>
            </div>`;
    }
    dataSheet(message) {
        const rows = this.deriveAnalysisRows(message);
        if (!message) return '<div class="empty">暂无回答，尚未生成分析数据。</div>';
        if (!rows.length) return '<div class="empty">当前返回中没有可结构化展示的数据明细。</div>';
        return `
            <div class="sheet">
                <div class="sheet__title"><strong>分析数据</strong><span>结构化呈现</span></div>
                <div class="table-wrap">
                    <table class="data-table">
                        <thead><tr><th>关键原因</th><th>关联失效模式</th><th>证据支持</th><th>RPN</th></tr></thead>
                        <tbody>${rows.map((r) => `
                            <tr>
                                <td>${this.escapeHtml(r.cause)}</td>
                                <td>${this.escapeHtml(r.failureMode)}</td>
                                <td>${this.escapeHtml(r.support)}</td>
                                <td><span class="risk-chip ${r.level}">${this.escapeHtml(r.rpn)}</span></td>
                            </tr>`).join('')}</tbody>
                    </table>
                </div>
            </div>`;
    }
    rawSheet(message) {
        if (!message) return '<div class="empty">暂无原始返回。</div>';
        return `<div class="sheet raw-sheet"><div class="sheet__title"><strong>原始返回</strong><span>调试 / 溯源</span></div><pre>${this.escapeHtml(JSON.stringify(message.raw || message.contextRaw || {}, null, 2))}</pre></div>`;
    }
    disclosure(item, index, open) {
        const labels = ['失效模式', '潜在原因', '推荐措施', '检索证据'];
        return `
            <details class="disclosure" ${open ? 'open' : ''}>
                <summary>
                    <span class="disclosure__idx">${index + 1}</span>
                    <span class="disclosure__title"><strong>${this.escapeHtml(this.truncate(item.title, 40))}</strong><em>${labels[index] || 'Context'}</em></span>
                    <svg class="disclosure__chev" viewBox="0 0 24 24" width="16" height="16"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                </summary>
                <pre>${this.escapeHtml(item.body)}</pre>
            </details>`;
    }

    bindCopyButtons() {
        this.chatContainer.querySelectorAll('[data-copy-message]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const session = this.currentSession();
                const m = session?.messages[Number(btn.dataset.copyMessage)];
                if (m) this.copyText(m.content, btn);
            });
        });
    }

    /* ---------- Dashboard rendering ---------- */
    renderDashboard(message) {
        const stats = this.computeStats(message);
        const evidence = this.normalizeEvidence(message?.context);
        this.overviewEvidenceCount.textContent = String(evidence.length);

        if (!stats.rpns.length) {
            this.metricMaxRpn.textContent = '—';
            this.metricAvgRpn.textContent = '—';
            this.metricHighRisk.textContent = '—';
            this.metricMaxRpnLabel.textContent = '等待查询';
            this.metricHighRiskLabel.textContent = 'RPN ≥ 100';
        } else {
            this.metricMaxRpn.textContent = String(stats.max);
            this.metricAvgRpn.textContent = String(stats.avg);
            this.metricHighRisk.textContent = String(stats.high);
            this.metricMaxRpnLabel.textContent = this.truncate(stats.maxLabel || '最高风险项', 12);
            this.metricHighRiskLabel.textContent = 'RPN ≥ 100';
        }
        this.renderRpnBars(stats.rpns);
        this.renderGauge(stats.rpns.length ? stats.max : null);
    }

    computeStats(message) {
        const rpns = this.extractRpns(message);
        if (!rpns.length) return { rpns: [], max: 0, avg: 0, high: 0, maxLabel: '' };
        const max = Math.max(...rpns);
        const avg = Math.round(rpns.reduce((a, b) => a + b, 0) / rpns.length);
        const high = rpns.filter((v) => v >= 100).length;
        return { rpns, max, avg, high, maxLabel: this.findMaxLabel(message, max) };
    }

    extractRpns(message) {
        if (!message) return [];
        const walk = (node, out) => {
            if (node == null) return;
            if (Array.isArray(node)) { node.forEach((n) => walk(n, out)); return; }
            if (typeof node === 'object') {
                for (const [k, v] of Object.entries(node)) {
                    if (/^rpn$/i.test(k)) { const n = Number(v); if (Number.isFinite(n) && n > 0) out.push(Math.round(n)); }
                    else walk(v, out);
                }
            }
        };
        // Take the first source that yields RPNs to avoid double-counting:
        // `raw` already embeds context/context_raw, so we never combine sources.
        for (const src of [message.contextRaw, message.context, message.raw]) {
            const out = [];
            walk(src, out);
            if (out.length) return out;
        }
        // heuristic fallback from derived rows
        const fallback = [];
        this.deriveAnalysisRows(message).forEach((r) => { const n = Number(r.rpn); if (Number.isFinite(n) && n > 0) fallback.push(n); });
        return fallback;
    }

    findMaxLabel(message, max) {
        const candidates = [];
        const walk = (node) => {
            if (node == null) return;
            if (Array.isArray(node)) { node.forEach(walk); return; }
            if (typeof node === 'object') {
                const rpn = Number(node.RPN ?? node.rpn);
                const mode = node.FailureMode || node.failureMode || node.mode;
                if (Number.isFinite(rpn) && mode) candidates.push({ rpn: Math.round(rpn), mode: String(mode) });
                Object.values(node).forEach(walk);
            }
        };
        walk(message.raw); walk(message.context); walk(message.contextRaw);
        const hit = candidates.find((c) => c.rpn === max);
        return hit ? hit.mode : '';
    }

    renderRpnBars(rpns) {
        const counts = RPN_BUCKETS.map((b) => rpns.filter((v) => v >= b.min && v <= b.max).length);
        const total = counts.reduce((a, b) => a + b, 0);
        const maxCount = Math.max(1, ...counts);
        const ghost = [16, 26, 40, 58, 76, 64, 46, 30]; // decorative baseline when no data
        this.rpnBars.innerHTML = RPN_BUCKETS.map((b, i) => {
            const has = total > 0;
            const pct = has ? Math.max(counts[i] ? 8 : 2, Math.round((counts[i] / maxCount) * 100)) : ghost[i];
            const color = RISK_COLORS[b.level];
            const opacity = has ? 1 : 0.32;
            const countText = has ? (counts[i] || '') : '';
            return `
                <div class="rpn-bar" data-bucket="${b.label}" data-label="${b.label}" data-min="${b.min}" data-max="${b.max}">
                    <span class="rpn-bar__count">${countText}</span>
                    <span class="rpn-bar__track"><span class="rpn-bar__fill" style="height:${pct}%;background:${color};opacity:${opacity}"></span></span>
                    <span class="rpn-bar__label">${b.label}</span>
                </div>`;
        }).join('');
    }

    renderGauge(value) {
        const r = 90, cx = 116, cy = 116, sw = 16;
        const arcLen = Math.PI * r;
        const has = Number.isFinite(value) && value > 0;
        const frac = has ? Math.min(1, value / GAUGE_MAX) : 0;
        const offset = arcLen * (1 - frac);
        const level = !has ? 'low' : value >= 150 ? 'high' : value >= 100 ? 'elevated' : value >= 60 ? 'mid' : 'low';
        const color = has ? RISK_COLORS[level] : 'var(--surface-3)';
        const path = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
        this.riskGauge.innerHTML = `
            <svg viewBox="0 0 232 144" role="img" aria-label="风险强度仪表">
                <path class="gauge__track" d="${path}" stroke-width="${sw}" stroke-linecap="round"/>
                <path class="gauge__value-arc" d="${path}" stroke-width="${sw}" stroke="${color}"
                      stroke-dasharray="${arcLen}" stroke-dashoffset="${offset}"/>
                <text class="gauge__num" x="${cx}" y="${cy - 16}" text-anchor="middle" font-size="36">${has ? value : '—'}</text>
                <text class="gauge__cap" x="${cx}" y="${cy + 4}" text-anchor="middle">最高 RPN</text>
                <text class="gauge__cap" x="${cx - r}" y="${cy + 24}" text-anchor="start" font-size="10">0</text>
                <text class="gauge__cap" x="${cx + r}" y="${cy + 24}" text-anchor="end" font-size="10">${GAUGE_MAX}+</text>
            </svg>`;
    }

    renderEvidence(message) {
        if (!message || message.role !== 'assistant') {
            this.evidenceCount.textContent = '0';
            this.evidencePanel.innerHTML = '<div class="empty empty--sm">暂无检索证据</div>';
            this.rawContextPanel.textContent = '暂无数据';
            return;
        }
        const evidence = this.normalizeEvidence(message.context);
        this.evidenceCount.textContent = String(evidence.length);
        this.evidencePanel.innerHTML = evidence.length
            ? evidence.slice(0, 6).map((it, i) => this.disclosure(it, i, i === 0)).join('')
            : '<div class="empty empty--sm">本次回答没有返回额外证据。</div>';
        this.rawContextPanel.textContent = JSON.stringify(message.raw || message.contextRaw || {}, null, 2);
    }

    /* ---------- Send / actions ---------- */
    async sendQuestion(explicit = null) {
        const question = (explicit || this.messageInput.value).trim();
        if (!question || this.isSending) return;
        let session = this.currentSession();
        if (!session) session = this.createNewSession(true);

        const first = session.messages.length === 0;
        session.messages.push({ role: 'user', content: question, timestamp: new Date().toISOString() });
        session.updatedAt = new Date().toISOString();
        if (first) session.title = this.truncate(question, 22);

        this.activeAnswerTab = 'summary';
        this.messageInput.value = '';
        this.autoResize();
        this.setSending(true);
        this.renderHistory();
        this.renderCurrentSession();
        this.showTyping();
        this.saveToStorage();

        try {
            const data = await this.fetchJson('/api/chat', {
                method: 'POST',
                body: JSON.stringify({ question: this.questionForMode(question), top_k: this.getTopK() }),
            });
            session.messages.push({
                role: 'assistant',
                content: data.answer || data.content || '未收到回答',
                timestamp: new Date().toISOString(),
                context: data.context || [],
                contextRaw: data.context_raw || [],
                answerFile: data.answer_file || null,
                elapsedMs: data.elapsed_ms || 0,
                raw: data.raw || data,
            });
            session.updatedAt = new Date().toISOString();
            this.setServiceState('ready', '问答完成');
        } catch (error) {
            session.messages.push({
                role: 'assistant',
                content: this.errorToText(error),
                timestamp: new Date().toISOString(),
                context: [], contextRaw: error.payload || {},
                status: error.status, error: true, raw: error.payload || {},
            });
            session.updatedAt = new Date().toISOString();
            this.setServiceState('error', error.status === 409 ? '需要建图' : '请求失败');
        } finally {
            this.setSending(false);
            this.removeTyping();
            this.renderHistory();
            this.renderCurrentSession();
            this.saveToStorage();
        }
    }

    async createGraph() {
        if (this.isBuilding) return;
        this.saveConfigFromInputs();
        const csvPath = this.config.csvPath || this.config.defaultCsvPath;
        if (!csvPath) { this.showToast('请先填写 CSV 路径', 'error'); return; }
        this.isBuilding = true;
        this.buildGraphBtn.disabled = true;
        this.buildGraphBtn.classList.add('is-loading');
        this.setServiceState('checking', '正在建图');
        this.showToast('已开始建立图谱，这一步可能需要一些时间', 'info');
        try {
            const data = await this.fetchJson('/api/create-graph', { method: 'POST', body: JSON.stringify({ path: csvPath }) });
            const sec = data.elapsed_ms ? `，耗时 ${(data.elapsed_ms / 1000).toFixed(1)}s` : '';
            this.graphStateLabel.textContent = '已建立';
            this.graphStateLabel.className = 'state-tag is-ready';
            this.setServiceState('ready', '图谱已就绪');
            this.showToast(`图谱建立完成${sec}`, 'success');
        } catch (error) {
            this.setServiceState('error', '建图失败');
            this.showToast(this.errorToText(error), 'error');
        } finally {
            this.isBuilding = false;
            this.buildGraphBtn.disabled = false;
            this.buildGraphBtn.classList.remove('is-loading');
        }
    }

    showClearConfirm() {
        this.clearConfirmCheck.checked = false;
        this.confirmClearBtn.disabled = true;
        this.confirmClearModal.classList.add('is-open');
        this.confirmClearModal.setAttribute('aria-hidden', 'false');
    }
    hideClearConfirm() {
        this.confirmClearModal.classList.remove('is-open');
        this.confirmClearModal.setAttribute('aria-hidden', 'true');
    }
    async clearGraph() {
        if (!this.clearConfirmCheck.checked) return;
        this.confirmClearBtn.disabled = true;
        this.confirmClearBtn.classList.add('is-loading');
        this.setServiceState('checking', '正在清空');
        try {
            const data = await this.fetchJson('/api/clear-graph', { method: 'POST', body: JSON.stringify({ confirm: true }) });
            this.hideClearConfirm();
            this.graphStateLabel.textContent = '未建立';
            this.graphStateLabel.className = 'state-tag';
            this.setServiceState('ready', '已清空图谱');
            this.showToast('FMEA 图谱已清空，可以重新导入 CSV', 'success');
            this.rawContextPanel.textContent = JSON.stringify(data.result || data, null, 2);
        } catch (error) {
            this.setServiceState('error', '清空失败');
            this.showToast(this.errorToText(error), 'error');
        } finally {
            this.confirmClearBtn.classList.remove('is-loading');
            this.confirmClearBtn.disabled = !this.clearConfirmCheck.checked;
        }
    }

    async applyTopK() {
        const topK = this.getTopK();
        this.config.topK = topK;
        this.topKInput.value = topK;
        this.saveToStorage();
        this.saveTopKBtn.disabled = true;
        try {
            await this.fetchJson('/api/top-k', { method: 'POST', body: JSON.stringify({ top_k: topK }) });
            this.showToast(`Top-K 已设置为 ${topK}`, 'success');
        } catch (error) {
            this.showToast(this.errorToText(error), 'error');
        } finally { this.saveTopKBtn.disabled = false; }
    }
    bumpTopK(delta) {
        const next = Math.min(20, Math.max(1, this.getTopK() + delta));
        this.topKInput.value = next;
        this.config.topK = next;
        this.saveToStorage();
    }
    usePrompt(prompt) { this.fillPrompt(prompt); this.sendQuestion(prompt); }

    copyLatestAnswer() {
        const latest = this.latestAssistant();
        if (!latest) { this.showToast('暂无可复制的回答', 'info'); return; }
        this.copyText(latest.content, this.copyAnswerBtn);
        this.showToast('已复制最新回答', 'success');
    }
    exportLatestAnswer() {
        const session = this.currentSession();
        const latest = this.latestAssistant();
        if (!latest) { this.showToast('暂无可导出的回答', 'info'); return; }
        const userMsg = session ? [...session.messages].reverse().find((m) => m.role === 'user') : null;
        const evidence = this.normalizeEvidence(latest.context);
        const lines = [
            `# FMEA 分析结果`, '',
            `**问题**：${userMsg ? userMsg.content : '—'}`, '',
            `## 回答`, '', latest.content, '',
        ];
        if (evidence.length) {
            lines.push('## 检索证据', '');
            evidence.forEach((it, i) => { lines.push(`### ${i + 1}. ${it.title}`, '', '```', it.body, '```', ''); });
        }
        const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `fmea_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.md`;
        a.click();
        URL.revokeObjectURL(url);
        this.showToast('已导出 Markdown', 'success');
    }

    /* ---------- Evidence / data helpers ---------- */
    normalizeEvidence(context) {
        if (context == null) return [];
        const list = Array.isArray(context) ? context : [context];
        return list.map((item) => {
            if (typeof item === 'string') return { title: 'Context', body: item, raw: item };
            if (item && typeof item === 'object') {
                const title = item.ProcessStep || item.FailureMode || item.PotentialFailureMode || item.metric || item.scope || 'Context';
                return { title: String(title), body: JSON.stringify(item, null, 2), raw: item };
            }
            return { title: 'Context', body: String(item), raw: item };
        }).filter((it) => it.body.trim());
    }
    deriveAnalysisRows(message) {
        if (!message) return [];
        const evidence = this.normalizeEvidence(message.context);
        return evidence.slice(0, 6).map((item, index) => {
            const src = item.raw && typeof item.raw === 'object' ? item.raw : {};
            const rpn = Number(src.RPN || src.rpn || src.Rpn || 0);
            const level = rpn >= 150 || (index === 0 && !rpn) ? 'high' : (rpn >= 100 || index < 3 ? 'medium' : 'low');
            return {
                cause: src.Cause || src.FailureCause || src.PotentialCause || src.reason || this.inferCause(item.body, index),
                failureMode: src.FailureMode || src.PotentialFailureMode || src.mode || item.title || 'Context',
                support: String(src.Support || src.score || src.weight || evidence.length - index),
                rpn: rpn ? String(rpn) : (level === 'high' ? '高' : level === 'medium' ? '中高' : '中'),
                level,
            };
        });
    }
    inferCause(body, index) {
        const m = String(body).match(/(?:原因|cause|Cause)["：:\s]+([^",，。\n]{2,28})/);
        if (m) return m[1].trim();
        return ['材料老化', '装配偏差', '环境影响', '检测覆盖不足', '设计余量不足', '过程控制不足'][index] || '上下文证据';
    }

    /* ---------- UI bits ---------- */
    showTyping() {
        const el = document.createElement('div');
        el.className = 'message is-assistant';
        el.id = 'typingIndicator';
        el.innerHTML = `<div class="message__meta"><span class="message__who">FMEA · RAG</span><time>检索中</time></div><div class="bubble" style="padding:0"><div class="typing"><span></span><span></span><span></span></div></div>`;
        this.chatContainer.appendChild(el);
        this.scrollChatToBottom();
    }
    removeTyping() { document.getElementById('typingIndicator')?.remove(); }

    setSending(s) {
        this.isSending = s;
        this.updateSendState();
        this.messageInput.disabled = s;
        this.sendBtn.classList.toggle('is-loading', s);
    }
    updateSendState() { this.sendBtn.disabled = this.isSending || !this.messageInput.value.trim(); }
    autoResize() { this.messageInput.style.height = 'auto'; this.messageInput.style.height = `${Math.min(168, Math.max(24, this.messageInput.scrollHeight))}px`; }
    setServiceState(state, text) {
        this.serviceStatus.classList.remove('is-ready', 'is-checking', 'is-error');
        this.serviceStatus.classList.add(`is-${state}`);
        this.serviceStatusText.textContent = text;
    }

    async fetchJson(url, options = {}) {
        const res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
        let data = null;
        try { data = await res.json(); } catch (_) { data = { detail: await res.text() }; }
        if (!res.ok) {
            const err = new Error(data.detail || data.error || data.message || `HTTP ${res.status}`);
            err.status = res.status; err.payload = data;
            throw err;
        }
        return data;
    }
    errorToText(error) {
        const detail = error?.payload?.detail || error?.message || String(error);
        if (error?.status === 409) return `${detail}\n\n请先在右侧"图谱管理"中使用 CSV 建立 FMEA 图谱，再重新提问。`;
        if (error?.status === 502) return `${detail}\n\n请确认 FMEA 后端已在仓库根目录通过 python code/kg_rag.py 启动。`;
        return detail;
    }
    questionForMode(question) {
        const mode = this.activeQueryMode || '标准检索';
        if (mode === '深度推理') return `${question}\n\n请进行深度推理：先列出关键证据，再说明推理链路、风险优先级和不确定性。`;
        if (mode === '原因追溯') return `${question}\n\n请重点追溯失效原因：按设计原因、制造/装配原因、环境原因和检测短板归类。`;
        if (mode === '措施推荐') return `${question}\n\n请重点输出可执行措施：区分预防性设计控制、探测性控制、临时措施和优先处理顺序。`;
        return question;
    }

    formatContent(content) {
        const text = String(content || '').trim();
        if (!text) return '';
        return this.escapeHtml(this.improveLineBreaks(text));
    }
    improveLineBreaks(text) {
        return text
            .replace(/；(?=\d+\)|\s*[^；。]{1,18}（项目）)/g, '；\n')
            .replace(/。(?=\d+\)|\s*[^。]{1,18}：)/g, '。\n');
    }

    async copyText(text, button) {
        try {
            await navigator.clipboard.writeText(text);
            if (button && button.classList.contains('bubble-action')) {
                button.classList.add('is-copied');
                const prev = button.textContent;
                button.textContent = '已复制';
                setTimeout(() => { button.classList.remove('is-copied'); button.textContent = prev; }, 1200);
            }
        } catch (_) { this.showToast('复制失败，请手动选择文本', 'error'); }
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${this.escapeHtml(message)}</span>`;
        this.toastStack.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('is-visible'));
        setTimeout(() => { toast.classList.remove('is-visible'); setTimeout(() => toast.remove(), 240); }, 3600);
    }

    /* ---------- Utils ---------- */
    getTopK() { const v = Number.parseInt(this.topKInput.value, 10); return Number.isFinite(v) ? Math.min(20, Math.max(1, v)) : 3; }
    formatTime(ts) { if (!ts) return ''; return new Date(ts).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', month: '2-digit', day: '2-digit' }); }
    basename(p) { const v = String(p || ''); const parts = v.split(/[\\/]/); return parts[parts.length - 1] || v; }
    compactPath(path, max = 42) {
        const v = String(path || '');
        if (v.length <= max) return v || '—';
        const head = Math.max(8, Math.floor(max * 0.35));
        const tail = Math.max(12, max - head - 3);
        return `${v.slice(0, head)}...${v.slice(-tail)}`;
    }
    truncate(text, len) { const v = String(text || '').replace(/\s+/g, ' ').trim(); return v.length > len ? `${v.slice(0, len)}...` : v; }
    escapeHtml(value) { const d = document.createElement('div'); d.textContent = String(value ?? ''); return d.innerHTML; }
    scrollChatToBottom() { if (this.activeAnswerTab === 'summary') this.chatContainer.scrollTop = this.chatContainer.scrollHeight; }
}

document.addEventListener('DOMContentLoaded', () => { window.fmeaRagApp = new FmeaRagApp(); });
