/* Navicat 仿真面板：做题时用图形界面完成建表、改数据、建视图/函数/触发器、写查询 */
"use strict";

/* 代码段库（查询页右侧面板用）：分类 + 名称 + SQL 模板 */
const NAV_SNIPPETS = [
  { name: "查询全部", cat: "查询", sql: "SELECT *\nFROM 表名;" },
  { name: "条件 + 排序 + 限量", cat: "查询", sql: "SELECT *\nFROM 表名\nWHERE 条件\nORDER BY 字段 DESC\nLIMIT 10;" },
  { name: "去重统计", cat: "查询", sql: "SELECT DISTINCT 字段\nFROM 表名;" },
  { name: "多表内连接", cat: "连接", sql: "SELECT a.*, b.*\nFROM 表a a\nINNER JOIN 表b b\n  ON a.字段 = b.字段;" },
  { name: "左连接", cat: "连接", sql: "SELECT a.*, b.*\nFROM 表a a\nLEFT JOIN 表b b\n  ON a.字段 = b.字段;" },
  { name: "三表连接", cat: "连接", sql: "SELECT a.*, b.*, c.*\nFROM 表a a\nINNER JOIN 表b b ON a.字段 = b.字段\nINNER JOIN 表c c ON b.字段 = c.字段;" },
  { name: "分组统计", cat: "聚合", sql: "SELECT 分组字段, COUNT(*) AS 数量\nFROM 表名\nGROUP BY 分组字段\nHAVING COUNT(*) > 1;" },
  { name: "合计 / 平均", cat: "聚合", sql: "SELECT SUM(字段) AS 合计, AVG(字段) AS 平均\nFROM 表名;" },
  { name: "子查询 IN", cat: "聚合", sql: "SELECT *\nFROM 表名\nWHERE 字段 IN (SELECT 字段 FROM 另一张表 WHERE 条件);" },
  { name: "建表", cat: "DDL", sql: "CREATE TABLE 表名 (\n  id INT UNSIGNED NOT NULL AUTO_INCREMENT,\n  name VARCHAR(50) NOT NULL,\n  PRIMARY KEY (id)\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;" },
  { name: "加字段", cat: "DDL", sql: "ALTER TABLE 表名\n  ADD COLUMN 新字段 VARCHAR(50) NOT NULL DEFAULT '';" },
  { name: "建视图", cat: "DDL", sql: "CREATE OR REPLACE VIEW 视图名 AS\nSELECT 字段\nFROM 表名\nWHERE 条件;" },
  { name: "插入数据", cat: "其他", sql: "INSERT INTO 表名 (字段1, 字段2)\nVALUES (值1, 值2);" },
  { name: "更新数据", cat: "其他", sql: "UPDATE 表名\nSET 字段 = 值\nWHERE 条件;" },
  { name: "删除数据", cat: "其他", sql: "DELETE FROM 表名\nWHERE 条件;" },
];

