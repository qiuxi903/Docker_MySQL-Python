/* SQL·Py 课堂实验室 —— Vue 3 前端应用 */
"use strict";

const { createApp } = Vue;

const EXAMPLES = [
  {
    name: "① Hello World",
    code: 'print("你好，MySQL & Python！")\nprint("这是在服务器上真实运行的 Python")\n',
  },
  {
    name: "② 循环与函数",
    code: "def fib(n):\n    a, b = 0, 1\n    result = []\n    for _ in range(n):\n        result.append(a)\n        a, b = b, a + b\n    return result\n\nprint(\"斐波那契数列前 10 项：\", fib(10))\n\nfor i in range(1, 4):\n    print(\"*\" * i)\n",
  },
  {
    name: "③ 连接 MySQL 查询",
    code: '# query(sql) 直接查你自己的数据库，返回元组列表\nrows = query("SELECT ENAME, JOB, SAL FROM emp ORDER BY SAL DESC LIMIT 5")\nprint("工资前 5 名：")\nfor name, job, sal in rows:\n    print(f"  {name:<8}{job:<10}{sal}")\n\n# 写入用 execute(sql)，返回影响行数\nn = execute("UPDATE emp SET SAL = SAL WHERE 1=0")   # 安全示例，不改数据\nprint("影响行数：", n)\n',
  },
  {
    name: "④ 交互问答（input 真的能用）",
    code: `# 运行后控制台会等你输入，直接在上面打字回车即可
name = input("你叫什么名字？")
print("你好，" + name)

n = int(input("再输入一个数字，我给你翻倍："))
print("结果是：", n * 2)
`,
  },
  {
    name: "⑤ 手写 pymysql 连接",
    code: 'import pymysql\n\nconn = get_conn()          # 等价于 pymysql.connect(...)，已帮你填好地址账号\ntry:\n    with conn.cursor() as cur:\n        cur.execute("SELECT DNAME, LOC FROM dept")\n        for dname, loc in cur.fetchall():\n            print(dname, "-", loc)\n    conn.commit()\nfinally:\n    conn.close()\n',
  },
];

const KIND_LABEL = { db: "数据库", py: "Python代码", csv: "表格", xlsx: "Excel" };

/* Lucide 风格 SVG 图标（线性、currentColor，自动适配主题） */
const ICONS = {
  terminal: '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
  table: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  "file-text": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
  "file-spreadsheet": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
  "folder-open": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  eraser: '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
  list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
  "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
  "menu": '<line x1="3" x2="21" y1="6" y2="6"/><line x1="3" x2="21" y1="12" y2="12"/><line x1="3" x2="21" y1="18" y2="18"/>',
  "link": '<path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/>',
  "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  "user-x": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="22" x2="16" y1="11" y2="11"/>',
  "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
};

/* Python 补全词库：关键字 + 常用内置 + 平台内置函数 */
const PY_WORDS = ["print", "input", "range", "len", "int", "str", "float", "bool",
  "list", "dict", "set", "tuple", "type", "sorted", "sum", "min", "max", "abs",
  "round", "enumerate", "zip", "map", "filter", "open", "def", "return", "if",
  "elif", "else", "for", "while", "in", "is", "not", "and", "or", "import",
  "from", "as", "class", "try", "except", "finally", "with", "lambda", "pass",
  "break", "continue", "global", "raise", "yield", "True", "False", "None",
  "self", "append", "extend", "insert", "remove", "pop", "sort", "keys",
  "values", "items", "get", "split", "join", "strip", "replace", "startswith",
  "endswith", "format", "lower", "upper", "find", "count",
  "query", "execute", "query_dicts", "get_conn"];

/* Python 自动补全：按光标前的前缀过滤词库 + 当前文档里的词 */
function pyWordHint(cm) {
  const cur = cm.getCursor();
  const before = cm.getLine(cur.line).slice(0, cur.ch);
  const m = before.match(/[A-Za-z_][A-Za-z0-9_]*$/);
  if (!m) return null;
  const word = m[0];
  const lower = word.toLowerCase();
  const list = [];
  const seen = new Set();
  PY_WORDS.forEach((w) => {
    const lw = w.toLowerCase();
    if (lw !== lower && lw.startsWith(lower) && !seen.has(lw)) { list.push(w); seen.add(lw); }
  });
  cm.getValue().split(/[^A-Za-z0-9_]/).forEach((w) => {
    const lw = w.toLowerCase();
    if (w.length > 2 && lw.startsWith(lower) && !seen.has(lw)) { list.push(w); seen.add(lw); }
  });
  if (!list.length) return null;
  return { list, from: CodeMirror.Pos(cur.line, cur.ch - word.length), to: cur };
}

const EIcon = {
  props: { name: String, size: { type: [Number, String], default: 15 } },
  computed: { path() { return ICONS[this.name] || ""; } },
  template: `<svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    style="vertical-align:-2.5px; flex:0 0 auto" v-html="path"></svg>`,
};

/* CodeMirror 编辑器组件：Vue 的 DOM 锚点固定在 textarea 上，
   CodeMirror 插入的节点 Vue 永远不会触碰，避免虚拟 DOM 冲突。 */
