/* SQL·Py 课堂实验室 —— Vue 3 前端应用 */
"use strict";

const { createApp } = Vue;

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
  "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
  "check": '<polyline points="20 6 9 17 4 12"/>',
  "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  "arrow-up": '<line x1="12" x2="12" y1="19" y2="5"/><polyline points="5 12 12 5 19 12"/>',
  "arrow-down": '<line x1="12" x2="12" y1="5" y2="19"/><polyline points="19 12 12 19 5 12"/>',
  "key": '<path d="M12.65 10C11.83 7.67 9.82 6 7.5 6 4.46 6 2 8.46 2 11.5S4.46 17 7.5 17c2.32 0 4.33-1.67 5.15-4H17v4h4v-4h2v-4H12.65zM7.5 15A3.5 3.5 0 1 1 11 11.5 3.5 3.5 0 0 1 7.5 15z"/>',
  "chart": '<line x1="12" x2="12" y1="20" y2="10"/><line x1="18" x2="18" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="16"/><path d="M2 20h20"/>',
  "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  "minus": '<path d="M5 12h14"/>',
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

/* 自建下拉选择：替代原生 <select>（手机内嵌浏览器会弹系统选择器，且样式与站点不统一）。
   浮层用 fixed 按按钮坐标定位：弹窗内容区是 overflow:auto 的滚动容器，
   绝对定位的浮层会撑大滚动区、被裁剪，fixed 不受影响也不会拉长弹窗。 */
const XSelect = {
  props: {
    modelValue: String,
    options: { type: Array, default: () => [] },   // [{ value, label }]
  },
  emits: ["update:modelValue"],
  data() { return { open: false, pos: { top: 0, left: 0, width: 0, maxH: 240 } }; },
  computed: {
    label() {
      const o = this.options.find(o => o.value === this.modelValue);
      return o ? o.label : (this.modelValue || "请选择");
    },
    popStyle() {
      return { top: this.pos.top + "px", left: this.pos.left + "px",
               width: this.pos.width + "px", maxHeight: this.pos.maxH + "px" };
    },
  },
  template: `<div class="xsel">
    <button type="button" class="xsel-btn" ref="btn" :aria-expanded="open" @click.stop="toggle">
      <span class="xsel-label">{{ label }}</span>
      <e-icon name="chevron-down" :size="13"></e-icon>
    </button>
    <div class="xsel-pop" ref="pop" v-show="open" :style="popStyle">
      <button type="button" v-for="o in options" :key="o.value" class="xsel-opt"
              :class="{ on: o.value === modelValue }" @click.stop="pick(o.value)">
        <span class="xsel-tick"><e-icon v-if="o.value === modelValue" name="check" :size="12"></e-icon></span>
        <span>{{ o.label }}</span>
      </button>
    </div>
  </div>`,
  methods: {
    toggle() {
      if (this.open) { this.open = false; return; }
      this.place();
      this.open = true;
    },
    // 按按钮在屏幕上的实际位置摆放浮层：优先完整显示列表，下方不够就往上翻，
    // 两边都不够才压缩高度（浮层自己滚动，绝不影响弹窗本身）
    place() {
      const btn = this.$refs.btn;
      if (!btn) return;
      const r = btn.getBoundingClientRect();
      const vh = window.innerHeight || 800;
      const gap = 4, pad = 8, ideal = 240;
      const spaceBelow = vh - r.bottom - gap - pad;
      const spaceAbove = r.top - gap - pad;
      let top, maxH;
      if (spaceBelow >= ideal) {
        maxH = ideal; top = r.bottom + gap;
      } else if (spaceAbove >= ideal) {
        maxH = ideal; top = r.top - gap - ideal;
      } else if (spaceBelow >= spaceAbove) {
        maxH = Math.max(90, spaceBelow); top = r.bottom + gap;
      } else {
        maxH = Math.max(90, spaceAbove); top = r.top - gap - maxH;
      }
      this.pos = { top, left: r.left, width: r.width, maxH };
    },
    pick(v) { this.$emit("update:modelValue", v); this.open = false; },
    outside(e) { if (!this.$el.contains(e.target)) this.open = false; },
    follow() { if (this.open) this.place(); },   // 弹窗内容滚动时跟着按钮走
  },
  mounted() {
    document.addEventListener("click", this.outside, true);
    window.addEventListener("scroll", this.follow, true);
    window.addEventListener("resize", this.follow);
  },
  unmounted() {
    document.removeEventListener("click", this.outside, true);
    window.removeEventListener("scroll", this.follow, true);
    window.removeEventListener("resize", this.follow);
  },
};

