"""사진 용량 분할기 - 한 폴더의 사진을 지정 용량 이하의 폴더들로 나눈다."""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import splitter

APP_TITLE = "사진 용량 분할기"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("620x520")
        self.minsize(560, 480)

        self.src_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.limit_var = tk.StringVar(value="2")
        self.unit_var = tk.StringVar(value="GB")
        self.mode_var = tk.StringVar(value="copy")
        self.order_var = tk.StringVar(value="name")
        self.all_files_var = tk.BooleanVar(value=False)

        self.events = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()

        self._build()
        self.after(100, self._poll_events)

    # ---------- 화면 구성 ----------
    def _build(self):
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="사진 폴더").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.src_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="찾아보기", command=self._pick_src).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="저장 위치").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="찾아보기", command=self._pick_out).grid(row=1, column=2, **pad)
        ttk.Label(frm, text="(비워두면 사진 폴더 안에 만듭니다)", foreground="gray").grid(
            row=2, column=1, sticky="w", padx=10)

        opt = ttk.LabelFrame(frm, text="옵션")
        opt.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=8)

        row = ttk.Frame(opt)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text="폴더당 최대 용량:").pack(side="left")
        ttk.Entry(row, textvariable=self.limit_var, width=8).pack(side="left", padx=4)
        ttk.Combobox(row, textvariable=self.unit_var, values=["GB", "MB"],
                     width=5, state="readonly").pack(side="left")

        row = ttk.Frame(opt)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text="방식:").pack(side="left")
        ttk.Radiobutton(row, text="복사 (원본 유지)", value="copy",
                        variable=self.mode_var).pack(side="left", padx=4)
        ttk.Radiobutton(row, text="이동", value="move",
                        variable=self.mode_var).pack(side="left", padx=4)

        row = ttk.Frame(opt)
        row.pack(fill="x", padx=8, pady=4)
        ttk.Label(row, text="정렬:").pack(side="left")
        ttk.Radiobutton(row, text="파일 이름순", value="name",
                        variable=self.order_var).pack(side="left", padx=4)
        ttk.Radiobutton(row, text="수정 날짜순", value="date",
                        variable=self.order_var).pack(side="left", padx=4)

        ttk.Checkbutton(opt, text="사진이 아닌 파일도 포함 (동영상 등 모든 파일)",
                        variable=self.all_files_var).pack(anchor="w", padx=8, pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=3, pady=4)
        self.preview_btn = ttk.Button(btns, text="미리보기", command=self._preview)
        self.preview_btn.pack(side="left", padx=4)
        self.run_btn = ttk.Button(btns, text="나누기 실행", command=self._run)
        self.run_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btns, text="중지", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=4)

        frm.rowconfigure(6, weight=1)
        log_frame = ttk.Frame(frm)
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=10, pady=4)
        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="none")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------- 입력 ----------
    def _pick_src(self):
        path = filedialog.askdirectory(title="사진 폴더 선택")
        if path:
            self.src_var.set(path)

    def _pick_out(self):
        path = filedialog.askdirectory(title="저장 위치 선택")
        if path:
            self.out_var.set(path)

    def _write(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _read_settings(self):
        src = self.src_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showwarning(APP_TITLE, "사진 폴더를 선택해 주세요.")
            return None
        out = self.out_var.get().strip() or src
        try:
            value = float(self.limit_var.get().replace(",", "."))
            if value <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "최대 용량에는 0보다 큰 숫자를 입력해 주세요.")
            return None
        unit = splitter.GB if self.unit_var.get() == "GB" else splitter.MB
        return src, out, int(value * unit)

    def _make_plan(self):
        settings = self._read_settings()
        if not settings:
            return None
        src, out, limit = settings
        items = splitter.scan_folder(src, include_all=self.all_files_var.get())
        if not items:
            messagebox.showinfo(APP_TITLE, "폴더에 사진 파일이 없습니다.")
            return None
        items = splitter.sort_files(items, self.order_var.get())
        groups = splitter.plan_groups(items, limit)
        base = os.path.basename(os.path.normpath(src)) or "사진"
        return src, out, limit, base, items, groups

    def _show_plan(self, plan):
        src, out, limit, base, items, groups = plan
        total = sum(i.size for i in items)
        self._clear_log()
        self._write(f"파일 {len(items)}개, 전체 {splitter.format_size(total)}")
        self._write(f"폴더당 최대 {splitter.format_size(limit)} → 폴더 {len(groups)}개로 나눕니다.")
        self._write(f"저장 위치: {out}")
        self._write("")
        names = splitter.group_folder_names(base, len(groups))
        for name, g in zip(names, groups):
            note = "  ※ 파일 하나가 제한보다 큼" if g.total > limit else ""
            self._write(f"  {name}: {len(g.files)}개, {splitter.format_size(g.total)}{note}")

    # ---------- 실행 ----------
    def _preview(self):
        plan = self._make_plan()
        if plan:
            self._show_plan(plan)

    def _run(self):
        plan = self._make_plan()
        if not plan:
            return
        self._show_plan(plan)
        src, out, limit, base, items, groups = plan
        move = self.mode_var.get() == "move"
        action = "이동" if move else "복사"
        if not messagebox.askyesno(
                APP_TITLE, f"{len(items)}개 파일을 {len(groups)}개 폴더로 {action}할까요?"):
            return

        self.stop_flag.clear()
        self._set_running(True)
        self.progress.configure(maximum=len(items), value=0)
        self._write("")
        self._write(f"{action} 시작...")

        def work():
            try:
                done = splitter.execute(
                    groups, out, base, move=move,
                    progress=lambda d, t, p: self.events.put(("progress", d)),
                    should_stop=self.stop_flag.is_set)
                self.events.put(("done", (done, len(items), action)))
            except Exception as exc:  # 화면에 오류를 보여주기 위해 모두 잡는다
                self.events.put(("error", str(exc)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _stop(self):
        self.stop_flag.set()
        self._write("중지 요청됨...")

    def _set_running(self, running):
        state = "disabled" if running else "normal"
        self.preview_btn.configure(state=state)
        self.run_btn.configure(state=state)
        self.stop_btn.configure(state="normal" if running else "disabled")

    def _poll_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "progress":
                    self.progress.configure(value=data)
                elif kind == "done":
                    done, total, action = data
                    self._set_running(False)
                    if done < total:
                        msg = f"중지됨: {total}개 중 {done}개 {action} 완료"
                    else:
                        msg = f"완료: {done}개 파일 {action} 완료"
                    self._write(msg)
                    messagebox.showinfo(APP_TITLE, msg)
                elif kind == "error":
                    self._set_running(False)
                    self._write(f"오류: {data}")
                    messagebox.showerror(APP_TITLE, f"오류가 발생했습니다:\n{data}")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


if __name__ == "__main__":
    App().mainloop()