const CmEditor = {
  props: {
    mode: String,
    placeholder: String,
    value: { type: String, default: "" },
    run: Function,
    hintTables: { type: Object, default: () => ({}) },
  },
  template: "<textarea></textarea>",
  mounted() {
    const extra = {
      "Ctrl-Enter": () => this.run && this.run(),
      "Cmd-Enter": () => this.run && this.run(),
    };
    if (this.mode === "text/x-mysql") {
      extra["Ctrl-Space"] = (cm) => cm.showHint({
        hint: CodeMirror.hint.sql,
        tables: this.hintTables || {},
        completeSingle: false,
      });
    }
    if (this.mode === "text/x-python") {
      extra["Tab"] = (cm) => {
        // 补全弹层开着时交给它处理（Tab 选中补全项）
        if (cm.state.completionActive) return;
        cm.replaceSelection("    ");
      };
    }
    this.cm = CodeMirror.fromTextArea(this.$el, {
      mode: this.mode,
      lineNumbers: true,
      matchBrackets: true,
      autoCloseBrackets: true,
      styleActiveLine: true,
      indentUnit: 4,
      placeholder: this.placeholder,
      extraKeys: extra,
    });
    // 输入字母自动弹补全预览；弹层开着时 Tab/Enter 直接选中
    if (this.mode === "text/x-python") {
      this.cm.on("inputRead", (cmInst, change) => {
        if (!change || change.origin !== "+input" || !/^[A-Za-z_]$/.test(change.text.join(""))) return;
        const tok = cmInst.getTokenAt(cmInst.getCursor());
        if (tok.type && /string|comment/.test(tok.type)) return;
        setTimeout(() => {
          const h = pyWordHint(cmInst);
          if (h && h.list.length) {
            cmInst.showHint({
              hint: () => h,
              completeSingle: false,
              extraKeys: { "Tab": (c, handle) => handle.pick() },
            });
          }
        }, 30);
      });
    }
    if (this.value) this.cm.setValue(this.value);
    this.cm.on("change", () => this.$emit("change", this.cm.getValue()));
  },
  watch: {
    // 编辑器在启动遮罩期间就已挂载，登录后父组件才把初始内容设进来，
    // 必须跟着 prop 同步，否则首次访问的预填 SQL 不会出现
    value(v) {
      if (this.cm && v !== this.cm.getValue()) this.cm.setValue(v);
    },
  },
  methods: {
    refresh() { if (this.cm) this.cm.refresh(); },
    getValue() { return this.cm ? this.cm.getValue() : ""; },
    setValue(v) { if (this.cm) this.cm.setValue(v); },
    focus() { if (this.cm) this.cm.focus(); },
  },
};

