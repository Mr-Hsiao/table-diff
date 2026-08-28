const { createApp, ref, reactive, computed } = Vue;

const FILE_OK = /\.(xlsx|xls|csv)$/i;

// ---- 访问口令(公网部署时后端配置 TABLE_DIFF_TOKEN 后启用) ----
const TOKEN_KEY = 'td_token';

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
}
function setToken(t) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch (e) {}
}

async function apiFetch(url, opts) {
  opts = opts || {};
  opts.headers = Object.assign({}, opts.headers);
  const t = getToken();
  if (t) opts.headers['X-Token'] = t;
  let r = await fetch(url, opts);
  if (r.status === 401) {
    const input = window.prompt('此服务需要访问口令才能使用,请输入(向管理员获取):');
    if (input && input.trim()) {
      setToken(input.trim());
      opts.headers['X-Token'] = input.trim();
      r = await fetch(url, opts);
      if (r.status === 401) window.alert('口令不正确,请重试');
    }
  }
  return r;
}

function exportUrl(path) {
  const t = getToken();
  return t ? (path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(t)) : path;
}

createApp({
  setup() {
    const view = ref('recon');
    const CN = ['一', '二', '三', '四', '五', '六'];

    const plans = ref([]);
    const planSel = ref('');
    const reconFiles = ref([]);
    const busy = ref(false);
    const reconStep = ref('setup');
    const runId = ref('');
    const stats = ref(null);
    const colStats = ref([]);
    const resultInfo = reactive({ plan_name: '' });
    const resultTables = ref([]);
    const result = reactive({ items: [] });
    const activeTab = ref('diff');
    const resultQuery = ref('');
    const dragOver = ref('');

    const editorMode = ref('new');
    const editorId = ref(null);
    const editorName = ref('');
    const editorTables = ref([]);

    const toast = reactive({ show: false, type: 'ok', msg: '' });
    let toastTimer = 0;
    const dialog = reactive({ show: false, title: '', msg: '', okText: '确定', danger: false });
    let dialogResolve = null;
    const qrMissing = ref(false);
    const qrSrc = ref('/qrcode.jpg');
    function qrError() {
      if (qrSrc.value === '/qrcode.jpg') { qrSrc.value = '/qrcode.png'; return; }
      qrMissing.value = true;
    }

    const selectedPlan = computed(() =>
      plans.value.find(p => String(p.id) === planSel.value) || null);

    const reconTables = computed(() =>
      selectedPlan.value ? selectedPlan.value.tables : []);

    const masterName = computed(() =>
      (resultTables.value[0] && resultTables.value[0].name) || '表一');

    const satName = computed(() => {
      const sats = (resultTables.value || []).slice(1);
      const names = sats.map(t => t && t.name).filter(Boolean);
      return names.length ? names.join('、') : '表二';
    });

    const reconReadyCount = computed(() =>
      reconTables.value.filter((_, i) => reconFiles.value[i]).length);

    const canRecon = computed(() => {
      if (!planSel.value) return false;
      const ts = reconTables.value;
      if (!ts.length) return false;
      return ts.every((_, i) => reconFiles.value[i]);
    });

    const tablesReady = computed(() => {
      if (!editorTables.value.length) return false;
      return editorTables.value.every(t => t.name && t.key);
    });

    const tabs = computed(() => [
      { key: 'diff', label: '有差异' },
      { key: 'master_only', label: masterName.value + '独有' },
      { key: 'table_only', label: satName.value + '独有' },
      { key: 'matched', label: '一致' },
    ]);

    const resultGroups = computed(() => {
      const q = resultQuery.value.trim().toLowerCase();
      const groups = [];
      const byTable = new Map();
      for (const it of result.items) {
        if (it.kind !== activeTab.value) continue;
        const note = noteOf(it);
        if (q) {
          const hay = `${it.key || ''} ${note}`.toLowerCase();
          if (!hay.includes(q)) continue;
        }
        if (!byTable.has(it.table)) byTable.set(it.table, { table: it.table, cols: [], rows: [] });
        const g = byTable.get(it.table);
        if (!g.cols.length && (it.cols || []).length) {
          g.cols = it.cols.map(c => ({ left: c.left, right: c.right }));
        }
        const pad = g.cols.map((c, i) => {
          const raw = (it.cols || [])[i] || {};
          return { left_val: raw.left_val || '', right_val: raw.right_val || '', equal: !!raw.equal };
        });
        g.rows.push({ key: it.key, kind: it.kind, cols: pad, note });
      }
      return Array.from(byTable.values());
    });

    function noteOf(it) {
      if (it.kind === 'diff') return '数值不一致';
      if (it.kind === 'matched') return '对比列全部一致';
      if (it.kind === 'master_only') return `「${masterName.value}」有,「${it.table}」无`;
      return `「${it.table}」有,「${masterName.value}」无`;
    }

    function cn(i) { return CN[i] || '?'; }

    function letterOf(label) {
      return String(label || '').replace(/^列/, '').split('(')[0].trim();
    }

    function fmtVal(v) {
      if (v === null || v === undefined || v === '') return '';
      const n = Number(v);
      return Number.isNaN(n) ? String(v) : (Number.isInteger(n) ? String(n) : n.toFixed(2));
    }

    function fmtSize(n) {
      if (!n && n !== 0) return '';
      if (n < 1024) return n + ' B';
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      return (n / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function itemsOf(kind) {
      return result.items.filter(i => i.kind === kind);
    }

    function showToast(msg, type) {
      toast.msg = msg;
      toast.type = type || 'ok';
      toast.show = true;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => { toast.show = false; }, 2800);
    }

    function ask(title, msg, opts) {
      opts = opts || {};
      return new Promise(resolve => {
        dialog.title = title;
        dialog.msg = msg;
        dialog.okText = opts.okText || '确定';
        dialog.danger = !!opts.danger;
        dialog.show = true;
        dialogResolve = resolve;
      });
    }

    function closeDialog(ok) {
      dialog.show = false;
      if (dialogResolve) dialogResolve(ok);
      dialogResolve = null;
    }

    function isOkFile(file) {
      return file && FILE_OK.test(file.name);
    }

    function pickFile(onPicked) {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.xlsx,.xls,.csv';
      input.onchange = () => {
        const file = input.files && input.files[0];
        if (file) onPicked(file);
      };
      input.click();
    }

    function onDragOver(key) { dragOver.value = key; }
    function onDragLeave() { dragOver.value = ''; }

    async function loadPlans() {
      const r = await apiFetch('/api/plans');
      const d = await r.json();
      plans.value = d.plans || [];
    }

    function switchView(v) {
      view.value = v;
      loadPlans();
      if (v === 'plans') resetEditor();
    }

    function setReconFile(i, file) {
      if (!isOkFile(file)) {
        showToast('请上传 Excel 或 CSV 文件', 'err');
        return;
      }
      const next = reconFiles.value.slice();
      next[i] = file;
      reconFiles.value = next;
      dragOver.value = '';
    }

    function pickReconFile(i) {
      pickFile(file => setReconFile(i, file));
    }

    function dropReconFile(i, e) {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      setReconFile(i, file);
    }

    function clearReconFile(i) {
      const next = reconFiles.value.slice();
      next[i] = null;
      reconFiles.value = next;
    }

    async function runRecon() {
      const fd = new FormData();
      fd.append('plan_id', planSel.value);
      reconTables.value.forEach((_, i) => {
        if (reconFiles.value[i]) fd.append('files', reconFiles.value[i]);
      });
      busy.value = true;
      try {
        const r = await apiFetch('/api/recon', { method: 'POST', body: fd });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || '对账失败');
        runId.value = d.run_id;
        stats.value = d.stats;
        colStats.value = d.col_stats || [];
        resultInfo.plan_name = d.plan_name || '';
        resultTables.value = d.tables || [];
        result.items = d.items || [];
        activeTab.value = 'diff';
        resultQuery.value = '';
        reconStep.value = 'result';
        showToast('对账完成');
      } catch (e) {
        showToast('对账失败: ' + e.message, 'err');
      } finally {
        busy.value = false;
      }
    }

    function exportCsv() {
      if (runId.value) window.location.href = exportUrl('/api/export/' + runId.value);
    }

    function resetRecon() {
      reconStep.value = 'setup';
      reconFiles.value = [];
      planSel.value = '';
      resultTables.value = [];
      colStats.value = [];
      resultQuery.value = '';
    }

    function newTable(name) {
      return { name, key: '', has_header: true, comparisons: [], labels: [], fileName: '' };
    }

    function resetEditor() {
      editorMode.value = 'new';
      editorId.value = null;
      editorName.value = '';
      const t1 = newTable('表一');
      const t2 = newTable('表二');
      t2.comparisons = [{ left: '', right: '', tolerance: '0.01' }];
      editorTables.value = [t1, t2];
    }

    function addTable() {
      if (editorTables.value.length < 6) {
        const t = newTable('表' + cn(editorTables.value.length));
        t.comparisons = [{ left: '', right: '', tolerance: '0.01' }];
        editorTables.value.push(t);
      }
    }

    function removeTable(i) {
      if (i > 0 && editorTables.value.length > 2) {
        editorTables.value.splice(i, 1);
      }
    }

    async function onTableFile(ti, file) {
      if (!isOkFile(file)) {
        showToast('请上传 Excel 或 CSV 文件', 'err');
        return;
      }
      const t = editorTables.value[ti];
      const fd = new FormData();
      fd.append('file', file);
      fd.append('has_header', t.has_header ? '1' : '0');
      try {
        const r = await apiFetch('/api/preview', { method: 'POST', body: fd });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || '预览失败');
        t.fileName = file.name;
        t.labels = d.labels || [];
        if (!t.key && d.suggested_key) t.key = d.suggested_key;
        dragOver.value = '';
        showToast('已识别 ' + (t.labels.length || 0) + ' 列');
      } catch (e) {
        showToast('预览失败: ' + e.message, 'err');
      }
    }

    function pickEditorFile(ti) {
      pickFile(file => onTableFile(ti, file));
    }

    function dropEditorFile(ti, e) {
      const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      onTableFile(ti, file);
    }

    function editPlan(p) {
      view.value = 'plans';
      editorMode.value = 'edit';
      editorId.value = p.id;
      editorName.value = p.name;
      editorTables.value = (p.tables || []).map(t => ({
        name: t.name,
        key: t.key,
        has_header: !!t.has_header,
        comparisons: (t.comparisons || []).map(c => ({
          left: c.left || '',
          right: c.right || '',
          tolerance: c.tolerance !== undefined && c.tolerance !== null ? String(c.tolerance) : '0.01',
        })),
        labels: [],
        fileName: '',
      }));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    async function savePlan() {
      const tables = editorTables.value.map(t => ({
        name: t.name.trim(),
        key: t.key,
        has_header: t.has_header ? 1 : 0,
        comparisons: (t.comparisons || [])
          .filter(c => c.left && c.right)
          .map(c => ({
            left: c.left,
            right: c.right,
            tolerance: c.tolerance === '' || c.tolerance === undefined
              ? 0.01 : Number(c.tolerance),
          })),
      }));
      const fd = new FormData();
      fd.append('name', editorName.value.trim());
      fd.append('tables', JSON.stringify(tables));
      const url = editorMode.value === 'edit' ? '/api/plans/' + editorId.value : '/api/plans';
      try {
        const r = await apiFetch(url, { method: editorMode.value === 'edit' ? 'PUT' : 'POST', body: fd });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || '保存失败');
        await loadPlans();
        resetEditor();
        showToast('映射已保存');
      } catch (e) {
        showToast('保存失败: ' + e.message, 'err');
      }
    }

    async function deletePlan(id) {
      const ok = await ask('删除映射', '确定删除该映射？此操作不可撤销。', { okText: '删除', danger: true });
      if (!ok) return;
      const r = await apiFetch('/api/plans/' + id, { method: 'DELETE' });
      if (!r.ok) {
        showToast('删除失败', 'err');
        return;
      }
      await loadPlans();
      if (planSel.value === String(id)) planSel.value = '';
      showToast('映射已删除');
    }

    resetEditor();
    loadPlans();

    return {
      view, switchView,
      plans, planSel, selectedPlan, reconTables, reconFiles, busy, canRecon, reconReadyCount,
      reconStep, runId, stats, colStats, resultInfo, result, activeTab, tabs, resultGroups, resultQuery,
      itemsOf, fmtVal, fmtSize, cn, setReconFile, pickReconFile, dropReconFile, clearReconFile,
      runRecon, exportCsv, resetRecon, masterName, satName,
      dragOver, onDragOver, onDragLeave,
      editorMode, editorId, editorName, editorTables, tablesReady, letterOf,
      addTable, removeTable, onTableFile, pickEditorFile, dropEditorFile,
      savePlan, editPlan, deletePlan, resetEditor,
      toast, dialog, closeDialog, qrMissing, qrSrc, qrError,
    };
  },
}).mount('#app');