const NavicatPanel = {
  props: {
    drill: { type: Object, required: true },
    db: { type: String, default: "" },
    token: { type: String, default: "" },
    ready: { type: Boolean, default: true },
  },
  emits: ["log", "query", "toast", "changed"],
  template: "#navicat-tpl",

  data() {
    return {
      schema: { db: "", charset: "", collation: "", tables: [], views: [], routines: [], triggers: [] },
      loading: false,
      active: "objects",
      node: "tables",
      filter: "",
      selected: "",
      tabs: [],
      menu: "",
      // 查询页
      sqlText: "",
      queryResult: null,
      queryMsg: "",
      queryInfo: "",
      resultTab: "result",
      // 结果区 5 标签（视频 41.5s）：信息 / 摘要 / 结果 1 / 剖析 / 状态
      profileResult: null,
      // 右侧代码段面板（视频 41.5s）
      snippetPane: false, snipSearch: "", snipTag: "全部",
      running: false,
      lastQuerySql: "",
      cursor: { line: 1, col: 1 },
      // 表数据
      table: {
        name: "", kind: "table", columns: [], rows: [], total: 0,
        page: 0, size: 100, edits: {}, added: [], deleted: [],
        loading: false, filter: "", orderBy: "", orderDir: "ASC",
      },
      // 设计表
      design: this.blankDesign(),
      // 视图/例程/触发器编辑
      viewForm: { name: "", definition: "", mode: "new" },
      routineForm: { name: "", type: "PROCEDURE", params: "", returns: "INT",
                     body: "", comment: "", mode: "new" },
      triggerForm: { name: "", timing: "BEFORE", event: "INSERT", table: "",
                     statement: "", mode: "new" },
      // 弹窗
      dlg: "",
      build: this.blankBuilder(),
      newRow: { tid: "", col: "" },
      builderMode: false,
      // 创建图表（用当前查询结果画柱状/折线/饼图）
      chart: { open: false, type: "bar", x: "", y: "" },
      // 连接设置对话框（视频 8-21s：常规/高级/SSH/HTTP/SSL）
      connForm: { tab: "常规", name: "本地", host: "localhost", port: 3306, init: "",
                  user: "root", pw: "", db: "", socket: "tcp",
                  timeout: 0, keepAlive: 240, maxRows: 1000, compress: false, autoCommit: true,
                  ssh: false, sshHost: "", sshPort: 22, sshUser: "", sshAuth: "pw", sshPass: "",
                  http: false, ssl: false },
      connMsg: "",
      condPop: null,
      buildDragName: "",
      condOps: ["=", "<>", ">", "<", ">=", "<=", "LIKE", "NOT LIKE",
                "IN", "NOT IN", "BETWEEN", "IS NULL", "IS NOT NULL"],
      dragTable: null,
      dragJoin: null,
      dragPos: null,
      hoverJoin: null,
      ctx: { show: false, x: 0, y: 0, items: [] },
      stemOpen: false,
      mobileTree: false,
      runForm: { routine: null, args: "", result: null, msg: "" },
      importForm: { file: null, table: "", header: true, overwrite: false, busy: false },
      typeList: ["INT", "BIGINT", "TINYINT", "SMALLINT", "VARCHAR", "CHAR", "TEXT",
                 "LONGTEXT", "DATE", "DATETIME", "TIMESTAMP", "TIME", "DECIMAL",
                 "DOUBLE", "FLOAT", "BLOB", "JSON"],
    };
  },

  computed: {
    treeNodes() {
      return [
        { key: "tables", label: "表", icon: "table", count: this.schema.tables.length },
        { key: "views", label: "视图", icon: "file-text", count: this.schema.views.length },
        { key: "routines", label: "函数", icon: "code", count: this.schema.routines.length },
        { key: "triggers", label: "触发器", icon: "target", count: this.schema.triggers.length },
        { key: "queries", label: "查询", icon: "search", count: 0 },
        { key: "backup", label: "备份", icon: "folder-open", count: 0 },
      ];
    },
    nodeLabel() {
      const n = this.treeNodes.find(x => x.key === this.node);
      return n ? n.label : "对象";
    },
    objects() {
      if (this.node === "tables") return this.schema.tables;
      if (this.node === "views") return this.schema.views;
      if (this.node === "routines") return this.schema.routines;
      if (this.node === "triggers") return this.schema.triggers;
      return [];
    },
    filteredObjects() {
      const f = (this.filter || "").toLowerCase();
      return f ? this.objects.filter(o => String(o.name || "").toLowerCase().includes(f)) : this.objects;
    },
    selectedObject() {
      return this.objects.find(o => o.name === this.selected) || null;
    },
    currentTab() {
      return this.tabs.find(t => t.id === this.active) || null;
    },
    toolActive() {
      if (this.active === "query") return "query";
      if (this.node === "views") return "views";
      if (this.node === "routines") return "routines";
      if (this.node === "triggers") return "triggers";
      return "tables";
    },
    statusText() {
      if (this.loading) return "正在读取数据库结构…";
      return `${this.objects.length} ${this.nodeLabel}`;
    },
    tablePk() {
      const t = this.schema.tables.find(x => x.name === this.table.name);
      return (t && t.primaryKey) || [];
    },
    ctxKind() {
      return this.node === "views" ? "view"
        : this.node === "routines" ? "routine"
        : this.node === "triggers" ? "trigger" : "table";
    },
    tools() {
      return [
        { key: "conn", label: "连接", icon: "link", color: "#5b8def", cls: "nc-tool-conn" },
        { key: "query", label: "新建查询", icon: "search", color: "#e8833a" },
        { key: "tables", label: "表", icon: "table", color: "#3aa0e8" },
        { key: "views", label: "视图", icon: "file-text", color: "#7b61d1" },
        { key: "routines", label: "函数", icon: "code", color: "#c04fb0" },
        { key: "triggers", label: "触发器", icon: "target", color: "#d05c5c" },
        { key: "users", label: "用户", icon: "user", color: "#e0a92e" },
        { key: "other", label: "其他", icon: "menu", color: "#4c9a86" },
        { key: "backup", label: "备份", icon: "download", color: "#4c7fb0" },
      ];
    },
    designTypeOptions() {
      const set = new Set(this.typeList);
      (this.design.columns || []).forEach(c => { if (c.type) set.add(c.type); });
      return [...set];
    },
    // 查询创建工具左侧「对象」窗格：表 + 视图，可搜索，点一下加进图表
    builderObjects() {
      const f = String((this.build && this.build.search) || "").toLowerCase();
      const match = (o) => !f || String(o.name).toLowerCase().includes(f);
      return [
        { key: "tables", label: "表", icon: "table", items: (this.schema.tables || []).filter(match) },
        { key: "views", label: "视图", icon: "file-text", items: (this.schema.views || []).filter(match) },
      ];
    },
    // SQL 窗格：只读、关键字高亮（先转义再一次性替换，避免嵌套）
    builderSqlHtml() { return this.sqlHighlight((this.build && this.build.sql) || ""); },
    // 设计表：当前选中的字段（底部属性栏绑定它）
    curCol() {
      const i = this.design.sel;
      const cols = this.design.columns || [];
      return (i >= 0 && i < cols.length) ? cols[i] : null;
    },
    // 设计表：这张表上的触发器（信息来自 information_schema）
    designTriggers() {
      const n = this.design.name || this.design.originalName;
      return (this.schema.triggers || []).filter(t => t.table === n);
    },
    // 设计表「SQL 预览」：按当前设计实时生成完整 CREATE TABLE（和 Navicat 一样边改边看）
    designDdl() {
      const d = this.design;
      if (!d) return "";
      const defs = (d.columns || []).map(c => this.colSql(c));
      const pk = (d.columns || []).filter(c => c.pk).map(c => this.ident(c.name));
      if (pk.length) defs.push("PRIMARY KEY (" + pk.join(", ") + ")");
      for (const ix of d.indexes || []) {
        const cols = String(ix.columns || "").split(",").map(x => x.trim()).filter(Boolean);
        if (!ix.name || !cols.length) continue;
        defs.push(`${this.idxPrefix(ix.itype)}KEY ${this.ident(ix.name)} (${cols.map(c => this.ident(c)).join(", ")})`);
      }
      for (const f of d.fks || []) {
        if (!f.name || !f.col || !f.refTable || !f.refCol) continue;
        defs.push(`CONSTRAINT ${this.ident(f.name)} FOREIGN KEY (${this.ident(f.col)}) ` +
                  `REFERENCES ${this.ident(f.refTable)} (${this.ident(f.refCol)})` +
                  ` ON DELETE ${f.onDelete || "RESTRICT"} ON UPDATE ${f.onUpdate || "RESTRICT"}`);
      }
      for (const ck of d.checks || []) {
        if (!ck.name || !ck.expr) continue;
        defs.push(`CONSTRAINT ${this.ident(ck.name)} CHECK (${ck.expr})`);
      }
      let sql = `CREATE TABLE ${this.ident(d.name || "新表")} (\n  ${defs.join(",\n  ")}\n) ` +
                `ENGINE=${d.engine || "InnoDB"} DEFAULT CHARSET=${d.charset || "utf8mb4"}`;
      if (d.comment) sql += ` COMMENT=${this.lit(d.comment)}`;
      return sql + ";";
    },
    designDdlHtml() { return this.sqlHighlight(this.designDdl); },
    /* 右侧代码段面板：分类标签 + 搜索过滤 */
    snipTags() { return ["全部", ...new Set(NAV_SNIPPETS.map(s => s.cat))]; },
    snipList() {
      const f = (this.snipSearch || "").toLowerCase();
      return NAV_SNIPPETS.filter(s =>
        (this.snipTag === "全部" || s.cat === this.snipTag) &&
        (!f || s.name.toLowerCase().includes(f) || s.sql.toLowerCase().includes(f)));
    },
    /* ---------------- 创建图表 ---------------- */
    // 可画的列：X 任意列，Y 取数值列（结果集里能解析成数字的）
    chartCols() {
      const r = this.queryResult;
      return r && r.columns ? r.columns : [];
    },
    chartNumericCols() {
      const r = this.queryResult;
      if (!r || !r.rows || !r.rows.length) return [];
      return r.columns.filter((c, i) =>
        r.rows.some(row => row[i] !== null && row[i] !== "" && isFinite(Number(row[i]))));
    },
    chartData() {
      const r = this.queryResult, ch = this.chart;
      if (!r || !r.columns) return [];
      const xi = r.columns.indexOf(ch.x);
      const yi = r.columns.indexOf(ch.y);
      if (xi < 0 || yi < 0 || xi === yi) return [];
      const out = [];
      for (const row of (r.rows || [])) {
        const v = Number(row[yi]);
        if (row[xi] === null || row[xi] === undefined) continue;
        if (!isFinite(v)) continue;
        out.push({ label: String(row[xi]), value: v });
        if (out.length >= 30) break;
      }
      return out;
    },
    chartSvg() {
      const data = this.chartData;
      if (!data.length) return "";
      const W = 640, H = 340, L = 56, R = 18, T = 22, B = 52;
      const IW = W - L - R, IH = H - T - B;
      const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
      let max = Math.max(...data.map(d => d.value), 0.000001);
      const min = Math.min(...data.map(d => d.value), 0);
      if (min >= 0) max += (max - min) * 0.1;   // 顶部留 10%，给柱顶数值标签腾地方
      const span = (max - min) || 1;
      const ticks = 4;
      let g = "";
      // 轴 + 网格线 + 刻度值
      for (let i = 0; i <= ticks; i++) {
        const v = min + (span * i) / ticks;
        const y = T + IH - (IH * i) / ticks;
        g += `<line x1="${L}" y1="${y.toFixed(1)}" x2="${W - R}" y2="${y.toFixed(1)}" class="cgrid"/>` +
             `<text x="${L - 6}" y="${(y + 4).toFixed(1)}" class="ctick" text-anchor="end">${fmtNum(v)}</text>`;
      }
      g += `<line x1="${L}" y1="${T}" x2="${L}" y2="${T + IH}" class="caxis"/>` +
           `<line x1="${L}" y1="${T + IH}" x2="${W - R}" y2="${T + IH}" class="caxis"/>`;
      function fmtNum(v) {
        return Math.abs(v) >= 1000 ? (Math.round(v)).toLocaleString("en-US")
             : (Math.round(v * 100) / 100).toString();
      }
      const title = esc(this.chart.x) + " → " + esc(this.chart.y);
      g = `<text x="${(W / 2).toFixed(0)}" y="14" class="ctitle" text-anchor="middle">${title}</text>` + g;

      if (this.chart.type === "pie") {
        const total = data.reduce((a, d) => a + Math.max(d.value, 0), 0) || 1;
        const cx = L + IW * 0.32, cy = T + IH / 2, rad = Math.min(IW, IH) * 0.42;
        const palette = ["#4c7ddb", "#4caf7d", "#e0a92e", "#d05c5c", "#7b61d1",
                         "#4c9a86", "#c04fb0", "#8a97a8", "#b0604c", "#5c8ac0"];
        let a0 = -Math.PI / 2, ly = T + 10;
        data.forEach((d, i) => {
          const frac = Math.max(d.value, 0) / total;
          const a1 = a0 + frac * Math.PI * 2;
          const large = frac > 0.5 ? 1 : 0;
          const x0 = (cx + rad * Math.cos(a0)).toFixed(2), y0 = (cy + rad * Math.sin(a0)).toFixed(2);
          const x1 = (cx + rad * Math.cos(a1)).toFixed(2), y1 = (cy + rad * Math.sin(a1)).toFixed(2);
          const col = palette[i % palette.length];
          if (frac > 0.0001) {
            g += `<path d="M ${cx} ${cy} L ${x0} ${y0} A ${rad} ${rad} 0 ${large} 1 ${x1} ${y1} Z" ` +
                 `fill="${col}" stroke="#fff" stroke-width="1.5"><title>${esc(d.label)}: ${fmtNum(d.value)}（${(frac * 100).toFixed(1)}%）</title></path>`;
          }
          g += `<rect x="${W - R - 168}" y="${ly}" width="10" height="10" rx="2" fill="${col}"/>` +
               `<text x="${W - R - 152}" y="${ly + 9}" class="clab">${esc(clip(d.label, 12))} ${(frac * 100).toFixed(0)}%</text>`;
          a0 = a1; ly += 17;
          if (ly > T + IH) { ly = T + 10; }   // 图例太长就折回顶部（罕见）
        });
      } else if (this.chart.type === "line") {
        const pts = data.map((d, i) => {
          const x = data.length === 1 ? L + IW / 2 : L + (IW * i) / (data.length - 1);
          const y = T + IH - ((d.value - min) / span) * IH;
          return { x, y: Math.max(T, Math.min(T + IH, y)), d };
        });
        g += `<polyline points="${pts.map(p => p.x.toFixed(1) + "," + p.y.toFixed(1)).join(" ")}" ` +
             `fill="none" stroke="#4c7ddb" stroke-width="2.2" stroke-linejoin="round"/>`;
        pts.forEach((p, i) => {
          g += `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.4" fill="#4c7ddb">` +
               `<title>${esc(p.d.label)}: ${fmtNum(p.d.value)}</title></circle>`;
          const step = Math.ceil(data.length / 8);
          if (i % step === 0) {
            g += `<text x="${p.x.toFixed(1)}" y="${T + IH + 16}" class="clab" text-anchor="middle">${esc(clip(p.d.label, 8))}</text>`;
          }
        });
      } else {   // bar 柱状图
        const bw = IW / data.length;
        const barW = Math.max(4, Math.min(46, bw * 0.62));
        data.forEach((d, i) => {
          const x = L + bw * i + (bw - barW) / 2;
          const zero = T + IH - ((0 - min) / span) * IH;
          const y = T + IH - ((d.value - min) / span) * IH;
          const top = Math.min(y, zero), h = Math.max(Math.abs(zero - y), 1);
          g += `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" ` +
               `rx="2.5" fill="${d.value >= 0 ? "#4c7ddb" : "#d05c5c"}"><title>${esc(d.label)}: ${fmtNum(d.value)}</title></rect>`;
          if (data.length <= 12) {
            g += `<text x="${(x + barW / 2).toFixed(1)}" y="${(top - 5).toFixed(1)}" class="cval" text-anchor="middle">${fmtNum(d.value)}</text>`;
          }
          const step = Math.ceil(data.length / 10);
          if (i % step === 0) {
            g += `<text x="${(L + bw * i + bw / 2).toFixed(1)}" y="${T + IH + 16}" class="clab" text-anchor="middle">${esc(clip(d.label, 8))}</text>`;
          }
        });
      }
      function clip(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
      return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" class="nc-chart-svg">${g}</svg>`;
    },
  },

  watch: {
    db(v) {
      if (v) this.reload();
    },
    active(v) {
      this.$nextTick(() => {
        if (v === "query" && this.$refs.cmQuery) this.$refs.cmQuery.refresh();
      });
    },
    // 图表 / 准则一变（勾字段、选汇总、连线、条件），生成的 SQL 自动刷新
    "build.tables": { deep: true, handler() { this.syncBuilderSql(); } },
    "build.joins": { deep: true, handler() { this.syncBuilderSql(); } },
    "build.rows": { deep: true, handler() { this.syncBuilderSql(); } },
    builderMode(v) {
      if (v) this.syncBuilderSql();
    },
  },

  mounted() {
    if (this.db) this.reload();
    this._menuOff = () => { this.menu = ""; this.ctx.show = false; this.condPop = null; };
    this._escOff = (e) => { if (e.key === "Escape") { this.ctx.show = false; this.menu = ""; this.condPop = null; this.chart.open = false; } };
    document.addEventListener("click", this._menuOff);
    document.addEventListener("keydown", this._escOff);
  },
  beforeUnmount() {
    document.removeEventListener("click", this._menuOff);
    document.removeEventListener("keydown", this._escOff);
    clearTimeout(this._pressTimer);
  },

  methods: {
    /* ---------------- 基础 ---------------- */
    async api(path, opts = {}) {
      const init = { method: opts.method || "GET", headers: { "X-Token": this.token } };
      if (opts.signal) init.signal = opts.signal;
      if (opts.body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
      let resp;
      try { resp = await fetch(path, init); }
      catch (e) { throw new Error("网络连接失败，请检查网络"); }
      let data = {};
      try { data = await resp.json(); } catch (e) { /* 忽略非 JSON */ }
      if (!resp.ok) throw new Error(typeof data.detail === "string" ? data.detail : `请求失败（${resp.status}）`);
      return data;
    },
    toast(m) { this.$emit("toast", String(m || "")); },
    ident(n) { return "`" + String(n).replace(/`/g, "``") + "`"; },
    lit(v) {
      if (v === null || v === undefined) return "NULL";
      if (typeof v === "number") return String(v);
      return "'" + String(v).replace(/\\/g, "\\\\").replace(/'/g, "''") + "'";
    },
    fmtBytes(n) {
      n = Number(n) || 0;
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / 1024 / 1024).toFixed(1) + " MB";
    },
    fmtDate(s) { return s ? String(s).replace("T", " ").slice(0, 19) : ""; },
    // SQL 高亮（查询创建工具右侧预览 / 设计表 SQL 预览共用）：先转义再一次性替换
    sqlHighlight(sql) {
      const esc = String(sql || "")
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return esc.replace(
        /('[^']*'|`[^`]*`)|\b(SELECT|FROM|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|INNER JOIN|LEFT JOIN|RIGHT JOIN|JOIN|ON|AS|AND|OR|NOT|LIKE|IN|BETWEEN|IS NULL|IS NOT NULL|ASC|DESC|EXPLAIN|CREATE TABLE|ALTER TABLE|DROP|ADD|PRIMARY KEY|UNIQUE|KEY|CONSTRAINT|FOREIGN KEY|REFERENCES|CHECK|ENGINE|DEFAULT|CHARSET|COMMENT|AUTO_INCREMENT|UNSIGNED|ZEROFILL|NULL|INTO|VALUES|SET|UPDATE|DELETE|INSERT|TRIGGER|CASCADE|RESTRICT)\b/gi,
        (m, s) => s ? '<span class="tk-s">' + s + "</span>" : '<span class="tk-k">' + m + "</span>");
    },
    normType(t) {
      const m = /^([a-zA-Z]+)(?:\((\d+)(?:,(\d+))?\))?(.*)$/.exec(String(t || ""));
      if (!m) return { type: String(t || "VARCHAR").toUpperCase(), length: null, scale: null, extra: "" };
      return { type: m[1].toUpperCase(), length: m[2] ? Number(m[2]) : null,
               scale: m[3] !== undefined ? Number(m[3]) : null, extra: (m[4] || "").trim() };
    },

    /* ---------------- 结构 ---------------- */
    async reload() {
      this.loading = true;
      try {
        this.schema = await this.api(`/api/drills/${this.drill.id}/navicat/schema`);
        if (this.table.name && !this.currentTab) this.selected = this.table.name;
      } catch (e) {
        this.toast(e.message);
      } finally {
        this.loading = false;
      }
    },
    async runBatch(stmts, log = true) {
      const list = (stmts || []).filter(s => String(s || "").trim());
      if (!list.length) return [];
      const sql = list.join(";\n") + ";";
      const d = await this.api("/api/sql", { method: "POST", body: { sql, db: this.db } });
      const results = d.results || [];
      const err = results.find(r => r.type === "error");
      if (err) throw new Error(err.msg || "执行失败");
      if (log) this.$emit("log", sql);
      this.$emit("changed");
      return results;
    },
    async execOne(sql, log = true) {
      return this.runBatch([sql], log);
    },

    /* ---------------- 树 / 对象列表 ---------------- */
    selectNode(key) {
      this.node = key;
      this.selected = "";
      this.active = "objects";
      this.mobileTree = false;
    },
    openObjects() { this.active = "objects"; },
    openObject(o) {
      if (this.node === "tables") this.openTable(o.name, "table");
      else if (this.node === "views") this.openTable(o.name, "view");
      else if (this.node === "routines") this.openRoutine(o, "edit");
      else if (this.node === "triggers") this.openTrigger(o, "edit");
    },
    objectIcon(o) { return this.node === "views" ? "file-text" : "table"; },

    /* ---------------- 标签页 ---------------- */
    ensureTab(tab) {
      const found = this.tabs.find(t => t.id === tab.id);
      if (found) { Object.assign(found, tab); this.active = tab.id; return found; }
      this.tabs.push(tab);
      this.active = tab.id;
      return tab;
    },
    closeTab(t) {
      const i = this.tabs.indexOf(t);
      if (i >= 0) this.tabs.splice(i, 1);
      if (this.active === t.id) this.active = this.tabs.length ? this.tabs[this.tabs.length - 1].id : "objects";
    },
    newQueryTab() {
      this.ensureTab({ id: "query", kind: "query", title: "查询", icon: "search" });
      this.$nextTick(() => { if (this.$refs.cmQuery) this.$refs.cmQuery.refresh(); });
    },

    /* ---------------- 表数据 ---------------- */
    async openTable(name, kind) {
      const meta = (kind === "view" ? this.schema.views : this.schema.tables).find(x => x.name === name);
      this.ensureTab({
        id: "data:" + name, kind, name, icon: kind === "view" ? "file-text" : "table",
        title: name,
      });
      this.table = {
        name, kind, columns: (meta && meta.columns ? meta.columns.map(c => c.name) : []),
        rows: [], total: 0, page: 0, size: 100,
        edits: {}, added: [], deleted: [], loading: true,
        filter: "", orderBy: "", orderDir: "ASC",
      };
      await this.loadRows();
    },
    async loadRows() {
      const t = this.table;
      if (!t.name) return;
      t.loading = true;
      try {
        const where = t.filter ? " WHERE " + t.filter : "";
        const order = t.orderBy ? ` ORDER BY ${this.ident(t.orderBy)} ${t.orderDir}` : "";
        const lim = ` LIMIT ${t.size} OFFSET ${t.page * t.size}`;
        const res = await this.runBatch([
          `SELECT * FROM ${this.ident(t.name)}${where}${order}${lim}`,
          `SELECT COUNT(*) AS cnt FROM ${this.ident(t.name)}${where}`,
        ], false);
        const rowsRes = res.find(r => r.type === "rows");
        const countRes = [...res].reverse().find(r => r.type === "rows");
        if (rowsRes) {
          t.columns = rowsRes.columns || t.columns;
          t.rows = (rowsRes.rows || []).map(r => r.slice());
        } else {
          t.rows = [];
        }
        t.total = countRes && countRes.rows && countRes.rows[0] ? Number(countRes.rows[0][0]) : t.rows.length;
        t.edits = {};
        t.added = [];
        t.deleted = [];
      } catch (e) {
        this.toast(e.message);
      } finally {
        t.loading = false;
      }
    },
    cellValue(rowIdx, colIdx) {
      const t = this.table;
      if (rowIdx >= t.rows.length) {
        const add = t.added[rowIdx - t.rows.length];
        return add ? add[colIdx] : null;
      }
      const ed = t.edits[rowIdx];
      if (ed && Object.prototype.hasOwnProperty.call(ed, colIdx)) return ed[colIdx];
      return t.rows[rowIdx][colIdx];
    },
    isEdited(rowIdx, colIdx) {
      const ed = this.table.edits[rowIdx];
      return !!(ed && Object.prototype.hasOwnProperty.call(ed, colIdx));
    },
    cellInput(rowIdx, colIdx, ev) {
      const t = this.table;
      const val = ev.target.value === "" ? "" : ev.target.value;
      if (rowIdx >= t.rows.length) {
        const add = t.added[rowIdx - t.rows.length];
        if (add) add[colIdx] = val;
        return;
      }
      if (!t.edits[rowIdx]) t.edits[rowIdx] = {};
      const orig = t.rows[rowIdx][colIdx];
      if (String(orig === null ? "" : orig) === String(val)) delete t.edits[rowIdx][colIdx];
      else t.edits[rowIdx][colIdx] = val;
    },
    addRow() {
      this.table.added.push(this.table.columns.map(() => null));
      this.$nextTick(() => {
        const rows = this.$el.querySelectorAll(".nc-data-table tbody tr");
        if (rows.length) rows[rows.length - 1].scrollIntoView({ block: "nearest" });
      });
    },
    deleteRow(rowIdx) {
      const t = this.table;
      if (rowIdx >= t.rows.length) {
        t.added.splice(rowIdx - t.rows.length, 1);
        return;
      }
      if (t.deleted.includes(rowIdx)) t.deleted = t.deleted.filter(x => x !== rowIdx);
      else t.deleted.push(rowIdx);
    },
    async applyTable() {
      const t = this.table;
      const stmts = [];
      const whereOf = (row) => {
        const parts = this.tablePk.length
          ? this.tablePk.map(k => {
              const i = t.columns.indexOf(k);
              return `${this.ident(k)} <=> ${this.lit(row[i])}`;
            })
          : t.columns.map((c, i) => `${this.ident(c)} <=> ${this.lit(row[i])}`);
        return parts.join(" AND ");
      };
      for (const idx of t.deleted) {
        if (t.rows[idx]) stmts.push(`DELETE FROM ${this.ident(t.name)} WHERE ${whereOf(t.rows[idx])} LIMIT 1`);
      }
      for (const key of Object.keys(t.edits)) {
        const idx = Number(key);
        const row = t.rows[idx];
        if (!row) continue;
        const sets = Object.entries(t.edits[key]).map(([ci, v]) =>
          `${this.ident(t.columns[Number(ci)])} = ${this.lit(v)}`);
        if (sets.length) stmts.push(`UPDATE ${this.ident(t.name)} SET ${sets.join(", ")} WHERE ${whereOf(row)} LIMIT 1`);
      }
      for (const vals of t.added) {
        stmts.push(`INSERT INTO ${this.ident(t.name)} (${t.columns.map(c => this.ident(c)).join(", ")}) ` +
                   `VALUES (${vals.map(v => this.lit(v)).join(", ")})`);
      }
      if (!stmts.length) { this.toast("没有需要保存的修改"); return; }
      try {
        await this.runBatch(stmts);
        this.toast(`已保存 ${stmts.length} 条修改`);
        await this.loadRows();
        await this.reload();
      } catch (e) { this.toast(e.message); }
    },
    revertTable() { this.loadRows(); },
    tablePage(dir) {
      const max = Math.max(0, Math.ceil(this.table.total / this.table.size) - 1);
      const next = Math.min(max, Math.max(0, this.table.page + dir));
      if (next === this.table.page) return;
      this.table.page = next;
      this.loadRows();
    },

    /* ---------------- 设计表（Navicat 同款：工具栏 + 字段/索引/外键/检查/触发器/选项/注释/SQL预览） ---------------- */
    blankDesign() {
      return {
        mode: "new", name: "", originalName: "", engine: "InnoDB", charset: "utf8mb4",
        comment: "", originalEngine: "InnoDB", originalCharset: "utf8mb4", originalComment: "",
        columns: [{ name: "id", type: "INT", length: null, scale: null, extra: "",
                    pk: true, auto: true, unsigned: false, zerofill: false,
                    virtual: false, stored: false, genExpr: "",
                    nullable: false, default: "", comment: "" }],
        indexes: [], fks: [], checks: [],
        originalColumns: [], originalIndexes: [], originalFks: [],
        doneChecks: [],          // 本次会话里已经 ALTER 过的检查名（5.7 不回读，防重复）
        sel: 0, tab: "columns",
      };
    },
    openDesign(name, mode = "edit") {
      if (mode === "new") {
        this.design = this.blankDesign();
        this.ensureTab({ id: "design:__new", kind: "design", title: "新建表", icon: "table" });
        return;
      }
      const t = this.schema.tables.find(x => x.name === name);
      if (!t) return;
      const cols = (t.columns || []).map(c => {
        const p = this.normType(c.type);
        const extra = String(c.extra || "").toUpperCase();
        return {
          name: c.name, type: p.type, length: p.length, scale: p.scale,
          extra: p.extra || "", nullable: c.nullable, pk: c.key === "PRI",
          auto: extra.includes("AUTO_INCREMENT"),
          unsigned: /\bunsigned\b/i.test(c.type || ""),
          zerofill: /\bzerofill\b/i.test(c.type || ""),
          // 生成列（虚拟列）：EXTRA = VIRTUAL GENERATED / STORED GENERATED
          virtual: extra.includes("GENERATED"),
          stored: extra.includes("STORED"),
          genExpr: c.genExpr || "",
          default: c.default === null ? "" : c.default, comment: c.comment || "",
        };
      });
      // 索引类型（视频 54.5s）：名 / 字段 / 索引类型（NORMAL / UNIQUE / FULLTEXT / SPATIAL）
      const idxKind = (i) => i.unique ? "UNIQUE"
        : String(i.type || "").toUpperCase() === "FULLTEXT" ? "FULLTEXT"
        : String(i.type || "").toUpperCase() === "SPATIAL" ? "SPATIAL" : "NORMAL";
      const indexes = (t.indexes || [])
        .filter(i => i.name !== "PRIMARY")
        .map(i => ({ name: i.name, columns: (i.columns || []).join(", "), itype: idxKind(i) }));
      // 外键：按约束名分组（多列外键合并成一行，编辑时锁定）
      const fkMap = {};
      for (const f of (t.fks || [])) {
        const k = f.name || f.col;
        const g = fkMap[k] = fkMap[k] || {
          name: k, col: f.col, refTable: f.refTable, refCol: f.refCol,
          onDelete: f.onDelete || "RESTRICT", onUpdate: f.onUpdate || "RESTRICT",
          cols: [], refCols: [],
        };
        g.cols.push(f.col); g.refCols.push(f.refCol);
      }
      const fks = Object.values(fkMap).map(g => {
        g.multi = g.cols.length > 1;
        g.col = g.cols[0]; g.refCol = g.refCols[0];
        return g;
      });
      this.design = {
        mode: "edit", name: t.name, originalName: t.name,
        engine: t.engine || "InnoDB", charset: this.schema.charset || "utf8mb4",
        comment: t.comment || "",
        originalEngine: t.engine || "InnoDB", originalCharset: this.schema.charset || "utf8mb4",
        originalComment: t.comment || "",
        columns: cols, indexes, fks, checks: [],
        originalColumns: JSON.parse(JSON.stringify(cols)),
        originalIndexes: JSON.parse(JSON.stringify(indexes)),
        originalFks: JSON.parse(JSON.stringify(fks)),
        doneChecks: [], sel: 0, tab: "columns",
      };
      this.ensureTab({ id: "design:" + name, kind: "design", name, title: "设计表 - " + name, icon: "table" });
    },
    /* 工具栏（图1）：添加字段 / 插入字段 / 删除字段 / 主键 / 上移 / 下移，都作用在选中行上 */
    addDesignCol() {
      const blank = this.blankCol();
      this.design.columns.push(blank);
      this.design.sel = this.design.columns.length - 1;
    },
    blankCol() {
      return { name: "new_col", type: "VARCHAR", length: 50, scale: null, extra: "",
               pk: false, auto: false, unsigned: false, zerofill: false,
               virtual: false, stored: false, genExpr: "",
               nullable: true, default: "", comment: "" };
    },
    insertDesignCol() {
      const blank = this.blankCol();
      const at = Math.min(this.design.sel + 1, this.design.columns.length);
      this.design.columns.splice(at, 0, blank);
      this.design.sel = at;
    },
    delDesignColSel() {
      const i = this.design.sel;
      if (i < 0 || i >= this.design.columns.length) { this.toast("先在网格里点一行选中字段"); return; }
      this.design.columns.splice(i, 1);
      this.design.sel = Math.max(0, Math.min(i, this.design.columns.length - 1));
    },
    togglePkSel() {
      const c = this.design.columns[this.design.sel];
      if (!c) { this.toast("先在网格里点一行选中字段"); return; }
      c.pk = !c.pk;
      if (c.pk) { c.nullable = false; c.auto = (c.type || "").match(/INT|BIGINT|TINYINT|SMALLINT|MEDIUMINT/) ? true : c.auto; }
    },
    moveDesignColSel(dir) {
      const i = this.design.sel;
      const c = this.design.columns;
      const j = i + dir;
      if (i < 0 || j < 0 || j >= c.length) return;
      [c[i], c[j]] = [c[j], c[i]];
      this.design.sel = j;
    },
    // 键 列：PRI / UNI / MUL（像 Navicat 一样从主键 + 索引推导）
    colKeyTag(c) {
      if (!c) return "";
      if (c.pk) return "PRI";
      const hit = (this.design.indexes || []).find(ix => {
        const cols = String(ix.columns || "").split(",").map(x => x.trim()).filter(Boolean);
        return cols.includes(c.name);
      });
      if (!hit) return "";
      return hit.itype === "UNIQUE" ? "UNI" : "MUL";
    },
    addDesignFk() {
      const firstOther = (this.schema.tables.find(t => t.name !== this.design.name) || {}).name || "";
      this.design.fks.push({
        name: "fk_" + (this.design.fks.length + 1), col: (this.design.columns[0] || {}).name || "",
        refTable: firstOther, refCol: "",
        onDelete: "RESTRICT", onUpdate: "RESTRICT",
      });
    },
    delDesignFk(i) { this.design.fks.splice(i, 1); },
    // 外键引用表的字段下拉（从 schema 拿，选择引用表后自动选第一个字段）
    refTableCols(f) {
      const t = this.schema.tables.find(x => x.name === f.refTable);
      return t ? t.columns.map(c => c.name) : [];
    },
    setFkRefTable(f, name) {
      f.refTable = name;
      const t = this.schema.tables.find(x => x.name === name);
      f.refCol = (t && t.columns[0]) ? t.columns[0].name : "";
    },
    addDesignCheck() {
      this.design.checks.push({ name: "chk_" + (this.design.checks.length + 1), expr: "" });
    },
    delDesignCheck(i) { this.design.checks.splice(i, 1); },
    // 设计表「触发器」标签页：在这张表上新建 / 编辑触发器（复用触发器编辑页）
    addDesignTrigger() {
      this.openTrigger(null, "new");
      this.triggerForm.table = this.design.name || this.design.originalName || "";
    },
    editDesignTrigger(t) { this.openTrigger(t); },
    trigBrief(t) {
      const s = String(t.statement || "").replace(/\s+/g, " ").trim();
      return s.length > 60 ? s.slice(0, 59) + "…" : s;
    },
    addIndex() {
      this.design.indexes.push({ name: "idx_" + (this.design.indexes.length + 1),
                                 columns: "", itype: "NORMAL" });
    },
    delIndex(i) { this.design.indexes.splice(i, 1); },
    // 索引类型 → SQL 前缀（NORMAL 无前缀，其余加 UNIQUE / FULLTEXT / SPATIAL）
    idxPrefix(itype) {
      return { UNIQUE: "UNIQUE ", FULLTEXT: "FULLTEXT ", SPATIAL: "SPATIAL " }[itype] || "";
    },
    // 外键「引用模式」（视频 59.5s）：选一个模式同时应用到 ON DELETE 和 ON UPDATE
    fkModeOf(f) { return f.onDelete === f.onUpdate ? f.onDelete : ""; },
    setFkMode(f, v) { f.onDelete = v; f.onUpdate = v; },
    colTypeSql(c) {
      let t = String(c.type || "VARCHAR").toUpperCase();
      if (["VARCHAR", "CHAR"].includes(t) && c.length) t += `(${c.length})`;
      else if (["DECIMAL", "DOUBLE", "FLOAT"].includes(t) && c.length)
        t += `(${c.length}${c.scale !== null && c.scale !== "" && c.scale !== undefined ? "," + c.scale : ""})`;
      else if (["INT", "BIGINT", "TINYINT", "SMALLINT", "MEDIUMINT"].includes(t) && c.length)
        t += `(${c.length})`;
      if (c.unsigned && /INT|BIGINT|TINYINT|SMALLINT|MEDIUMINT|DECIMAL|DOUBLE|FLOAT/.test(t)) t += " UNSIGNED";
      if (c.zerofill && /INT|BIGINT|TINYINT|SMALLINT|MEDIUMINT|DECIMAL|DOUBLE|FLOAT/.test(t)) t += " ZEROFILL";
      if (c.extra) t += " " + String(c.extra).toUpperCase();
      return t;
    },
    colSql(c) {
      let s = `${this.ident(c.name)} ${this.colTypeSql(c)}`;
      // 生成列（虚拟列，视频 46.5s 的「虚拟」）：类型 AS (表达式) VIRTUAL / STORED
      if (c.virtual) {
        const ge = String(c.genExpr || "").trim();
        if (!ge) return s + " NULL";
        s += ` AS ${ge.startsWith("(") ? ge : "(" + ge + ")"} ${c.stored ? "STORED" : "VIRTUAL"}`;
        s += c.nullable ? " NULL" : " NOT NULL";
        if (c.comment) s += " COMMENT " + this.lit(c.comment);
        return s;
      }
      s += c.nullable ? " NULL" : " NOT NULL";
      if (c.auto) s += " AUTO_INCREMENT";
      if (!c.auto && c.default !== "" && c.default !== null && c.default !== undefined) {
        const d = String(c.default).trim();
        const expr = /^(CURRENT_TIMESTAMP(\(\d*\))?|NULL|TRUE|FALSE|-?\d+(\.\d+)?)$/i.test(d);
        s += " DEFAULT " + (expr ? d.toUpperCase() : this.lit(d));
      }
      if (c.comment) s += " COMMENT " + this.lit(c.comment);
      return s;
    },
    fkSql(f) {
      return `CONSTRAINT ${this.ident(f.name)} FOREIGN KEY (${this.ident(f.col)}) ` +
             `REFERENCES ${this.ident(f.refTable)} (${this.ident(f.refCol)})` +
             ` ON DELETE ${f.onDelete || "RESTRICT"} ON UPDATE ${f.onUpdate || "RESTRICT"}`;
    },
    async saveDesign() {
      const d = this.design;
      if (!d.name.trim()) { this.toast("表名不能为空"); return; }
      // 校验外键 / 检查（Navicat 也是必填项校验）
      for (const f of d.fks || []) {
        if (!f.name.trim() || !f.col || !f.refTable || !f.refCol) {
          this.toast("外键的 名/字段/引用表/引用字段 都要填完整"); return;
        }
      }
      for (const ck of d.checks || []) {
        if (!ck.name.trim() || !String(ck.expr || "").trim()) {
          this.toast("检查约束的 名 和 表达式 都要填（例如 salary > 0）"); return;
        }
      }
      const stmts = [];
      try {
        if (d.mode === "new") {
          const defs = d.columns.map(c => this.colSql(c));
          const pk = d.columns.filter(c => c.pk).map(c => this.ident(c.name));
          if (pk.length) defs.push("PRIMARY KEY (" + pk.join(", ") + ")");
          for (const ix of d.indexes) {
            const cols = String(ix.columns || "").split(",").map(x => x.trim()).filter(Boolean);
            if (!ix.name || !cols.length) continue;
            defs.push(`${this.idxPrefix(ix.itype)}KEY ${this.ident(ix.name)} (${cols.map(c => this.ident(c)).join(", ")})`);
          }
          for (const f of d.fks) defs.push(this.fkSql(f));
          for (const ck of d.checks) defs.push(`CONSTRAINT ${this.ident(ck.name)} CHECK (${ck.expr})`);
          stmts.push(`CREATE TABLE ${this.ident(d.name)} (\n  ${defs.join(",\n  ")}\n) ENGINE=${d.engine || "InnoDB"} DEFAULT CHARSET=${d.charset || "utf8mb4"}` +
                     (d.comment ? ` COMMENT=${this.lit(d.comment)}` : ""));
        } else {
          const cur = d.name;
          if (d.name !== d.originalName) {
            stmts.push(`RENAME TABLE ${this.ident(d.originalName)} TO ${this.ident(d.name)}`);
          }
          // 先处理外键差异（列变动前 DROP，避免顺序冲突）
          const oldFk = {};
          (d.originalFks || []).forEach(f => { oldFk[f.name] = f; });
          for (const f of d.originalFks || []) {
            if (!d.fks.find(x => x.name === f.name)) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP FOREIGN KEY ${this.ident(f.name)}`);
          }
          const old = {};
          (d.originalColumns || []).forEach(c => { old[c.name] = c; });
          const newNames = new Set(d.columns.map(c => c.name));
          for (const c of d.originalColumns || []) {
            if (!newNames.has(c.name)) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP COLUMN ${this.ident(c.name)}`);
          }
          let prev = "";
          for (const c of d.columns) {
            const o = old[c.name];
            if (!o) {
              const pos = prev ? ` AFTER ${this.ident(prev)}` : " FIRST";
              stmts.push(`ALTER TABLE ${this.ident(cur)} ADD COLUMN ${this.colSql(c)}${pos}`);
            } else if (this.colSql(c) !== this.colSql(o)) {
              stmts.push(`ALTER TABLE ${this.ident(cur)} MODIFY COLUMN ${this.colSql(c)}`);
            }
            prev = c.name;
          }
          const oldPk = (d.originalColumns || []).filter(c => c.pk).map(c => c.name).sort().join(",");
          const newPk = d.columns.filter(c => c.pk).map(c => c.name).sort().join(",");
          if (oldPk !== newPk) {
            if (oldPk) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP PRIMARY KEY`);
            if (newPk) stmts.push(`ALTER TABLE ${this.ident(cur)} ADD PRIMARY KEY (${d.columns.filter(c => c.pk).map(c => this.ident(c.name)).join(", ")})`);
          }
          const oldIdx = {};
          (d.originalIndexes || []).forEach(i => { oldIdx[i.name] = i; });
          for (const i of d.originalIndexes || []) {
            if (!d.indexes.find(x => x.name === i.name)) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP INDEX ${this.ident(i.name)}`);
          }
          for (const ix of d.indexes) {
            const cols = String(ix.columns || "").split(",").map(x => x.trim()).filter(Boolean);
            if (!cols.length) continue;
            const o = oldIdx[ix.name];
            const sig = cols.join(",") + "|" + (ix.itype || "NORMAL");
            const osig = o ? (o.columns || []).join(",") + "|" + (o.itype || "NORMAL") : "";
            if (sig !== osig) {
              if (o) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP INDEX ${this.ident(ix.name)}`);
              stmts.push(`ALTER TABLE ${this.ident(cur)} ADD ${this.idxPrefix(ix.itype)}INDEX ${this.ident(ix.name)} (${cols.map(c => this.ident(c)).join(", ")})`);
            }
          }
          // 新外键在列/索引之后加
          for (const f of d.fks) {
            const o = oldFk[f.name];
            const sig = f.col + "|" + f.refTable + "|" + f.refCol + "|" + f.onDelete + "|" + f.onUpdate;
            const osig = o && !o.multi ? o.col + "|" + o.refTable + "|" + o.refCol + "|" + o.onDelete + "|" + o.onUpdate : "";
            if (sig !== osig) {
              if (o && !o.multi) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP FOREIGN KEY ${this.ident(f.name)}`);
              stmts.push(`ALTER TABLE ${this.ident(cur)} ADD ${this.fkSql(f)}`);
            }
          }
          // 检查约束：5.7 只解析不强制，但语句是真实有效的 DDL（会记录到作答）
          for (const ck of d.checks) {
            if ((d.doneChecks || []).includes(ck.name)) continue;
            stmts.push(`ALTER TABLE ${this.ident(cur)} ADD CONSTRAINT ${this.ident(ck.name)} CHECK (${ck.expr})`);
          }
          if (d.engine !== d.originalEngine || d.charset !== d.originalCharset || d.comment !== d.originalComment) {
            stmts.push(`ALTER TABLE ${this.ident(cur)} ENGINE=${d.engine || "InnoDB"} DEFAULT CHARSET=${d.charset || "utf8mb4"}` +
                       (d.comment ? ` COMMENT=${this.lit(d.comment)}` : ""));
          }
        }
        if (!stmts.length) { this.toast("没有需要保存的修改"); return; }
        await this.runBatch(stmts);
        this.toast(`表「${d.name}」已保存`);
        d.doneChecks = d.checks.map(c => c.name);
        const wasNew = d.mode === "new";
        await this.reload();
        // reload 重建了 schema，把当前设计对象的引用对上
        if (!wasNew) {
          const t = this.schema.tables.find(x => x.name === d.name);
          if (t) this.openDesignKeepTab(t, d);
        }
        const tab = this.currentTab;
        if (tab) { tab.title = "设计表 - " + d.name; tab.name = d.name; tab.id = "design:" + d.name; }
        if (wasNew) this.openTable(d.name, "table");
      } catch (e) { this.toast(e.message); }
    },
    // 保存后用最新 schema 刷新设计器，但保留当前标签页和已填的 检查（5.7 不回读）
    openDesignKeepTab(t, d) {
      const checks = d.checks, done = d.doneChecks, sel = d.sel, tab = d.tab;
      this.openDesign(t.name, "edit");
      this.design.checks = checks;
      this.design.doneChecks = done;
      this.design.sel = sel;
      this.design.tab = tab;
    },
    async dropTable(name) {
      if (!confirm(`删除表「${name}」？表结构和数据都会删除。`)) return;
      try {
        await this.execOne(`DROP TABLE ${this.ident(name)}`);
        this.toast("已删除表 " + name);
        await this.reload();
        const tab = this.tabs.find(t => t.name === name);
        if (tab) this.closeTab(tab);
      } catch (e) { this.toast(e.message); }
    },

    /* ---------------- 视图 ---------------- */
    openViewDesign(name, mode = "edit") {
      const v = name ? this.schema.views.find(x => x.name === name) : null;
      this.viewForm = {
        mode: v ? "edit" : "new", name: v ? v.name : "",
        definition: v ? v.definition : "SELECT ",
      };
      this.ensureTab({ id: "vdesign:" + (name || "__new"), kind: "viewDesign", name: name || "",
                       title: v ? "设计视图 - " + name : "新建视图", icon: "file-text" });
    },
    async saveView() {
      const f = this.viewForm;
      if (!f.name.trim()) { this.toast("视图名不能为空"); return; }
      if (!f.definition.trim()) { this.toast("请填写 SELECT 定义"); return; }
      try {
        await this.execOne(`CREATE OR REPLACE VIEW ${this.ident(f.name)} AS\n${f.definition.trim()}`);
        this.toast("视图已保存");
        await this.reload();
        const t = this.currentTab;
        if (t) { t.title = "设计视图 - " + f.name; t.name = f.name; t.id = "vdesign:" + f.name; }
      } catch (e) { this.toast(e.message); }
    },
    async dropView(name) {
      if (!confirm(`删除视图「${name}」？`)) return;
      try {
        await this.execOne(`DROP VIEW ${this.ident(name)}`);
        this.toast("已删除视图 " + name);
        await this.reload();
        const tab = this.tabs.find(t => t.name === name);
        if (tab) this.closeTab(tab);
      } catch (e) { this.toast(e.message); }
    },

    /* ---------------- 函数 / 存储过程 ---------------- */
    openRoutine(r, mode = "edit") {
      const isNew = mode === "new" || !r;
      this.routineForm = {
        mode: isNew ? "new" : "edit",
        name: isNew ? "" : r.name,
        type: isNew ? (r && r.type) || "PROCEDURE" : r.type,
        params: isNew ? "" : (r.params || []).map(p => `${p.mode} ${p.name} ${p.type}`).join(", "),
        returns: isNew ? "INT" : (r.type === "FUNCTION" ? r.returns : "INT"),
        body: isNew ? "" : (r.definition || ""),
        comment: isNew ? "" : (r.comment || ""),
      };
      this.ensureTab({ id: "routine:" + (isNew ? "__new" : r.name), kind: "routine",
                       name: isNew ? "" : r.name,
                       title: isNew ? "新建" + (this.routineForm.type === "FUNCTION" ? "函数" : "存储过程")
                                    : "设计" + (r.type === "FUNCTION" ? "函数" : "存储过程") + " - " + r.name,
                       icon: "code" });
    },
    async saveRoutine() {
      const f = this.routineForm;
      if (!f.name.trim()) { this.toast("名称不能为空"); return; }
      const isFn = f.type === "FUNCTION";
      const params = f.params.trim();
      let sql;
      if (isFn) {
        sql = `DROP FUNCTION IF EXISTS ${this.ident(f.name)};\nDELIMITER //\n` +
              `CREATE FUNCTION ${this.ident(f.name)}(${params}) RETURNS ${f.returns || "INT"}\n` +
              (f.comment ? `COMMENT ${this.lit(f.comment)}\n` : "") +
              `BEGIN\n${f.body}\nEND//\nDELIMITER ;`;
      } else {
        sql = `DROP PROCEDURE IF EXISTS ${this.ident(f.name)};\nDELIMITER //\n` +
              `CREATE PROCEDURE ${this.ident(f.name)}(${params})\n` +
              (f.comment ? `COMMENT ${this.lit(f.comment)}\n` : "") +
              `BEGIN\n${f.body}\nEND//\nDELIMITER ;`;
      }
      try {
        await this.execOne(sql);
        this.toast((isFn ? "函数" : "存储过程") + "已保存");
        await this.reload();
        const t = this.currentTab;
        if (t) { t.title = "设计" + (isFn ? "函数" : "存储过程") + " - " + f.name; t.name = f.name; t.id = "routine:" + f.name; }
      } catch (e) { this.toast(e.message); }
    },
    async dropRoutine(r) {
      const type = r.type === "FUNCTION" ? "FUNCTION" : "PROCEDURE";
      if (!confirm(`删除${type === "FUNCTION" ? "函数" : "存储过程"}「${r.name}」？`)) return;
      try {
        await this.execOne(`DROP ${type} IF EXISTS ${this.ident(r.name)}`);
        this.toast("已删除 " + r.name);
        await this.reload();
        const tab = this.tabs.find(t => t.name === r.name);
        if (tab) this.closeTab(tab);
      } catch (e) { this.toast(e.message); }
    },
    openRunRoutine(r) {
      this.runForm = { routine: r, args: "", result: null, msg: "" };
      this.dlg = "runRoutine";
    },
    async runRoutineNow() {
      const r = this.runForm.routine;
      if (!r) return;
      const args = this.runForm.args.trim();
      const sql = r.type === "FUNCTION"
        ? `SELECT ${this.ident(r.name)}(${args}) AS result`
        : `CALL ${this.ident(r.name)}(${args})`;
      try {
        const res = await this.runBatch([sql], false);
        const rows = res.find(x => x.type === "rows");
        this.runForm.result = rows || null;
        this.runForm.msg = res.map(x => x.type === "error" ? x.msg
          : x.type === "ok" ? `执行成功，影响 ${x.affected || 0} 行`
          : `${x.rowCount || 0} 行`).join("；");
      } catch (e) { this.runForm.msg = e.message; this.runForm.result = null; }
    },

    /* ---------------- 触发器 ---------------- */
    openTrigger(t, mode = "edit") {
      const isNew = mode === "new" || !t;
      this.triggerForm = {
        mode: isNew ? "new" : "edit",
        name: isNew ? "" : t.name,
        timing: isNew ? "BEFORE" : t.timing,
        event: isNew ? "INSERT" : t.event,
        table: isNew ? (this.selectedObject ? this.selectedObject.name : "") : t.table,
        statement: isNew ? "" : t.statement,
      };
      this.ensureTab({ id: "trigger:" + (isNew ? "__new" : t.name), kind: "trigger",
                       name: isNew ? "" : t.name,
                       title: isNew ? "新建触发器" : "设计触发器 - " + t.name, icon: "target" });
    },
    async saveTrigger() {
      const f = this.triggerForm;
      if (!f.name.trim()) { this.toast("触发器名不能为空"); return; }
      if (!f.table) { this.toast("请选择作用表"); return; }
      if (!f.statement.trim()) { this.toast("请填写触发器语句"); return; }
      const sql = `DROP TRIGGER IF EXISTS ${this.ident(f.name)};\nDELIMITER //\n` +
                  `CREATE TRIGGER ${this.ident(f.name)} ${f.timing} ${f.event} ON ${this.ident(f.table)}\n` +
                  `FOR EACH ROW\nBEGIN\n${f.statement}\nEND//\nDELIMITER ;`;
      try {
        await this.execOne(sql);
        this.toast("触发器已保存");
        await this.reload();
        const t = this.currentTab;
        if (t) { t.title = "设计触发器 - " + f.name; t.name = f.name; t.id = "trigger:" + f.name; }
      } catch (e) { this.toast(e.message); }
    },
    async dropTrigger(t) {
      if (!confirm(`删除触发器「${t.name}」？`)) return;
      try {
        await this.execOne(`DROP TRIGGER IF EXISTS ${this.ident(t.name)}`);
        this.toast("已删除触发器 " + t.name);
        await this.reload();
        const tab = this.tabs.find(x => x.name === t.name);
        if (tab) this.closeTab(tab);
      } catch (e) { this.toast(e.message); }
    },

    /* ---------------- 查询页 ---------------- */
    onSqlChange(v) {
      this.sqlText = v || "";
      this.updateCursor();
    },
    updateCursor() {
      const cm = this.$refs.cmQuery && this.$refs.cmQuery.cm;
      if (!cm) return;
      const p = cm.getCursor();
      this.cursor = { line: p.line + 1, col: p.ch + 1 };
    },
    async runQuery() {
      const sql = (this.builderMode && this.build.tables.length
        ? this.build.sql : this.sqlText || "").trim();
      if (!sql) { this.toast("先写点 SQL"); return; }
      this.running = true;
      this.queryMsg = "";
      this.queryResult = null;
      this.profileResult = null;
      this._runAbort = new AbortController();   // 「停止」按钮用
      try {
        const d = await this.api("/api/sql", { method: "POST", body: { sql, db: this.db },
                                               signal: this._runAbort.signal });
        const results = d.results || [];
        const rowsRes = [...results].reverse().find(r => r.type === "rows");
        const err = results.find(r => r.type === "error");
        const ok = results.filter(r => r.type === "ok");
        this.queryResult = rowsRes || null;
        this.queryInfo = rowsRes ? `${rowsRes.rowCount} 行 · ${rowsRes.ms || 0} ms`
          : ok.length ? `执行成功${ok.reduce((a, r) => a + (r.affected || 0), 0) ? " · 影响 " +
              ok.reduce((a, r) => a + (r.affected || 0), 0) + " 行" : ""}`
          : "";
        this.queryMsg = err ? err.msg
          : results.map(r => r.type === "rows" ? `返回 ${r.rowCount} 行（${r.ms || 0} ms）`
            : r.type === "ok" ? `执行成功，影响 ${r.affected || 0} 行（${r.ms || 0} ms）`
            : r.msg).join("\n");
        this.resultTab = err ? "info" : "result";
        if (!err) {
          this.lastQuerySql = sql;
          this.$emit("query", sql);
          this.$emit("changed");
        } else {
          this.resultTab = "info";
        }
      } catch (e) {
        if (e && e.name === "AbortError") {
          this.queryMsg = "已停止（用户中断）";
          this.queryInfo = "已停止";
        } else {
          this.queryMsg = e.message;
        }
        this.resultTab = "info";
      } finally {
        this.running = false;
        this._runAbort = null;
      }
    },
    stopQuery() {
      if (this._runAbort) this._runAbort.abort();
    },
    // 「文本」按钮（视频 41.5s）：把选中的行加 / 去 -- 注释
    commentToggle() {
      if (this.builderMode) { this.toast("查询创建工具打开时 SQL 是自动生成的，先关闭再编辑"); return; }
      const cm = this.$refs.cmQuery && this.$refs.cmQuery.cm;
      if (!cm) return;
      cm.operation(() => {
        const sels = cm.somethingSelected() ? cm.listSelections()
          : [{ from: cm.getCursor(true), to: cm.getCursor(false) }];
        let commenting = false;
        for (const s of sels) {
          for (let l = s.from.line; l <= s.to.line; l++) {
            if (!(cm.getLine(l) || "").startsWith("-- ")) commenting = true;
          }
        }
        for (const s of sels) {
          for (let l = s.from.line; l <= s.to.line; l++) {
            if (commenting) cm.replaceRange("-- ", { line: l, ch: 0 });
            else if ((cm.getLine(l) || "").startsWith("-- "))
              cm.replaceRange("", { line: l, ch: 0 }, { line: l, ch: 3 });
          }
        }
      });
      this.sqlText = cm.getValue();
    },
    // 「导出结果」：当前结果网格 → CSV 下载
    exportResult() {
      const r = this.queryResult;
      if (!r || !r.columns || !r.columns.length) { this.toast("没有可导出的结果"); return; }
      const esc = (v) => {
        const s = v === null || v === undefined ? "NULL" : String(v);
        return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const lines = [r.columns.map(esc).join(",")];
      for (const row of (r.rows || [])) lines.push(row.map(esc).join(","));
      const blob = new Blob(["\ufeff" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.download = "result_" + Date.now() + ".csv";
      a.href = URL.createObjectURL(blob);
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      this.toast(`已导出 ${r.rowCount} 行 CSV`);
    },
    // 「剖析」标签（视频 41.5s）：对最近一次查询跑 EXPLAIN
    async openProfile() {
      this.resultTab = "profile";
      const sql = (this.lastQuerySql ||
        (this.builderMode && this.build.tables.length ? this.build.sql : this.sqlText) || "").trim();
      if (!/^select/i.test(sql)) { this.profileResult = null; return; }
      try {
        const d = await this.api("/api/sql", {
          method: "POST", body: { sql: "EXPLAIN " + sql.replace(/;\s*$/, ""), db: this.db } });
        this.profileResult = (d.results || []).find(x => x.type === "rows") || null;
      } catch (e) { this.profileResult = null; }
    },
    async explainQuery() {
      const sql = (this.builderMode && this.build.tables.length
        ? this.build.sql : this.sqlText || "").trim();
      if (!sql) { this.toast("先写点 SQL"); return; }
      try {
        const d = await this.api("/api/sql", {
          method: "POST", body: { sql: "EXPLAIN " + sql.replace(/;\s*$/, ""), db: this.db } });
        const rowsRes = (d.results || []).find(r => r.type === "rows");
        this.queryResult = rowsRes || null;
        this.queryInfo = "执行计划";
        this.queryMsg = "EXPLAIN 执行计划";
        this.resultTab = "result";
      } catch (e) { this.queryMsg = e.message; this.resultTab = "info"; }
    },
    beautifySql() {
      // 查询创建工具开着时：先收起工具（生成的 SQL 已经同步在编辑器里），再排版 —— 美化始终可用
      if (this.builderMode) this.builderMode = false;
      if (!String(this.sqlText || "").trim()) { this.toast("还没有可排版的 SQL"); return; }
      this.sqlText = this.formatSql(this.sqlText);
      this.$nextTick(() => {
        if (this.$refs.cmQuery) {
          this.$refs.cmQuery.setValue(this.sqlText);
          this.$refs.cmQuery.refresh();
        }
      });
    },
    // SQL 排版器：字符串字面量先抽出保护 → 关键字大写 → 主子句换行 → ON/AND/OR 缩进 → 顶层逗号换行（括号内不拆）
    formatSql(sql) {
      const strs = [];
      let s = String(sql).replace(/'(?:[^']|'')*'/g, (m) => { strs.push(m); return "\x00" + (strs.length - 1) + "\x00"; });
      s = s.replace(/\s+/g, " ").trim();
      s = s.replace(/\b(select|from|where|group by|having|order by|limit|union all|union|left join|right join|inner join|cross join|join|on|and|or|not|in|like|between|is null|is not null|as|asc|desc|distinct|insert into|values|update|set|delete|create table|alter table|drop table|primary key|foreign key|references|check|constraint|unique|key|engine|default charset|auto_increment|unsigned|zerofill|current_timestamp|null)\b/gi,
                    (m) => m.toUpperCase());
      s = s.replace(/\s?\b(SELECT|FROM|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|UNION ALL|UNION|LEFT JOIN|RIGHT JOIN|INNER JOIN|CROSS JOIN|JOIN|VALUES|SET)\b/g, "\n$1");
      s = s.replace(/^SELECT/, "SELECT");
      s = s.replace(/\b(ON|AND|OR)\b/g, "\n  $1");
      // 只拆顶层逗号：IN (1,2,3)、COUNT(a,b) 这类括号里的逗号保持原样
      let out = "", depth = 0;
      for (const ch of s) {
        if (ch === "(") depth++;
        if (ch === ")") depth = Math.max(0, depth - 1);
        out += (ch === "," && depth === 0) ? ",\n  " : ch;
      }
      s = out.split("\n").map(l => l.replace(/\s+$/, "")).join("\n").trim();
      s = s.replace(/;\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXPLAIN)\b/g, ";\n\n$1");
      s = s.replace(/\x00(\d+)\x00/g, (m, i) => strs[Number(i)]);
      return s.replace(/\s+$/, "").replace(/;?$/, ";");
    },
    /* 代码段面板（视频 41.5s）：分类 + 搜索 + 点击插入 */
    insertSnippet(ev) {
      this.snippetPane = true;
    },
    pasteSnippet(text) {
      if (this.builderMode) this.builderMode = false;
      this.$nextTick(() => {
        this.sqlText = (String(this.sqlText || "").trim() ? String(this.sqlText).trim() + "\n\n" : "") + text + "\n";
        if (this.$refs.cmQuery) {
          this.$refs.cmQuery.setValue(this.sqlText);
          this.$refs.cmQuery.refresh();
        }
      });
    },
    saveQuery() {
      try {
        localStorage.setItem("lab_nav_query:" + this.drill.id, this.sqlText || "");
        this.toast("查询已保存到本浏览器");
      } catch (e) { this.toast("保存失败"); }
    },

    /* ---------------- 创建图表（把查询结果画成柱状/折线/饼图） ---------------- */
    openChart() {
      const r = this.queryResult;
      if (!r || !r.rows || !r.rows.length) {
        this.toast("先运行一个返回数据的查询（比如分组统计），再点「创建图表」");
        return;
      }
      const numeric = this.chartNumericCols;
      if (!numeric.length) { this.toast("结果里没有数值列，画不了图"); return; }
      this.chart.x = r.columns[0] || "";
      this.chart.y = numeric.find(c => c !== this.chart.x) || numeric[0];
      this.chart.open = true;
    },
    closeChart() { this.chart.open = false; },
    downloadChartPng() {
      const svg = this.chartSvg;
      if (!svg) { this.toast("先选好 X / Y 字段再导出"); return; }
      try {
        const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          const cv = document.createElement("canvas");
          cv.width = 1280; cv.height = 680;
          const c2 = cv.getContext("2d");
          c2.fillStyle = "#ffffff";
          c2.fillRect(0, 0, cv.width, cv.height);
          c2.drawImage(img, 0, 0, cv.width, cv.height);
          URL.revokeObjectURL(url);
          const a = document.createElement("a");
          a.download = "chart_" + Date.now() + ".png";
          a.href = cv.toDataURL("image/png");
          a.click();
        };
        img.onerror = () => { URL.revokeObjectURL(url); this.toast("导出失败"); };
        img.src = url;
      } catch (e) { this.toast("导出失败"); }
    },

    /* ---------------- 连接设置对话框（视频 8-21s） ---------------- */
    openConnDlg() {
      this.connForm.db = this.schema.db || this.db;
      this.connMsg = "";
      this.dlg = "conn";
    },
    async testConn() {
      this.connMsg = "正在测试…";
      try {
        await this.reload();
        this.connMsg = "";
        this.toast("连接成功（本地 · MySQL 5.7）");
      } catch (e) {
        this.connMsg = "";
        this.toast(e.message || "连接失败");
      }
    },
    async connectNow() {
      this.dlg = "";
      await this.reload();
      this.toast("已连接 " + (this.connForm.host || "localhost") + ":" + this.connForm.port);
    },

    /* ---------------- 查询创建工具（Navicat 同款：内嵌在查询页，工具栏按钮切换） ---------------- */
    blankBuilder() {
      // rows：准则网格的行，逐行选 表.字段（拖入表不会自动选字段，和 Navicat 一样）
      return { tables: [], joins: [], rows: [], sql: "", search: "", viewMode: "fields" };
    },
    // 「构建」：把生成的 SQL 放进编辑器（构建器保持打开）；「构建并运行」= 运行；「取消」= 收起
    buildToEditor() {
      if (!this.build.sql) { this.toast("先加一张表再构建"); return; }
      this.sqlText = this.build.sql;
      this.$nextTick(() => {
        if (this.$refs.cmQuery) this.$refs.cmQuery.setValue(this.build.sql);
      });
      this.toast("SQL 已构建到编辑器");
    },
    openBuilder() {
      if (!this.build || !this.build.tables) this.build = this.blankBuilder();
      if (!this.build.viewMode) this.build.viewMode = "fields";   // 旧会话兼容
      if (this.active !== "query") this.newQueryTab();
      this.builderMode = !this.builderMode;
      if (this.builderMode) this.syncBuilderSql();
    },
    clearBuilder() {
      this.build = this.blankBuilder();
      this.toast("已清空图表");
    },
    isBuildAdded(name) { return this.build.tables.some(t => t.name === name); },
    toggleBuildTable(name) {
      const added = this.build.tables.find(t => t.name === name);
      if (added) this.removeBuildTable(added);
      else this.addBuildTableByName(name);
    },
    addBuildTable(t) {
      if (!t || this.isBuildAdded(t.name)) return;
      const n = this.build.tables.length;
      const nt = {
        id: "t" + Date.now() + "_" + n,
        name: t.name, alias: "",
        x: 24 + (n % 3) * 216, y: 18 + Math.floor(n / 3) * 200,
        columns: (t.columns || []).map(c => ({ name: c.name, key: c.key || "" })),
      };
      this.build.tables.push(nt);
      this.autoJoinFks(nt);   // Navicat 同款：按外键自动连线
    },
    // 新表引用了已加的表，或已加的表引用了新表，都自动连上
    autoJoinFks(nt) {
      const src = this.schema.tables.find(x => x.name === nt.name) || {};
      const link = (a, acol, b, bcol) => {
        if (!a || !b || a.id === b.id || !acol || !bcol) return;
        this.makeJoin({ t: a, c: a.columns.find(c => c.name === acol) },
                      { t: b, c: b.columns.find(c => c.name === bcol) });
      };
      for (const fk of src.fks || [])
        link(nt, fk.col,
             this.build.tables.find(x => x.name === fk.refTable && x.id !== nt.id), fk.refCol);
      for (const other of this.build.tables) {
        if (other.id === nt.id) continue;
        const osrc = this.schema.tables.find(x => x.name === other.name) || {};
        for (const fk of osrc.fks || [])
          if (fk.refTable === nt.name) link(other, fk.col, nt, fk.refCol);
      }
    },
    addBuildTableByName(name) {
      const t = this.schema.tables.find(x => x.name === name) ||
                this.schema.views.find(x => x.name === name);
      if (t) this.addBuildTable(t);
    },
    // 桌面：从「对象」窗格把表拖进图表，落点即位置
    dropBuildTable(ev) {
      const name = this.buildDragName;
      this.buildDragName = "";
      if (!name || this.isBuildAdded(name)) return;
      this.addBuildTableByName(name);
      const cv = this.$refs.canvas;
      const t = this.build.tables[this.build.tables.length - 1];
      if (t && cv) {
        const r = cv.getBoundingClientRect();
        t.x = Math.max(0, Math.round(ev.clientX - r.left - 80));
        t.y = Math.max(0, Math.round(ev.clientY - r.top - 12));
      }
    },
    removeBuildTable(t) {
      this.build.tables = this.build.tables.filter(x => x !== t);
      this.build.joins = this.build.joins.filter(j => j.a.tid !== t.id && j.b.tid !== t.id);
      this.build.rows = this.build.rows.filter(r => r.tid !== t.id);
    },
    tableById(id) { return this.build.tables.find(t => t.id === id) || null; },
    // Navicat 生成的 SQL 用 emp.SAL 这种裸引用，不加反引号
    colRef(t, col) {
      const base = t.alias || t.name;
      return col === "*" ? base + ".*" : base + "." + col;
    },

    /* ---- 准则网格的行：拖入表不选任何字段，行是逐个挑出来的 ---- */
    rowByField(tid, col) {
      return this.build.rows.find(r => r.tid === tid && r.col === col) || null;
    },
    keyOf(t, col) {
      const c = t && (t.columns || []).find(x => x.name === col);
      return (c && c.key) || "";
    },
    // 图表卡片上勾字段 = 添加/移除一行（显示默认勾上）
    toggleBuildField(t, col) {
      const row = this.rowByField(t.id, col);
      if (row) this.build.rows = this.build.rows.filter(r => r !== row);
      else this.addBuildRow(t.id, col);
    },
    isFieldOn(t, col) { return !!this.rowByField(t.id, col); },
    addBuildRow(tid, col) {
      if (!col || this.rowByField(tid, col)) return;
      this.build.rows.push({ tid, col, show: true, alias: "", agg: "",
                             sort: "", op: "", val: "", op2: "", val2: "" });
    },
    rowSetTable(r, tid) {
      if (!tid || tid === r.tid) return;
      r.tid = tid;
      r.col = "";
      r.alias = ""; r.agg = ""; r.sort = ""; r.op = ""; r.val = ""; r.op2 = ""; r.val2 = "";
    },
    rowSetCol(r, col) {
      if (!col) return;
      const dup = this.rowByField(r.tid, col);
      if (dup && dup !== r) { this.toast("这个字段已经在准则里了"); return; }
      r.col = col;
    },
    removeBuildRow(r) { this.build.rows = this.build.rows.filter(x => x !== r); },
    // 网格最后一行「新行」：先选表再选字段，选完落成一行
    commitNewRow(col) {
      const nw = this.newRow;
      if (!nw.tid || !col) return;
      if (this.rowByField(nw.tid, col)) { this.toast("这个字段已经在准则里了"); nw.col = ""; return; }
      this.addBuildRow(nw.tid, col);
      nw.tid = ""; nw.col = "";
    },
    colAnchor(t, colName, side) {
      const i = Math.max(0, t.columns.findIndex(c => c.name === colName));
      return { x: side === "r" ? t.x + 180 : t.x, y: t.y + 30 + i * 22 + 11 };
    },
    // 连线两端各自挑离对方更近的那条边，避免线绕到表框后面
    joinEnds(j) {
      const a = this.tableById(j.a.tid), b = this.tableById(j.b.tid);
      if (!a || !b) return null;
      const right = (b.x + 90) > (a.x + 90);
      return {
        p1: this.colAnchor(a, j.a.col, right ? "r" : "l"),
        p2: this.colAnchor(b, j.b.col, right ? "l" : "r"),
      };
    },
    joinPath(j) {
      const e = this.joinEnds(j);
      if (!e) return "";
      const dx = Math.max(30, Math.abs(e.p2.x - e.p1.x) / 2);
      return `M ${e.p1.x} ${e.p1.y} C ${e.p1.x + dx} ${e.p1.y}, ` +
             `${e.p2.x - dx} ${e.p2.y}, ${e.p2.x} ${e.p2.y}`;
    },
    joinMid(j) {
      const e = this.joinEnds(j);
      if (!e) return { x: 0, y: 0 };
      return { x: Math.round((e.p1.x + e.p2.x) / 2), y: Math.round((e.p1.y + e.p2.y) / 2) };
    },
    joinTypeName(j) {
      return { INNER: "内连接", LEFT: "左连接", RIGHT: "右连接" }[j.type] || "内连接";
    },
    joinLabel(j) {
      const a = this.tableById(j.a.tid), b = this.tableById(j.b.tid);
      if (!a || !b) return "";
      return this.joinTypeName(j) + "：" + this.colRef(a, j.a.col) + " = " + this.colRef(b, j.b.col);
    },
    openJoinMenu(ev, j) { this.openCtx(ev, "join", j); },
    removeJoin(j) { this.build.joins = this.build.joins.filter(x => x !== j); },

    /* ---- 画布拖拽：鼠标和触屏统一走 Pointer Events ----
       按下时把指针捕获到画布，后续 move/up 都在画布上收到；
       用 elementFromPoint 找悬停字段（触屏的 pointerup 原本只会落在
       起点元素上）。没拖动就抬起时进入“选中”状态，再点一下目标
       字段也能连线（手机上点-点连线更好用）。 */
    startMoveTable(ev, t) {
      if (ev.target.closest && ev.target.closest("button, input, select")) return;
      const cv = this.$refs.canvas;
      if (!cv) return;
      const r = cv.getBoundingClientRect();
      this.dragTable = { t, dx: ev.clientX - r.left - t.x, dy: ev.clientY - r.top - t.y };
      try { cv.setPointerCapture(ev.pointerId); } catch (e) {}
      ev.preventDefault();
    },
    startJoin(ev, t, c) {
      // 已经“选中”了一个源字段：这次点的是目标字段（点-点连线）
      if (this.dragJoin && !this.dragJoin.dragging) {
        const from = this.dragJoin;
        if (from.t.id !== t.id) this.makeJoin(from, { t, c });
        this.dragJoin = null; this.dragPos = null; this.hoverJoin = null;
        return;
      }
      const cv = this.$refs.canvas;
      if (!cv) return;
      this.dragJoin = { t, c, dragging: false, sx: ev.clientX, sy: ev.clientY };
      try { cv.setPointerCapture(ev.pointerId); } catch (e) {}
      ev.preventDefault();
    },
    makeJoin(from, to) {
      if (!from || !to || from.t.id === to.t.id) return;
      const dup = this.build.joins.some(j =>
        (j.a.tid === from.t.id && j.a.col === from.c.name &&
         j.b.tid === to.t.id && j.b.col === to.c.name) ||
        (j.b.tid === from.t.id && j.b.col === from.c.name &&
         j.a.tid === to.t.id && j.a.col === to.c.name));
      if (dup) return;
      this.build.joins.push({
        id: "j" + Date.now(), type: "INNER",
        a: { tid: from.t.id, col: from.c.name },
        b: { tid: to.t.id, col: to.c.name },
      });
    },
    joinTargetAt(ev) {
      const el = document.elementFromPoint(ev.clientX, ev.clientY);
      const col = el && el.closest ? el.closest(".nc-tcol") : null;
      if (!col) return null;
      const t = this.tableById(col.dataset.tid);
      const c = t && t.columns.find(x => x.name === col.dataset.col);
      return (t && c) ? { t, c } : null;
    },
    onCanvasMove(ev) {
      const cv = this.$refs.canvas;
      if (!cv) return;
      const r = cv.getBoundingClientRect();
      const x = ev.clientX - r.left, y = ev.clientY - r.top;
      if (this.dragTable) {
        this.dragTable.t.x = Math.max(0, Math.round(x - this.dragTable.dx));
        this.dragTable.t.y = Math.max(0, Math.round(y - this.dragTable.dy));
      } else if (this.dragJoin) {
        if (!this.dragJoin.dragging &&
            Math.hypot(ev.clientX - this.dragJoin.sx, ev.clientY - this.dragJoin.sy) > 6)
          this.dragJoin.dragging = true;
        if (this.dragJoin.dragging) {
          this.dragPos = { x, y };
          const hit = this.joinTargetAt(ev);
          this.hoverJoin = (hit && hit.t.id !== this.dragJoin.t.id) ? hit : null;
        }
      }
    },
    onCanvasUp(ev) {
      if (this.dragTable) { this.dragTable = null; return; }
      if (!this.dragJoin) return;
      const from = this.dragJoin;
      if (from.dragging) {
        const hit = ev ? this.joinTargetAt(ev) : null;
        if (hit && hit.t.id !== from.t.id) this.makeJoin(from, hit);
        this.dragJoin = null; this.dragPos = null; this.hoverJoin = null;
      }
      // 没拖动就抬起：保持“选中”，等下一次点目标字段
    },
    dragLinePath() {
      if (!this.dragJoin) return "";
      const t = this.dragJoin.t;
      const p = this.dragPos || this.colAnchor(t, this.dragJoin.c.name, "r");
      const side = p.x >= t.x + 90 ? "r" : "l";
      const a = this.colAnchor(t, this.dragJoin.c.name, side);
      return `M ${a.x} ${a.y} L ${p.x} ${p.y}`;
    },

    /* ---- SQL 生成（Navicat 同款：裸引用；汇总行进 SELECT 聚合，未聚合的显示行进
       GROUP BY，聚合行的条件进 HAVING、普通行的条件进 WHERE；「条件」「或」先各自
       OR，不同字段之间 AND） ---- */
    condSql(ref, op, val) {
      if (!op) return "";
      if (/^IS/i.test(op)) return ref + " " + op.toUpperCase();
      const v = String(val == null ? "" : val).trim();
      if (!v) return "";
      if (op === "IN" || op === "NOT IN")
        return ref + " " + op + " " + (v.startsWith("(") ? v : "(" + v + ")");
      if (op === "BETWEEN") {
        const m = v.split(/\s+AND\s+/i);
        if (m.length === 2 && m[0].trim() && m[1].trim())
          return ref + " BETWEEN " + m[0].trim() + " AND " + m[1].trim();
        return "";
      }
      const raw = /^-?\d+(\.\d+)?$/.test(v) || /^[\('"]/.test(v);
      return ref + " " + op + " " + (raw ? v : this.lit(v));
    },
    // 行的表达式：有汇总就包一层聚合函数（* 与聚合组合成 COUNT(*)）
    rowExpr(t, r) {
      if (!r.agg) return this.colRef(t, r.col);
      if (r.col === "*") return r.agg + "(*)";
      return r.agg + "(" + this.colRef(t, r.col) + ")";
    },
    rowConds(r) {
      const t = this.tableById(r.tid);
      const ref = this.rowExpr(t, r);
      const c1 = this.condSql(ref, r.op, r.val);
      const c2 = this.condSql(ref, r.op2, r.val2);
      if (c1 && c2) return "(" + c1 + " OR " + c2 + ")";
      return c1 || c2;
    },
    genSql() {
      const b = this.build;
      if (!b.tables.length) return "";
      // SELECT：勾了「显示」的行（没有任何行就 SELECT *）
      const sel = [];
      for (const r of b.rows) {
        if (!r.show || !r.col || !this.tableById(r.tid)) continue;
        const t = this.tableById(r.tid);
        sel.push(this.rowExpr(t, r) + (r.alias ? " AS " + r.alias : ""));
      }
      let sql = "SELECT " + (sel.length ? sel.join(", ") : "*");
      // FROM + JOIN：从第一张表沿连线把表一张张挂进来（连线方向可能反着），
      // 没连到的表用逗号并列；成环的多余连线不重复 JOIN
      const first = b.tables[0];
      const inFrom = new Set([first.id]);
      let from = first.name + (first.alias ? " " + first.alias : "");
      const pending = b.joins.slice();
      let progressed = true;
      while (pending.length && progressed) {
        progressed = false;
        for (let i = 0; i < pending.length; i++) {
          const j = pending[i];
          const ta = this.tableById(j.a.tid), tb = this.tableById(j.b.tid);
          if (!ta || !tb) { pending.splice(i, 1); i--; continue; }
          let side = null;
          if (inFrom.has(j.a.tid) && !inFrom.has(j.b.tid)) side = tb;
          else if (inFrom.has(j.b.tid) && !inFrom.has(j.a.tid)) side = ta;
          if (!side) continue;
          from += " " + j.type + " JOIN " + side.name + (side.alias ? " " + side.alias : "") +
                  " ON " + this.colRef(ta, j.a.col) + " = " + this.colRef(tb, j.b.col);
          inFrom.add(side.id);
          pending.splice(i, 1);
          progressed = true;
          break;
        }
      }
      for (const t of b.tables) {
        if (inFrom.has(t.id)) continue;
        from += ", " + t.name + (t.alias ? " " + t.alias : "");
        inFrom.add(t.id);
      }
      sql += "\nFROM " + from;
      // WHERE：普通行的条件；HAVING：汇总行的条件
      const wheres = [], havings = [];
      for (const r of b.rows) {
        if (!r.col || !this.tableById(r.tid)) continue;
        (r.agg ? havings : wheres).push(this.rowConds(r));
      }
      if (wheres.filter(Boolean).length) sql += "\nWHERE " + wheres.filter(Boolean).join(" AND ");
      // GROUP BY：没汇总但显示了的字段（有汇总时才需要）
      const hasAgg = b.rows.some(r => r.agg && r.col && this.tableById(r.tid));
      const groups = [];
      for (const r of b.rows) {
        if (r.agg || !r.show || !r.col || !this.tableById(r.tid)) continue;
        groups.push(this.colRef(this.tableById(r.tid), r.col));
      }
      if (hasAgg && groups.length) sql += "\nGROUP BY " + groups.join(", ");
      if (havings.filter(Boolean).length) sql += "\nHAVING " + havings.filter(Boolean).join(" AND ");
      // ORDER BY
      const ords = [];
      for (const r of b.rows) {
        if (!r.sort || !r.col || !this.tableById(r.tid)) continue;
        ords.push(this.rowExpr(this.tableById(r.tid), r) + " " + r.sort);
      }
      if (ords.length) sql += "\nORDER BY " + ords.join(", ");
      return sql + ";";
    },
    syncBuilderSql() {
      const b = this.build;
      if (!b) return;
      b.sql = this.genSql();
      // SQL 窗格只读；生成的语句就是查询页的 SQL（和 Navicat 一致，「运行」即作答）
      if (this.builderMode && b.tables.length) this.sqlText = b.sql;
    },

    /* ---- 准则网格「条件 / 或」组合框弹层（不用自己打 SQL） ---- */
    condNeedVal(op) { return !!op && !/^IS/i.test(op); },
    condText(r, which) {
      const op = which === "or" ? r.op2 : r.op;
      if (!op) return "";
      if (/^IS/i.test(op)) return op;
      const v = String((which === "or" ? r.val2 : r.val) || "").trim();
      return op + (v ? " " + v : "");
    },
    openCond(ev, r, which) {
      const t = this.tableById(r.tid);
      const rect = this.$el.getBoundingClientRect();
      this.condPop = {
        tid: r.tid, col: r.col, which,
        label: (t ? (t.alias || t.name) : "") + "." + r.col,
        op: which === "or" ? (r.op2 || "") : (r.op || ""),
        val: which === "or" ? (r.val2 || "") : (r.val || ""),
        x: Math.round(ev.clientX - rect.left), y: Math.round(ev.clientY - rect.top),
      };
      this.$nextTick(() => this.clampCond());
    },
    clampCond() {
      const el = this.$refs.condPop;
      if (!el || !this.condPop) return;
      const r = this.$el.getBoundingClientRect();
      const w = el.offsetWidth, h = el.offsetHeight;
      if (this.condPop.x + w > r.width - 8) this.condPop.x = Math.max(6, r.width - w - 8);
      if (this.condPop.y + h > r.height - 8) this.condPop.y = Math.max(6, r.height - h - 8);
    },
    setCondOp(op) { if (this.condPop) this.condPop.op = op; },
    applyCond() {
      const p = this.condPop;
      if (!p) return;
      this.writeCond(p, p.op, p.val);
      this.condPop = null;
    },
    clearCond() {
      const p = this.condPop;
      if (!p) return;
      this.writeCond(p, "", "");
      this.condPop = null;
    },
    writeCond(p, op, val) {
      const r = this.rowByField(p.tid, p.col);
      if (!r) return;
      if (p.which === "or") { r.op2 = op; r.val2 = val; }
      else { r.op = op; r.val = val; }
    },

    /* ---------------- 菜单 / 工具栏 ---------------- */
    toggleMenu(m) {
      this.menu = this.menu === m ? "" : m;
    },
    async menuAction(a) {
      this.menu = "";
      if (a === "newQuery") this.newQueryTab();
      else if (a === "refresh") await this.reload();
      else if (a === "closeTab" && this.currentTab) this.closeTab(this.currentTab);
      else if (a === "export") await this.exportDb();
    },
    toolClick(t) {
      if (t.key === "query") { this.newQueryTab(); return; }
      if (t.key === "tables") { this.selectNode("tables"); return; }
      if (t.key === "views") { this.selectNode("views"); return; }
      if (t.key === "routines") { this.selectNode("routines"); return; }
      if (t.key === "triggers") { this.selectNode("triggers"); return; }
      if (t.key === "users") { this.toast("用户管理请在站点「管理」里操作"); return; }
      if (t.key === "backup") { this.exportDb(); return; }
      if (t.key === "other") { this.toast("课堂版：常用对象在左侧树里"); return; }
    },
    async exportDb() {
      try {
        const resp = await fetch(`/api/databases/${encodeURIComponent(this.db)}/export`,
                                 { headers: { "X-Token": this.token } });
        if (!resp.ok) throw new Error("导出失败");
        const blob = await resp.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = this.db + ".sql";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 3000);
        this.toast("已导出 " + this.db + ".sql");
      } catch (e) { this.toast(e.message); }
    },

    /* ---------------- 导入 ---------------- */
    openImport() {
      this.importForm = { file: null, table: "", header: true, overwrite: false, busy: false };
      this.dlg = "import";
    },
    pickImport(ev) { this.importForm.file = (ev.target.files || [])[0] || null; },
    async doImport() {
      const f = this.importForm;
      if (!f.file) { this.toast("先选一个 .csv / .xlsx / .sql 文件"); return; }
      f.busy = true;
      try {
        const fd = new FormData();
        fd.append("file", f.file);
        fd.append("table", f.table);
        fd.append("header", f.header ? "true" : "false");
        fd.append("overwrite", f.overwrite ? "true" : "false");
        fd.append("db", this.db);
        const resp = await fetch("/api/import", { method: "POST",
          headers: { "X-Token": this.token }, body: fd });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(typeof d.detail === "string" ? d.detail : "导入失败");
        this.toast("导入完成");
        this.dlg = "";
        await this.reload();
      } catch (e) { this.toast(e.message); }
      finally { f.busy = false; }
    },

    /* ---------------- 右键菜单（Navicat 风格） ---------------- */
    openCtx(ev, kind, payload) {
      if (ev && ev.preventDefault) ev.preventDefault();
      const items = this.ctxItems(kind, payload).filter(Boolean);
      if (!items.length) return;
      const r = this.$el.getBoundingClientRect();
      this.ctx = { show: true, x: Math.round(ev.clientX - r.left), y: Math.round(ev.clientY - r.top), items };
      this.$nextTick(() => this.clampCtx());
    },
    clampCtx() {
      const el = this.$refs.ctxMenu;
      if (!el) return;
      const r = this.$el.getBoundingClientRect();
      const w = el.offsetWidth, h = el.offsetHeight;
      if (this.ctx.x + w > r.width - 6) this.ctx.x = Math.max(4, r.width - w - 6);
      if (this.ctx.y + h > r.height - 6) this.ctx.y = Math.max(4, r.height - h - 6);
    },
    runCtx(it) {
      this.ctx.show = false;
      if (it && !it.disabled && typeof it.action === "function") it.action();
    },
    // 触屏长按等同右键
    pressStart(ev, kind, payload) {
      if (ev.pointerType === "mouse") return;
      clearTimeout(this._pressTimer);
      const x = ev.clientX, y = ev.clientY;
      this._pressTimer = setTimeout(() => {
        this.openCtx({ clientX: x, clientY: y, preventDefault() {} }, kind, payload);
      }, 550);
    },
    pressEnd() { clearTimeout(this._pressTimer); },
    async copyText(text) {
      try {
        await navigator.clipboard.writeText(String(text == null ? "" : text));
        this.toast("已复制：" + String(text).slice(0, 40));
      } catch (e) {
        this.toast("复制失败，请手动选中复制");
      }
    },
    async pasteCell(ri, ci) {
      try {
        const txt = await navigator.clipboard.readText();
        this.cellInput(ri, ci, { target: { value: txt } });
      } catch (e) { this.toast("浏览器不允许读取剪贴板，请直接输入"); }
    },
    ctxItems(kind, p) {
      const sep = { sep: true };
      const refresh = { label: "刷新", icon: "refresh", action: () => this.reload() };
      const newQuery = { label: "新建查询", icon: "search", action: () => this.newQueryTab() };
      if (kind === "conn") {
        return [
          { label: "连接属性…", icon: "database", action: () => this.openConnDlg() },
          { label: "新建查询", icon: "search", action: () => this.newQueryTab() },
          sep,
          { label: "刷新", icon: "refresh", action: () => this.reload() },
        ];
      }
      if (kind === "tree") {
        const map = {
          tables: { label: "新建表", icon: "plus", action: () => this.openDesign("", "new") },
          views: { label: "新建视图", icon: "plus", action: () => this.openViewDesign("", "new") },
          routines: { label: "新建存储过程", icon: "plus", action: () => this.openRoutine(null, "new") },
          triggers: { label: "新建触发器", icon: "plus", action: () => this.openTrigger(null, "new") },
          queries: newQuery,
        };
        return [map[p], sep, newQuery, refresh].filter(Boolean);
      }
      if (kind === "table") {
        return [
          { label: "打开表", icon: "folder-open", action: () => this.openTable(p, "table") },
          { label: "设计表", icon: "file-text", action: () => this.openDesign(p) },
          sep,
          { label: "新建表", icon: "plus", action: () => this.openDesign("", "new") },
          { label: "删除表", icon: "trash", danger: true, action: () => this.dropTable(p) },
          sep,
          { label: "复制表名", icon: "list", action: () => this.copyText(p) },
          { label: "导入向导", icon: "upload", action: () => this.openImport() },
          { label: "导出整库", icon: "download", action: () => this.exportDb() },
          refresh,
        ];
      }
      if (kind === "view") {
        return [
          { label: "打开视图", icon: "folder-open", action: () => this.openTable(p, "view") },
          { label: "设计视图", icon: "file-text", action: () => this.openViewDesign(p) },
          sep,
          { label: "新建视图", icon: "plus", action: () => this.openViewDesign("", "new") },
          { label: "删除视图", icon: "trash", danger: true, action: () => this.dropView(p) },
          sep,
          { label: "复制视图名", icon: "list", action: () => this.copyText(p) },
          refresh,
        ];
      }
      if (kind === "routine") {
        const r = this.schema.routines.find(x => x.name === p) || {};
        return [
          { label: "运行", icon: "play", action: () => this.openRunRoutine(r) },
          { label: "设计", icon: "file-text", action: () => this.openRoutine(r) },
          sep,
          { label: "新建存储过程", icon: "plus", action: () => this.openRoutine(null, "new") },
          { label: "新建函数", icon: "plus", action: () => this.openRoutine({ type: "FUNCTION" }, "new") },
          { label: "删除", icon: "trash", danger: true, action: () => this.dropRoutine(r) },
          sep,
          { label: "复制名称", icon: "list", action: () => this.copyText(p) },
          refresh,
        ];
      }
      if (kind === "trigger") {
        const t = this.schema.triggers.find(x => x.name === p) || {};
        return [
          { label: "设计", icon: "file-text", action: () => this.openTrigger(t) },
          { label: "新建触发器", icon: "plus", action: () => this.openTrigger(null, "new") },
          { label: "删除", icon: "trash", danger: true, action: () => this.dropTrigger(t) },
          sep,
          { label: "复制名称", icon: "list", action: () => this.copyText(p) },
          refresh,
        ];
      }
      if (kind === "cell") {
        const val = this.cellValue(p.ri, p.ci);
        const isView = this.currentTab && this.currentTab.kind === "view";
        return [
          { label: "复制该值", icon: "list", action: () => this.copyText(val) },
          isView ? null : { label: "粘贴", icon: "download", action: () => this.pasteCell(p.ri, p.ci) },
          isView ? null : { label: "设为 NULL", icon: "eraser", action: () => this.cellInput(p.ri, p.ci, { target: { value: "" } }) },
          sep,
          isView ? null : { label: "在上面插入一行", icon: "plus", action: () => this.addRow() },
          isView ? null : { label: "删除这一行", icon: "trash", danger: true, action: () => this.deleteRow(p.ri) },
          sep,
          { label: "应用修改", icon: "check", action: () => this.applyTable() },
          { label: "刷新数据", icon: "refresh", action: () => this.loadRows() },
        ].filter(Boolean);
      }
      if (kind === "editor") {
        return [
          { label: "运行", icon: "play", action: () => this.runQuery() },
          { label: "解释执行计划", icon: "search", action: () => this.explainQuery() },
          sep,
          { label: "美化 SQL", icon: "list", action: () => this.beautifySql() },
          { label: "插入代码段", icon: "plus", action: () => this.insertSnippet() },
          sep,
          { label: "全选", icon: "check", action: () => { const cm = this.$refs.cmQuery && this.$refs.cmQuery.cm; if (cm) cm.execCommand("selectAll"); } },
          { label: "清空", icon: "eraser", danger: true, action: () => { this.sqlText = ""; this.$nextTick(() => { if (this.$refs.cmQuery) this.$refs.cmQuery.setValue(""); }); } },
          { label: "保存查询", icon: "file-text", action: () => this.saveQuery() },
        ];
      }
      if (kind === "join") {
        const cur = (t) => (p.type === t ? "● " : "") + { INNER: "内连接", LEFT: "左连接", RIGHT: "右连接" }[t] + "（" + t + " JOIN）";
        return [
          { label: cur("INNER"), action: () => { p.type = "INNER"; } },
          { label: cur("LEFT"), action: () => { p.type = "LEFT"; } },
          { label: cur("RIGHT"), action: () => { p.type = "RIGHT"; } },
          sep,
          { label: "删除连接", icon: "trash", danger: true, action: () => this.removeJoin(p) },
        ];
      }
      if (kind === "canvas") {
        return [
          { label: "添加表", icon: "plus", action: () => this.toast("从左边「对象」窗格点一张表，或拖进图表") },
          { label: "清空图表", icon: "eraser", danger: true, action: () => this.clearBuilder() },
        ];
      }
      if (kind === "tab") {
        return [
          { label: "关闭", icon: "x", action: () => this.closeTab(this.currentTab) },
          { label: "关闭其他", icon: "x", action: () => { this.tabs = []; this.active = "objects"; } },
          sep,
          newQuery,
          refresh,
        ];
      }
      // 空白处
      return [newQuery, { label: "新建表", icon: "plus", action: () => this.openDesign("", "new") }, sep, refresh];
    },

    /* ---------------- 模板辅助 ---------------- */
    objCount(name) { return (this.schema[name] || []).length; },
    typeIcon(t) { return t === "FUNCTION" ? "code" : "file-text"; },
  },
};