/* 自建复选框：替代原生 <input type=checkbox>，样式统一、手指点得准 */
const XCheck = {
  props: { modelValue: Boolean, label: String, slim: Boolean },
  emits: ["update:modelValue"],
  template: `<button type="button" class="xchk" :class="{ on: modelValue, slim }" role="checkbox"
    :aria-checked="modelValue" @click="$emit('update:modelValue', !modelValue)">
    <span class="xchk-box"><e-icon v-if="modelValue" name="check" :size="11"></e-icon></span>
    <span class="xchk-label" v-if="label">{{ label }}</span>
  </button>`,
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
    const extra = this.buildExtra(this.mode);
    this.cm = CodeMirror.fromTextArea(this.$el, {
      mode: this.mode,
      lineNumbers: true,
      matchBrackets: true,
      autoCloseBrackets: true,
      styleActiveLine: true,
      indentUnit: 4,
      // 手机上长代码自动换行，避免横向滚动条和文字被截断
      lineWrapping: window.innerWidth < 920,
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
    this.smoothCaret(this.cm);
    // 网页字体或样式晚到时，CodeMirror 会沿用首次测量的行号栏宽度，
    // 字体一变宽行号就挤进正文；下一帧和字体加载完成后各重测一次。
    const refreshGutter = () => {
      const cm = this.cm;
      if (cm && cm.getWrapperElement().isConnected) cm.refresh();
    };
    requestAnimationFrame(refreshGutter);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(refreshGutter).catch(() => {});
    }
  },
  watch: {
    // 父组件异步拿到内容后要同步进来（编辑器可能在数据到达前就已挂载）
    value(v) {
      if (this.cm && v !== this.cm.getValue()) this.cm.setValue(v);
    },
    // 同一套题里可能既有 SQL 题又有 Python 题，切换时高亮和快捷键要跟着变
    mode(m) {
      if (!this.cm) return;
      this.cm.setOption("mode", m);
      this.cm.setOption("extraKeys", this.buildExtra(m));
    },
  },
  methods: {
    /* 平滑插入符：CodeMirror 每次绘制都会重建光标元素，CSS 过渡不生效。
       这里在光标移动后用 FLIP（先摆到旧位置再过渡回 0）让它“滑”过去，
       手感类似 Word；移动距离越远滑得越快，系统开了减少动态效果就不做。 */
    smoothCaret(cm) {
      if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      let prev = null;
      const apply = () => {
        const el = cm.display && cm.display.cursorDiv &&
                   cm.display.cursorDiv.querySelector(".CodeMirror-cursor");
        if (!el || !el.isConnected) return;
        const r = el.getBoundingClientRect();
        const now = { x: r.left, y: r.top };
        if (prev) {
          const dx = prev.x - now.x, dy = prev.y - now.y;
          const dist = Math.hypot(dx, dy);
          if (dist > 0.5 && dist < 600) {
            el.style.transition = "none";
            el.style.transform = `translate(${dx}px, ${dy}px)`;
            void el.offsetWidth;                 // 强制回流，保证过渡从旧位置起步
            const dur = Math.min(140, 70 + dist * 0.35);
            el.style.transition = `transform ${dur}ms cubic-bezier(.25,.7,.3,1)`;
            el.style.transform = "";
            el.addEventListener("transitionend",
              () => { el.style.transition = ""; }, { once: true });
          }
        }
        prev = now;
      };
      cm.on("cursorActivity", () => setTimeout(apply, 0));
    },
    buildExtra(mode) {
      const extra = {
        "Ctrl-Enter": () => this.run && this.run(),
        "Cmd-Enter": () => this.run && this.run(),
      };
      if (mode === "text/x-mysql") {
        extra["Ctrl-Space"] = (cm) => cm.showHint({
          hint: CodeMirror.hint.sql,
          tables: this.hintTables || {},
          completeSingle: false,
        });
      }
      if (mode === "text/x-python") {
        extra["Tab"] = (cm) => {
          // 补全弹层开着时交给它处理（Tab 选中补全项）
          if (cm.state.completionActive) return;
          cm.replaceSelection("    ");
        };
      }
      return extra;
    },
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
      pyProjects: [],
      pyProjectId: 0,
      pyProjectCollapsed: false,
      pyOpenFiles: [],
      pyCurrent: "main.py",
      pySaveTimer: null,
      pyDirty: new Set(),
      pyCapsule: "",
      pyCapsuleTimer: null,
      pyRunCount: 0,
      pyJob: "",
      pyStdin: "",
      pendingShareCode: "",
      shareForm: { db: "", shareName: "", link: "", done: false },

      // 自制弹窗（内嵌浏览器会屏蔽原生 prompt/confirm，必须用页面内弹窗）
      ask: { open: false, title: "", label: "", value: "", ok: null, _resolve: null },
      confirmBox: { open: false, title: "", text: "", danger: false,
                    okText: "", cancelText: "", _resolve: null },

      KIND_LABEL,

      importForm: { file: null, table: "", header: true, overwrite: false },

      ctForm: { name: "", db: "", overwrite: false, cols: [{ name: "id", type: "INT", pk: true }] },
      colTypes: [
        { value: "INT", label: "整数 INT" },
        { value: "VARCHAR(50)", label: "文字 VARCHAR" },
        { value: "DOUBLE", label: "小数 DOUBLE" },
        { value: "DATE", label: "日期 DATE" },
        { value: "TEXT", label: "长文本 TEXT" },
      ],

      preview: { open: false, tab: "data", name: "", loading: false, columns: [], rows: null,
                 desc: null, descColumns: [], ddl: "", source: null },

      community: [],
      communityQuestions: [],
      myQuestions: [],
      qTab: "square",
      qForm: { id: 0, title: "", note: "", db: "", pyMap: {} },
      qBusy: false,
      // 练习
      drillCourse: "sql",
      drillView: "list",            // list 清单 / paper 试卷详情 / do 做题
      papers: [],
      paperCurrent: null,
      paperForm: { id: 0, maxAttempts: 0, showAnswer: true,
                   timeLimitMinutes: 0, allowPause: true, maxResumes: 3,
                   busy: false },
      paperStats: null,
      paperStatsBusy: false,
      statsBack: "paper",
      paperBusy: false,
      paperAnswers: {},        // 本次作答：题目 id -> 是否已写答案
      paperNav: {},            // 本题 Navicat 操作缓存：题目 id -> {log, query, mode}
      paperLimitMinutes: 0,    // 本套限时（分钟）
      paperStartAt: 0,         // 本次作答开始时间戳（本地换算）
      paperDeadline: 0,        // 本次作答截止时间戳
      paperNow: Date.now(),
      paperAutoSubmitting: false,
      paperAutoRetryAt: 0,
      paperActive: false,      // 已经进入这套卷子的作答（哪怕一题没写）
      paperDescOpen: false,    // 「数据库说明」默认收成一行摘要，点开是浮层，不挤压做题区
      hintOff: { sql: false, py: false, drills: false },  // 新手引导是否已关闭（按账号存本地）
      paperAllowPause: true,   // 本卷是否允许中途退出并暂停计时
      paperMaxResumes: 3,      // 不允许中途退出时，异常退出可续做次数
      paperResumeCount: 0,
      paperResumeBlocked: false,
      pageVisitId: "v" + Math.random().toString(36).slice(2) + Date.now().toString(36),
      _lastHeartbeat: 0,
      papersBusy: false,
      drillTabs: [
        { value: "sql", label: "MySQL", icon: "database" },
        { value: "python", label: "Python", icon: "code" },
        { value: "basic", label: "客观题", icon: "list" },
        { value: "wrong", label: "错题本", icon: "shield" },
      ],
      drillList: [],
      drillCurrent: null,
      drillLoading: false,
      drillDirty: false,
      navMode: false,
      navLog: [],
      navLastQuery: "",
      drillOpenSeq: 0,
      drillResult: null,
      drillCode: "",
      drillPick: "",
      drillFill: "",
      drillBusy: false,
      drillShowSetup: false,
      drillShowHint: false,
      drillProgress: {},
      qpack: null,
      qpackBusy: false,
      qpackDrag: false,
      sqlJudgeOptions: [
        { value: "dbstate", label: "整库状态（建表/增删改）" },
        { value: "result", label: "结果集一致" },
        { value: "result_ordered", label: "结果集（含顺序）" },
        { value: "rows_only", label: "只比数据" },
        { value: "cell", label: "只比单值" },
        { value: "state", label: "校验指定查询" },
      ],
      pyJudgeOptions: [
        { value: "output", label: "输出一致" },
        { value: "contains", label: "输出包含" },
        { value: "regex", label: "正则匹配" },
        { value: "tests", label: "多组用例" },
      ],
      drillSandbox: { db: "", tables: [], loading: false, error: "" },
      drillRunLog: [],
      drillMulti: [],
      dq: { id: 0, course: "sql", type: "sql", typeLabel: "", title: "", stem: "", hint: "",
            setupSql: "", verifySql: "", starterCode: "", inputData: "", expectedOutput: "",
            optionsText: "", rightKey: "", multiKeys: [], fillAnswers: "", status: 1,
            judgeMode: "result", cases: [], trySql: "", tryCode: "", importDb: "",
            paper: "", score: 10 },
      dqBusy: false,
      authorDirty: false,
      tryResult: null,
      drillTypes: [
        { value: "sql", label: "SQL 题", icon: "database", desc: "建表造数，学生写查询，按结果集判分" },
        { value: "python", label: "Python 题", icon: "code", desc: "学生写代码，按输出/测试用例判分" },
        { value: "single", label: "单选题", icon: "list", desc: "多个选项里选一个，自动判分" },
        { value: "multiple", label: "多选题", icon: "list", desc: "可选多个正确项，全对才通过" },
        { value: "boolean", label: "判断题", icon: "check", desc: "对 / 错 二选一" },
        { value: "fill", label: "填空题", icon: "file-text", desc: "填一个词，宽松匹配大小写空格" },
      ],
      judgeModes: {
        sql: [
          { value: "result", label: "结果集一致（不看行序）" },
          { value: "result_ordered", label: "结果集一致（行序也要对）" },
          { value: "rows_only", label: "只比数据，不检查列名" },
          { value: "cell", label: "只比第一个值" },
          { value: "contains", label: "结果中包含指定值" },
          { value: "state", label: "改数据题：校验执行后的数据状态" },
        ],
        python: [
          { value: "output", label: "输出完全一致" },
          { value: "contains", label: "输出包含指定文字" },
          { value: "regex", label: "输出匹配正则" },
          { value: "tests", label: "多组测试用例全部通过" },
        ],
        single: [{ value: "key", label: "选中正确选项" }],
        multiple: [{ value: "keys", label: "选出全部正确选项" }],
        boolean: [{ value: "key", label: "选中正确答案" }],
        fill: [{ value: "loose", label: "宽松匹配（忽略大小写/空格/标点）" }],
      },

      qpv: { loading: false, id: 0, title: "", note: "", uploader: "", createdAt: "",
             downloads: 0, tables: [], tableData: [], pyPreview: [] },
      qpvFile: null,
      qpvTable: null,
      qpvTab: "data",

      detail: { open: false, loading: false, id: 0, title: "", uploader: "", isScript: false,
                tables: [], builtin: false, filename: "" },
      dbPv: { loading: false, name: "", cols: [], rows: [], ddl: "", script: false,
              rowCount: null, truncated: false },
      dbPvTab: "data",

      // 用户管理
      adminTab: "overview",
      adminOverview: null,
      adminList: [],
      adminTotal: 0, adminPage: 1, adminPages: 1,
      adminQuery: "", adminOnly: "",
      adminOnlyOptions: [
        { value: "", label: "全部" },
        { value: "publish", label: "有出题权限" },
        { value: "nopublish", label: "无出题权限" },
        { value: "disabled", label: "已禁用" },
      ],
      adminChecked: [],
      adminLogs: [], adminLogOnlyFail: false,
      userDetail: null,
      // 个人中心
      profile: null,
      pwForm: { old: "", new: "", repeat: "" }, pwBusy: false,
      // 新建账号
      cuForm: { username: "", password: "", canPublish: false }, cuBusy: false,
      drawer: "",
    };
  },

  computed: {
    dbOptions() {
      return [{ value: "", label: "不包含 MySQL 部分" }].concat(
        (this.databases || []).map(d => ({
          value: d.name, label: d.name + (d.primary ? "（默认）" : "") + ` · ${d.tables} 张表`,
        })));
    },
    drillPassedCount() { return this.drillList.filter(d => d.passed).length; },
    // 做题页左侧列的是「本套试卷的题目」，不在试卷里时退回按分类的题目列表
    drillSideList() {
      return (this.paperCurrent && this.paperCurrent.questions) || this.drillList;
    },
    courseStat() {
      const p = this.drillProgress[this.drillCourse] || {};
      return { total: p.total || 0, done: p.done || 0,
               maxScore: p.maxScore || 0, myScore: p.myScore || 0 };
    },
    paperPct() {
      return (p) => (p && p.totalScore
        ? Math.round((p.myScore || 0) / p.totalScore * 100) : 0);
    },
    courseProgress() {
      const out = {};
      for (const t of this.drillTabs) {
        const p = this.drillProgress[t.value];
        out[t.value] = p ? p.done : 0;
      }
      return out;
    },
    textChoice() { return ["single", "multiple", "boolean"].includes(this.dq.type); },
    judgeModeOptions() { return this.judgeModes[this.dq.type] || []; },
    judgeModeHint() {
      const t = this.dq.type, m = this.dq.judgeMode;
      const map = {
        "sql:result": "学生写好查询后，系统把标准答案跑一遍，比对列名和全部数据（行和列的顺序都不计较）。最常用。",
        "sql:result_ordered": "同上，但要求行的顺序也完全一致（比如 ORDER BY 后顺序不同就算错）。",
        "sql:rows_only": "只看查出来的数据是否一样，列名不同没关系（适合学生用别名的情况）。",
        "sql:cell": "只比对查询结果的第一个格子，适合「查一个数」的题（如 COUNT、MAX）。",
        "sql:contains": "标准答案只写一个值，学生的结果里包含这个值就算对（适合「找出某个人」）。",
        "sql:state": "适合改数据题（UPDATE/INSERT/DELETE）：先执行学生的 SQL，再跑标准答案 SQL 取数据状态来比对。参考答案里填期望的值（逗号分隔）。",
        "python:output": "学生程序的标准输出与期望输出逐行比对（忽略每行首尾空格和空行）。",
        "python:contains": "要求输出里包含期望文字即可，适合开放一点的小题。",
        "python:regex": "用正则表达式匹配整个输出，适合格式有规律但内容可变的题。",
        "python:tests": "给多组输入/期望输出，学生程序每组都要跑对才通过。",
        "fill:loose": "忽略大小写、空格、全角半角和常见标点，答对任意一个可接受答案就通过。",
      };
      return map[t + ":" + m] || "选择一种判分方式，右侧可以实时试跑检查。";
    },
    setupDbOptions() {
      return (this.databases || []).map(d => ({
        value: d.name,
        label: d.name + (d.primary ? "（默认）" : "") + ` · ${d.tables} 张表`,
      }));
    },
    optionKeys() {
      return String(this.dq.optionsText || "").split("\n")
        .map(l => (/^\s*([A-Za-z0-9])\s*[.、)]/.exec(l) || [])[1])
        .filter(Boolean).map(k => k.toUpperCase());
    },
    adminAllChecked() {
      const ids = this.adminList.filter(u => u.role !== "admin").map(u => u.id);
      return ids.length > 0 && ids.every(id => this.adminChecked.includes(id));
    },
    pyProjectName() {
      const p = this.pyProjects.find(x => x.id === this.pyProjectId);
      return p ? p.name : "";
    },
    drillCodeType() {
      const t = this.drillCurrent && this.drillCurrent.type;
      return t === "sql" || t === "python";
    },
    // 整卷口径：可交卷次数按「套」算；出卷人和管理员不限制
    paperTriesLeft() {
      const p = this.paperCurrent;
      if (!p || !p.maxAttempts) return null;
      if (p.mine || (this.user && this.user.role === "admin")) return null;
      return Math.max(0, p.maxAttempts - (p.attemptCount || 0));
    },
    paperOutOfTries() {
      return this.paperTriesLeft === 0;
    },
    paperAnsweredCount() {
      return Object.values(this.paperAnswers || {}).filter(Boolean).length;
    },
    // 数据库说明收起后，标题栏留一句摘要，避免完全看不到
    paperDescPreview() {
      const s = (this.paperCurrent && this.paperCurrent.description) || "";
      return s.split("\n").map(x => x.trim()).filter(Boolean).join(" ").slice(0, 110);
    },
    paperSecondsLeft() {
      if (!this.paperDeadline || !this.paperLimitMinutes) return null;
      return Math.max(0, Math.ceil((this.paperDeadline - this.paperNow) / 1000));
    },
    paperTimeLow() {
      const s = this.paperSecondsLeft;
      return s !== null && s <= 300;
    },
    paperTimeText() {
      const s = this.paperSecondsLeft;
      if (s === null) return "";
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      const pad = n => String(n).padStart(2, "0");
      return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
    },
    paperElapsedSeconds() {
      if (!this.paperStartAt) return null;
      return Math.max(0, Math.floor((this.paperNow - this.paperStartAt) / 1000));
    },
    paperElapsedText() {
      const s = this.paperElapsedSeconds;
      if (s === null) return "";
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      const pad = n => String(n).padStart(2, "0");
      return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
    },
    drillIndex() {
      const list = this.drillSideList || [];
      return list.findIndex(x => this.drillCurrent && x.id === this.drillCurrent.id);
    },
    isFirstDrill() { return this.drillIndex <= 0; },
    isLastDrill() {
      const i = this.drillIndex;
      return i < 0 || i >= (this.drillSideList || []).length - 1;
    },
    draftCount() { return this.myQuestions.filter(q => !q.status).length; },
    // 题库广场：题目在前、旧资源条目在后，放进同一个网格里铺开（避免两排各自留空）
    squareList() {
      const qs = (this.communityQuestions || []).map(q => Object.assign({ isQuestion: true }, q));
      const items = (this.community || []).map(i => Object.assign({ isQuestion: false }, i));
      return qs.concat(items);
    },
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
    busy(v) {
      this.$nextTick(() => {
        const el = document.getElementById("busy");
        if (!el) return;
        if (v) this._popShow(el); else this._popHide(el);
      });
    },
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
        else if (this.view === "drills" && this.drillCurrent && this.drillCodeType) this.runDrillOnly();
      }
    });
    // 刷新/关闭页面时，未交卷的作答先让浏览器拦一下
    window.addEventListener("beforeunload", this.onBeforeUnload);
    // 整卷限时：每秒刷新倒计时，到点自动交卷
    setInterval(() => {
      this.paperNow = Date.now();
      this.checkPaperTimeout();
      if (this.paperAllowPause && this.drillView === "do" && this.paperCurrent
          && this.paperStartAt && Date.now() - this._lastHeartbeat > 15000) {
        this._lastHeartbeat = Date.now();
        this.api(`/api/papers/${this.paperCurrent.id}/heartbeat`, { method: "POST" })
          .catch(() => {});
      }
    }, 1000);
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
    kindLabel(kind) {
      return { sql_select: "查询题", sql_dml: "修改/新增题", sql_ddl: "建对象题",
               python: "Python 题" }[kind] || kind;
    },
    toggleTheme() {
      this.theme = this.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = this.theme;
      localStorage.setItem("lab_theme", this.theme);
    },

    kindIcon(kind) {
      return { db: "database", py: "code", csv: "file-text", xlsx: "file-spreadsheet", table: "table" }[kind] || "table";
    },

    // popover 元素进 top layer，弹窗打开时也不会被遮挡
    _popShow(el) {
      if (!el) return;
      try {
        if (el.matches(":popover-open")) return;
        if (el.showPopover) el.showPopover();
      } catch (e) {}
    },
    _popHide(el) {
      if (!el) return;
      try {
        if (el.matches(":popover-open")) el.hidePopover();
      } catch (e) {}
    },
    toast(msg, ms) {
      this.toastMsg = msg;
      clearTimeout(this.toastTimer);
      this.$nextTick(() => {
        const el = document.getElementById("toast");
        if (el) { this._popShow(el); el.classList.add("show"); }
      });
      this.toastTimer = setTimeout(() => {
        this.toastMsg = "";
        const el = document.getElementById("toast");
        if (el) el.classList.remove("show");
        this._popHide(el);
      }, ms || 2600);
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
        if (!el) return;
        // 滚到最新一条的「开头」而不是最底部：这样能看到「N 行」和表头，
        // 结果很长时也不会一进去就只看到表格最末几行。
        el.scrollTop = el.scrollHeight;
        const blocks = el.querySelectorAll(".cblock");
        const last = blocks[blocks.length - 1];
        if (last) {
          const top = last.offsetTop - el.offsetTop - 8;
          el.scrollTop = Math.max(0, top);
        }
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
      this.loadHints();
      this.databases = me.databases || [];
      this.selectedDb = me.db || (this.databases[0] ? this.databases[0].name : "");
      this.dbTables = { [this.selectedDb]: me.tables || [] };
      this.openDbs = { [this.selectedDb]: true };
      // SQL 编辑器：只恢复学生自己上次写的内容；没有就保持空白，不预填任何示例
      const who = (me.user && me.user.name) || "?";
      let draft = "";
      try { draft = localStorage.getItem("lab_sql_draft:" + who) || ""; } catch (e) {}
      this.sqlInit = draft;
      this.logged = true;
      this.initPyFiles();
      this.checkPendingShare();
      // 上传的临时 py 文件按需求"每次刷新即删"：进应用时先清一次
      this.api("/api/pyfiles/clear-uploaded", { method: "POST" })
        .then(() => {
          this.refreshPyList();
          this.loadPyProjects().catch(() => {});
        }).catch(() => {});
    },

    async logout() {
      if (this.view === "drills") {
        if (!await this.confirmLeaveDrill(true)) return;
        if (this.paperAllowPause && this.paperCurrent) {
          await this.pausePaper(this.drillView === "do");
        }
        if (!this._leavePrompted) {
          const hasDrafts = this.drillView === "paper" && this.paperCurrent &&
                            this.paperHasSavedDrafts();
          const timer = this.paperDeadline ? "限时还在继续计时。" : "";
          const text = hasDrafts
            ? "本套试卷还有没交卷的作答。" + timer + "退出登录后草稿会保留，重新登录可以继续。确定退出吗？"
            : "确定要退出登录吗？未交卷的草稿会保留，正在计时的试卷会继续计时。";
          if (!await this.askConfirm("退出登录", text, true, "退出登录", "取消")) return;
        }
        this._leavePrompted = false;
      }
      if (!await this.confirmLeaveWorkspace()) return;
      this.flushDrillDraft();
      this.stashPaperNav();
      try { await this.api("/api/logout", { method: "POST" }); } catch (e) {}
      this.token = "";
      this.user = null;
      this.logged = false;
      this.drillDirty = false;
      localStorage.removeItem("lab_token");
    },

    /* ---------- 新手引导（按账号记忆是否关闭） ---------- */
    loadHints() {
      const who = (this.user && this.user.name) || "?";
      let saved = null;
      try { saved = JSON.parse(localStorage.getItem("lab_hint_off:" + who)); } catch (e) {}
      this.hintOff = { sql: false, py: false, drills: false,
                       ...(saved && typeof saved === "object" ? saved : {}) };
    },
    dismissHint(v) {
      this.hintOff = { ...this.hintOff, [v]: true };
      const who = (this.user && this.user.name) || "?";
      try { localStorage.setItem("lab_hint_off:" + who, JSON.stringify(this.hintOff)); } catch (e) {}
    },
    // 引导卡上的「试跑一条查询」：填一条最简单的语句并运行
    trySampleQuery() {
      if (this.$refs.cmSqlRef) this.$refs.cmSqlRef.setValue("SHOW TABLES");
      this.runSql();
    },

    async switchView(v) {
      if (!await this.confirmLeaveDrill(true)) return;
      this.flushDrillDraft();
      this.stashPaperNav();
      if (this.paperCurrent && this.paperAllowPause) {
        await this.pausePaper(this.drillView === "do");
      }
      this.view = v;
      this.drawer = "";
      if (v === "community" && !this.community.length) this.loadCommunity();
      if (v === "drills") {
        // 从别的页面点「练习」总是回到清单，不停在上次那道题里
        this.drillView = "list";
        this.paperCurrent = null;
        this.drillCurrent = null;
        this.drillResult = null;
        this.loadPapers();
      }
    },

    /* ---------- 练习：清单 → 试卷详情 → 做题 ---------- */

    async loadPapers() {
      this.papersBusy = true;
      try {
        const path = this.drillCourse === "wrong"
          ? "/api/drills/wrong"
          : "/api/papers?course=" + encodeURIComponent(this.drillCourse);
        const [d, pr] = await Promise.all([this.api(path), this.api("/api/drills/progress")]);
        this.drillProgress = pr.progress || {};
        if (this.drillCourse === "wrong") {
          // 错题本没有「套」的概念，直接把做错的题铺成卡片
          this.drillList = d.drills || [];
          this.papers = (d.drills || []).map(x => ({
            id: -x.id, single: true, drillId: x.id, course: "wrong",
            title: x.title, description: x.stem || "", questionCount: 1,
            totalScore: x.score || 0, myScore: 0, doneCount: 0, triedCount: x.attempts || 0,
            uploader: x.uploader, courseLabel: "错题重做", typeLabel: x.typeLabel,
          }));
        } else {
          this.papers = d.papers || [];
        }
      } catch (e) { this.toast(e.message); }
      finally { this.papersBusy = false; }
    },

    async switchDrillCourse(c) {
      this.drillCourse = c;
      this.drillView = "list";
      this.paperCurrent = null;
      this.drillCurrent = null;
      this.drillResult = null;
      await this.loadPapers();
    },

    async backToPapers() {
      if (!await this.confirmLeaveDrill(true)) return;
      this.flushDrillDraft();
      this.stashPaperNav();
      if (this.paperCurrent && this.paperAllowPause) {
        await this.pausePaper(this.drillView === "do");
      }
      this.drillView = "list";
      this.paperCurrent = null;
      this.drillCurrent = null;
      this.drillResult = null;
      this.drillDirty = false;
      this.loadPapers();
    },

    async openPaper(p) {
      // 错题本里的卡片是单题，直接进做题页
      if (p.single) {
        this.paperCurrent = null;
        await this.startDrill({ id: p.drillId });
        return;
      }
      try {
        this.paperCurrent = await this.api(`/api/papers/${p.id}`);
        this.paperDescOpen = false;
        this.paperDeadline = 0;
        this.paperStartAt = 0;
        this.paperLimitMinutes = this.paperCurrent.timeLimitMinutes || 0;
        this.paperAllowPause = this.paperCurrent.allowPause !== false;
        this.paperMaxResumes = this.paperCurrent.maxResumes || 3;
        this.paperResumeBlocked = false;
        this.loadPaperActive(p.id);
        this.loadPaperNav(p.id);
        this.paperAnswers = {};
        this.syncPaperAnswers();
        this.drillCurrent = null;
        this.drillResult = null;
        this.drillView = "paper";
        window.scrollTo(0, 0);
      } catch (e) { this.toast(e.message); }
    },

    async refreshPaper() {
      if (!this.paperCurrent) return;
      try {
        this.paperCurrent = await this.api(`/api/papers/${this.paperCurrent.id}`);
      } catch (e) { /* 忽略：刷新失败不影响做题 */ }
    },

    async backToPaper() {
      if (!await this.confirmLeaveDrill(false)) return;
      this.flushDrillDraft();
      this.stashPaperNav();
      if (this.paperCurrent && this.paperAllowPause) await this.pausePaper(true);
      this.drillView = "paper";
      this.drillCurrent = null;
      this.drillResult = null;
      this.drillDirty = false;
      this.refreshPaper();
    },

    /* ---------- 试卷设置（出卷人） ---------- */
    openPaperSettings(p) {
      if (!p || !p.mine || !this.user || !this.user.canPublish) return;
      this.paperForm = { id: p.id, maxAttempts: p.maxAttempts || 0,
                         showAnswer: p.showAnswer !== false,
                         timeLimitMinutes: p.timeLimitMinutes || 0,
                         allowPause: p.allowPause !== false,
                         maxResumes: p.maxResumes || 3, busy: false };
      const d = this.$refs.paperSetDlg;
      if (d && !d.open) { try { d.showModal(); } catch (e) { d.setAttribute("open", ""); } }
    },
    closePaperSettings() {
      const d = this.$refs.paperSetDlg;
      if (d && d.open) d.close();
    },
    async savePaperSettings() {
      const f = this.paperForm;
      if (!f.id || f.busy) return;
      f.maxAttempts = Math.max(0, Math.min(99, parseInt(f.maxAttempts, 10) || 0));
      f.timeLimitMinutes = Math.max(0, Math.min(1440, parseInt(f.timeLimitMinutes, 10) || 0));
      f.maxResumes = Math.max(1, Math.min(5, parseInt(f.maxResumes, 10) || 3));
      f.busy = true;
      try {
        const r = await this.api(`/api/papers/${f.id}/settings`, {
          method: "POST",
          body: { maxAttempts: f.maxAttempts, showAnswer: !!f.showAnswer,
                  timeLimitMinutes: f.timeLimitMinutes,
                  allowPause: !!f.allowPause, maxResumes: f.maxResumes },
        });
        if (this.paperCurrent && this.paperCurrent.id === f.id) {
          this.paperCurrent.maxAttempts = r.maxAttempts;
          this.paperCurrent.showAnswer = r.showAnswer;
          this.paperCurrent.timeLimitMinutes = r.timeLimitMinutes;
          this.paperCurrent.allowPause = r.allowPause;
          this.paperCurrent.maxResumes = r.maxResumes;
          this.paperAllowPause = r.allowPause;
          this.paperMaxResumes = r.maxResumes;
          this.paperDeadline = 0;
          this.paperStartAt = 0;
          this.paperLimitMinutes = r.timeLimitMinutes;
        }
        const p = this.papers.find(x => x.id === f.id);
        if (p) {
          p.maxAttempts = r.maxAttempts;
          p.showAnswer = r.showAnswer;
          p.timeLimitMinutes = r.timeLimitMinutes;
          p.allowPause = r.allowPause;
          p.maxResumes = r.maxResumes;
        }
        this.closePaperSettings();
        this.toast("试卷设置已保存");
      } catch (e) { this.toast(e.message); }
      finally { f.busy = false; }
    },

    /* ---------- 本套统计（交卷后的作答详情与分数） ---------- */
    async openPaperStats(p) {
      const pid = (p && p.id) || (this.paperCurrent && this.paperCurrent.id) ||
                  (this.drillCurrent && this.drillCurrent.paperId) || 0;
      if (!pid || this.paperStatsBusy) return;
      this.statsBack = this.drillView === "do" ? "do" : (this.paperCurrent ? "paper" : "list");
      this.paperStatsBusy = true;
      try {
        this.paperStats = await this.api(`/api/papers/${pid}/stats`);
        this.drillView = "stats";
        window.scrollTo(0, 0);
      } catch (e) { this.toast(e.message); }
      finally { this.paperStatsBusy = false; }
    },
    backFromStats() {
      if (this.statsBack === "do" && this.drillCurrent) {
        this.drillView = "do";
        return;
      }
      if (this.paperCurrent) {
        this.drillView = "paper";
        this.refreshPaper();
      } else {
        this.backToPapers();
      }
    },
    fmtAnswer(a) {
      if (a === null || a === undefined || a === "") return "（未作答）";
      if (Array.isArray(a)) return a.join("、");
      if (typeof a === "object") return JSON.stringify(a);
      return String(a);
    },

    async deletePaper(p) {
      if (!await this.askConfirm("删除整套题",
        `将删除「${p.title}」里的 ${p.questionCount} 道题和全部作答记录，无法恢复。继续？`)) return;
      try {
        await this.api(`/api/papers/${p.id}`, { method: "DELETE" });
        this.toast("已删除整套题");
        await this.loadPapers();
      } catch (e) { this.toast(e.message); }
    },

    async renamePaper(p) {
      const name = await this.askText("试卷名称", "练习页卡片上显示的标题", p.title);
      if (name === null) return;
      const t = String(name).trim();
      if (!t || t === p.title) return;
      try {
        await this.api(`/api/papers/${p.id}/rename`, { method: "POST", body: { title: t } });
        this.toast("已改名");
        if (this.paperCurrent && this.paperCurrent.id === p.id) this.paperCurrent.title = t;
        await this.loadPapers();
      } catch (e) { this.toast(e.message); }
    },

    setNavMode(on) {
      this.navMode = !!on;
      try { localStorage.setItem("lab_drill_mode", on ? "nav" : "sql"); } catch (e) {}
      if (on) this.$nextTick(() => { if (this.$refs.navPanel) this.$refs.navPanel.reload(); });
      this.stashPaperNav();
    },
    onNavLog(sql) {
      if (sql && !this.navLog.includes(sql)) this.navLog.push(sql);
      if (sql) this.drillDirty = true;
      this.stashPaperNav();
    },
    onNavQuery(sql) {
      this.navLastQuery = String(sql || "");
      if (this.navLastQuery.trim()) this.drillDirty = true;
      this.stashPaperNav();
    },

    /* ---------- 整卷作答：跨题保存答案 + 一次交卷 ---------- */
    _paperNavKey(pid) {
      const who = (this.user && this.user.name) || "?";
      return "lab_paper_nav:" + who + ":" + pid;
    },
    loadPaperNav(pid) {
      try {
        const raw = localStorage.getItem(this._paperNavKey(pid));
        this.paperNav = raw ? (JSON.parse(raw) || {}) : {};
      } catch (e) { this.paperNav = {}; }
    },
    _paperActiveKey(pid) {
      const who = (this.user && this.user.name) || "?";
      return "lab_paper_active:" + who + ":" + pid;
    },
    loadPaperActive(pid) {
      try { this.paperActive = localStorage.getItem(this._paperActiveKey(pid)) === "1"; }
      catch (e) { this.paperActive = false; }
    },
    setPaperActive(on) {
      this.paperActive = !!on;
      const pid = this.paperCurrent && this.paperCurrent.id;
      if (!pid) return;
      try {
        if (on) localStorage.setItem(this._paperActiveKey(pid), "1");
        else localStorage.removeItem(this._paperActiveKey(pid));
      } catch (e) {}
    },
    savePaperNav() {
      const pid = this.paperCurrent && this.paperCurrent.id;
      if (!pid) return;
      try { localStorage.setItem(this._paperNavKey(pid), JSON.stringify(this.paperNav)); } catch (e) {}
    },
    // 把当前题的 Navicat 操作记进本卷缓存；切题/交卷/刷新后都还能用
    stashPaperNav() {
      const d = this.drillCurrent;
      if (!d || !d.paperId) return;
      this.paperNav[d.id] = {
        log: this.navLog.slice(),
        query: this.navLastQuery || "",
        mode: this.navMode ? "nav" : "sql",
      };
      this.savePaperNav();
      this.syncPaperAnswers();
    },
    hasSavedAnswer(id) {
      const d = this.loadDrillDraft(id) || {};
      const nav = this.paperNav[id] || {};
      return !!(String(d.code || "").trim() || d.pick ||
                String(d.fill || "").trim() ||
                (Array.isArray(d.multi) && d.multi.length) ||
                (Array.isArray(nav.log) && nav.log.length) ||
                String(nav.query || "").trim());
    },
    syncPaperAnswers() {
      const map = {};
      for (const q of this.drillSideList) {
        if (!q || !q.id) continue;
        if (this.drillCurrent && q.id === this.drillCurrent.id) {
          map[q.id] = this.drillHasAnswer();
        } else {
          map[q.id] = this.hasSavedAnswer(q.id);
        }
      }
      this.paperAnswers = map;
    },
    paperHasUnsubmitted() {
      for (const q of this.drillSideList) {
        if (!q || !q.id) continue;
        if (this.drillCurrent && q.id === this.drillCurrent.id) {
          if (this.drillHasAnswer()) return true;
        } else if (this.hasSavedAnswer(q.id)) {
          return true;
        }
      }
      return false;
    },
    paperHasSavedDrafts() {
      for (const q of this.drillSideList) {
        if (q && q.id && this.hasSavedAnswer(q.id)) return true;
      }
      return false;
    },
    // 按题型把「这道题的答案」取出来；整卷交卷时逐题收集
    answerForDrill(q, saved) {
      const draft = (saved && saved.draft) || {};
      const nav = (saved && saved.nav) || {};
      if (q.type === "sql") {
        const mode = saved ? (nav.mode || "sql") : (this.navMode ? "nav" : "sql");
        const judge = q.judgeMode || "result";
        const queryModes = ["result", "result_ordered", "rows_only", "cell", "contains"];
        if (mode === "nav") {
          if (queryModes.includes(judge)) {
            const query = saved ? nav.query : this.navLastQuery;
            return String(query || "").trim() ? query : "";
          }
          const log = (saved ? nav.log : this.navLog) || [];
          return log.length ? log.join(";\n") + ";" : "";
        }
        return (saved ? draft.code : this.drillCode) || "";
      }
      if (q.type === "python") return (saved ? draft.code : this.drillCode) || "";
      if (q.type === "fill") return (saved ? draft.fill : this.drillFill) || "";
      if (q.type === "multiple") {
        const m = (saved ? draft.multi : this.drillMulti) || [];
        return Array.isArray(m) ? m.slice() : [];
      }
      return (saved ? draft.pick : this.drillPick) || "";
    },
    collectPaperAnswers() {
      this.flushDrillDraft();
      this.stashPaperNav();
      const out = {};
      for (const q of this.drillSideList) {
        if (!q || !q.id) continue;
        const isCurrent = this.drillCurrent && q.id === this.drillCurrent.id;
        const saved = isCurrent ? null : {
          draft: this.loadDrillDraft(q.id) || {},
          nav: this.paperNav[q.id] || {},
        };
        const ans = this.answerForDrill(q, saved);
        if (ans === null || ans === undefined) continue;
        if (typeof ans === "string" && !ans.trim()) continue;
        if (Array.isArray(ans) && !ans.length) continue;
        out[q.id] = ans;
      }
      return out;
    },
    clearPaperDrafts() {
      for (const q of this.drillSideList) {
        if (!q || !q.id) continue;
        try { localStorage.removeItem(this._drillDraftKey(q.id)); } catch (e) {}
      }
      const pid = this.paperCurrent && this.paperCurrent.id;
      if (pid) {
        try { localStorage.removeItem(this._paperNavKey(pid)); } catch (e) {}
      }
      this.paperNav = {};
      this.paperAnswers = {};
      this.drillDirty = false;
      this.drillCode = "";
      this.drillPick = "";
      this.drillFill = "";
      this.drillMulti = [];
      this.navLog = [];
      this.navLastQuery = "";
    },
    async ensurePaperSession() {
      if (!this.paperCurrent) return null;
      try {
        const r = await this.api(`/api/papers/${this.paperCurrent.id}/start`, {
          method: "POST", body: { visitId: this.pageVisitId },
        });
        this.paperLimitMinutes = r.limitMinutes || 0;
        this.paperAllowPause = r.allowPause !== false;
        this.paperMaxResumes = r.maxResumes || 3;
        this.paperResumeCount = r.resumeCount || 0;
        this.paperResumeBlocked = !!r.resumeBlocked;
        this.paperNow = Date.now();
        this.paperStartAt = this.paperNow - Math.max(0, r.elapsedSeconds || 0) * 1000;
        if (r.limitMinutes > 0) {
          this.paperDeadline = this.paperNow + Math.max(0, r.secondsLeft || 0) * 1000;
        } else {
          this.paperDeadline = 0;
        }
        this._lastHeartbeat = Date.now();
        return r;
      } catch (e) {
        this.toast(e.message);
        return null;
      }
    },
    async pausePaper(active = true) {
      if (!this.paperCurrent || !this.paperAllowPause) return;
      try {
        await this.api(`/api/papers/${this.paperCurrent.id}/pause`, {
          method: "POST", body: { active: !!active },
        });
      } catch (e) { /* 暂停失败就让心跳兜底 */ }
      this.clearPaperTimer();
    },
    clearPaperTimer() {
      this.paperDeadline = 0;
      this.paperStartAt = 0;
      this.paperLimitMinutes = 0;
      this.paperAutoRetryAt = 0;
      this.paperAutoSubmitting = false;
    },
    checkPaperTimeout() {
      if (this.view !== "drills" || !this.paperCurrent) return;
      // 不允许中途退出的卷子，在试卷详情页计时也继续，到点同样自动交卷
      if (this.drillView !== "do" && this.drillView !== "paper") return;
      if (!this.paperDeadline || this.paperSecondsLeft > 0) return;
      if (this.paperBusy || this.paperAutoSubmitting) return;
      if (Date.now() < this.paperAutoRetryAt) return;
      this.paperAutoSubmitting = true;
      this.submitPaper(true).finally(() => { this.paperAutoSubmitting = false; });
    },
    prevDrill() {
      const i = this.drillIndex;
      if (i <= 0) return;
      this.startDrill(this.drillSideList[i - 1]);
    },
    nextDrill() {
      const i = this.drillIndex;
      if (i < 0 || i >= (this.drillSideList || []).length - 1) {
        this.toast("已经是最后一题了，请点「交卷」");
        return;
      }
      this.startDrill(this.drillSideList[i + 1]);
    },
    startPaper() {
      if (!this.paperCurrent || !this.paperCurrent.questions.length) return;
      this.paperDescOpen = false;
      const qs = this.paperCurrent.questions;
      const first = qs.find(q => !q.passed) || qs[0];
      this.startDrill(first);
    },
    async submitPaper(auto = false, keepView = false, reason = "") {
      const p = this.paperCurrent;
      if (!p || this.paperBusy) return false;
      if (this.paperOutOfTries) {
        if (!auto) this.toast("本套试卷的交卷次数已经用完");
        return false;
      }
      const answers = this.collectPaperAnswers();
      const n = Object.keys(answers).length;
      if (!auto && !n) { this.toast("先作答至少一道题再交卷"); return false; }
      const total = this.drillSideList.length;
      const left = total - n;
      this.paperBusy = true;
      try {
        if (!auto) {
          if (!await this.askConfirm(
              "确认交卷",
              `本套共 ${total} 题，已作答 ${n} 题${left ? `，还有 ${left} 题未作答` : ""}。` +
              "请检查好再交卷，交卷后会统一判分并记录本次成绩。",
              false, "确认交卷", "再检查一下")) return false;
        }
        const r = await this.api(`/api/papers/${p.id}/submit`, {
          method: "POST", body: { answers, auto: !!auto },
        });
        this.paperStats = r;
        if (!keepView) {
          this.statsBack = "paper";
          this.drillView = "stats";
        }
        this.clearPaperDrafts();
        this.clearPaperTimer();
        this.setPaperActive(false);
        this.paperResumeBlocked = false;
        this.refreshPaper();
        await this.loadPapers();
        const label = reason || (auto ? "时间到，已自动交卷" : "交卷成功");
        this.toast(`${label}：${r.myScore}/${r.totalScore} 分`);
        if (!keepView) window.scrollTo(0, 0);
        return true;
      } catch (e) {
        if (auto) this.paperAutoRetryAt = Date.now() + 5000;
        this.toast(e.message);
        return false;
      } finally { this.paperBusy = false; }
    },
    viewAttempt(a) {
      const s = this.paperStats;
      if (!s || !a) return;
      s.currentNo = a.no;
      s.myScore = a.score;
      s.totalScore = a.totalScore;
      s.doneCount = a.passedCount;
      s.triedCount = a.answeredCount;
      s.questionCount = a.questionCount;
      s.finished = a.finished;
      s.questions = a.questions;
    },

    async startDrill(d) {
      // 已经在这道题里就不用重新加载，避免把正在写的内容重置
      if (this.drillView === "do" && this.drillCurrent && this.drillCurrent.id === d.id) return;
      // 切题前先把上一题的草稿和 Navicat 操作落盘
      this.flushDrillDraft();
      this.stashPaperNav();
      let sess = null;
      if (this.paperCurrent) {
        this.setPaperActive(true);
        if (this.drillView !== "do") sess = await this.ensurePaperSession();
      }
      this.drillView = "do";
      window.scrollTo(0, 0);
      await this.openDrill(d);
      if (sess && sess.resumeBlocked) {
        await this.submitPaper(true, false, "非正常退出续做次数已用完，已自动交卷");
      }
    },

    // ---------- 每题草稿（学生自己的输入，不是默认内容） ----------
    _drillDraftKey(id) {
      const who = (this.user && this.user.name) || "?";
      return "lab_drill_draft:" + who + ":" + id;
    },
    loadDrillDraft(id) {
      try {
        const raw = localStorage.getItem(this._drillDraftKey(id));
        return raw ? JSON.parse(raw) : null;
      } catch (e) { return null; }
    },
    saveDrillDraft() {
      const d = this.drillCurrent;
      if (!d || !d.id) return;
      clearTimeout(this.drillDraftTimer);
      this.drillDraftTimer = setTimeout(() => this.writeDrillDraft(), 250);
    },
    writeDrillDraft() {
      const d = this.drillCurrent;
      if (!d || !d.id) return;
      clearTimeout(this.drillDraftTimer);
      try {
        const key = this._drillDraftKey(d.id);
        const data = { code: this.drillCode || "", pick: this.drillPick || "",
                       fill: this.drillFill || "",
                       multi: Array.isArray(this.drillMulti) ? this.drillMulti : [],
                       // 交过卷且内容没再改过：下次进来点返回不再重复提醒
                       submitted: !this.drillDirty };
        if (!data.code.trim() && !data.pick && !data.fill.trim() && !data.multi.length) {
          localStorage.removeItem(key);
        } else {
          localStorage.setItem(key, JSON.stringify(data));
        }
      } catch (e) { /* 隐私模式下 localStorage 可能不可用，忽略 */ }
    },
    flushDrillDraft() {
      this.writeDrillDraft();
    },
    // 当前题是否已经写了有效作答（空答案不提示离开）
    drillHasAnswer() {
      const d = this.drillCurrent;
      if (!d) return false;
      if (d.type === "sql" && this.navMode) {
        return !!(this.navLog.length || String(this.navLastQuery || "").trim());
      }
      if (d.type === "sql" || d.type === "python") return !!String(this.drillCode || "").trim();
      if (d.type === "fill") return !!String(this.drillFill || "").trim();
      if (d.type === "multiple") return Array.isArray(this.drillMulti) && this.drillMulti.length > 0;
      return !!this.drillPick;
    },
    markDrillDirty() {
      this.drillDirty = this.drillHasAnswer();
    },
    // 主工作台（MySQL / Python）退出前的防误触
    async confirmLeaveWorkspace() {
      if (this.view === "sql") {
        const sql = this.$refs.cmSqlRef ? this.$refs.cmSqlRef.getValue() : "";
        if (!sql.trim()) return true;
        return await this.askConfirm(
          "SQL 还没有处理",
          "MySQL 工作台里还有没运行的 SQL。退出后当前内容会留在浏览器草稿里，重新登录还能恢复。确定退出吗？",
          true, "退出登录", "留下继续");
      }
      if (this.view === "py" && this.pyDirty && this.pyDirty.size) {
        return await this.askConfirm(
          "Python 还有未保存的修改",
          "当前 Python 文件还有没保存的修改。确定退出登录吗？",
          true, "退出登录", "留下继续");
      }
      return true;
    },
    // 离开做题页前的防误触：整套卷子还没交卷先确认
    async confirmLeaveDrill(finalExit = true) {
      this._leavePrompted = false;
      if (this.view !== "drills") return true;
      const inPaperDo = this.drillView === "do" && this.drillCurrent && this.paperCurrent;
      const inPaperDetail = this.drillView === "paper" && this.paperCurrent;
      if (inPaperDo || inPaperDetail) {
        const activeAttempt = this.paperActive || this.paperHasSavedDrafts() ||
                              (inPaperDo && this.paperHasUnsubmitted());
        if (!this.paperAllowPause) {
          // 不允许中途退出
          if (!finalExit) {
            if (!activeAttempt) return true;
            this._leavePrompted = true;
            return await this.askConfirm(
              "返回试卷详情",
              "本次作答不会交卷，计时会继续。确定返回试卷详情吗？",
              false, "返回详情", "继续做题");
          }
          if (!activeAttempt) return true;
          if (this.paperOutOfTries) {
            // 次数已用完，无法再交卷；允许离开，避免把人困在页面里
            return true;
          }
          const has = this.paperHasSavedDrafts();
          this._leavePrompted = true;
          if (!await this.askConfirm(
              "本卷不允许中途退出",
              "离开会直接交卷" + (has ? "，已写的答案会一并提交" : "（本次还没写答案，将记 0 分）") +
              "。交卷后本次作答结束。确定交卷并离开吗？",
              true, "交卷并离开", "继续做题")) return false;
          return await this.submitPaper(true, true, "已交卷并离开");
        }
        // 允许中途退出：保存草稿 + 暂停计时
        if (!activeAttempt) return true;
        this._leavePrompted = true;
        return await this.askConfirm(
          "试卷还没有交卷",
          "离开后会保存草稿并暂停计时，回来可以继续作答。确定离开吗？",
          true, "离开", "继续做题");
      }
      // 错题本单题
      if (this.drillView === "do" && this.drillCurrent) {
        if (!this.drillDirty || !this.drillHasAnswer()) return true;
        this._leavePrompted = true;
        return await this.askConfirm(
          "题目还没有提交",
          "当前作答还没有交卷，离开后已写的内容会保留为草稿，但本次作答不会计入成绩。确定要离开吗？",
          true, "离开", "继续做题");
      }
      return true;
    },
    onBeforeUnload(e) {
      let dirty = false;
      if (this.view === "drills" && this.drillView === "do" && this.drillCurrent) {
        dirty = this.paperCurrent ? (this.paperActive || this.paperHasUnsubmitted())
                                  : (this.drillDirty && this.drillHasAnswer());
      } else if (this.view === "drills" && this.drillView === "paper" && this.paperCurrent) {
        dirty = this.paperActive || this.paperHasSavedDrafts();
      } else if (this.view === "sql") {
        const sql = this.$refs.cmSqlRef ? this.$refs.cmSqlRef.getValue() : "";
        dirty = !!sql.trim();
      } else if (this.view === "py") {
        dirty = !!(this.pyDirty && this.pyDirty.size);
      }
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
      return "";
    },
    // 题目自带的序号（"1. xxx"）在试卷里已经有编号，显示时去掉避免重复
    qTitle(t) {
      const s = String(t || "");
      return s.replace(/^\s*\d+\s*[.、．)）]\s*/, "") || s;
    },

    async loadDrills(autopick) {
      try {
        const path = this.drillCourse === "wrong"
          ? "/api/drills/wrong"
          : "/api/drills?course=" + encodeURIComponent(this.drillCourse);
        const [d, pr] = await Promise.all([
          this.api(path),
          this.api("/api/drills/progress"),
        ]);
        this.drillList = d.drills || [];
        this.drillProgress = pr.progress || {};
        if (this.drillCurrent) {
          const fresh = this.drillList.find(x => x.id === this.drillCurrent.id);
          if (fresh) { this.drillCurrent = Object.assign({}, this.drillCurrent, fresh); return; }
        }
        if (autopick !== false && this.drillList.length) await this.openDrill(this.drillList[0]);
      } catch (e) { this.toast(e.message); }
    },

    async openDrill(d) {
      // 快速连点不同题目时，只认最后一次请求，避免旧响应把新题覆盖掉
      const seq = ++this.drillOpenSeq;
      this.drillLoading = true;
      this.drillCurrent = null;
      this.drillBusy = false;
      this.drillResult = null;
      this.drillDirty = false;
      this.drillShowSetup = false;
      this.drillShowHint = false;
      this.drillRunLog = [];
      this.navLog = [];
      this.navLastQuery = "";
      this.drillSandbox = { db: "", tables: [], loading: false, error: "" };
      try {
        const det = await this.api(`/api/drills/${d.id}`);
        if (seq !== this.drillOpenSeq) return;
        this.drillCurrent = det;
        // SQL 题默认用 Navicat 图形界面；学生上次主动切到纯 SQL 就记住
        let pref = "nav";
        try { pref = localStorage.getItem("lab_drill_mode") || "nav"; } catch (e) {}
        this.navMode = det.type === "sql" && pref !== "sql";
        // 恢复这道题之前的 Navicat 操作（换题后仍能整卷交卷）
        if (det.type === "sql" && det.paperId) {
          const nav = this.paperNav[det.id];
          if (nav) {
            this.navLog = Array.isArray(nav.log) ? nav.log.slice() : [];
            this.navLastQuery = nav.query || "";
            if (nav.mode === "sql") this.navMode = false;
            else if (nav.mode === "nav" && pref !== "sql") this.navMode = true;
          }
        }
        this.drawer = "";
        // 恢复这道题上次写了一半的内容（按账号 + 题目分开存，换题不互相覆盖）
        const draft = this.loadDrillDraft(det.id) || {};
        this.drillCode = draft.code || "";
        this.drillPick = draft.pick || "";
        this.drillFill = draft.fill || "";
        this.drillMulti = Array.isArray(draft.multi) ? draft.multi : [];
        // 有内容且没交过卷：点返回/刷新时提醒；交过卷且没改过就不再打扰
        this.drillDirty = this.drillHasAnswer() && !draft.submitted;
        if (this.paperCurrent) this.syncPaperAnswers();
        if (det.type === "sql") {
          // 建/复用本题的沙箱库（初始化 SQL 已在里面跑好），侧栏显示它的表
          this.drillSandbox.loading = true;
          try {
            const sb = await this.api(`/api/drills/${det.id}/sandbox`,
                                      { method: "POST", body: { reset: false } });
            if (seq !== this.drillOpenSeq) return;
            this.drillSandbox = { db: sb.db, tables: sb.tables || [], loading: false, error: "" };
          } catch (e) {
            if (seq !== this.drillOpenSeq) return;
            this.drillSandbox = { db: "", tables: [], loading: false, error: e.message };
            this.toast(e.message);
          }
        }
        if (det.type === "sql" || det.type === "python") {
          this.$nextTick(() => {
            if (seq !== this.drillOpenSeq) return;
            if (this.$refs.cmDrillRef) {
              // 程序化回填不算学生修改，别把「已交卷」又标成未提交
              this._settingDrillCode = true;
              this.$refs.cmDrillRef.setValue(this.drillCode);
              this._settingDrillCode = false;
              this.$refs.cmDrillRef.refresh();
            }
          });
        }
      } catch (e) {
        if (seq === this.drillOpenSeq) this.toast(e.message);
      } finally {
        if (seq === this.drillOpenSeq) this.drillLoading = false;
      }
    },

    // 左侧沙箱库里的表 → 看数据/结构（和主页「点表名预览」一致）
    async openDrillTable(name) {
      const db = this.drillSandbox.db;
      if (!db) return;
      this.preview = { open: true, tab: "data", name, db, loading: true,
                       columns: [], rows: null, desc: null, descColumns: [], ddl: "", source: null };
      this.$refs.previewDlg.showModal();
      try {
        const rs = await this.sqlQuery(`SELECT * FROM \`${name}\` LIMIT 200`, db);
        this.preview.columns = rs.columns || [];
        this.preview.rows = rs.rows || [];
        this.preview.loading = false;
      } catch (e) {
        this.preview.loading = false;
        this.toast(e.message);
      }
    },

    async retryDrillSandbox() {
      if (!this.drillCurrent) return;
      this.drillSandbox = { db: "", tables: [], loading: true, error: "" };
      try {
        const sb = await this.api(`/api/drills/${this.drillCurrent.id}/sandbox`,
                                  { method: "POST", body: { reset: true } });
        this.drillSandbox = { db: sb.db, tables: sb.tables || [], loading: false, error: "" };
        if (this.$refs.navPanel) this.$refs.navPanel.reload();
        this.toast("题目数据库已重新准备好");
      } catch (e) {
        this.drillSandbox = { db: "", tables: [], loading: false, error: e.message };
        this.toast(e.message);
      }
    },
    async resetSandbox() {
      if (!this.drillCurrent) return;
      if (!await this.askConfirm("重置本题数据",
          "把这个题的数据库恢复到初始状态（你改过的数据会丢失），继续？", true)) return;
      try {
        const sb = await this.api(`/api/drills/${this.drillCurrent.id}/sandbox`,
                                  { method: "POST", body: { reset: true } });
        this.drillSandbox = { db: sb.db, tables: sb.tables || [], loading: false, error: "" };
        this.drillRunLog = [];
        // 图形界面的操作记录也要清掉，否则重放会把已还原的改动又算进去
        this.navLog = [];
        this.navLastQuery = "";
        if (this.$refs.navPanel) this.$refs.navPanel.reload();
        this.toast("已恢复到初始数据");
      } catch (e) { this.toast(e.message); }
    },

    async clearDrillCode() {
      if (this.drillHasAnswer() && !await this.askConfirm(
          "清空作答", "本题已经写的内容会被清空，确定吗？", true, "清空", "取消")) return;
      if (this.$refs.cmDrillRef) { this.$refs.cmDrillRef.setValue(""); this.$refs.cmDrillRef.focus(); }
      this.drillCode = "";
      this.drillDirty = false;
      this.saveDrillDraft();
      this.syncPaperAnswers();
    },

    onDrillCodeChange(v) {
      this.drillCode = v || "";
      if (this._settingDrillCode) return;
      this.markDrillDirty();
      this.saveDrillDraft();
      this.syncPaperAnswers();
    },

    onDrillFillInput(ev) {
      if (ev && ev.target) this.drillFill = String(ev.target.value || "").trim();
      this.markDrillDirty();
      this.saveDrillDraft();
      this.syncPaperAnswers();
    },

    pickDrillOption(key) {
      if (this.drillCurrent && this.drillCurrent.type === "multiple") {
        const i = this.drillMulti.indexOf(key);
        if (i >= 0) this.drillMulti.splice(i, 1); else this.drillMulti.push(key);
      } else {
        this.drillPick = key;
      }
      this.markDrillDirty();
      this.saveDrillDraft();
      this.syncPaperAnswers();
    },

    resetDrillCode() {
      if (!this.drillCurrent) return;
      if (this.$refs.cmDrillRef) this.$refs.cmDrillRef.setValue("");
      this.drillCode = "";
      this.drillFill = "";
      this.drillPick = "";
      this.drillMulti = [];
      this.drillResult = null;
      this.saveDrillDraft();
    },

    /* ---------- 出题中心：统一入口，先选类型 ---------- */
    openAuthorHub() {
      if (!this.user || !this.user.canPublish) { this.toast("还没有出题权限（找老师开通）"); return; }
      this.$refs.hubDlg.showModal();
    },
    closeAuthorHub() { this.$refs.hubDlg.close(); },
    /* ---------- 导入题目包 ---------- */
    openQpack() {
      if (!this.user || !this.user.canPublish) { this.toast("还没有出题权限（找老师开通）"); return; }
      this.qpack = null;
      this.qpackBusy = false;
      this.view = "qpack";
      window.scrollTo(0, 0);
    },
    exitQpack() {
      this.view = "drills";
      this.qpack = null;
      this.drillView = "list";
      this.loadPapers();
    },
    resetQpack() { this.qpack = null; },

    async onQpackPicked(ev) {
      const files = Array.from(ev.target.files || []);
      ev.target.value = "";
      if (files.length) await this.uploadQpack(files);
    },
    async onQpackDrop(ev) {
      this.qpackDrag = false;
      const files = Array.from((ev.dataTransfer && ev.dataTransfer.files) || []);
      if (files.length) await this.uploadQpack(files);
    },
    async uploadQpack(files) {
      const zips = files.filter((f) => /\.zip$/i.test(f.name));
      if (!zips.length) {
        this.toast("请先把题干、答案、数据脚本打成一个 .zip 再上传");
        return;
      }
      if (zips.length > 1) {
        this.toast("一次只能导入一份试卷，请只上传一个 zip");
        return;
      }
      const z = zips[0];
      if (z.size > 40 * 1024 * 1024) {
        this.toast("压缩包超过 40MB，请精简数据库导出后再试");
        return;
      }
      this.qpackBusy = true;
      try {
        const form = new FormData();
        form.append("files", z);
        const d = await this.api("/api/author/qpack/parse", { method: "POST", form });
        this.qpack = d;
        if (!d.stats.withAnswer) {
          this.toast("没有匹配到参考答案，请检查答案文件（题号分隔要用 -- 1 / ---8）");
        } else {
          this.toast(`解析出 ${d.stats.total} 道题，其中 ${d.stats.withAnswer} 道有答案`);
        }
      } catch (e) { this.toast(e.message); }
      finally { this.qpackBusy = false; }
    },

    async createQpackQuestions() {
      if (!this.qpack) return;
      const judge = {};
      for (const q of this.qpack.questions) {
        if (q.hasAnswer) judge[String(q.no)] = q.judgeMode;
      }
      if (!await this.askConfirm("创建题目",
        `将创建 ${this.qpack.stats.withAnswer} 道练习题并直接发布，学生马上能做题。继续？`)) return;
      this.qpackBusy = true;
      try {
        const r = await this.api("/api/author/qpack/create", { method: "POST",
          body: { package: this.qpack, publish: true, judge } });
        const dup = (r.duplicates || []).length;
        const warns = r.warnings || [];
        if (warns.length) {
          await this.askConfirm(
            "创建完成，有提醒",
            warns.slice(0, 4).join("；") + (warns.length > 4 ? "…" : ""),
            false, "知道了", "关闭");
        }
        this.toast(dup
          ? `已创建 ${r.created.length} 道题，跳过 ${dup} 道重复题`
          : `已创建 ${r.created.length} 道题并发布`);
        this.qpack = null;
        this.view = "drills";
        this.drillCourse = "sql";
        this.drillView = "list";
        await this.loadPapers();
      } catch (e) { this.toast(e.message); }
      finally { this.qpackBusy = false; }
    },

    async pickAuthor(kind) {
      this.$refs.hubDlg.close();
      if (kind === "qpack") { this.openQpack(); return; }
      if (kind === "drill") this.openDrillEditor();
      else { await this.switchView("community"); this.qTab = "drafts"; this.openQuestionEditor(); }
    },
    typeLabelOf(t) {
      const x = this.drillTypes.find(v => v.value === t);
      return x ? x.label : t;
    },
    fillDrillExample() {
      const t = this.dq.type;
      const set = (o) => { Object.assign(this.dq, o); this.authorDirty = true; };
      if (t === "sql") {
        set({
          title: "查询工资最高的 5 名员工",
          stem: "从 emp 表查出工资最高的 5 名员工，返回工号、姓名和工资，按工资从高到低排序。",
          setupSql: "CREATE TABLE emp (\n  EMPNO INT PRIMARY KEY,\n  ENAME VARCHAR(20),\n  JOB VARCHAR(20),\n  SAL DOUBLE,\n  DEPTNO INT\n);\nINSERT INTO emp VALUES\n  (7369,'SMITH','CLERK',800,20),\n  (7499,'ALLEN','SALESMAN',1600,30),\n  (7566,'JONES','MANAGER',2975,20),\n  (7698,'BLAKE','MANAGER',2850,30),\n  (7782,'CLARK','MANAGER',2450,10),\n  (7839,'KING','PRESIDENT',5000,10),\n  (7876,'ADAMS','CLERK',1100,20),\n  (7902,'FORD','ANALYST',3000,20),\n  (7934,'MILLER','CLERK',1300,10);\n",
          verifySql: "SELECT EMPNO, ENAME, SAL FROM emp ORDER BY SAL DESC LIMIT 5",
          trySql: "SELECT EMPNO, ENAME, SAL FROM emp ORDER BY SAL DESC LIMIT 5",
          hint: "用 ORDER BY ... DESC 排序，再用 LIMIT 限制条数。",
        });
        this.toast("已填入完整示例，可直接点右侧「跑一遍」检查");
      } else if (t === "python") {
        if (this.dq.judgeMode === "tests") {
          set({
            title: "两数求和（多组测试）",
            stem: "读入两个整数，输出它们的和。",
            cases: [
              { input: "1\n2", expected: "3" },
              { input: "10\n5", expected: "15" },
            ],
            tryCode: "a = int(input())\nb = int(input())\nprint(a + b)\n",
            hint: "input() 读到的是字符串，记得转成 int。",
          });
        } else {
          set({
            title: "计算平均分",
            stem: "已知三个分数 88、95、92，输出它们的平均分，保留两位小数。",
            inputData: "",
            expectedOutput: "91.67",
            tryCode: "scores = [88, 95, 92]\nprint(f'{sum(scores)/len(scores):.2f}')\n",
            hint: "sum() 求和、len() 求个数，f-string 保留两位小数。",
          });
        }
        this.toast("已填入完整示例，可直接点右侧「运行」检查");
      } else if (t === "fill") {
        set({
          title: "主键关键字",
          stem: "建表时声明主键用 ______ 关键字。",
          fillAnswers: "PRIMARY KEY\nprimary key",
          hint: "两个单词，中间一个空格。",
        });
        this.toast("已填入示例");
      } else if (t === "multiple") {
        set({
          title: "以下哪些是 SQL 关键字？",
          stem: "选出所有属于 SQL 的关键字。",
          optionsText: "A. SELECT\nB. print\nC. WHERE\nD. def\n",
          multiKeys: ["A", "C"],
          hint: "print 和 def 是 Python 的。",
        });
        this.toast("已填入示例");
      } else if (t === "boolean") {
        set({
          title: "判断题：SELECT 用于查询数据",
          stem: "在 SQL 中，SELECT 语句用于查询数据。",
          optionsText: "A. 正确\nB. 错误\n",
          rightKey: "A",
          hint: "",
        });
        this.toast("已填入示例");
      } else {
        set({
          title: "SQL 查询关键字",
          stem: "要从表里查出数据，SQL 用哪个关键字开头？",
          optionsText: "A. SELECT\nB. INSERT\nC. UPDATE\n",
          rightKey: "A",
          hint: "查询用 SELECT。",
        });
        this.toast("已填入示例");
      }
    },

    exitAuthor() {
      this.view = "drills";
      this.authorDirty = false;
      this.drillView = "list";
      this.loadPapers();
    },
    pickDrillType(t) {
      this.dq.type = t;
      this.dq.course = t === "sql" ? "sql" : (t === "python" ? "python" : "basic");
      this.dq.judgeMode = (this.judgeModes[t] || [{ value: "" }])[0].value;
      this.dq.typeLabel = this.typeLabelOf(t);
      if (t === "multiple" && !Array.isArray(this.dq.multiKeys)) this.dq.multiKeys = [];
      if (!Array.isArray(this.dq.cases)) this.dq.cases = [];
      this.authorDirty = true;
    },
    toggleMultiKey(k) {
      const i = this.dq.multiKeys.indexOf(k);
      if (i >= 0) this.dq.multiKeys.splice(i, 1); else this.dq.multiKeys.push(k);
      this.authorDirty = true;
    },

    /* ---------- 出题 ---------- */
    openDrillEditor(d) {
      if (!this.user || !this.user.canPublish) { this.toast("还没有出题权限（找老师开通）"); return; }
      const modes = this.judgeModes;
      this.tryResult = null;
      if (d && d.id) {
        let cases = [];
        try { cases = JSON.parse(d.testCases || "[]") || []; } catch (e) { cases = []; }
        let ans = {};
        try { ans = typeof d.answer === "object" && d.answer ? d.answer : JSON.parse(d.answerJson || "{}"); }
        catch (e) { ans = {}; }
        this.dq = {
          id: d.id, course: d.course, type: d.type, typeLabel: this.typeLabelOf(d.type),
          title: d.title || "", stem: d.stem || "", hint: d.hint || "",
          setupSql: d.setupSql || "", verifySql: d.verifySql || "",
          starterCode: d.starterCode || "", inputData: d.inputData || "",
          expectedOutput: d.expectedOutput || "",
          optionsText: (d.options || []).map(o => o.key + ". " + o.text).join("\n"),
          rightKey: (ans.key || ""), multiKeys: ans.keys || [],
          fillAnswers: (ans.values || []).join("\n"),
          status: d.status,
          judgeMode: d.judgeMode || ((modes[d.type] || [{}])[0].value || ""),
          cases,
          trySql: d.verifySql || "",
          tryCode: d.starterCode || "",
          paper: "",
          score: d.score || 10,
        };
      } else {
        this.dq = {
          id: 0, course: "sql", type: "sql", typeLabel: "SQL 题",
          title: "", stem: "", hint: "", setupSql: "", verifySql: "",
          starterCode: "", inputData: "", expectedOutput: "",
          optionsText: "", rightKey: "", multiKeys: [], fillAnswers: "", status: 1,
          judgeMode: "result", cases: [{ input: "", expected: "" }],
          trySql: "", tryCode: "",
          paper: "", score: 10,
        };
      }
      this.authorDirty = false;
      this.view = "author";
      window.scrollTo(0, 0);
    },
    closeDrillEditor() { this.view = "drills"; },

    _drillPayload(publish) {
      const d = this.dq;
      const body = {
        id: d.id, course: d.course, type: d.type, title: d.title, stem: d.stem,
        hint: d.hint, setupSql: d.setupSql, verifySql: d.verifySql,
        starterCode: d.starterCode, inputData: d.inputData,
        expectedOutput: d.expectedOutput, options: [], answer: {}, publish,
        judgeMode: d.judgeMode, paper: d.paper || "", score: d.score || 10,
        testCases: d.type === "python" && d.judgeMode === "tests"
          ? JSON.stringify((d.cases || []).filter(c => (c.input || "").trim() !== ""
                                                     || (c.expected || "").trim() !== ""))
          : "",
      };
      if (["single", "multiple", "boolean"].includes(d.type)) {
        body.options = String(d.optionsText || "").split("\n")
          .map(l => l.trim()).filter(Boolean)
          .map(l => {
            const m = /^([A-Za-z0-9])\s*[.、)]\s*(.*)$/.exec(l);
            return m ? { key: m[1].toUpperCase(), text: m[2] } : { key: l.slice(0, 1).toUpperCase(), text: l };
          });
        body.answer = d.type === "multiple"
          ? { keys: (d.multiKeys || []).map(k => String(k).toUpperCase()) }
          : { key: (d.rightKey || "").trim().toUpperCase() };
      } else if (d.type === "fill") {
        body.answer = {
          values: String(d.fillAnswers || "").split(/[\n；;]/)
            .map(s => s.trim()).filter(Boolean),
        };
      } else if (d.type === "sql" && d.judgeMode === "state") {
        // 改数据题：期望值可写在「参考答案」里（这里复用 fillAnswers 输入框）
        const vals = String(d.fillAnswers || "").split(/[\n,，]/)
          .map(s => s.trim()).filter(Boolean);
        if (vals.length) body.answer = { values: vals };
      }
      return body;
    },

    async saveDrill(publish) {
      this.dqBusy = true;
      try {
        const r = await this.api("/api/drills", { method: "POST", body: this._drillPayload(publish) });
        this.dq.id = r.id;
        this.authorDirty = false;
        this.toast(publish ? "题目已发布，学生现在能做了" : "已保存草稿");
        this.drillCourse = this.dq.course === "basic" ? "basic" : this.dq.course;
        this.drillView = "list";
        await this.loadPapers();
        return r;
      } catch (e) { this.toast(e.message); }
      finally { this.dqBusy = false; }
    },

    async importSetupFile(ev) {
      const f = (ev.target.files || [])[0];
      ev.target.value = "";
      if (!f) return;
      this.dqBusy = true;
      try {
        const form = new FormData();
        form.append("file", f);
        const r = await this.api("/api/author/setup_from_file", { method: "POST", form });
        this.dq.setupSql = r.sql || "";
        this.dq.trySql = (r.tables && r.tables[0]) ? ("SELECT * FROM `" + r.tables[0] + "` LIMIT 20") : "";
        this.authorDirty = true;
        this.toast(r.rows ? `已生成 ${r.tables.join("、")}（${r.rows} 行）` : `已导入 ${r.tables.join("、") || "SQL 脚本"}`);
        if (r.tables && r.tables.length === 1 && !this.dq.verifySql) {
          this.dq.verifySql = `SELECT * FROM \`${r.tables[0]}\``;
        }
      } catch (e) { this.toast(e.message); }
      finally { this.dqBusy = false; }
    },

    async importSetupDb() {
      if (!this.dq.importDb) { this.toast("先选一个数据库"); return; }
      this.dqBusy = true;
      try {
        const r = await this.api("/api/author/setup_from_db", { method: "POST",
          body: { db: this.dq.importDb } });
        this.dq.setupSql = r.sql || "";
        this.dq.trySql = (r.tables && r.tables[0]) ? ("SELECT * FROM `" + r.tables[0] + "` LIMIT 20") : "";
        this.authorDirty = true;
        this.toast(`已从 ${r.db} 生成初始化 SQL（${(r.tables || []).length} 张表）`);
      } catch (e) { this.toast(e.message); }
      finally { this.dqBusy = false; }
    },

    async tryRunAuthor() {
      if (this.dq.type === "sql") {
        this.dqBusy = true;
        try {
          this.tryResult = await this.api("/api/author/try_sql", { method: "POST",
            body: { setup: this.dq.setupSql, sql: this.dq.trySql || this.dq.verifySql } });
        } catch (e) { this.toast(e.message); }
        finally { this.dqBusy = false; }
      } else if (this.dq.type === "python") {
        this.dqBusy = true;
        try {
          const stdin = this.dq.judgeMode === "tests"
            ? ((this.dq.cases[0] || {}).input || "")
            : (this.dq.inputData || "");
          const r = await this.api("/api/author/try_python", { method: "POST",
            body: { code: this.dq.tryCode || this.dq.starterCode, stdin } });
          this.tryResult = r;
        } catch (e) { this.toast(e.message); }
        finally { this.dqBusy = false; }
      }
    },
    trySelectAll() {
      this.dq.trySql = "SELECT * FROM ";
      this.toast("在右侧补齐表名，或点上方表名自动查询");
    },
    tryRunVerify() { this.dq.trySql = this.dq.verifySql || ""; this.tryRunAuthor(); },

    async publishDrill(on) {
      try {
        await this.api(`/api/drills/${this.dq.id}/publish`, { method: "POST", body: { publish: on } });
        this.toast(on ? "已发布" : "已撤回为草稿");
        await this.loadPapers();
      } catch (e) { this.toast(e.message); }
    },

    // 只运行不判分（和主页一样，结果进控制台）
    // 把本题的标准输入整段喂给沙箱里的程序，input() 就能直接读到
    async feedPyInput(job, text) {
      if (!job || !text) return;
      try {
        await this.api("/api/pyrun/input", { method: "POST", body: { job, text } });
      } catch (e) { /* 程序可能已结束，不影响判分 */ }
    },

    async runDrillOnly() {
      const d = this.drillCurrent;
      if (!d) return;
      const code = this.drillCode;
      if (!code.trim()) { this.toast("先写点内容再运行"); return; }
      if (d.type === "sql" && !this.drillSandbox.db) {
        this.toast("本题数据库还在准备中，请稍候再运行");
        return;
      }
      this.drillBusy = true;
      try {
        if (d.type === "sql") {
          try {
            const run = await this.api("/api/sql", { method: "POST",
              body: { sql: code, db: this.drillSandbox.db || "" } });
            this.drillRunLog.push({ code, results: run.results || [] });
          } catch (e) {
            this.drillRunLog.push({ code, results: [{ type: "error", index: 1, msg: e.message }] });
          }
        } else if (d.type === "python") {
          const entry = { code, out: "", err: "", dur: "", meta: "" };
          this.drillRunLog.push(entry);
          try {
            const st = await this.api("/api/pyrun/start", { method: "POST",
              body: { code, filename: "", db: this.selectedDb } });
            await this.feedPyInput(st.job, d.inputData);
            const t0 = Date.now();
            let cur = {};
            for (let i = 0; i < 60; i++) {
              await new Promise(r => setTimeout(r, 500));
              cur = await this.api(`/api/pyrun/status/${encodeURIComponent(st.job)}`);
              entry.out = cur.out || "";
              entry.err = cur.err || "";
              this.scrollConsole("drillConsoleEl");
              if (!cur.running) break;
            }
            entry.dur = ((Date.now() - t0) / 1000).toFixed(2);
            if (cur.why === "idle") entry.meta = "等待输入超时，已结束";
            else if (cur.why === "max") entry.meta = "超过运行上限，已结束";
            else if (cur.exit && cur.exit !== 0) entry.meta = "退出码 " + cur.exit;
          } catch (e) { entry.meta = e.message; }
        }
        this.scrollConsole("drillConsoleEl");
      } finally { this.drillBusy = false; }
    },

    async submitDrill() {
      const d = this.drillCurrent;
      if (!d || this.drillBusy) return;
      if (this.paperOutOfTries) {
        this.toast("本套试卷的交卷次数已经用完");
        return;
      }
      let answer = "";
      if (d.type === "sql" && this.navMode) {
        // Navicat 模式：查询题交「最后一次运行的 SELECT」，
        // 建表/改数据/建对象题交图形操作翻译出来的 SQL（判分时在干净库里重放）
        const mode = d.judgeMode || "result";
        const queryModes = ["result", "result_ordered", "rows_only", "cell", "contains"];
        if (queryModes.includes(mode)) {
          answer = this.navLastQuery ||
            (this.$refs.navPanel && this.$refs.navPanel.lastQuerySql) || "";
          if (!answer.trim()) {
            this.toast("先在「查询」页写一条查询并点「运行」，再提交");
            return;
          }
        } else {
          answer = this.navLog.join(";\n");
          if (answer.trim()) answer += ";";
          if (!answer.trim()) {
            this.toast("还没有做任何修改：可以新建表、改数据或建视图/函数/触发器");
            return;
          }
        }
      } else if (d.type === "sql" || d.type === "python") {
        answer = this.drillCode;
        if (!answer.trim()) { this.toast("先写点内容再提交"); return; }
      } else if (d.type === "fill") {
        answer = this.drillFill;
        if (!answer.trim()) { this.toast("先填写答案"); return; }
      } else if (d.type === "multiple") {
        answer = this.drillMulti.slice();
        if (!answer.length) { this.toast("先选出至少一个选项"); return; }
      } else {
        answer = this.drillPick;
        if (!answer) { this.toast("先选择一个选项"); return; }
      }
      this.drillBusy = true;
      // 交卷防误触：先把检查提示摆出来，确认后才真正判分
      const again = d.passed ? "本题之前已经通过，重新交卷不会降低已有成绩。" : "";
      if (!await this.askConfirm(
          "确认交卷",
          "请检查好再交卷。提交后会立即判分并记录本次作答。" + again,
          false, "确认交卷", "再检查一下")) {
        this.drillBusy = false;
        return;
      }
      this.drillResult = null;
      try {
        // 1) 先像主页一样真跑一遍，把过程留在控制台（SQL 跑在本题沙箱库，Python 走沙箱）
        if (d.type === "sql" && this.drillSandbox.db && !this.navMode) {
          try {
            const run = await this.api("/api/sql", { method: "POST",
              body: { sql: answer, db: this.drillSandbox.db } });
            this.drillRunLog.push({ code: answer, results: run.results || [] });
          } catch (e) {
            this.drillRunLog.push({ code: answer,
              results: [{ type: "error", index: 1, msg: e.message }] });
          }
        } else if (d.type === "python") {
          const entry = { code: answer, out: "", err: "", dur: "", meta: "" };
          this.drillRunLog.push(entry);
          try {
            const st = await this.api("/api/pyrun/start", { method: "POST",
              body: { code: answer, filename: "", db: this.selectedDb } });
            await this.feedPyInput(st.job, d.inputData);
            const t0 = Date.now();
            let cur = {};
            for (let i = 0; i < 60; i++) {
              await new Promise(r => setTimeout(r, 500));
              cur = await this.api(`/api/pyrun/status/${encodeURIComponent(st.job)}`);
              entry.out = cur.out || "";
              entry.err = cur.err || "";
              this.scrollConsole("drillConsoleEl");
              if (!cur.running) break;
            }
            entry.dur = ((Date.now() - t0) / 1000).toFixed(2);
            if (cur.why === "idle") entry.meta = "等待输入超时，已结束";
            else if (cur.why === "max") entry.meta = "超过运行上限，已结束";
            else if (cur.exit && cur.exit !== 0) entry.meta = "退出码 " + cur.exit;
          } catch (e) {
            entry.meta = e.message;
          }
        }
        this.scrollConsole("drillConsoleEl");
        // 2) 再交给服务端判分
        const r = await this.api(`/api/drills/${d.id}/submit`, {
          method: "POST", body: { answer_text: answer },
        });
        this.drillResult = r;
        // 交卷完成：内容已计入成绩，返回/刷新不再重复提醒
        this.drillDirty = false;
        this.flushDrillDraft();
        this.scrollConsole("drillConsoleEl");
        const got = r.score != null ? `本题 ${r.score}/${r.maxScore} 分` : "";
        const tot = r.paper ? ` · 本套 ${r.paper.myScore}/${r.paper.totalScore} 分` : "";
        this.toast(r.passed ? `通过！${got}${tot}` : (r.reason || "没通过，再想想"));
        await this.loadDrills(false);
        this.refreshPaper();
        const fresh = this.drillList.find(x => x.id === d.id);
        if (fresh) this.drillCurrent = Object.assign({}, this.drillCurrent, fresh);
      } catch (e) { this.toast(e.message); }
      finally { this.drillBusy = false; }
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
      if (this.pyCurrent) this.pyDirty.add(this.pyCurrent);
      // 每次输入都自动保存（250ms 微合并，连打字也不会丢最后一次）
      clearTimeout(this.pySaveTimer);
      const name = this.pyCurrent;
      const pid = this.pyProjectId;
      const content = this.$refs.cmPyRef ? this.$refs.cmPyRef.getValue() : null;
      if (!name || content === null) return;
      this.pySaveTimer = setTimeout(async () => {
        try {
          await this.api(`/api/pyfiles/${encodeURIComponent(name)}?projectId=${pid}`,
                         { method: "PUT", body: { content } });
          this.pyDirty.delete(name);
        } catch (e) {}
      }, 250);
    },

    clearSql() { this.$refs.cmSqlRef.setValue(""); this.$refs.cmSqlRef.focus(); },
    clearPy() {
      this.$refs.cmPyRef.setValue("");
      this.$refs.cmPyRef.focus();
    },

    /* ---------- 自制弹窗（替代原生 prompt/confirm，内嵌浏览器兼容） ---------- */
    focusEl(el) {
      if (!el) return;
      try { el.focus({ preventScroll: true }); } catch (e) { try { el.focus(); } catch (e2) {} }
      // 内嵌浏览器里"点开弹窗立即聚焦"可能被吞，补一次延时聚焦
      setTimeout(() => { try { el.focus({ preventScroll: true }); } catch (e) {} }, 80);
    },
    askText(title, label, def) {
      return new Promise(resolve => {
        this.ask = { open: true, title, label, value: def || "", _resolve: resolve };
        // 原生 dialog → 进浏览器 top layer，后打开的窗自然叠在已有弹窗之上
        const d = this.$refs.askDlg;
        if (d && !d.open) { try { d.showModal(); } catch (e) { d.setAttribute("open", ""); } }
        this.$nextTick(() => {
          const el = this.$refs.askInputEl;
          if (el) { this.focusEl(el); try { el.select(); } catch (e) {} }
        });
      });
    },
    _closeAsk() {
      const d = this.$refs.askDlg;
      if (d && d.open) d.close();
    },
    askOk() {
      const r = this.ask._resolve;
      this.ask.open = false;
      this._closeAsk();
      if (r) r(this.ask.value.trim());
    },
    askCancel() {
      const r = this.ask._resolve;
      this.ask.open = false;
      this._closeAsk();
      if (r) r(null);
    },
    askConfirm(title, text, danger, okText, cancelText) {
      return new Promise(resolve => {
        this.confirmBox = { open: true, title, text, danger: !!danger,
                            okText: okText || "", cancelText: cancelText || "",
                            _resolve: resolve };
        const d = this.$refs.confirmDlg;
        if (d && !d.open) { try { d.showModal(); } catch (e) { d.setAttribute("open", ""); } }
      });
    },
    _closeConfirm() {
      const d = this.$refs.confirmDlg;
      if (d && d.open) d.close();
    },
    confirmOk() {
      const r = this.confirmBox._resolve;
      this.confirmBox.open = false;
      this._closeConfirm();
      if (r) r(true);
    },
    confirmCancel() {
      const r = this.confirmBox._resolve;
      this.confirmBox.open = false;
      this._closeConfirm();
      if (r) r(false);
    },

    /* ---------- Python 多项目 / 多文件 ---------- */
    pyProjectKey() {
      const who = (this.user && this.user.name) || "?";
      return "lab_py_project:" + who;
    },
    pyUrl(name) {
      const base = "/api/pyfiles" + (name ? "/" + encodeURIComponent(name) : "");
      return base + "?projectId=" + (this.pyProjectId || 0);
    },
    async loadPyProjects() {
      const d = await this.api("/api/pyprojects");
      this.pyProjects = d.projects || [];
      if (!this.pyProjects.some(p => p.id === this.pyProjectId)) {
        this.pyProjectId = this.pyProjects[0] ? this.pyProjects[0].id : 0;
      }
      return this.pyProjects;
    },
    async initPyFiles() {
      await this.$nextTick();
      try {
        await this.loadPyProjects();
        let pid = 0;
        try { pid = parseInt(localStorage.getItem(this.pyProjectKey()) || "0", 10) || 0; } catch (e) {}
        if (!this.pyProjects.some(p => p.id === pid)) {
          pid = this.pyProjects[0] ? this.pyProjects[0].id : 0;
        }
        // 旧版草稿：默认项目的 main.py 还是空的时候恢复一次
        const draft = localStorage.getItem("lab_py_draft");
        if (draft && pid) {
          this.pyProjectId = pid;
          try {
            const main = await this.api(this.pyUrl("main.py"));
            if (!String(main.content || "").trim()) {
              await this.api(this.pyUrl("main.py"), { method: "PUT", body: { content: draft } });
            }
            localStorage.removeItem("lab_py_draft");
          } catch (e) {}
        }
        await this.switchPyProject(pid, true);
      } catch (e) { /* 列表加载失败时编辑器仍可用 */ }
    },
    async switchPyProject(pid, initial = false) {
      if (!pid) return;
      if (!initial && pid === this.pyProjectId) return;
      if (!initial && this.pyCurrent) {
        if (!await this.ensurePySaved(this.pyCurrent)) return;
      }
      this.pyProjectId = pid;
      this.pyProjectCollapsed = false;
      try { localStorage.setItem(this.pyProjectKey(), String(pid)); } catch (e) {}
      this.pyOpenFiles = [];
      this.pyCurrent = "";
      this.pyFiles = [];
      this.pyDirty.clear();
      if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
      try {
        const d = await this.api(this.pyUrl());
        this.pyFiles = d.files || [];
        const f = this.pyFiles[0];
        if (f) await this.openPyFile(f.name);
        this.$nextTick(() => { if (this.$refs.cmPyRef) this.$refs.cmPyRef.refresh(); });
      } catch (e) { this.toast(e.message); }
      this.loadPyProjects().catch(() => {});
    },
    async togglePyProject(pj) {
      if (!pj) return;
      if (pj.id !== this.pyProjectId) {
        await this.switchPyProject(pj.id);
        return;
      }
      this.pyProjectCollapsed = !this.pyProjectCollapsed;
    },
    async newPyProject() {
      if (this.pyProjects.length >= 10) { this.toast("最多创建 10 个项目"); return; }
      const name = await this.askText("新建 Python 项目", "项目名称（最多 24 个字）", "");
      if (name === null) return;
      if (!String(name).trim()) return;
      try {
        const p = await this.api("/api/pyprojects", { method: "POST", body: { name } });
        await this.loadPyProjects();
        await this.switchPyProject(p.id);
        this.toast(`已创建项目「${p.name}」`);
      } catch (e) { this.toast(e.message); }
    },
    async renamePyProject(pj) {
      if (!pj) return;
      const name = await this.askText("重命名项目", "项目名称（最多 24 个字）", pj.name);
      if (name === null) return;
      const nm = String(name || "").trim();
      if (!nm || nm === pj.name) return;
      try {
        await this.api(`/api/pyprojects/${pj.id}/rename`, { method: "POST", body: { name: nm } });
        await this.loadPyProjects();
        this.toast("项目已改名");
      } catch (e) { this.toast(e.message); }
    },
    async deletePyProject(pj) {
      if (!pj) return;
      if (!await this.askConfirm("删除项目",
          `将删除「${pj.name}」及其中 ${pj.fileCount} 个 Python 文件，无法恢复。确定吗？`, true)) return;
      try {
        await this.api(`/api/pyprojects/${pj.id}`, { method: "DELETE" });
        if (this.pyProjectId === pj.id) {
          this.pyProjectId = 0;
          this.pyCurrent = "";
          this.pyOpenFiles = [];
          this.pyFiles = [];
          if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
        }
        await this.loadPyProjects();
        const next = this.pyProjects.find(p => p.id === this.pyProjectId) || this.pyProjects[0];
        if (next) await this.switchPyProject(next.id);
        this.toast("项目已删除");
      } catch (e) { this.toast(e.message); }
    },
    async refreshPyList() {
      try {
        const d = await this.api(this.pyUrl());
        this.pyFiles = d.files || [];
      } catch (e) {}
    },
    async flushPySave() {
      if (this.pySaveTimer) { clearTimeout(this.pySaveTimer); this.pySaveTimer = null; }
      const name = this.pyCurrent;
      const content = this.$refs.cmPyRef ? this.$refs.cmPyRef.getValue() : null;
      if (content === null || !name) return;
      await this.api(this.pyUrl(name), { method: "PUT", body: { content } });
      this.pyDirty.delete(name);
    },
    // 切走前把当前文件落盘；保存失败才留在原文件（平时每次输入都已自动保存）
    async ensurePySaved(name) {
      try { await this.flushPySave(); return true; }
      catch (e) { this.toast(e.message); return false; }
    },
    // 编辑器上方的小胶囊提示（如「已切换到 b.py」），1.6 秒自动消失
    showPyCapsule(text) {
      this.pyCapsule = text;
      clearTimeout(this.pyCapsuleTimer);
      this.$nextTick(() => {
        const el = document.querySelector(".py-capsule");
        if (el) { this._popShow(el); el.classList.add("show"); }
      });
      this.pyCapsuleTimer = setTimeout(() => {
        this.pyCapsule = "";
        const el = document.querySelector(".py-capsule");
        if (el) { el.classList.remove("show"); this._popHide(el); }
      }, 1600);
    },
    async openPyFile(name) {
      if (name === this.pyCurrent) return;
      if (!await this.ensurePySaved(this.pyCurrent)) return;
      try {
        const f = await this.api(this.pyUrl(name));
        this.pyCurrent = f.name;
        if (!this.pyOpenFiles.includes(f.name)) this.pyOpenFiles.push(f.name);
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
        this.showPyCapsule("已切换到 " + f.name);
      } catch (e) { this.toast(e.message); }
    },
    async closePyTab(name) {
      const index = this.pyOpenFiles.indexOf(name);
      if (index < 0) return;
      if (name === this.pyCurrent) {
        if (!await this.ensurePySaved(name)) return;
      }
      this.pyOpenFiles = this.pyOpenFiles.filter(f => f !== name);
      if (name !== this.pyCurrent) return;
      this.pyCurrent = "";
      if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
      if (this.pyOpenFiles.length) {
        const next = this.pyOpenFiles[Math.min(index, this.pyOpenFiles.length - 1)];
        await this.openPyFile(next);
      }
    },
    async uploadPyFiles(ev) {
      const files = Array.from(ev.target.files || []);
      ev.target.value = "";
      if (!files.length) return;
      if (files.some(f => !f.name.toLowerCase().endsWith(".py"))) {
        this.toast("只能上传 .py 文件");
        return;
      }
      this.busy = true;
      try {
        await this.flushPySave();
        const form = new FormData();
        for (const file of files) form.append("files", file);
        form.append("projectId", String(this.pyProjectId || 0));
        const result = await this.api("/api/pyfiles/upload", { method: "POST", form });
        await this.refreshPyList();
        await this.loadPyProjects().catch(() => {});
        this.pyOpenFiles = Array.from(new Set([...this.pyOpenFiles, ...result.files.map(f => f.name)]));
        const last = result.files[result.files.length - 1];
        if (last) await this.openPyFile(last.name);
        this.toast(`已上传 ${result.files.length} 个 Python 文件`);
      } catch (e) { this.toast(e.message); }
      finally { this.busy = false; }
    },
    async newPyFile() {
      if (!this.pyProjectId) { this.toast("先创建一个项目"); return; }
      const name = await this.askText("新建 Python 文件", "文件名（可省略 .py 后缀）", "");
      if (!name) return;
      const final = name.toLowerCase().endsWith(".py") ? name : name + ".py";
      this.busy = true;
      try {
        await this.flushPySave();
        let exists = true;
        try {
          await this.api(this.pyUrl(final));
        } catch (e) {
          if (e.status !== 404) throw e;
          exists = false;
        }
        if (exists) {
          this.toast("文件已存在，已为你打开");
          await this.openPyFile(final);
          return;
        }
        await this.api(this.pyUrl(final), { method: "PUT", body: { content: "" } });
        await this.refreshPyList();
        await this.loadPyProjects().catch(() => {});
        if (!this.pyOpenFiles.includes(final)) this.pyOpenFiles.push(final);
        this.pyCurrent = final;
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
        this.toast(`已创建 ${final}`);
      } catch (e) { this.toast(e.message); }
      finally { this.busy = false; }
    },
    async deletePyFile(name) {
      // 临时文件（上传的）删除不需要确认，本来刷新就没了
      const isTemp = (this.pyFiles.find(f => f.name === name) || {}).uploaded;
      if (!isTemp && !await this.askConfirm("删除文件", `确定删除文件「${name}」？`, true)) return;
      try {
        if (this.pyCurrent === name && this.pySaveTimer) {
          clearTimeout(this.pySaveTimer);
          this.pySaveTimer = null;
        }
        this.pyDirty.delete(name);
        await this.api(this.pyUrl(name), { method: "DELETE" });
        await this.refreshPyList();
        await this.loadPyProjects().catch(() => {});
        this.pyOpenFiles = this.pyOpenFiles.filter(f => f !== name);
        if (this.pyCurrent === name) {
          this.pyCurrent = "";
          if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue("");
          const next = this.pyFiles[0];
          if (next) await this.openPyFile(next.name);
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
      const name = await this.askText("新建数据库", "名称（字母/数字/下划线）", "");
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
      if (!await this.askConfirm("删除数据库", `确定删除数据库「${d.name}」？里面所有表和数据都会删除，不可恢复！`, true)) return;
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
        this.toast("私有分享链接已生成，复制发给同学（不会出现在题库）");
      } catch (e) { this.toast(e.message); }
      this.busy = false;
    },


    copyShareLink() {
      const link = this.shareForm.link;
      if (!link) return;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => this.toast("链接已复制"),
          () => this.askText("复制链接", "手动复制下面的链接", link));
      } else {
        this.askText("复制链接", "手动复制下面的链接", link);
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


    async downloadSource() {
      await this.downloadFile("/api/source/" + encodeURIComponent(this.preview.name) + "/download",
                              this.preview.source ? this.preview.source.filename : this.preview.name);
    },

    async dropFromPreview() {
      const name = this.preview.name;
      const db = this.preview.db;
      if (!await this.askConfirm("删除表", `确定删除表「${name}」？数据不可恢复！`, true)) return;
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

    /* ---------- 新建数据表（可视化，不写 SQL） ---------- */
    openCreateTable() {
      if (!this.selectedDb) { this.toast("先创建或选择一个数据库"); return; }
      this.ctForm = { name: "", db: this.selectedDb, overwrite: false,
                      cols: [{ name: "id", type: "INT", pk: true }] };
      this.$refs.ctDlg.showModal();
      this.$nextTick(() => this.focusEl(this.$refs.ctDlg.querySelector("input")));
    },
    closeCreateTable() { this.$refs.ctDlg.close(); },

    async submitCreateTable() {
      const f = this.ctForm;
      const table = f.name;
      if (!table) { this.toast("先填表名"); return; }
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(table)) {
        this.toast("表名要用字母开头，只能字母/数字/下划线"); return;
      }
      const cols = f.cols.filter(c => c.name);
      if (!cols.length) { this.toast("至少要有一个字段"); return; }
      for (const c of cols) {
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(c.name)) {
          this.toast(`字段名「${c.name}」不合法（字母开头，字母/数字/下划线）`); return;
        }
      }
      const pks = cols.filter(c => c.pk);
      if (pks.length > 1) { this.toast("主键只能选一个字段"); return; }
      const defs = cols.map(c => `\`${c.name}\` ${c.type}${c.pk ? " NOT NULL PRIMARY KEY" : " NOT NULL"}`);
      const sql = `CREATE TABLE \`${table}\` (\n  ${defs.join(",\n  ")}\n)`;
      const full = f.overwrite ? `DROP TABLE IF EXISTS \`${table}\`\n${sql}` : sql;
      this.busy = true;
      try {
        const d = await this.api("/api/sql", { method: "POST", body: { sql: full, db: f.db } });
        const bad = (d.results || []).find(r => r.type === "error");
        if (bad) { this.toast(bad.msg); return; }
        this.closeCreateTable();
        await this.loadDbTables(f.db, true);
        this.selectDb({ name: f.db });
        // 编辑器填上 SELECT，学生点运行就能看到新表
        if (this.$refs.cmSqlRef) this.$refs.cmSqlRef.setValue(`SELECT * FROM \`${table}\` LIMIT 20`);
        this.toast(`表 ${table} 已建到 ${f.db}，点「运行」查看`);
      } catch (e) { this.toast(e.message); }
      finally { this.busy = false; }
    },

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
      this.busy = true;
      this.pyRunCount += 1;
      const n = this.pyRunCount;
      this.pyConsole = [{ n, running: true, out: "", err: "", start: Date.now() }];
      this.scrollConsole("pyConsoleEl");
      try {
        await this.flushPySave();
        const d = await this.api("/api/pyrun/start", {
          method: "POST", body: { code, filename: this.pyCurrent, db: this.selectedDb,
                                  projectId: this.pyProjectId }
        });
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

    /* ---------- 题库 ---------- */
    async loadCommunity() {
      try {
        const d = await this.api("/api/community");
        this.community = d.items;
        this.communityQuestions = d.questions || [];
      } catch (e) { this.toast(e.message); }
    },

    /* ---------- 题目（草稿 → 发布） ---------- */
    async openDrafts() {
      this.qTab = "drafts";
      await this.loadMyQuestions();
    },

    async loadMyQuestions() {
      try {
        const d = await this.api("/api/questions/mine");
        this.myQuestions = d.questions || [];
        if (d.databases) this.databases = d.databases;
      } catch (e) { this.toast(e.message); }
    },

    // 打开题目编辑器：q 为已有题目（编辑），prefillDb 为预选数据库（工作台「存为草稿」）
    async openQuestionEditor(q, prefillDb) {
      this.qForm = { id: 0, title: "", note: "", db: prefillDb || "", pyMap: {} };
      if (q && q.id) {
        try {
          const d = await this.api(`/api/questions/${q.id}`);
          this.qForm.id = d.id;
          this.qForm.title = d.title || "";
          this.qForm.note = d.note || "";
          this.qForm.db = d.dbName || "";
          // 只勾选仍存在的文件（题目里记录的旧文件可能已被删除）
          const exist = new Set(this.pyFiles.map(f => f.name));
          (d.pyFiles || []).filter(n => exist.has(n)).forEach(n => { this.qForm.pyMap[n] = true; });
        } catch (e) { this.toast(e.message); return; }
      } else if (prefillDb) {
        this.qForm.title = prefillDb;
      }
      if (!this.pyFiles.length) { try { await this.refreshPyList(); } catch (e) {} }
      this.$refs.qDlg.showModal();
      this.$nextTick(() => this.focusEl(this.$refs.qDlg.querySelector("input")));
    },
    closeQuestionEditor() { this.$refs.qDlg.close(); },

    // 题目预览：MySQL 表清单 + Python 文件内容（点文件名展开）
    async openQuestionPreview(q) {
      this.qpv = { loading: true, id: q.id, title: q.title, note: q.note || "",
                   uploader: q.uploader || "", createdAt: q.createdAt || "",
                   downloads: q.downloads || 0, tables: [], tableData: [], pyPreview: [] };
      this.qpvFile = null;
      this.qpvTable = null;
      this.$refs.qPreviewDlg.showModal();
      try {
        const d = await this.api(`/api/questions/${q.id}`);
        this.qpv = { loading: false, id: d.id, title: d.title, note: d.note || "",
                     uploader: d.uploader || "", createdAt: d.createdAt || "",
                     downloads: d.downloads || 0,
                     tables: d.tables || [], tableData: d.tableData || [],
                     pyPreview: d.pyPreview || [] };
      } catch (e) {
        this.closeQuestionPreview();
        this.toast(e.message);
      }
    },
    closeQuestionPreview() { this.$refs.qPreviewDlg.close(); this.qpvFile = null; this.qpvTable = null; },

    // 点表名：展开这张表的数据（前 200 行）与结构
    toggleQpvTable(name) {
      if (this.qpvTable && this.qpvTable.name === name) { this.qpvTable = null; return; }
      const t = (this.qpv.tableData || []).find(x => x.name === name);
      if (!t) { this.toast("这道题保存时没有附带表数据预览（旧题目只有表名）"); return; }
      this.qpvTable = t;
      this.qpvTab = "data";
    },

    async saveQuestion(publish) {
      const py = Object.keys(this.qForm.pyMap).filter(n => this.qForm.pyMap[n]);
      this.qBusy = true;
      try {
        const r = await this.api("/api/questions/save", {
          method: "POST",
          body: { id: this.qForm.id, title: this.qForm.title, note: this.qForm.note,
                  db: this.qForm.db, py, pyp: this.pyProjectId, publish },
        });
        this.closeQuestionEditor();
        this.toast(publish ? "题目已发布到题库广场" : "已存为草稿，可随时回来编辑再发布");
        this.qForm.id = r.id;
        await this.loadMyQuestions();
        if (publish) await this.loadCommunity();
      } catch (e) { this.toast(e.message); }
      finally { this.qBusy = false; }
    },

    async publishQuestion(q, publish) {
      try {
        await this.api(`/api/questions/${q.id}/publish`, { method: "POST", body: { publish } });
        this.toast(publish ? `「${q.title}」已发布到广场` : `「${q.title}」已撤回为草稿`);
        await this.loadMyQuestions();
        await this.loadCommunity();
      } catch (e) { this.toast(e.message); }
    },

    async deleteQuestion(q) {
      if (!await this.askConfirm("删除题目", `确定删除题目「${q.title}」？删除后无法恢复。`, true)) return;
      try {
        await this.api(`/api/questions/${q.id}`, { method: "DELETE" });
        this.toast("已删除");
        await this.loadMyQuestions();
        await this.loadCommunity();
      } catch (e) { this.toast(e.message); }
    },

    // 学生一键导入整套：MySQL 建独立库 + Python 文件加进自己的文件列表
    async importQuestion(q) {
      if (!await this.askConfirm("一键导入题目",
        `导入「${q.title}」？\nMySQL 部分会建成你自己的独立数据库${q.pyCount ? "，Python 文件会加进你的文件列表" : ""}。`)) return;
      this.busy = true;
      try {
        const r = await this.api(`/api/questions/${q.id}/import`, {
          method: "POST", body: { db: "", pyp: this.pyProjectId },
        });
        if (r.pyFiles && r.pyFiles.length) {
          await this.refreshPyList();
          await this.loadPyProjects().catch(() => {});
        }
        const bits = [];
        if (r.db) bits.push(`数据库 ${r.db}${r.tables && r.tables.length ? "（" + r.tables.length + " 张表）" : ""}`);
        if (r.pyFiles && r.pyFiles.length) bits.push(`${r.pyFiles.length} 个 Python 文件`);
        this.toast(bits.length ? `已导入：${bits.join(" + ")}` : "这个题目是空的，没有可导入的内容");
        if (r.db) {
          const dbs = await this.api("/api/databases");
          this.databases = dbs.databases;
          this.loadDbTables(r.db, true);
        }
        await this.refreshPyList();
      } catch (e) { this.toast(e.message); }
      finally { this.busy = false; }
    },

    async downloadQuestion(q) {
      await this.downloadFile(`/api/questions/${q.id}/download`, `${q.title}.zip`);
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
            if (await this.askConfirm("覆盖导入", "你的空间里已有同名表，覆盖它吗？")) return doImport(true);
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

    // 题库里的数据库：不导入也能先看这张表的数据/结构
    async previewDbTable(name) {
      if (this.dbPv.loading) return;
      this.dbPv = { loading: true, name, cols: [], rows: [], ddl: "", script: false,
                    rowCount: null, truncated: false };
      this.dbPvTab = "data";
      try {
        const d = await this.api(`/api/community/${this.detail.id}/preview?table=${encodeURIComponent(name)}`);
        this.dbPv = { loading: false, name: d.name, cols: d.cols || [], rows: d.rows || [],
                      ddl: d.ddl || "", script: !!d.script,
                      rowCount: d.rowCount, truncated: !!d.truncated };
        this.dbPvTab = d.script ? "struct" : "data";
      } catch (e) {
        this.closeDbPv();
        this.toast(e.message);
      }
    },
    closeDbPv() {
      this.dbPv = { loading: false, name: "", cols: [], rows: [], ddl: "", script: false,
                    rowCount: null, truncated: false };
      this.dbPvTab = "data";
    },

    closeDbDetail() {
      this.closeDbPv();
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
            if (await this.askConfirm("覆盖导入", "已存在同名数据库/表，覆盖导入吗？")) return doIt(true);
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
            if (await this.askConfirm("覆盖导入", `你的空间里已有同名表「${name}」，覆盖它吗？`)) return doIt(true);
          } else this.toast(e.message);
        } finally { this.busy = false; }
      };
      return doIt(false);
    },

    async openPyItem(it) {
      try {
        await this.flushPySave();
        const d = await this.api("/api/community/open", {
          method: "POST", body: { id: it.id, projectId: this.pyProjectId },
        });
        if (d.projectId && d.projectId !== this.pyProjectId) await this.switchPyProject(d.projectId);
        await this.refreshPyList();
        await this.loadPyProjects().catch(() => {});
        this.switchView("py");
        this.pyCurrent = d.filename;
        if (!this.pyOpenFiles.includes(d.filename)) this.pyOpenFiles.push(d.filename);
        const f = await this.api(this.pyUrl(d.filename));
        if (this.$refs.cmPyRef) this.$refs.cmPyRef.setValue(f.content);
        this.toast(`已保存为文件 ${d.filename}，点 ▶ 运行 试试`);
      } catch (e) { this.toast(e.message); }
    },

    downloadItem(it) {
      this.downloadFile(`/api/community/${it.id}/download`, it.filename || it.title);
    },

    async deleteItem(it) {
      if (!await this.askConfirm("删除题库资源", `确定从题库删除「${it.title}」？`, true)) return;
      try {
        await this.api(`/api/community/${it.id}`, { method: "DELETE" });
        this.toast("已删除");
        this.loadCommunity();
      } catch (e) { this.toast(e.message); }
    },

    /* ---------- 管理 ---------- */
    async openAdmin() {
      this.adminTab = "overview";
      this.adminChecked = [];
      this.$refs.adminDlg.showModal();
      await this.loadOverview();
    },
    closeAdmin() {
      this.$refs.adminDlg.close();
      this.adminList = [];
      this.adminChecked = [];
      this.adminLogs = [];
      this.userDetail = null;
    },
    async refreshAdmin() {
      await this.loadOverview();
      if (this.adminTab === "user" || this.adminTab === "guest") await this.loadAdminList(this.adminPage);
      if (this.adminTab === "log") await this.loadAuthLog();
    },
    async switchAdminTab(tab) {
      this.adminTab = tab;
      if (tab === "user" || tab === "guest") {
        this.adminQuery = ""; this.adminOnly = ""; this.adminChecked = [];
        await this.loadAdminList(1);
      } else if (tab === "log") {
        await this.loadAuthLog();
      } else {
        await this.loadOverview();
      }
    },
    async loadOverview() {
      try { this.adminOverview = await this.api("/api/admin/overview"); }
      catch (e) { this.toast(e.message); }
    },
    async loadAdminList(page) {
      this.adminChecked = [];
      try {
        const kind = this.adminTab === "guest" ? "guest" : "user";
        const qs = new URLSearchParams({
          kind, page: String(page || 1), size: "20",
          q: this.adminQuery || "", only: this.adminOnly || "",
        });
        const d = await this.api("/api/admin/users?" + qs.toString());
        this.adminList = d.users || [];
        this.adminTotal = d.total || 0;
        this.adminPage = d.page || 1;
        this.adminPages = d.pages || 1;
      } catch (e) { this.toast(e.message); }
    },
    toggleUser(id, on) {
      this.adminChecked = on
        ? Array.from(new Set([...this.adminChecked, id]))
        : this.adminChecked.filter(x => x !== id);
    },
    toggleAllUsers(on) {
      const ids = this.adminList.filter(u => u.role !== "admin").map(u => u.id);
      this.adminChecked = on ? ids : [];
    },
    async batchAction(action) {
      const n = this.adminChecked.length;
      if (!n) return;
      const label = { grant: "开通出题权限", revoke: "收回出题权限", disable: "禁用",
                      enable: "解禁", delete: "删除" }[action] || action;
      const danger = action === "delete";
      if (!await this.askConfirm(label, `确定对选中的 ${n} 个账号执行「${label}」？${danger ? "删除后数据不可恢复！" : ""}`, danger)) return;
      try {
        const r = await this.api("/api/admin/batch", { method: "POST",
          body: { ids: this.adminChecked, action } });
        this.toast(`已处理 ${r.done} 个${r.skipped && r.skipped.length ? "，跳过 " + r.skipped.length + " 个" : ""}`);
        await this.loadOverview();
        await this.loadAdminList(this.adminPage);
      } catch (e) { this.toast(e.message); }
    },
    async togglePublishPerm(u) {
      try {
        await this.api(`/api/admin/users/${u.id}/update`, { method: "POST",
          body: { can_publish: !u.canPublish } });
        this.toast(u.canPublish ? `已收回「${u.username}」的出题权限` : `已给「${u.username}」开通出题权限`);
        await this.loadOverview();
        await this.loadAdminList(this.adminPage);
      } catch (e) { this.toast(e.message); }
    },
    async toggleDisabled(u) {
      const next = !u.disabled;
      if (next && !await this.askConfirm("禁用账号",
          `禁用「${u.username}」后，该账号将立即无法登录（已登录的也会被踢下线）。继续？`, true)) return;
      try {
        await this.api(`/api/admin/users/${u.id}/update`, { method: "POST",
          body: { disabled: next } });
        this.toast(next ? `已禁用「${u.username}」` : `已解禁「${u.username}」`);
        await this.loadOverview();
        await this.loadAdminList(this.adminPage);
      } catch (e) { this.toast(e.message); }
    },
    async openUserDetail(u) {
      this.userDetail = null;
      this.$refs.userDlg.showModal();
      try { this.userDetail = await this.api(`/api/admin/users/${u.id}`); }
      catch (e) { this.closeUserDetail(); this.toast(e.message); }
    },
    closeUserDetail() { this.$refs.userDlg.close(); this.userDetail = null; },
    async kickUser() {
      if (!this.userDetail) return;
      if (!await this.askConfirm("强制下线",
          `让「${this.userDetail.user.username}」在所有设备上退出登录？`, true)) return;
      try {
        const r = await this.api(`/api/admin/users/${this.userDetail.user.id}/revoke_sessions`,
                                 { method: "POST" });
        this.toast(`已下线 ${r.killed} 个会话`);
        await this.openUserDetail({ id: this.userDetail.user.id });
      } catch (e) { this.toast(e.message); }
    },
    async loadAuthLog() {
      try {
        const d = await this.api(`/api/admin/auth_log?limit=150&only_fail=${this.adminLogOnlyFail ? "true" : "false"}`);
        this.adminLogs = d.logs || [];
      } catch (e) { this.toast(e.message); }
    },
    openCreateUser() {
      this.cuForm = { username: "", password: "", canPublish: false };
      this.$refs.createUserDlg.showModal();
      this.$nextTick(() => this.focusEl(this.$refs.createUserDlg.querySelector("input")));
    },
    closeCreateUser() { this.$refs.createUserDlg.close(); },
    async createUser() {
      if (!this.cuForm.username || !this.cuForm.password) { this.toast("账号和初始密码都要填"); return; }
      this.cuBusy = true;
      try {
        const r = await this.api("/api/admin/users", { method: "POST",
          body: { username: this.cuForm.username, password: this.cuForm.password,
                  can_publish: this.cuForm.canPublish } });
        this.closeCreateUser();
        this.toast(`账号「${r.username}」已创建`);
        await this.loadOverview();
        await this.loadAdminList(1);
      } catch (e) { this.toast(e.message); }
      finally { this.cuBusy = false; }
    },

    /* ---------- 个人中心 ---------- */
    /* 手机端底部栏「我的」：个人中心 / 管理后台 / 退出登录 */
    openMe() {
      const dlg = this.$refs.meDlg;
      if (!dlg) return;
      if (dlg.open) return;
      dlg.showModal();
    },
    meAction(a) {
      const dlg = this.$refs.meDlg;
      if (dlg && dlg.open) dlg.close();
      if (a === "profile") this.openProfile();
      else if (a === "admin") this.openAdmin();
      else if (a === "logout") this.logout();
    },

    async openProfile() {
      this.profile = null;
      this.pwForm = { old: "", new: "", repeat: "" };
      this.$refs.profileDlg.showModal();
      try { this.profile = await this.api("/api/me/profile"); }
      catch (e) { this.closeProfile(); this.toast(e.message); }
    },
    closeProfile() { this.$refs.profileDlg.close(); this.profile = null; },
    async changePassword() {
      const f = this.pwForm;
      if (!f.old || !f.new) { this.toast("原密码和新密码都要填"); return; }
      if (f.new !== f.repeat) { this.toast("两次输入的新密码不一致"); return; }
      this.pwBusy = true;
      try {
        const r = await this.api("/api/me/password", { method: "POST",
          body: { old_password: f.old, new_password: f.new } });
        this.toast(r.killed ? `密码已更新，其他 ${r.killed} 个设备已退出登录` : "密码已更新");
        this.pwForm = { old: "", new: "", repeat: "" };
      } catch (e) { this.toast(e.message); }
      finally { this.pwBusy = false; }
    },
    async logoutAll() {
      if (!await this.askConfirm("退出所有设备", "除了当前这台设备，其他设备的登录都会失效。继续？")) return;
      try {
        const r = await this.api("/api/me/logout_all", { method: "POST" });
        this.toast(`已退出其他 ${r.killed} 个设备`);
      } catch (e) { this.toast(e.message); }
    },

    async resetPw(u) {
      const pw = await this.askText(`重置「${u.username}」的密码`, "新密码（8-32 位，含字母和数字）", "");
      if (!pw) return;
      try {
        await this.api(`/api/admin/users/${u.id}/update`, { method: "POST",
          body: { password: pw } });
        this.toast("密码已重置，该用户需要重新登录");
        await this.loadAdminList(this.adminPage);
      } catch (e) { this.toast(e.message); }
    },

    async deleteUser(u) {
      const what = u.kind === "guest" ? "游客" : "用户";
      if (!await this.askConfirm(`删除${what}`, `删除${what}「${u.username}」？其所有数据库和数据将一并删除，不可恢复！`, true)) return;
      try {
        await this.api("/api/admin/delete_user", { method: "POST", body: { id: u.id } });
        this.toast("已删除");
        await this.loadOverview();
        await this.loadAdminList(this.adminPage);
      } catch (e) { this.toast(e.message); }
    },
  },
};

const app = createApp(App);
app.component("cm-editor", CmEditor);
app.component("e-icon", EIcon);
app.component("x-select", XSelect);
app.component("x-check", XCheck);
app.component("navicat-panel", NavicatPanel);
app.mount("#app");
