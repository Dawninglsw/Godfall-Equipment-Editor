"""Compatibility entry point for both existing launchers."""
from localized_widgets import tk
from tkinter import messagebox
import traceback
from pathlib import Path
from equipment_editor import Settings

if __name__ == '__main__':
    root = None
    try:
        root = tk.Tk()
        Settings(root)
        root.mainloop()
    except Exception:
        log = Path(__file__).resolve().parent/'editor_startup_error.log'
        log.write_text(traceback.format_exc(), encoding='utf-8')
        if root is not None:
            messagebox.showerror('装备设置未能打开', '错误已记录到 editor_startup_error.log。请保留该文件供检查。', parent=root)