const App = {
  data() {
    return {
      token: localStorage.getItem("lab_token") || "",
      user: null,
      logged: false,
      booting: true,
      view: "sql",
      theme: document.documentElement.dataset.theme || "light",
      busy: false,
      toastMsg: "",
      toastTimer: null,

      loginForm: { username: "", password: "" },

      tables: [],
      databases: [],
      dbTables: {},
      openDbs: {},
      selectedDb: "",
      dragOver: false,
      sqlConsole: [],
      pyConsole: [],
      sqlInit: "",
      pyInit: "",
      pyFiles: [],
      pyCurrent: "main.py",
      pySaveTimer: null,
      pyRunCount: 0,
      pyJob: "",
      pyStdin: "",
      pendingShareCode: "",
      shareForm: { db: "", shareName: "", link: "", done: false },

      examples: EXAMPLES,
      KIND_LABEL,

      importForm: { file: null, table: "", header: true, overwrite: false },

      preview: { open: false, tab: "data", name: "", loading: false, columns: [], rows: null,
                 desc: null, descColumns: [], ddl: "", source: null },

      community: [],
      uploadFile: null,
      uploadKind: "db",
      uploadTitle: "",

      detail: { open: false, loading: false, id: 0, title: "", uploader: "", isScript: false,
                tables: [], builtin: false, filename: "" },

      adminUsers: [],
      adminGuests: [],
      adminKind: "user",
      drawer: "",
    };
  },

  computed: {
    tablesHint() {
      const m = {};
      (this.dbTables[this.selectedDb] || []).forEach((t) => { m[t.name] = []; });
      return m;
    },
    isSqlFile() {
      const f = this.importForm.file;
      return !!f && /\.sql$/i.test(f.name);
    },
  },

  watch: {
    view() {
      this.$nextTick(() => {
        if (this.$refs.cmSqlRef) this.$refs.cmSqlRef.refresh();
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.refresh();
        this.scrollConsole("sqlConsoleEl");
        this.scrollConsole("pyConsoleEl");
      });
    },
  },

  async mounted() {
    // 软键盘：弹起时给 body 加标记（隐藏悬浮按钮），收起时移除
    if (window.visualViewport) {
      const vv = window.visualViewport;
      const sync = () => {
        // 键盘弹起判定：可视区明显变矮（阈值放宽，兼容各家浏览器）
        const kbOpen = (window.innerHeight - vv.height) > 120 ||
                       (window.innerHeight - vv.height * (window.devicePixelRatio || 1)) > 0;
        document.body.classList.toggle("kb-open", kbOpen);
        // 让应用高度跟随真正的可视区，键盘弹起时内容不被底栏遮挡
        const app = document.getElementById("app");
        if (app) app.style.height = kbOpen ? vv.height + "px" : "";
      };
      vv.addEventListener("resize", sync);
      vv.addEventListener("scroll", sync);
      setTimeout(sync, 300);
    }
    // 输入框聚焦/失焦时同步（部分 Android 只触发 focus）
    window.addEventListener("focusin", (e) => {
      if (e.target && /INPUT|TEXTAREA/.test(e.target.tagName)) {
        setTimeout(() => {
          if (!window.visualViewport) return;
          const kbOpen = (window.innerHeight - window.visualViewport.height) > 120;
          document.body.classList.toggle("kb-open", kbOpen);
        }, 260);
      }
    });
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && this.logged) {
        e.preventDefault();
        if (this.view === "sql") this.runSql();
        else if (this.view === "py") this.runPy();
      }
    });
    // 分享链接：/s/码 或 #/s/码（进站即记录，登录后自动弹出）
    const m = location.pathname.match(/^\/s\/([A-Za-z0-9]{4,})/) ||
              (location.hash || "").match(/s\/([A-Za-z0-9]{4,})/);
    if (m) sessionStorage.setItem("lab_pending_share", m[1]);
    // 兜底：无论发生什么（甚至意外抛错），启动遮罩最多 6 秒后必定消失，绝不卡死在转圈
    const bootGuard = setTimeout(() => { this.booting = false; }, 6000);
    if (this.token) {
      // 只有服务端明确返回 401 才算登录失效；
      // 限流(429)、服务器错误(5xx)、网络抖动都会重试，绝不因临时故障把用户踢回登录页
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const me = await this.api("/api/me");
          this.enterApp(me);
          clearTimeout(bootGuard);
          return;
        } catch (e) {
          if (e.status === 401) {
            this.token = "";
            localStorage.removeItem("lab_token");
            break;
          }
          await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
        }
      }
    }
    clearTimeout(bootGuard);
    this.booting = false;
  },

  methods: {
    /* ---------- 基础 ---------- */
    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = this.theme;
      localStorage.setItem("lab_theme", this.theme);
    },

    kindIcon(kind) {
      return { db: "database", py: "code", csv: "file-text", xlsx: "file-spreadsheet", table: "table" }[kind] || "table";
    },

    toast(msg, ms) {
      this.toastMsg = msg;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => (this.toastMsg = ""), ms || 2600);
    },

    async api(path, opts = {}) {
      const init = { method: opts.method || "GET", headers: { "X-Token": this.token } };
      if (opts.form) init.body = opts.form;
      else if (opts.body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
      let resp;
      try {
        resp = await fetch(path, init);
      } catch (e) {
        throw new Error("网络连接失败，请检查后再试");
      }
      let data = {};
      try { data = await resp.json(); } catch (e) { /* 下载等非 JSON 响应 */ }
      if (!resp.ok) {
        if (resp.status === 401 && this.token) {
          this.token = "";
          localStorage.removeItem("lab_token");
          this.logged = false;
          this.toast("登录已失效，请重新登录");
        }
        const msg = typeof data.detail === "string" ? data.detail : "请求失败（" + resp.status + "）";
        const err = new Error(msg);
        err.status = resp.status;
        throw err;
      }
      return data;
    },

    async downloadFile(url, fallbackName) {
      const resp = await fetch(url, { headers: { "X-Token": this.token } });
      if (!resp.ok) { this.toast("下载失败"); return; }
      const blob = await resp.blob();
      const cd = resp.headers.get("Content-Disposition") || "";
      const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
      let name = fallbackName;
      if (m) { try { name = decodeURIComponent(m[1]); } catch (e) {} }
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    },

    fmtSize(n) {
      if (n === null || n === undefined) return "";
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / 1024 / 1024).toFixed(1) + " MB";
    },

    scrollConsole(refName) {
      this.$nextTick(() => {
        const el = this.$refs[refName];
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    /* ---------- 登录 ---------- */
    async doLogin(mode) {
      const { username, password } = this.loginForm;
      if (mode !== "guest" && (!username || !password)) { this.toast("请输入账号和密码"); return; }
      this.busy = true;
      try {
        const d = await this.api("/api/login", { method: "POST", body: { mode, username, password } });
        this.token = d.token;
        localStorage.setItem("lab_token", d.token);
        this.toast(mode === "guest" ? "已进入游客模式，先用起来！"
          : mode === "register" ? "注册成功，已自动登录" : "欢迎回来，" + d.user.name);
        const me = await this.api("/api/me");
        this.enterApp(me);
      } catch (e) {
        this.toast(e.message);
      } finally {
        this.busy = false;
      }
    },

    enterApp(me) {
      this.booting = false;
      this.user = me.user;
      this.databases = me.databases || [];
      this.selectedDb = me.db || (this.databases[0] ? this.databases[0].name : "");
      this.dbTables = { [this.selectedDb]: me.tables || [] };
      this.openDbs = { [this.selectedDb]: true };
      // SQL 编辑器：同一个账号有草稿就接着写；否则首次访问预填示例，点开就能跑通第一条。
      // 草稿与"看过示例"都按账号分开存，共用电脑的学生互不串号
      const who = (me.user && me.user.name) || "?";
      let draft = "";
      try { draft = localStorage.getItem("lab_sql_draft:" + who) || ""; } catch (e) {}
      if (draft.trim()) {
        this.sqlInit = draft;
      } else if (!sessionStorage.getItem("lab_sql_seen:" + who)) {
        this.sqlInit = "SELECT * FROM emp";
        sessionStorage.setItem("lab_sql_seen:" + who, "1");
      } else {
        this.sqlInit = "";
      }
      this.logged = true;
      this.initPyFiles();
      this.checkPendingShare();
    },

    async logout() {
      try { await this.api("/api/logout", { method: "POST" }); } catch (e) {}
      this.token = "";
      this.user = null;
      this.logged = false;
      localStorage.removeItem("lab_token");
    },

    switchView(v) {
      this.view = v;
      this.drawer = "";
      if (v === "community" && !this.community.length) this.loadCommunity();
    },

    /* ---------- 编辑器 ---------- */
    onSqlChange() {
      // SQL 没有服务器存档，手机切后台重载会丢，随手存一份浏览器草稿
      clearTimeout(this.sqlDraftTimer);
      this.sqlDraftTimer = setTimeout(() => {
        const sql = this.$refs.cmSqlRef ? this.$refs.cmSqlRef.getValue() : "";
        const who = (this.user && this.user.name) || "?";
        try { localStorage.setItem("lab_sql_draft:" + who, sql.slice(0, 20000)); } catch (e) {}
      }, 500);
    },

    onPyChange() {
      clearTimeout(this.pySaveTimer);
      this.pySaveTimer = setTimeout(async () => {
        const content = this.$refs.cmPyRef ? this.$refs.cmPyRef.getValue() : null;
        if (content === null || !this.pyCurrent) return;
        try {
          await this.api(`/api/pyfiles/${encodeURIComponent(this.pyCurrent)}`,
                         { method: "PUT", body: { content } });
        } catch (e) {}
      }, 600);
    },

    clearSql() { this.$refs.cmSqlRef.setValue(""); this.$refs.cmSqlRef.focus(); },
    clearPy() {
      this.$refs.cmPyRef.setValue("");
      this.$refs.cmPyRef.focus();
    },

    insertExample(ev) {
      const idx = ev.target.value;
      ev.target.value = "";
      if (idx === "") return;
      const ex = this.examples[+idx];
      if (!ex) return;
      this.$refs.cmPyRef.setValue(ex.code);
      this.toast("已插入示例，点 ▶ 运行 试试");
    },

    /* ---------- Python 多文件 ---------- */
    async initPyFiles() {
      await this.$nextTick();
      try {
        let d = await this.api("/api/pyfiles");
        const draft = localStorage.getItem("lab_py_draft");
        if (!d.files.length && draft) {
          await this.api("/api/pyfiles/main.py", { method: "PUT", body: { content: draft } });
          localStorage.removeItem("lab_py_draft");
          d = await this.api("/api/pyfiles");
        }
        this.pyFiles = d.files;
        this.pyCurrent = this.pyFiles[0] ? this.pyFiles[0].name : "main.py";
        const f = await this.api(`/api/pyfiles/${encodeURIComponent(this.pyCurrent)}`);
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
        this.$nextTick(() => { if (this.$refs.cmPyRef) this.$refs.cmPyRef.refresh(); });
      } catch (e) { /* 列表加载失败时编辑器仍可用 */ }
    },

    async refreshPyList() {
      try {
        const d = await this.api("/api/pyfiles");
        this.pyFiles = d.files;
      } catch (e) {}
    },

    async flushPySave() {
      if (this.pySaveTimer) { clearTimeout(this.pySaveTimer); this.pySaveTimer = null; }
      const name = this.pyCurrent;
      const content = this.$refs.cmPyRef ? this.$refs.cmPyRef.getValue() : null;
      if (content === null || !name) return;
      try {
        await this.api(`/api/pyfiles/${encodeURIComponent(name)}`, { method: "PUT", body: { content } });
      } catch (e) {}
    },

    async openPyFile(name) {
      if (name === this.pyCurrent) return;
      await this.flushPySave();
      try {
        const f = await this.api(`/api/pyfiles/${encodeURIComponent(name)}`);
        this.pyCurrent = f.name;
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
      } catch (e) { this.toast(e.message); }
    },

    async newPyFile() {
      const name = prompt("新文件名（可省略 .py 后缀）：", "新建文件.py");
      if (!name) return;
      const final = name.toLowerCase().endsWith(".py") ? name : name + ".py";
      this.busy = true;
      try {
        await this.flushPySave();
        let exists = true;
        try {
          await this.api(`/api/pyfiles/${encodeURIComponent(final)}`);
        } catch (e) { exists = false; }
        if (exists) {
          this.toast("文件已存在，已为你打开");
          return this.openPyFile(final);
        }
        await this.api(`/api/pyfiles/${encodeURIComponent(final)}`,
                       { method: "PUT", body: { content: "# " + final + "\n" } });
        await this.refreshPyList();
        this.pyCurrent = final;
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("# " + final + "\n");
        this.toast(`已创建 ${final}`);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    async deletePyFile(name) {
      if (!confirm(`确定删除文件「${name}」？`)) return;
      try {
        await this.api(`/api/pyfiles/${encodeURIComponent(name)}`, { method: "DELETE" });
        await this.refreshPyList();
        if (this.pyCurrent === name) {
          this.pyCurrent = this.pyFiles[0] ? this.pyFiles[0].name : "main.py";
          try {
            const f = await this.api(`/api/pyfiles/${encodeURIComponent(this.pyCurrent)}`);
            if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
          } catch (e) {
            await this.api("/api/pyfiles/main.py", { method: "PUT", body: { content: "" } });
            if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
          }
        }
        this.toast(`已删除 ${name}`);
      } catch (e) { this.toast(e.message); }
    },

    /* ---------- SQL 执行 ---------- */
    async runSql() {
      const sql = (this.$refs.cmSqlRef ? this.$refs.cmSqlRef.getValue() : "").trim();
      if (!sql) { this.toast("先写点 SQL 再运行"); return; }
      this.busy = true;
      try {
        const d = await this.api("/api/sql", { method: "POST", body: { sql, db: this.selectedDb } });
        this.sqlConsole.push({ sql, results: d.results || [], tookMs: d.tookMs, db: d.db || this.selectedDb });
        this.scrollConsole("sqlConsoleEl");
        this.loadDbTables(this.selectedDb, true);
      } catch (e) {
        this.sqlConsole.push({ sql, results: [{ type: "error", index: 1, msg: e.message }], tookMs: 0 });
        this.scrollConsole("sqlConsoleEl");
      } finally {
        this.busy = false;
      }
    },

    /* ---------- 表列表 / 预览 ---------- */
    async loadTables(silent) {
      try {
        const d = await this.api("/api/databases");
        this.databases = d.databases;
        if (!this.selectedDb && d.databases.length) this.selectDb(d.databases[0]);
        if (this.selectedDb) this.loadDbTables(this.selectedDb, true);
      } catch (e) {
        if (!silent) this.toast(e.message);
      }
    },

    async loadDbTables(name, silent) {
      if (!name) return;
      try {
        const d = await this.api(`/api/databases/${encodeURIComponent(name)}/tables`);
        this.dbTables = Object.assign({}, this.dbTables, { [name]: d.tables });
      } catch (e) {
        if (!silent) this.toast(e.message);
        if (e.message.indexOf("不存在") >= 0 || e.message.indexOf("名下") >= 0) {
          try {
            const d = await this.api("/api/databases");
            this.databases = d.databases;
          } catch (e2) {}
        }
      }
    },

    selectDb(d) {
      this.selectedDb = d.name;
      if (this.openDbs[d.name] === undefined) this.openDbs = Object.assign({}, this.openDbs, { [d.name]: true });
      if (!this.dbTables[d.name]) this.loadDbTables(d.name, true);
      this.$nextTick(() => { if (this.$refs.cmSqlRef) this.$refs.cmSqlRef.refresh(); });
    },

    toggleDb(name) {
      this.openDbs = Object.assign({}, this.openDbs, { [name]: !this.openDbs[name] });
      if (this.openDbs[name] && !this.dbTables[name]) this.loadDbTables(name, true);
    },

    async createDb() {
      const name = prompt("新数据库的名称（字母/数字/下划线）：");
      if (!name) return;
      this.busy = true;
      try {
        const d = await this.api("/api/databases", { method: "POST", body: { name } });
        this.databases = d.databases;
        this.selectDb({ name: d.name });
        this.toast(`数据库 ${d.name} 已创建`);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    async dropDb(d) {
      if (!confirm(`确定删除数据库「${d.name}」？里面所有表和数据都会删除，不可恢复！`)) return;
      this.busy = true;
      try {
        const r = await this.api(`/api/databases/${encodeURIComponent(d.name)}`, { method: "DELETE" });
        this.databases = r.databases;
        delete this.dbTables[d.name];
        if (this.selectedDb === d.name) this.selectDb(this.databases[0] || { name: "" });
        this.toast(`已删除数据库 ${d.name}`);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    exportDb(d) {
      this.downloadFile(`/api/databases/${encodeURIComponent(d.name)}/export`, d.name + ".sql");
    },

    openShareDlg(d) {
      this.shareForm = { db: d.name, shareName: d.name, link: "", done: false };
      this.$refs.shareDlg.showModal();
    },

    closeShareDlg() {
      if (this.$refs.shareDlg.open) this.$refs.shareDlg.close();
      this.shareForm = { db: "", shareName: "", link: "", done: false };
    },

    async generateShareLink() {
      this.busy = true;
      try {
        const r = await this.api("/api/community/publish", { method: "POST",
          body: { db: this.shareForm.db, share_name: this.shareForm.shareName, public: false } });
        this.shareForm.link = location.origin + "/s/" + r.shareCode;
        this.shareForm.done = true;
        this.toast("私有分享链接已生成，复制发给同学（不会出现在社区）");
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    /* 发布到社区广场（公开上架） */
    async publishDb(d) {
      this.busy = true;
      try {
        const r = await this.api("/api/community/publish", { method: "POST",
          body: { db: d.name, public: true } });
        this.toast(`「${d.name}」（${r.tables} 张表）已发布到社区，去社区页看看`);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    copyShareLink() {
      const link = this.shareForm.link;
      if (!link) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => this.toast("链接已复制"),
          () => { prompt("手动复制：", link); });
      } else {
        prompt("手动复制：", link);
      }
    },

    async openShareByCode(code) {
      try {
        const d = await this.api(`/api/community/by-code/${encodeURIComponent(code)}`);
        this.detail = Object.assign({ open: true, loading: false,
                                      newDbName: d.shareName || d.name }, d);
        this.$refs.dbDlg.showModal();
        this.switchView("sql");
      } catch (e) { this.toast(e.message); }
    },

    checkPendingShare() {
      const code = sessionStorage.getItem("lab_pending_share");
      if (!code) return;
      sessionStorage.removeItem("lab_pending_share");
      this.pendingShareCode = "";
      this.openShareByCode(code);
    },

    async sqlQuery(text, db) {
      const d = await this.api("/api/sql", { method: "POST", body: { sql: text, db: db || this.selectedDb } });
      const err = (d.results || []).find((r) => r.type === "error");
      if (err) throw new Error(err.msg);
      return d.results || [];
    },

    openPreview(name, dbName) {
      this.preview = { open: true, tab: "data", name, db: dbName || this.selectedDb,
                       loading: true, columns: [], rows: null,
                       desc: null, descColumns: [], ddl: "", source: null };
      this.$refs.previewDlg.showModal();
      this.previewTab("data");
    },

    closePreview() {
      this.$refs.previewDlg.close();
      this.preview.open = false;
    },

    async previewTab(tab) {
      this.preview.tab = tab;
      const p = this.preview;
      if (tab === "data" && p.rows === null) {
        p.loading = true;
        try {
          const rs = await this.sqlQuery(`SELECT * FROM \`${p.name}\` LIMIT 200`, p.db);
          p.columns = rs[0] ? rs[0].columns : [];
          p.rows = rs[0] ? rs[0].rows : [];
        } catch (e) { this.toast(e.message); p.rows = []; }
        p.loading = false;
      } else if (tab === "struct" && p.desc === null) {
        p.loading = true;
        try {
          const rs = await this.sqlQuery(`DESCRIBE \`${p.name}\``, p.db);
          p.descColumns = rs[0] ? rs[0].columns : [];
          p.desc = rs[0] ? rs[0].rows : [];
          const rs2 = await this.sqlQuery(`SHOW CREATE TABLE \`${p.name}\``, p.db);
          p.ddl = rs2[0] && rs2[0].rows[0] ? rs2[0].rows[0][1] : "";
        } catch (e) { this.toast(e.message); }
        p.loading = false;
      } else if (tab === "source" && p.source === null) {
        p.loading = true;
        try {
          const d = await this.api("/api/source/" + encodeURIComponent(p.name));
          p.source = d.exists ? d : false;
        } catch (e) { p.source = false; this.toast(e.message); }
        p.loading = false;
      }
    },

    queryFromPreview() {
      this.selectDb({ name: this.preview.db });
      this.$refs.cmSqlRef.setValue(`SELECT * FROM \`${this.preview.name}\` LIMIT 20`);
      this.closePreview();
      this.switchView("sql");
      this.runSql();
    },

    async publishFromPreview() {
      this.busy = true;
      try {
        await this.api("/api/community/publish", { method: "POST", body: { table: this.preview.name } });
        this.toast(`已把「${this.preview.name}」发布到社区`);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    async downloadSource() {
      await this.downloadFile("/api/source/" + encodeURIComponent(this.preview.name) + "/download",
                              this.preview.source ? this.preview.source.filename : this.preview.name);
    },

    async dropFromPreview() {
      const name = this.preview.name;
      const db = this.preview.db;
      if (!confirm(`确定删除表「${name}」？数据不可恢复！`)) return;
      this.busy = true;
      try {
        await this.sqlQuery(`DROP TABLE \`${name}\``, db);
        this.toast("已删除 " + name);
        this.closePreview();
        this.loadDbTables(db, true);
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    /* ---------- 导入 ---------- */
    openImport() {
      this.importForm = { file: null, table: "", header: true, overwrite: false };
      this.dragOver = false;
      if (this.$refs.importFileEl) this.$refs.importFileEl.value = "";
      this.$refs.importDlg.showModal();
    },
    closeImport() { this.$refs.importDlg.close(); },

    pickImportFile() { this.$refs.importFileEl.click(); },

    validateImportFile(f) {
      if (!f) return false;
      const ext = f.name.split(".").pop().toLowerCase();
      if (!["csv", "xlsx", "sql"].includes(ext)) {
        this.toast("仅支持 .csv / .xlsx / .sql 文件");
        return false;
      }
      if (f.size > 5 * 1024 * 1024) {
        this.toast("文件超过 5MB 上限");
        return false;
      }
      return true;
    },

    setImportFile(f) {
      if (!this.validateImportFile(f)) return;
      this.importForm.file = f;
      if (!this.importForm.table && !/\.sql$/i.test(f.name)) {
        this.importForm.table = f.name.replace(/\.[^.]+$/, "");
      }
    },

    onImportPicked(e) {
      const f = e.target.files[0];
      this.setImportFile(f);
      e.target.value = "";
    },

    onImportDrop(e) {
      this.dragOver = false;
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      this.setImportFile(f);
    },

    clearImportFile() {
      this.importForm.file = null;
      if (this.$refs.importFileEl) this.$refs.importFileEl.value = "";
    },

    async submitImport() {
      const f = this.importForm.file;
      if (!f) { this.toast("先选择文件"); return; }
      const fd = new FormData();
      fd.append("file", f);
      fd.append("table", this.importForm.table);
      fd.append("header", this.importForm.header);
      fd.append("overwrite", this.importForm.overwrite);
      fd.append("db", this.selectedDb);
      this.busy = true;
      try {
        const d = await this.api("/api/import", { method: "POST", form: fd });
        if (d.kind === "table") {
          this.toast(`✔ 导入成功：${d.result.table}（${d.result.rows} 行）`);
        } else {
          const results = (d.result && d.result.results) || [];
          const errN = results.filter((r) => r.type === "error").length;
          if (errN) this.toast(`脚本执行完成：${results.length - errN} 条成功，${errN} 条失败`);
          else this.toast(`✔ SQL 脚本执行成功：${results.length} 条语句`);
        }
        if (d.databases) this.databases = d.databases;
        this.dbTables = Object.assign({}, this.dbTables, { [this.selectedDb]: d.tables || [] });
        this.closeImport();
      } catch (e) {
        this.toast(e.message);
      } finally {
        this.busy = false;
      }
    },

    /* ---------- Python ---------- */
    async runPy() {
      const code = (this.$refs.cmPyRef ? this.$refs.cmPyRef.getValue() : "").trim();
      if (!code) { this.toast("先写点 Python 代码再运行"); return; }
      await this.flushPySave();
      this.busy = true;
      this.pyRunCount += 1;
      const n = this.pyRunCount;
      this.pyConsole = [{ n, running: true, out: "", err: "", start: Date.now() }];
      this.scrollConsole("pyConsoleEl");
      try {
        const d = await this.api("/api/pyrun/start", { method: "POST", body: { code, db: this.selectedDb } });
        this.pyJob = d.job;
        this.pyConsole[0].job = d.job;
        this.busy = false;
        this.pollPyJob();
      } catch (e) {
        this.pyConsole = [{ n, running: false, exit: -1, out: "", err: "",
                            start: Date.now(), dur: 0, meta: "✖ " + e.message }];
        this.scrollConsole("pyConsoleEl");
        this.busy = false;
      }
    },

    async pollPyJob() {
      const job = this.pyJob;
      if (!job) return;
      try {
        const d = await this.api(`/api/pyrun/status/${encodeURIComponent(job)}`);
        const e = this.pyConsole.find((x) => x.job === job);
        if (!e) return;
        e.running = d.running;
        e.out = d.out || "";
        e.err = d.err || "";
        e.exit = d.exit;
        e.why = d.why || "";
        e.timed_out = e.why;
        if (!d.running) e.dur = ((Date.now() - e.start) / 1000).toFixed(2);
        this.scrollConsole("pyConsoleEl");
        if (d.running) setTimeout(() => this.pollPyJob(), 600);
        else this.pyJob = "";
      } catch (e) {
        this.toast(e.message);
      }
    },

    async sendPyInput() {
      const text = this.pyStdin;
      if (text === undefined || text === null || !this.pyJob) return;
      this.pyStdin = "";
      try {
        await this.api("/api/pyrun/input", { method: "POST", body: { job: this.pyJob, text } });
      } catch (e) { this.toast(e.message); }
    },

    /* ---------- 社区 ---------- */
    async loadCommunity() {
      try {
        const d = await this.api("/api/community");
        this.community = d.items;
      } catch (e) { this.toast(e.message); }
    },

    async uploadCommunity() {
      const f = this._uploadRaw;
      if (!f) { this.toast("先选择文件（.sql / .py / .csv / .xlsx）"); return; }
      const fd = new FormData();
      fd.append("file", f);
      fd.append("title", this.uploadTitle);
      this.busy = true;
      try {
        const d = await this.api("/api/community/upload", { method: "POST", form: fd });
        this.toast(d.kind === "db"
          ? "已作为「数据库」分享到社区，别人点开详情就能看到表清单"
          : `已分享到社区（${KIND_LABEL[d.kind] || d.kind} · ${this.fmtSize(d.size)}）`);
        this.uploadTitle = "";
        this.uploadFile = null;
        this._uploadRaw = null;
        if (this.$refs.uploadFileEl) this.$refs.uploadFileEl.value = "";
        this.loadCommunity();
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },

    onUploadPicked(e) {
      const f = e.target.files[0];
      if (!f) return;
      const ext = f.name.split(".").pop().toLowerCase();
      if (!["sql", "py", "csv", "xlsx"].includes(ext)) {
        this.toast("仅支持 .sql / .py / .csv / .xlsx");
        e.target.value = "";
        return;
      }
      const cap = ext === "py" ? 256 * 1024 : 8 * 1024 * 1024;
      if (f.size > cap) {
        this.toast(`文件超过 ${cap / 1024}KB 上限`);
        e.target.value = "";
        return;
      }
      this._uploadRaw = f;
      this.uploadKind = ext === "sql" ? "db" : ext;
      this.uploadFile = { name: f.name, size: f.size };
    },

    async importItem(it) {
      const doImport = async (overwrite) => {
        this.busy = true;
        try {
          const d = await this.api("/api/community/import", {
            method: "POST", body: { id: it.id, overwrite, header: true, db: this.selectedDb } });
          const r = d.result || {};
          if (r.imported && r.imported.length) {
            this.toast(`已导入「${r.imported.join("、")}」到 ${d.db}，去工作台查看`);
          } else if (r.script) {
            this.toast("SQL 脚本已执行，去工作台查看效果");
          } else {
            this.toast("导入完成");
          }
          if (d.tables) this.dbTables = Object.assign({}, this.dbTables, { [d.db]: d.tables });
        } catch (e) {
          if (e.message.indexOf("同名") >= 0 && !overwrite) {
            if (confirm("你的空间里已有同名表，覆盖它吗？")) return doImport(true);
          } else this.toast(e.message);
        } finally { this.busy = false; }
      };
      return doImport(false);
    },

    openDbDetail(it) {
      this.detail = { open: true, loading: true, id: it.id, title: it.title,
                      uploader: it.uploader, isScript: false, tables: [],
                      builtin: it.builtin, filename: it.filename };
      this.$refs.dbDlg.showModal();
      this.api(`/api/community/${it.id}/detail`).then((d) => {
        this.detail = Object.assign({ open: true, loading: false }, d);
      }).catch((e) => {
        this.toast(e.message);
        this.closeDbDetail();
      });
    },

    closeDbDetail() {
      if (this.$refs.dbDlg.open) this.$refs.dbDlg.close();
      this.detail = { open: false, loading: false, id: 0, title: "", uploader: "",
                      isScript: false, tables: [], builtin: false, filename: "" };
    },

    async importWholeDb() {
      const id = this.detail.id;
      const newName = (this.detail.newDbName || "").trim();
      const doIt = async (overwrite) => {
        this.busy = true;
        try {
          const d = await this.api("/api/community/import", {
            method: "POST", body: { id, overwrite, header: true, new_db_name: newName } });
          const r = d.result || {};
          // 整库导入 → 创建了独立新库，切到该库
          if (d.db) {
            this.selectedDb = d.db;
            this.openDbs = Object.assign({}, this.openDbs, { [d.db]: true });
          }
          if (d.tables) this.dbTables = Object.assign({}, this.dbTables, { [d.db]: d.tables });
          if (r.databases) this.databases = r.databases;
          if (r.script) this.toast("整库脚本已执行，已创建独立数据库 " + d.db);
          else {
            let msg = r.imported.length ? `已导入 ${r.imported.length} 张表（${r.imported.join("、")}）` : "没有导入新表";
            if (r.skipped.length) msg += `，跳过已存在的 ${r.skipped.length} 张`;
            this.toast(msg + ` → 独立数据库 ${d.db}（仅你可访问）`);
          }
          this.closeDbDetail();
          this.switchView("sql");
        } catch (e) {
          if ((e.message.indexOf("同名") >= 0 || e.message.indexOf("已被占用") >= 0) && !overwrite) {
            if (confirm("已存在同名数据库/表，覆盖导入吗？")) return doIt(true);
          } else this.toast(e.message);
        } finally { this.busy = false; }
      };
      return doIt(false);
    },

    async importDbTable(name) {
      const id = this.detail.id;
      const doIt = async (overwrite) => {
        this.busy = true;
        try {
          const d = await this.api("/api/community/import", {
            method: "POST", body: { id, overwrite, table: name, db: this.selectedDb } });
          if (d.tables) this.dbTables = Object.assign({}, this.dbTables, { [this.selectedDb]: d.tables });
          this.toast(`已把表「${name}」导入到 ${this.selectedDb}，去工作台查看`);
        } catch (e) {
          if (e.message.indexOf("同名") >= 0 && !overwrite) {
            if (confirm(`你的空间里已有同名表「${name}」，覆盖它吗？`)) return doIt(true);
          } else this.toast(e.message);
        } finally { this.busy = false; }
      };
      return doIt(false);
    },

    async openPyItem(it) {
      try {
        const d = await this.api("/api/community/open", { method: "POST", body: { id: it.id } });
        await this.refreshPyList();
        this.switchView("py");
        this.pyCurrent = d.filename;
        const f = await this.api(`/api/pyfiles/${encodeURIComponent(d.filename)}`);
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
        this.toast(`已保存为文件 ${d.filename}，点 ▶ 运行 试试`);
      } catch (e) { this.toast(e.message); }
    },

    downloadItem(it) {
      this.downloadFile(`/api/community/${it.id}/download`, it.filename || it.title);
    },

    async deleteItem(it) {
      if (!confirm(`确定从社区删除「${it.title}」？`)) return;
      try {
        await this.api(`/api/community/${it.id}`, { method: "DELETE" });
        this.toast("已删除");
        this.loadCommunity();
      } catch (e) { this.toast(e.message); }
    },

    /* ---------- 管理 ---------- */
    async openAdmin() {
      this.$refs.adminDlg.showModal();
      await this.loadAdmin(this.adminKind);
    },

    switchAdminKind(kind) {
      if (this.adminKind === kind) return;
      this.adminKind = kind;
      this.loadAdmin(kind);
    },

    async loadAdmin(kind) {
      try {
        const d = await this.api("/api/admin/users?kind=" + kind);
        if (kind === "guest") this.adminGuests = d.users;
        else this.adminUsers = d.users;
      } catch (e) { this.toast(e.message); }
    },
    closeAdmin() { this.$refs.adminDlg.close(); this.adminUsers = []; },

    async resetPw(u) {
      const pw = prompt(`给「${u.username}」设置新密码（至少4位）：`);
      if (!pw) return;
      try {
        await this.api("/api/admin/reset_password", { method: "POST",
          body: { username: u.username, new_password: pw } });
        this.toast("密码已重置");
      } catch (e) { this.toast(e.message); }
    },

    async deleteUser(u) {
      const what = u.kind === "guest" ? "游客" : "用户";
      if (!confirm(`删除${what}「${u.username}」？其所有数据库和数据将一并删除，不可恢复！`)) return;
      try {
        await this.api("/api/admin/delete_user", { method: "POST", body: { id: u.id } });
        this.toast("已删除");
        this.loadAdmin(this.adminKind);
      } catch (e) { this.toast(e.message); }
    },
  },
};

const app = createApp(App);
app.component("cm-editor", CmEditor);
app.component("e-icon", EIcon);
app.mount("#app");
