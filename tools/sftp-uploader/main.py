"""OneWeblog SFTP 内容上传工具 — Windows GUI"""

import datetime
import json
import os
import re
import stat
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import paramiko

CONFIG_FILE = Path.home() / ".oneweblog-uploader.json"
REMOTE_CONTENT = "/opt/oneweblog/src/content"
REMOTE_IMAGES = "/opt/oneweblog/public/images"

# 远程重建命令：build 成功后才 restart（&& 链保证失败时旧版本继续服务）
# 末尾输出健康检查状态码与哨兵标记，供工具确认结果
REBUILD_CMD = (
    "bash -lc '"
    "cd /opt/oneweblog && npx astro build 2>&1 && "
    "pm2 restart oneweblog && sleep 2 && "
    'echo "HEALTH: $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:4321/posts)" && '
    "echo __REBUILD_OK__"
    "'"
)
REBUILD_SENTINEL = "__REBUILD_OK__"


# ── helpers ────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(data: dict):
    CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_path: str):
    """Recursively create remote directory like `mkdir -p`."""
    dirs = remote_path.strip("/").split("/")
    cur = ""
    for d in dirs:
        cur += "/" + d
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


# ── frontmatter 检查与生成 ─────────────────────────────────

_FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)


def parse_frontmatter(text: str):
    """Return (data dict | None, body, error str | None)."""
    if not text.startswith("---"):
        return None, text, None
    m = _FM_RE.match(text)
    if not m:
        return None, text, "frontmatter 未正确闭合（缺少结束的 ---）"
    raw, body = m.group(1), text[m.end():]
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            return None, body, "frontmatter 不是键值对形式"
        return data, body, None
    except ImportError:
        # 简易回退解析（无 PyYAML 时）
        data = {}
        for line in raw.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
        return data, body, None
    except Exception as e:
        return None, body, f"YAML 解析失败: {e}"


def _valid_date(v) -> bool:
    if isinstance(v, (datetime.date, datetime.datetime)):
        return True
    if isinstance(v, str):
        try:
            datetime.datetime.strptime(v.strip(), "%Y-%m-%d")
            return True
        except ValueError:
            return False
    return False


def check_content_file(path: str) -> dict:
    """Check a .md/.mdx file against the site's content schema (title/date required)."""
    result = {"ok": False, "error": "", "missing": [], "data": {},
              "body": "", "suggested_title": "", "has_h1": False}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = Path(path).read_text(encoding="gbk")
        except Exception as e:
            result["error"] = f"无法读取文件: {e}"
            return result
    except Exception as e:
        result["error"] = f"无法读取文件: {e}"
        return result

    data, body, fm_err = parse_frontmatter(text)
    result["body"] = body
    if fm_err:
        result["error"] = fm_err
        return result
    result["data"] = data or {}

    missing = []
    if data is None:
        missing = ["title", "date"]
    else:
        t = data.get("title")
        if not (isinstance(t, str) and t.strip()):
            missing.append("title")
        if not _valid_date(data.get("date")):
            missing.append("date")
    result["missing"] = missing

    # 正文首个非空行若是 H1 → 可作 title 建议，并提供移除选项
    for line in body.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("# "):
            result["has_h1"] = True
            result["suggested_title"] = s[2:].strip()
        break

    result["ok"] = not missing and not fm_err
    return result


