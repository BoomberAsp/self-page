"""OneWeblog SFTP 内容上传工具 — Windows GUI"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import paramiko

CONFIG_FILE = Path.home() / ".oneweblog-uploader.json"
REMOTE_CONTENT = "/home/ubuntu/datadisk/self-page/src/content"
REMOTE_IMAGES = "/home/ubuntu/datadisk/self-page/public/images"


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
        self._cancel_upload = False

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

        # ── bottom bar ──
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(bottom, text="上传", command=self._upload).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bottom, text="刷新远端列表", command=self._list_remote).pack(side=tk.RIGHT, padx=4)

        # upload target
        self.target_var = tk.StringVar(value="posts")
        ttk.Radiobutton(bottom, text="图片 (images)", variable=self.target_var, value="images").pack(side=tk.RIGHT, padx=4)
        ttk.Radiobutton(bottom, text="笔记 (notes)", variable=self.target_var, value="notes").pack(side=tk.RIGHT, padx=4)
        ttk.Radiobutton(bottom, text="博文 (posts)", variable=self.target_var, value="posts").pack(side=tk.RIGHT, padx=4)
        ttk.Label(bottom, text="上传目标:").pack(side=tk.RIGHT, padx=(16, 4))

        # image subdirectory entry
        self.img_subdir_var = tk.StringVar(value="posts/")
        self.img_subdir_entry = ttk.Entry(bottom, textvariable=self.img_subdir_var, width=24)
        self.img_subdir_entry.pack(side=tk.RIGHT, padx=4)
        ttk.Label(bottom, text="图片子目录:").pack(side=tk.RIGHT, padx=4)

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
        ttk.Label(f, text="提示：拖放 .mdx 文件到上方列表区域", foreground="gray").pack(anchor=tk.W, pady=(4, 0))

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

    def _save_config(self):
        cfg = {
            "host": self.host_var.get(),
            "port": self.port_var.get(),
            "user": self.user_var.get(),
            "password": self.pass_var.get(),
            "key_file": self.key_var.get(),
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
        for key_class in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey):
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

        def do_list():
            try:
                lines = []
                for folder in ("posts", "notes"):
                    path = f"{REMOTE_CONTENT}/{folder}"
                    try:
                        items = self.sftp.listdir_attr(path)
                    except FileNotFoundError:
                        items = []
                    lines.append((folder, items))
                # images directory — list subdirectories
                try:
                    img_items = self.sftp.listdir_attr(REMOTE_IMAGES)
                except FileNotFoundError:
                    img_items = []
                lines.append(("images", img_items))
                self.after(0, lambda: self._on_remote_listed(lines))
            except Exception as e:
                self.after(0, lambda err=str(e): self._log(f"获取远端列表失败: {err}"))

        self._list_thread = threading.Thread(target=do_list, daemon=True)
        self._list_thread.start()

    def _on_remote_listed(self, folders: list):
        self.remote_tree.delete(*self.remote_tree.get_children())
        for folder, items in folders:
            node = self.remote_tree.insert("", tk.END, text=folder + "/", open=True)
            for attr in sorted(items, key=lambda a: a.filename):
                size = f"{attr.st_size / 1024:.0f} KB" if attr.st_size > 1024 else f"{attr.st_size} B"
                self.remote_tree.insert(node, tk.END, text=attr.filename, values=(size,))
        self.status_var.set("就绪")
        self._log("远端文件列表已刷新")

    # ── file list ──────────────────────────────────────────

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="选择 .mdx 文件",
            filetypes=[("MDX files", "*.mdx"), ("Markdown", "*.md"), ("All Files", "*.*")]
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

        files = self._get_file_list()
        if not files:
            messagebox.showwarning("提示", "请先添加待上传文件")
            return

        target = self.target_var.get()
        if target == "images":
            subdir = self.img_subdir_var.get().strip().rstrip("/")
            target_dir = f"{REMOTE_IMAGES}/{subdir}" if subdir else REMOTE_IMAGES
            display = f"images/{subdir or '.'}"
        else:
            target_dir = f"{REMOTE_CONTENT}/{target}"
            display = target

        self._cancel_upload = False
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
            self._log(f"已完成 {success} 个文件 → {display}/, 刷新页面即可查看")

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
        self._disconnect()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
