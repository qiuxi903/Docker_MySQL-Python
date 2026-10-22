/* Navicat 仿真面板：做题时用图形界面完成建表、改数据、建视图/函数/触发器、写查询 */
"use strict";

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
      dragTable: null,
      dragJoin: null,
      dragPos: null,
      focusTarget: null,
      ctx: { show: false, x: 0, y: 0, items: [] },
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
  },

  mounted() {
    if (this.db) this.reload();
    this._menuOff = () => { this.menu = ""; this.ctx.show = false; };
    this._escOff = (e) => { if (e.key === "Escape") { this.ctx.show = false; this.menu = ""; } };
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

    /* ---------------- 设计表 ---------------- */
    blankDesign() {
      return {
        mode: "new", name: "", originalName: "", engine: "InnoDB", charset: "utf8mb4",
        comment: "", originalEngine: "InnoDB", originalCharset: "utf8mb4", originalComment: "",
        columns: [{ name: "id", type: "INT", length: null, scale: null, nullable: false,
                    pk: true, auto: true, default: "", comment: "" }],
        indexes: [], originalColumns: [], originalIndexes: [], tab: "columns",
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
        return {
          name: c.name, type: p.type, length: p.length, scale: p.scale,
          extra: p.extra || "", nullable: c.nullable, pk: c.key === "PRI",
          auto: String(c.extra || "").toUpperCase().includes("AUTO_INCREMENT"),
          default: c.default === null ? "" : c.default, comment: c.comment || "",
        };
      });
      const indexes = (t.indexes || [])
        .filter(i => i.name !== "PRIMARY")
        .map(i => ({ name: i.name, unique: i.unique, columns: (i.columns || []).join(", "), type: i.type }));
      this.design = {
        mode: "edit", name: t.name, originalName: t.name,
        engine: t.engine || "InnoDB", charset: this.schema.charset || "utf8mb4",
        comment: t.comment || "",
        originalEngine: t.engine || "InnoDB", originalCharset: this.schema.charset || "utf8mb4",
        originalComment: t.comment || "",
        columns: cols, indexes,
        originalColumns: JSON.parse(JSON.stringify(cols)),
        originalIndexes: JSON.parse(JSON.stringify(indexes)),
        tab: "columns",
      };
      this.ensureTab({ id: "design:" + name, kind: "design", name, title: "设计表 - " + name, icon: "table" });
    },
    addDesignCol() {
      this.design.columns.push({ name: "new_col", type: "VARCHAR", length: 50, scale: null,
                                 extra: "", nullable: true, pk: false, auto: false,
                                 default: "", comment: "" });
    },
    delDesignCol(i) { this.design.columns.splice(i, 1); },
    moveDesignCol(i, dir) {
      const c = this.design.columns;
      const j = i + dir;
      if (j < 0 || j >= c.length) return;
      [c[i], c[j]] = [c[j], c[i]];
    },
    addIndex() {
      this.design.indexes.push({ name: "idx_" + (this.design.indexes.length + 1),
                                 unique: false, columns: "", type: "BTREE" });
    },
    delIndex(i) { this.design.indexes.splice(i, 1); },
    colTypeSql(c) {
      let t = String(c.type || "VARCHAR").toUpperCase();
      if (["VARCHAR", "CHAR"].includes(t) && c.length) t += `(${c.length})`;
      else if (["DECIMAL", "DOUBLE", "FLOAT"].includes(t) && c.length)
        t += `(${c.length}${c.scale !== null && c.scale !== "" && c.scale !== undefined ? "," + c.scale : ""})`;
      else if (["INT", "BIGINT", "TINYINT", "SMALLINT", "MEDIUMINT"].includes(t) && c.length)
        t += `(${c.length})`;
      if (c.extra) t += " " + String(c.extra).toUpperCase();
      return t;
    },
    colSql(c) {
      let s = `${this.ident(c.name)} ${this.colTypeSql(c)}`;
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
    async saveDesign() {
      const d = this.design;
      if (!d.name.trim()) { this.toast("表名不能为空"); return; }
      const stmts = [];
      try {
        if (d.mode === "new") {
          const defs = d.columns.map(c => this.colSql(c));
          const pk = d.columns.filter(c => c.pk).map(c => this.ident(c.name));
          if (pk.length) defs.push("PRIMARY KEY (" + pk.join(", ") + ")");
          for (const ix of d.indexes) {
            const cols = String(ix.columns || "").split(",").map(x => x.trim()).filter(Boolean);
            if (!ix.name || !cols.length) continue;
            defs.push(`${ix.unique ? "UNIQUE " : ""}KEY ${this.ident(ix.name)} (${cols.map(c => this.ident(c)).join(", ")})`);
          }
          stmts.push(`CREATE TABLE ${this.ident(d.name)} (\n  ${defs.join(",\n  ")}\n) ENGINE=${d.engine || "InnoDB"} DEFAULT CHARSET=${d.charset || "utf8mb4"}` +
                     (d.comment ? ` COMMENT=${this.lit(d.comment)}` : ""));
        } else {
          const cur = d.name;
          if (d.name !== d.originalName) {
            stmts.push(`RENAME TABLE ${this.ident(d.originalName)} TO ${this.ident(d.name)}`);
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
            const sig = cols.join(",") + "|" + (ix.unique ? 1 : 0);
            const osig = o ? (o.columns || []).join(",") + "|" + (o.unique ? 1 : 0) : "";
            if (sig !== osig) {
              if (o) stmts.push(`ALTER TABLE ${this.ident(cur)} DROP INDEX ${this.ident(ix.name)}`);
              stmts.push(`ALTER TABLE ${this.ident(cur)} ADD ${ix.unique ? "UNIQUE " : ""}INDEX ${this.ident(ix.name)} (${cols.map(c => this.ident(c)).join(", ")})`);
            }
          }
          if (d.engine !== d.originalEngine || d.charset !== d.originalCharset || d.comment !== d.originalComment) {
            stmts.push(`ALTER TABLE ${this.ident(cur)} ENGINE=${d.engine || "InnoDB"} DEFAULT CHARSET=${d.charset || "utf8mb4"}` +
                       (d.comment ? ` COMMENT=${this.lit(d.comment)}` : ""));
          }
        }
        if (!stmts.length) { this.toast("没有需要保存的修改"); return; }
        await this.runBatch(stmts);
        this.toast(`表「${d.name}」已保存`);
        const wasNew = d.mode === "new";
        await this.reload();
        const tab = this.currentTab;
        if (tab) { tab.title = "设计表 - " + d.name; tab.name = d.name; tab.id = "design:" + d.name; }
        if (wasNew) this.openTable(d.name, "table");
      } catch (e) { this.toast(e.message); }
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
      const sql = (this.sqlText || "").trim();
      if (!sql) { this.toast("先写点 SQL"); return; }
      this.running = true;
      this.queryMsg = "";
      this.queryResult = null;
      try {
        const d = await this.api("/api/sql", { method: "POST", body: { sql, db: this.db } });
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
        this.resultTab = err ? "message" : "result";
        if (!err) {
          this.lastQuerySql = sql;
          this.$emit("query", sql);
          this.$emit("changed");
        } else {
          this.resultTab = "message";
        }
      } catch (e) {
        this.queryMsg = e.message;
        this.resultTab = "message";
      } finally {
        this.running = false;
      }
    },
    async explainQuery() {
      const sql = (this.sqlText || "").trim();
      if (!sql) { this.toast("先写点 SQL"); return; }
      try {
        const d = await this.api("/api/sql", {
          method: "POST", body: { sql: "EXPLAIN " + sql.replace(/;\s*$/, ""), db: this.db } });
        const rowsRes = (d.results || []).find(r => r.type === "rows");
        this.queryResult = rowsRes || null;
        this.queryInfo = "执行计划";
        this.queryMsg = "EXPLAIN 执行计划";
        this.resultTab = "result";
      } catch (e) { this.queryMsg = e.message; this.resultTab = "message"; }
    },
    beautifySql() {
      let s = this.sqlText || "";
      s = s.replace(/\s+/g, " ")
           .replace(/\b(from|where|group by|having|order by|limit|join|left join|right join|inner join|values|set)\b/gi,
                    (m) => "\n" + m.toUpperCase())
           .replace(/\b(and|or)\b/gi, (m) => "\n  " + m.toUpperCase())
           .replace(/,\s*/g, ",\n  ")
           .trim();
      this.sqlText = s;
      this.$nextTick(() => {
        if (this.$refs.cmQuery) {
          this.$refs.cmQuery.setValue(s);
          this.$refs.cmQuery.refresh();
        }
      });
    },
    insertSnippet() {
      const snip = "\n-- 常用：SELECT * FROM 表名 WHERE 条件 ORDER BY 字段 DESC LIMIT 10;\n";
      this.sqlText = (this.sqlText || "") + snip;
      this.$nextTick(() => {
        if (this.$refs.cmQuery) {
          this.$refs.cmQuery.setValue(this.sqlText);
          this.$refs.cmQuery.focus();
        }
      });
    },
    saveQuery() {
      try {
        localStorage.setItem("lab_nav_query:" + this.drill.id, this.sqlText || "");
        this.toast("查询已保存到本浏览器");
      } catch (e) { this.toast("保存失败"); }
    },

    /* ---------------- 查询创建工具 ---------------- */
    blankBuilder() {
      return {
        tab: "SELECT",
        tables: [],
        joins: [],
        select: [{ expr: "", alias: "" }],
        from: "",
        where: [{ col: "", op: "=", val: "" }],
        group: "",
        having: "",
        order: [{ col: "", dir: "ASC" }],
        limitOffset: "",
        limitCount: "",
      };
    },
    openBuilder() {
      this.build = this.blankBuilder();
      this.dlg = "builder";
    },
    addBuildRow(which) {
      if (which === "select") this.build.select.push({ expr: "", alias: "" });
      else if (which === "where") this.build.where.push({ col: "", op: "=", val: "" });
      else if (which === "order") this.build.order.push({ col: "", dir: "ASC" });
    },
    removeBuildRow(which, i) {
      if (this.build[which].length > 1) this.build[which].splice(i, 1);
    },
    /* ---- 可视化表连接 ---- */
    addBuildTable(t) {
      if (this.build.tables.some(x => x.name === t.name)) return;
      const n = this.build.tables.length;
      this.build.tables.push({
        id: "t" + Date.now() + "_" + n,
        name: t.name, alias: "",
        x: 16 + (n % 2) * 200, y: 14 + Math.floor(n / 2) * 168,
        columns: (t.columns || []).map(c => ({ name: c.name, key: c.key || "" })),
      });
    },
    addBuildTableByName(name) {
      const t = this.schema.tables.find(x => x.name === name);
      if (t) this.addBuildTable(t);
    },
    // 左边字段点一下插到当前正在填的输入框里；没有焦点就加到 SELECT
    insertField(ref) {
      const f = this.focusTarget;
      if (f && typeof f === "object" && "expr" in f) {
        f.expr = f.expr ? f.expr + ", " + ref : ref;
        return;
      }
      if (f && typeof f === "object" && "col" in f) {
        f.col = ref;
        return;
      }
      this.build.select.push({ expr: ref, alias: "" });
      this.build.tab = "SELECT";
    },
    removeBuildTable(t) {
      this.build.tables = this.build.tables.filter(x => x !== t);
      this.build.joins = this.build.joins.filter(j => j.a.tid !== t.id && j.b.tid !== t.id);
    },
    tableById(id) { return this.build.tables.find(t => t.id === id) || null; },
    colRef(t, col) { return (t.alias || t.name) + "." + col; },
    colAnchor(t, colName, side) {
      const i = Math.max(0, t.columns.findIndex(c => c.name === colName));
      return { x: side === "r" ? t.x + 158 : t.x, y: t.y + 27 + i * 20 + 10 };
    },
    // 连线两端各自挑离对方更近的那条边，避免线绕到表框后面
    joinEnds(j) {
      const a = this.tableById(j.a.tid), b = this.tableById(j.b.tid);
      if (!a || !b) return null;
      const right = (b.x + 79) > (a.x + 79);
      return {
        p1: this.colAnchor(a, j.a.col, right ? "r" : "l"),
        p2: this.colAnchor(b, j.b.col, right ? "l" : "r"),
      };
    },
    joinPath(j) {
      const e = this.joinEnds(j);
      if (!e) return "";
      const dx = Math.max(28, Math.abs(e.p2.x - e.p1.x) / 2);
      return `M ${e.p1.x} ${e.p1.y} C ${e.p1.x + dx} ${e.p1.y}, ` +
             `${e.p2.x - dx} ${e.p2.y}, ${e.p2.x} ${e.p2.y}`;
    },
    joinMid(j) {
      const e = this.joinEnds(j);
      if (!e) return { x: 0, y: 0 };
      return { x: Math.round((e.p1.x + e.p2.x) / 2), y: Math.round((e.p1.y + e.p2.y) / 2) };
    },
    cycleJoin(j) {
      const order = ["INNER", "LEFT", "RIGHT"];
      j.type = order[(order.indexOf(j.type) + 1) % order.length];
    },
    removeJoin(j) { this.build.joins = this.build.joins.filter(x => x !== j); },
    startMoveTable(ev, t) {
      const r = this.$refs.canvas.getBoundingClientRect();
      this.dragTable = { t, dx: ev.clientX - r.left - t.x, dy: ev.clientY - r.top - t.y };
      ev.preventDefault();
    },
    startJoin(ev, t, c) {
      const r = this.$refs.canvas.getBoundingClientRect();
      this.dragJoin = { t, c };
      this.dragPos = { x: ev.clientX - r.left, y: ev.clientY - r.top };
      ev.preventDefault();
    },
    onCanvasMove(ev) {
      const r = this.$refs.canvas.getBoundingClientRect();
      const x = ev.clientX - r.left, y = ev.clientY - r.top;
      if (this.dragTable) {
        this.dragTable.t.x = Math.max(0, Math.round(x - this.dragTable.dx));
        this.dragTable.t.y = Math.max(0, Math.round(y - this.dragTable.dy));
      } else if (this.dragJoin) {
        this.dragPos = { x, y };
      }
    },
    endJoin(ev, t, c) {
      const from = this.dragJoin;
      this.dragJoin = null;
      this.dragPos = null;
      if (!from || from.t.id === t.id) return;
      const dup = this.build.joins.some(j =>
        (j.a.tid === from.t.id && j.a.col === from.c.name &&
         j.b.tid === t.id && j.b.col === c.name) ||
        (j.b.tid === from.t.id && j.b.col === from.c.name &&
         j.a.tid === t.id && j.a.col === c.name));
      if (dup) return;
      this.build.joins.push({
        id: "j" + Date.now(),
        type: "INNER",
        a: { tid: from.t.id, col: from.c.name },
        b: { tid: t.id, col: c.name },
      });
    },
    onCanvasUp() { this.dragTable = null; this.dragJoin = null; this.dragPos = null; },
    dragLinePath() {
      if (!this.dragJoin || !this.dragPos) return "";
      const t = this.dragJoin.t;
      const side = this.dragPos.x >= t.x + 79 ? "r" : "l";
      const p1 = this.colAnchor(t, this.dragJoin.c.name, side);
      return `M ${p1.x} ${p1.y} L ${this.dragPos.x} ${this.dragPos.y}`;
    },
    availableColumns() {
      const out = [];
      for (const t of this.build.tables) {
        for (const c of t.columns) out.push(this.colRef(t, c.name));
      }
      return out;
    },

    builderSql() {
      const b = this.build;
      const sel = b.select.map(s => (s.expr || "").trim()
        ? (s.alias ? `${s.expr.trim()} AS ${this.ident(s.alias.trim())}` : s.expr.trim()) : "")
        .filter(Boolean);
      let sql = "SELECT " + (sel.length ? sel.join(", ") : "*");
      if (b.tables.length) {
        const first = b.tables[0];
        let from = this.ident(first.name) + (first.alias ? " " + first.alias : "");
        for (const j of b.joins) {
          const ta = this.tableById(j.a.tid), tb = this.tableById(j.b.tid);
          if (!ta || !tb) continue;
          from += `\n${j.type} JOIN ${this.ident(tb.name)}` +
                  (tb.alias ? " " + tb.alias : "") +
                  ` ON ${this.colRef(ta, j.a.col)} = ${this.colRef(tb, j.b.col)}`;
        }
        sql += "\nFROM " + from;
      } else if (b.from.trim()) {
        sql += "\nFROM " + b.from.trim();
      }
      const wh = b.where.filter(w => w.col.trim() && w.val !== "")
        .map(w => `${w.col.trim()} ${w.op} ${/^\d+(\.\d+)?$/.test(String(w.val).trim()) ? w.val : this.lit(w.val)}`);
      if (wh.length) sql += "\nWHERE " + wh.join(" AND ");
      if (b.group.trim()) sql += "\nGROUP BY " + b.group.trim();
      if (b.having.trim()) sql += "\nHAVING " + b.having.trim();
      const ord = b.order.filter(o => o.col.trim()).map(o => `${o.col.trim()} ${o.dir}`);
      if (ord.length) sql += "\nORDER BY " + ord.join(", ");
      if (String(b.limitCount).trim() !== "") {
        sql += "\nLIMIT " + (String(b.limitOffset).trim() !== ""
          ? `${b.limitOffset}, ${b.limitCount}` : b.limitCount);
      }
      return sql;
    },
    applyBuilder() {
      this.sqlText = this.builderSql();
      this.dlg = "";
      this.newQueryTab();
      this.$nextTick(() => {
        if (this.$refs.cmQuery) this.$refs.cmQuery.setValue(this.sqlText);
      });
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
      if (kind === "canvas") {
        return [
          { label: "添加表", icon: "plus", action: () => this.toast("从左边「＋ 添加表」里选一张表") },
          { label: "清空画布", icon: "eraser", danger: true, action: () => { this.build.tables = []; this.build.joins = []; } },
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