def build_frontmatter(title: str, date_s: str, tags: list, summary: str) -> str:
    """Serialize frontmatter; JSON strings are valid YAML double-quoted scalars."""
    lines = ["---", f"title: {json.dumps(title, ensure_ascii=False)}", f"date: {date_s}"]
    if tags:
        lines.append(f"tags: {json.dumps(tags, ensure_ascii=False)}")
    if summary:
        lines.append(f"summary: {json.dumps(summary, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def strip_leading_h1(body: str) -> str:
    """Remove the first '# ' heading line (site convention: title lives in frontmatter)."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.strip().startswith("# ") and not line.strip().startswith("##"):
            lines = lines[:i] + lines[i + 1:]
            while lines and i < len(lines) and not lines[i].strip():
                lines.pop(i)
        break
    return "\n".join(lines)


def is_url_safe_filename(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._\-]+", name))


# ── main window ─────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OneWeblog 内容上传")
        self.geometry("780x600")
        self.minsize(640, 480)
        self.resizable(True, True)

        self.client: paramiko.SSHClient | None = None
        self.sftp: paramiko.SFTPClient | None = None
        self._connect_thread = None
        self._list_thread = None
        self._upload_thread = None
        self._rebuild_thread = None
        self._cancel_upload = False
        self._last_upload_target = ""
        self._remote_subdirs: dict[str, list[str]] = {}

        self._build_ui()
        self._load_config()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ────────────────────────────────────

    def _build_ui(self):
        # ── menu bar ──
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="添加文件", command=self._add_files, accelerator="Ctrl+O")
        file_menu.add_command(label="清空文件列表", command=self._clear_files)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)
        self.config(menu=menubar)
        self.bind("<Control-o>", lambda _: self._add_files())

        # ── main paned window ──
        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        left = ttk.Frame(pw)
        right = ttk.Frame(pw)
        pw.add(left, weight=4)
        pw.add(right, weight=6)

        self._build_connection_panel(left)
        self._build_remote_panel(left)
        self._build_file_panel(right)
        self._build_log_panel(right)

        # ── bottom bar（两行：第一行目标+子目录，第二行勾选+按钮；单行在窄窗口会挤掉控件）──
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=4)

        row1 = ttk.Frame(bottom)
        row1.pack(fill=tk.X, pady=(0, 4))

        self.target_var = tk.StringVar(value="posts")
        ttk.Label(row1, text="上传目标:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(row1, text="博文 (posts)", variable=self.target_var, value="posts",
                        command=self._refresh_subdir_candidates).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row1, text="笔记 (notes)", variable=self.target_var, value="notes",
                        command=self._refresh_subdir_candidates).pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(row1, text="图片 (images)", variable=self.target_var, value="images",
                        command=self._refresh_subdir_candidates).pack(side=tk.LEFT, padx=4)

        # subdirectory combobox (applies to all targets): 已有远端目录按输入补全，无匹配则视为新目录
        self.subdir_var = tk.StringVar(value="")
        ttk.Label(row1, text="子目录:").pack(side=tk.LEFT, padx=(20, 4))
        self.subdir_combo = ttk.Combobox(row1, textvariable=self.subdir_var, width=28)
        self.subdir_combo.pack(side=tk.LEFT)
        self.subdir_combo.bind("<KeyRelease>", lambda _: self._refresh_subdir_candidates())
        ttk.Label(row1, text="（连接后按输入补全已有目录；无匹配上传时自动新建）",
                  foreground="gray").pack(side=tk.LEFT, padx=(8, 0))

        row2 = ttk.Frame(bottom)
        row2.pack(fill=tk.X)
        self.upload_btn = ttk.Button(row2, text="上传", command=self._upload)
        self.upload_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.rebuild_btn = ttk.Button(row2, text="仅重建", command=self._rebuild_remote)
        self.rebuild_btn.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(row2, text="刷新远端列表", command=self._list_remote).pack(side=tk.RIGHT, padx=4)

        # auto-rebuild checkbox (left side; persisted in config)
        self.auto_rebuild_var = tk.BooleanVar(value=load_config().get("auto_rebuild", True))
        ttk.Checkbutton(row2, text="上传后自动重建网站", variable=self.auto_rebuild_var).pack(side=tk.LEFT, padx=(4, 0))

        # status bar
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(6, 2)).pack(fill=tk.X)

    def _build_connection_panel(self, parent: ttk.Frame):
        f = ttk.LabelFrame(parent, text="连接配置", padding=8)
        f.pack(fill=tk.X, pady=(0, 8))

        cfg = load_config()

        # host
        ttk.Label(f, text="主机").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.host_var = tk.StringVar(value=cfg.get("host", ""))
        ttk.Entry(f, textvariable=self.host_var, width=28).grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=2)

        # port
        ttk.Label(f, text="端口").grid(row=0, column=2, sticky=tk.W, padx=(12, 0), pady=2)
        self.port_var = tk.StringVar(value=cfg.get("port", "22"))
        ttk.Entry(f, textvariable=self.port_var, width=6).grid(row=0, column=3, sticky=tk.W, padx=(8, 0), pady=2)

        # user
        ttk.Label(f, text="用户").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.user_var = tk.StringVar(value=cfg.get("user", "ubuntu"))
        ttk.Entry(f, textvariable=self.user_var, width=28).grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=2)

        # password / key passphrase
        ttk.Label(f, text="密码/密钥口令").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.pass_var = tk.StringVar(value=cfg.get("password", ""))
        ttk.Entry(f, textvariable=self.pass_var, show="*", width=28).grid(row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=2)

        # key file
        ttk.Label(f, text="密钥").grid(row=3, column=0, sticky=tk.W, pady=2)
        key_frame = ttk.Frame(f)
        key_frame.grid(row=3, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0), pady=2)
        self.key_var = tk.StringVar(value=cfg.get("key_file", ""))
        ttk.Entry(key_frame, textvariable=self.key_var, width=22).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(key_frame, text="浏览", command=self._browse_key).pack(side=tk.LEFT, padx=(4, 0))

        # buttons
        btn_frame = ttk.Frame(f)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=(8, 0))
        self.connect_btn = ttk.Button(btn_frame, text="连接", command=self._connect)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="断开", command=self._disconnect).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="保存配置", command=self._save_config).pack(side=tk.LEFT)

        f.columnconfigure(1, weight=1)

    def _build_remote_panel(self, parent: ttk.Frame):
        f = ttk.LabelFrame(parent, text="服务器文件", padding=8)
        f.pack(fill=tk.BOTH, expand=True)

        self.remote_tree = ttk.Treeview(f, columns=("size",), show="tree headings", height=8)
        self.remote_tree.heading("#0", text="名称")
        self.remote_tree.heading("size", text="大小")
        self.remote_tree.column("size", width=80, anchor=tk.E)
        self.remote_tree.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.remote_tree, orient=tk.VERTICAL, command=self.remote_tree.yview)
        self.remote_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_file_panel(self, parent: ttk.Frame):
        f = ttk.LabelFrame(parent, text="待上传文件", padding=8)
        f.pack(fill=tk.BOTH, expand=True)

        # listbox + scrollbar
        list_frame = ttk.Frame(f)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        lb_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=lb_scroll.set)
        lb_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # buttons
        btn_row = ttk.Frame(f)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_row, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="清空", command=self._clear_files).pack(side=tk.LEFT)

        # drag-drop hint
        ttk.Label(f, text="提示：可添加 .md / .mdx 及图片等任意文件；配合底栏「子目录」可传到栏目目录（如 advanced-linear-algebra），远端目录自动创建",
                  foreground="gray", wraplength=420, justify=tk.LEFT).pack(anchor=tk.W, pady=(4, 0))

    def _build_log_panel(self, parent: ttk.Frame):
        f = ttk.LabelFrame(parent, text="日志", padding=8)
        f.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.log_text = tk.Text(f, height=6, state=tk.DISABLED, wrap=tk.WORD,
                                font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

        log_btn = ttk.Frame(f)
        log_btn.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(log_btn, text="清除日志", command=self._clear_log).pack(side=tk.RIGHT)

    # ── config persistence ─────────────────────────────────

    def _load_config(self):
        cfg = load_config()
        if cfg:
            self.host_var.set(cfg.get("host", ""))
            self.port_var.set(cfg.get("port", "22"))
            self.user_var.set(cfg.get("user", "ubuntu"))
            self.pass_var.set(cfg.get("password", ""))
            self.key_var.set(cfg.get("key_file", ""))
            self.auto_rebuild_var.set(cfg.get("auto_rebuild", True))

    def _save_config(self):
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "user": self.user_var.get(),
            "password": self.pass_var.get(),
            "key_file": self.key_var.get(),
            "auto_rebuild": self.auto_rebuild_var.get(),
        }
        save_config(cfg)
        self._log("配置已保存")

    def _browse_key(self):
        path = filedialog.askopenfilename(title="选择 SSH 密钥文件", filetypes=[("All Files", "*.*")])
        if path:
            self.key_var.set(path)

    # ── connection ─────────────────────────────────────────

    def _connect(self):
        if self.client:
            self._disconnect()

        host = self.host_var.get().strip()
        port = int(self.port_var.get() or 22)
        user = self.user_var.get().strip()
        passphrase = self.pass_var.get()
        key_file = self.key_var.get().strip()

        if not host or not user:
            messagebox.showwarning("提示", "请填写主机和用户名")
            return

        # 如果选了密钥文件，先处理口令
        key_path = None
        if key_file:
            key_path = os.path.expanduser(key_file)
            if not os.path.exists(key_path):
                self._log(f"密钥文件不存在: {key_path}")
                key_path = None

        if key_path and not passphrase:
            # 密钥需要口令但字段为空 → 弹窗
            self._prompt_passphrase_then_connect(host, port, user, key_path)
            return

        if key_path:
            self._try_connect_with_key(host, port, user, key_path, passphrase)
        elif passphrase:
            self._try_connect_with_password(host, port, user, passphrase)
        else:
            self._try_connect_with_agent(host, port, user)

    def _try_connect_with_key(self, host, port, user, key_path, passphrase):
        self.connect_btn.configure(state=tk.DISABLED, text="连接中...")
        self.status_var.set("正在连接...")

        def do_connect():
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                pkey = self._load_private_key(key_path, passphrase)
                client.connect(hostname=host, port=port, username=user, pkey=pkey, timeout=15)
                sftp = client.open_sftp()
                self.after(0, lambda: self._on_connected(client, sftp, host))
            except (paramiko.PasswordRequiredException, paramiko.SSHException) as e:
                if isinstance(e, paramiko.SSHException) and "encrypted" not in str(e).lower() and "bad" not in str(e).lower():
                    self.after(0, lambda err=str(e): self._on_connect_error(err))
                    return
                # 口令错误 → 弹窗重新输入
                self.after(0, lambda: self._prompt_passphrase_then_connect(host, port, user, key_path))
            except paramiko.AuthenticationException:
                self.after(0, lambda err=str(passphrase): self._on_connect_error(f"认证失败 — 密钥口令可能不正确"))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_connect_error(err))

        t = threading.Thread(target=do_connect, daemon=True)
        t.start()

    def _try_connect_with_password(self, host, port, user, password):
        self.connect_btn.configure(state=tk.DISABLED, text="连接中...")
        self.status_var.set("正在连接...")

        def do_connect():
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname=host, port=port, username=user, password=password, timeout=15)
                sftp = client.open_sftp()
                self.after(0, lambda: self._on_connected(client, sftp, host))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_connect_error(err))

        t = threading.Thread(target=do_connect, daemon=True)
        t.start()

    def _try_connect_with_agent(self, host, port, user):
        self.connect_btn.configure(state=tk.DISABLED, text="连接中...")
        self.status_var.set("正在连接...")

        def do_connect():
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname=host, port=port, username=user,
                               allow_agent=True, look_for_keys=True, timeout=15)
                sftp = client.open_sftp()
                self.after(0, lambda: self._on_connected(client, sftp, host))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_connect_error(err))

        t = threading.Thread(target=do_connect, daemon=True)
        t.start()

    def _prompt_passphrase_then_connect(self, host, port, user, key_path):
        self.connect_btn.configure(state=tk.NORMAL, text="连接")
        self.status_var.set("等待输入密钥口令...")

        dialog = tk.Toplevel(self)
        dialog.title("密钥口令")
        dialog.geometry("360x140")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text=f"请输入密钥口令:\n{os.path.basename(key_path)}",
                  padding=(12, 8)).pack()
        frame = ttk.Frame(dialog)
        frame.pack(padx=12, pady=(0, 8))
        entry = ttk.Entry(frame, show="*", width=36)
        entry.pack(side=tk.LEFT)
        entry.focus_set()

        def on_ok():
            passphrase = entry.get()
            dialog.destroy()
            self._try_connect_with_key(host, port, user, key_path, passphrase)

        def on_cancel():
            dialog.destroy()
            self._on_connect_error("用户取消了密钥口令输入")

        ttk.Button(frame, text="确定", command=on_ok).pack(side=tk.LEFT, padx=(6, 0))
        entry.bind("<Return>", lambda _: on_ok())

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack()
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack()

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    def _load_private_key(self, key_path: str, passphrase: str):
        """Try to load a private key with passphrase. Raises on failure."""
        for key_class in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                return key_class.from_private_key_file(key_path, password=passphrase or None)
            except (paramiko.PasswordRequiredException, paramiko.SSHException) as ex:
                if isinstance(ex, paramiko.SSHException) and "encrypted" not in str(ex).lower():
                    continue
                raise paramiko.PasswordRequiredException(str(ex))
            except Exception:
                continue
        raise ValueError(f"无法识别的密钥格式: {key_path}")

    def _on_connected(self, client: paramiko.SSHClient, sftp: paramiko.SFTPClient, host: str):
        self.client = client
        self.sftp = sftp
        self.connect_btn.configure(text="已连接", state=tk.DISABLED)
        self.status_var.set(f"已连接 {host}")
        self._log(f"已连接到 {host}")
        self._list_remote()

    def _on_connect_error(self, err: str):
        self.connect_btn.configure(state=tk.NORMAL, text="连接")
        self.status_var.set("连接失败")
        self._log(f"连接失败: {err}")
        messagebox.showerror("连接失败", err)

    def _disconnect(self):
        if self._connect_thread and self._connect_thread.is_alive():
            return

        if self.sftp:
            try:
                self.sftp.close()
            except Exception:
                pass
            self.sftp = None
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

        self.connect_btn.configure(state=tk.NORMAL, text="连接")
        self.status_var.set("已断开")
        self.remote_tree.delete(*self.remote_tree.get_children())
        self._log("已断开连接")

    # ── remote listing ─────────────────────────────────────

    def _list_remote(self):
        if not self.sftp:
            return

        self.status_var.set("正在加载远端文件列表...")

        def collect_subdirs(base: str, prefix: str, depth: int) -> list:
            """Recursively collect relative subdirectory paths (depth-limited)."""
            out = []
            if depth <= 0:
                return out
            try:
                items = self.sftp.listdir_attr(base)
            except FileNotFoundError:
                return out
            for attr in items:
                if attr.st_mode is not None and stat.S_ISDIR(attr.st_mode):
                    rel = f"{prefix}{attr.filename}"
                    out.append(rel)
                    out.extend(collect_subdirs(f"{base}/{attr.filename}", rel + "/", depth - 1))
            return out

        def do_list():
            try:
                lines = []
                subdirs = {}
                bases = {"posts": f"{REMOTE_CONTENT}/posts",
                         "notes": f"{REMOTE_CONTENT}/notes",
                         "images": REMOTE_IMAGES}
                for folder in ("posts", "notes"):
                    path = bases[folder]
                    try:
                        items = self.sftp.listdir_attr(path)
                    except FileNotFoundError:
                        items = []
                    lines.append((folder, items))
                    subdirs[folder] = collect_subdirs(path, "", 3)
                # images directory — list subdirectories
                try:
                    img_items = self.sftp.listdir_attr(REMOTE_IMAGES)
                except FileNotFoundError:
                    img_items = []
                lines.append(("images", img_items))
                subdirs["images"] = collect_subdirs(REMOTE_IMAGES, "", 3)
                self.after(0, lambda: self._on_remote_listed(lines, subdirs))
            except Exception as e:
                self.after(0, lambda err=str(e): self._log(f"获取远端列表失败: {err}"))

        self._list_thread = threading.Thread(target=do_list, daemon=True)
        self._list_thread.start()

    def _on_remote_listed(self, folders: list, subdirs: dict):
        self.remote_tree.delete(*self.remote_tree.get_children())
        for folder, items in folders:
            node = self.remote_tree.insert("", tk.END, text=folder + "/", open=True)
            for attr in sorted(items, key=lambda a: a.filename):
                size = f"{attr.st_size / 1024:.0f} KB" if attr.st_size > 1024 else f"{attr.st_size} B"
                self.remote_tree.insert(node, tk.END, text=attr.filename, values=(size,))
        self._remote_subdirs = subdirs
        self._refresh_subdir_candidates()
        self.status_var.set("就绪")
        self._log("远端文件列表已刷新")

    def _refresh_subdir_candidates(self):
        """Filter remote subdirectories of the current target by what the user typed."""
        typed = self.subdir_var.get().strip().strip("/")
        pool = self._remote_subdirs.get(self.target_var.get(), [])
        if typed:
            vals = [d for d in pool if typed.lower() in d.lower()]
        else:
            vals = list(pool)
        self.subdir_combo.configure(values=sorted(vals)[:50])

    # ── file list ──────────────────────────────────────────

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="选择内容文件",
            filetypes=[("Markdown", "*.md"), ("MDX files", "*.mdx"), ("All Files", "*.*")]
        )
        for f in files:
            if f not in self._get_file_list():
                self.file_listbox.insert(tk.END, f)

    def _remove_selected(self):
        for idx in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(idx)

    def _clear_files(self):
        self.file_listbox.delete(0, tk.END)

    def _get_file_list(self):
        return [self.file_listbox.get(i) for i in range(self.file_listbox.size())]

    # ── upload ─────────────────────────────────────────────

    def _upload(self):
        if not self.sftp:
            messagebox.showwarning("提示", "请先连接服务器")
            return

        if self._rebuild_thread and self._rebuild_thread.is_alive():
            messagebox.showwarning("提示", "远程重建正在进行中，请等待完成后再上传")
            return

        files = self._get_file_list()
        if not files:
            messagebox.showwarning("提示", "请先添加待上传文件")
            return

        target = self.target_var.get()
        subdir = self.subdir_var.get().strip().strip("/")
        if target == "images":
            target_dir = f"{REMOTE_IMAGES}/{subdir}" if subdir else REMOTE_IMAGES
            display = f"images/{subdir}" if subdir else "images"
        else:
            target_dir = f"{REMOTE_CONTENT}/{target}/{subdir}" if subdir else f"{REMOTE_CONTENT}/{target}"
            display = f"{target}/{subdir}" if subdir else target

        # 内容文件上传前检查 frontmatter（posts/notes 的 .md/.mdx 必须含 title+date）
        if target in ("posts", "notes"):
            for f in files:
                name = os.path.basename(f)
                if not is_url_safe_filename(name):
                    self._log(f"⚠ 文件名含非 URL 安全字符（空格/顿号/中文等），建议改为小写字母、数字、连字符: {name}")
            content_files = [f for f in files if f.lower().endswith((".md", ".mdx"))]
            problems = [f for f in content_files if not check_content_file(f)["ok"]]
            if problems:
                self._log(f"检测到 {len(problems)} 个文件缺少有效 frontmatter，请在弹窗中补全（将写回本地原文件）")
                dlg = FrontmatterDialog(self, problems)
                self.wait_window(dlg)
                if not dlg.fixed_all:
                    self.status_var.set("已取消上传（frontmatter 未补全）")
                    return
                still = [f for f in problems if not check_content_file(f)["ok"]]
                if still:
                    messagebox.showerror("检查未通过", "以下文件仍缺少有效 frontmatter:\n" +
                                         "\n".join(os.path.basename(f) for f in still))
                    return
                self._log("frontmatter 补全完成，已写回本地文件")

        self._cancel_upload = False
        self._last_upload_target = target
        self.status_var.set("正在上传...")
        self._log(f"开始上传 {len(files)} 个文件到 {display}/ ...")

        progress_win = tk.Toplevel(self)
        progress_win.title("上传中")
        progress_win.geometry("400x120")
        progress_win.resizable(False, False)
        progress_win.transient(self)
        progress_win.grab_set()

        ttk.Label(progress_win, text="正在上传文件...", padding=(12, 8)).pack()
        progress_bar = ttk.Progressbar(progress_win, mode="determinate", length=360)
        progress_bar.pack(padx=20, pady=(0, 4))
        progress_bar["maximum"] = len(files)
        progress_bar["value"] = 0

        progress_label = ttk.Label(progress_win, text="")
        progress_label.pack()

        cancel_btn = ttk.Button(progress_win, text="取消", command=lambda: setattr(self, "_cancel_upload", True))
        cancel_btn.pack(pady=(4, 8))

        def do_upload():
            # ensure target directory exists
            try:
                ensure_remote_dir(self.sftp, target_dir)
            except Exception as e:
                self.after(0, lambda err=str(e): self._log(f"创建远程目录失败: {err}"))
                self.after(0, lambda: self._on_upload_done([], progress_win, display))
                return

            results = []
            for i, filepath in enumerate(files):
                if self._cancel_upload:
                    results.append(("已取消", filepath, "用户取消"))
                    break

                filename = os.path.basename(filepath)
                remote_path = f"{target_dir}/{filename}"

                self.after(0, lambda n=filename: progress_label.configure(text=n))
                self.after(0, lambda v=i + 1: progress_bar.configure(value=v))

                try:
                    self.sftp.put(filepath, remote_path)
                    results.append(("成功", filename, remote_path))
                except Exception as e:
                    results.append(("失败", filename, str(e)))

            self.after(0, lambda d=display: self._on_upload_done(results, progress_win, d))

        self._upload_thread = threading.Thread(target=do_upload, daemon=True)
        self._upload_thread.start()

    def _on_upload_done(self, results: list, progress_win: tk.Toplevel, display: str):
        progress_win.destroy()
        success = sum(1 for r in results if r[0] == "成功")
        fail = len(results) - success
        self.status_var.set(f"上传完成: {success} 成功, {fail} 失败")

        for status, name, detail in results:
            prefix = "✓" if status == "成功" else "✗"
            self._log(f"{prefix} {name} → {detail}")

        self._list_remote()

        if success > 0:
            self._log(f"已完成 {success} 个文件 → {display}/")
            # 图片由 nginx 直接伺服，无需重建；posts/notes 内容需重建生效
            if self._last_upload_target in ("posts", "notes"):
                if self.auto_rebuild_var.get():
                    self._rebuild_remote(reason="内容上传后自动重建")
                else:
                    self._log("提示：内容文件需重建网站才能生效（可点击「仅重建」）")

    # ── remote rebuild ──────────────────────────────────────

    def _rebuild_remote(self, reason: str = "手动触发"):
        if not self.client or not self.client.get_transport() or not self.client.get_transport().is_active():
            messagebox.showwarning("提示", "请先连接服务器")
            return

        if self._rebuild_thread and self._rebuild_thread.is_alive():
            messagebox.showwarning("提示", "重建已在进行中")
            return

        if not messagebox.askyesno("确认重建", f"将在服务器上重新构建网站并重启服务。\n触发原因：{reason}\n\n继续？"):
            return

        self.upload_btn.configure(state=tk.DISABLED)
        self.rebuild_btn.configure(state=tk.DISABLED, text="重建中...")
        self.status_var.set(f"正在远程重建（{reason}）...")
        self._log(f"── 远程重建开始（{reason}）──")

        progress_win = tk.Toplevel(self)
        progress_win.title("远程重建中")
        progress_win.geometry("400x110")
        progress_win.resizable(False, False)
        progress_win.transient(self)
        progress_win.grab_set()
        progress_win.protocol("WM_DELETE_WINDOW", lambda: None)  # 重建期间不允许关闭

        ttk.Label(progress_win, text="正在服务器上构建网站，约需 1-3 分钟...", padding=(12, 8)).pack()
        rebuild_bar = ttk.Progressbar(progress_win, mode="indeterminate", length=360)
        rebuild_bar.pack(padx=20, pady=(0, 8))
        rebuild_bar.start(12)

        def do_rebuild():
            start = time.time()
            lines: list[str] = []
            health = ""
            ok = False
            err_msg = ""
            try:
                transport = self.client.get_transport()
                chan = transport.open_session()
                chan.settimeout(300)
                chan.exec_command(REBUILD_CMD)
                buf = b""

                def pump() -> bool:
                    """Read available stdout/stderr; return True if any data was read."""
                    nonlocal buf, health, ok
                    got = False
                    if chan.recv_ready():
                        buf += chan.recv(4096)
                        got = True
                    if chan.recv_stderr_ready():
                        buf += chan.recv_stderr(4096)
                        got = True
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", "replace").rstrip()
                        lines.append(text)
                        if text.startswith("HEALTH:"):
                            health = text.split(":", 1)[1].strip()
                        if REBUILD_SENTINEL in text:
                            ok = True
                        self.after(0, lambda t=text: self._log(f"[server] {t}"))
                    return got

                while True:
                    if pump():
                        continue
                    if chan.exit_status_ready():
                        break
                    time.sleep(0.2)
                # drain remaining
                while pump():
                    pass
                if buf:
                    text = buf.decode("utf-8", "replace").rstrip()
                    lines.append(text)
                    if REBUILD_SENTINEL in text:
                        ok = True
                    self.after(0, lambda t=text: self._log(f"[server] {t}"))
                exit_code = chan.recv_exit_status()
                chan.close()
                if not ok:
                    err_msg = f"重建命令异常退出 (exit code {exit_code})"
            except Exception as e:
                err_msg = f"重建失败: {e}"
            elapsed = time.time() - start
            self.after(0, lambda: self._on_rebuild_done(
                progress_win, ok, health, elapsed, err_msg, lines))

        self._rebuild_thread = threading.Thread(target=do_rebuild, daemon=True)
        self._rebuild_thread.start()

    def _on_rebuild_done(self, progress_win: tk.Toplevel, ok: bool, health: str,
                         elapsed: float, err_msg: str, lines: list):
        progress_win.destroy()
        self.upload_btn.configure(state=tk.NORMAL)
        self.rebuild_btn.configure(state=tk.NORMAL, text="仅重建")

        if ok:
            self.status_var.set(f"重建成功 ({elapsed:.0f}s)，健康检查: HTTP {health or '?'}")
            self._log(f"── 远程重建成功，用时 {elapsed:.0f}s，/posts 返回 HTTP {health or '?'} ──")
            if health and health != "200":
                messagebox.showwarning(
                    "重建完成但健康检查异常",
                    f"重建成功，但 /posts 返回 HTTP {health}。\n请到服务器检查 pm2 日志。")
        else:
            self.status_var.set("重建失败 — 网站仍运行旧版本")
            self._log(f"── {err_msg}，用时 {elapsed:.0f}s ──")
            tail = "\n".join(lines[-20:]) or "(无输出)"
            messagebox.showerror(
                "重建失败",
                f"{err_msg}\n\nbuild 失败时不会重启服务，网站仍在运行旧版本。\n\n最后 20 行输出：\n{tail}")

    # ── log ─────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── cleanup ─────────────────────────────────────────────

    def _on_close(self):
        if self._upload_thread and self._upload_thread.is_alive():
            if not messagebox.askyesno("确认", "上传正在进行中，确定要退出吗？"):
                return
            self._cancel_upload = True
        if self._rebuild_thread and self._rebuild_thread.is_alive():
            if not messagebox.askyesno(
                    "确认",
                    "远程重建正在进行中！\n退出会断开连接，可能中断服务器上的构建\n（build 未完成则不会重启服务，网站仍运行旧版本）。\n确定要退出吗？"):
                return
        self._disconnect()
        self.destroy()


# ── frontmatter 补全对话框 ──────────────────────────────────

class FrontmatterDialog(tk.Toplevel):
    """逐个补全缺失 frontmatter 的内容文件；保存即写回本地原文件。"""

    def __init__(self, master, files: list):
        super().__init__(master)
        self.fixed_all = False
        self._files = files
        self._idx = 0

        self.title("补全文章信息")
        self.geometry("640x620")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        pad = {"padx": 12, "pady": 4}
        self._header = ttk.Label(self, text="", font=("Microsoft YaHei UI", 11, "bold"))
        self._header.pack(anchor=tk.W, **pad)
        self._issue = ttk.Label(self, text="", foreground="#b00020", wraplength=600, justify=tk.LEFT)
        self._issue.pack(anchor=tk.W, padx=12)

        form = ttk.Frame(self)
        form.pack(fill=tk.X, padx=12, pady=6)
        self.title_var = tk.StringVar()
        self.date_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.strip_h1_var = tk.BooleanVar(value=True)

        rows = [("标题 *", self.title_var, 58), ("日期 * (YYYY-MM-DD)", self.date_var, 16),
                ("标签 (逗号分隔)", self.tags_var, 40), ("摘要 (可选)", self.summary_var, 58)]
        for i, (label, var, width) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(form, textvariable=var, width=width).grid(row=i, column=1, sticky=tk.W, padx=(8, 0), pady=3)
        self._strip_cb = ttk.Checkbutton(form, text="移除正文开头重复的 # 标题（网站惯例：标题由 frontmatter 提供）",
                                         variable=self.strip_h1_var)
        self._strip_cb.grid(row=len(rows), column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        ttk.Label(self, text="正文预览:").pack(anchor=tk.W, padx=12)
        self._preview = tk.Text(self, height=10, state=tk.DISABLED, wrap=tk.WORD,
                                font=("Consolas", 9), background="#f6f6f6")
        self._preview.pack(fill=tk.BOTH, expand=True, padx=12, pady=(2, 6))

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=12, pady=(0, 10))
        self._prev_btn = ttk.Button(btns, text="上一个", command=self._prev)
        self._prev_btn.pack(side=tk.LEFT)
        ttk.Button(btns, text="取消上传", command=self._cancel).pack(side=tk.RIGHT, padx=(8, 0))
        self._save_btn = ttk.Button(btns, text="保存并继续", command=self._save_current)
        self._save_btn.pack(side=tk.RIGHT)

        self._populate()

    # ── 内部逻辑 ──

    def _populate(self):
        path = self._files[self._idx]
        r = check_content_file(path)
        self._header.configure(text=f"补全文章信息 ({self._idx + 1}/{len(self._files)})  —  {os.path.basename(path)}")

        data = r["data"]
        if r["error"]:
            self._issue.configure(text=f"✗ {r['error']}（请手动修复该文件后重新上传，或取消）")
            self._save_btn.configure(state=tk.DISABLED)
        else:
            miss = "、".join(r["missing"]) if r["missing"] else "格式校验"
            self._issue.configure(text=f"缺少必填字段: {miss}（带 * 为必填）" if r["missing"] else "")
            self._save_btn.configure(state=tk.NORMAL)

        d = data.get("date")
        if isinstance(d, (datetime.datetime, datetime.date)):
            date_s = d.strftime("%Y-%m-%d")
        elif isinstance(d, str) and d.strip():
            date_s = d.strip()
        else:
            date_s = datetime.date.today().strftime("%Y-%m-%d")

        self.title_var.set(str(data.get("title") or r["suggested_title"] or Path(path).stem))
        self.date_var.set(date_s)
        tags = data.get("tags") or []
        self.tags_var.set(", ".join(str(t) for t in tags) if isinstance(tags, list) else str(tags))
        self.summary_var.set(str(data.get("summary") or ""))
        self.strip_h1_var.set(r["has_h1"])
        self._strip_cb.configure(state=tk.NORMAL if r["has_h1"] else tk.DISABLED)

        preview_lines = [ln for ln in r["body"].split("\n")[:14]]
        self._preview.configure(state=tk.NORMAL)
        self._preview.delete("1.0", tk.END)
        self._preview.insert(tk.END, "\n".join(preview_lines))
        self._preview.configure(state=tk.DISABLED)

        self._prev_btn.configure(state=tk.NORMAL if self._idx > 0 else tk.DISABLED)
        self._save_btn.configure(
            text="保存并开始上传" if self._idx == len(self._files) - 1 else "保存并继续",
            state=tk.DISABLED if r["error"] else tk.NORMAL)

    def _save_current(self):
        path = self._files[self._idx]
        title = self.title_var.get().strip()
        date_s = self.date_var.get().strip()
        if not title:
            messagebox.showwarning("提示", "标题不能为空", parent=self)
            return
        try:
            datetime.datetime.strptime(date_s, "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("提示", "日期格式应为 YYYY-MM-DD，例如 2026-09-16", parent=self)
            return
        tags = [t.strip() for t in re.split(r"[,，、;；]", self.tags_var.get()) if t.strip()]
        summary = self.summary_var.get().strip()

        try:
            text = Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="gbk")
        _, body, err = parse_frontmatter(text)
        if err:
            messagebox.showerror("无法保存", f"该文件现有 frontmatter 解析失败:\n{err}", parent=self)
            return
        if self.strip_h1_var.get():
            body = strip_leading_h1(body)
        new_text = build_frontmatter(title, date_s, tags, summary) + body.lstrip("\n")
        Path(path).write_text(new_text, encoding="utf-8", newline="\n")

        if self._idx < len(self._files) - 1:
            self._idx += 1
            self._populate()
        else:
            self.fixed_all = True
            self.destroy()

    def _prev(self):
        if self._idx > 0:
            self._idx -= 1
            self._populate()

    def _cancel(self):
        self.fixed_all = False
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
