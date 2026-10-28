"""Shared presentation only; no editor state or game operations."""
from tkinter import ttk

APP='#1B2029'
SURFACE='#242C38'
CARD='#2B3543'
TEXT='#E5EAF3'
MUTED='#ABB7CA'
ACCENT='#D6B16B'
LINE='#455166'
SELECT='#414F64'
SUCCESS='#97D5AE'


def apply(root):
    from branding import apply_icon,set_process_identity
    set_process_identity();apply_icon(root)
    root.configure(background=APP)
    style=ttk.Style(root);style.theme_use('clam')
    style.configure('.',background=SURFACE,foreground=TEXT)
    style.configure('TFrame',background=SURFACE)
    style.configure('App.TFrame',background=APP)
    style.configure('TLabel',font=('Microsoft YaHei UI',10),background=SURFACE,foreground=TEXT)
    style.configure('Title.TLabel',font=('Microsoft YaHei UI',18,'bold'),background=APP,foreground=TEXT)
    style.configure('AppMuted.TLabel',background=APP,foreground=MUTED)
    style.configure('Muted.TLabel',foreground=MUTED)
    style.configure('Section.TLabel',font=('Microsoft YaHei UI',9,'bold'),foreground=MUTED)
    style.configure('Info.TLabel',background='#303C4E',foreground='#D0DAE9',padding=(10,4))
    style.configure('TButton',font=('Microsoft YaHei UI',10),padding=(10,5),background='#303B4B',
                    foreground=TEXT,bordercolor=LINE,lightcolor=SURFACE,darkcolor=LINE,relief='flat')
    style.map('TButton',background=[('active','#3D4C62')],foreground=[('disabled','#8290A5')])
    style.configure('Accent.TButton',background=ACCENT,foreground='#202733',bordercolor=ACCENT)
    style.map('Accent.TButton',background=[('disabled','#303B4B'),('pressed','#BA944F'),('active','#E4C486')],
              foreground=[('disabled','#8290A5'),('!disabled','#202733')])
    style.configure('QuietDanger.TButton',foreground='#E5A0A0')
    style.configure('TCheckbutton',font=('Microsoft YaHei UI',10),background=SURFACE)
    style.configure('App.TCheckbutton',background=APP)
    style.map('TCheckbutton',background=[('active',SURFACE)],foreground=[('disabled','#8290A5')])
    style.map('App.TCheckbutton',background=[('active',APP)])
    style.configure('TEntry',fieldbackground=SURFACE,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,padding=(5,3))
    style.configure('TCombobox',fieldbackground=SURFACE,background=CARD,bordercolor=LINE,
                    lightcolor=LINE,darkcolor=LINE,arrowsize=13,padding=(5,3))
    style.map('TCombobox',fieldbackground=[('readonly',SURFACE)],selectbackground=[('readonly',SURFACE)],
              selectforeground=[('readonly',TEXT)])
    style.configure('Treeview',font=('Microsoft YaHei UI',10),rowheight=30,background=SURFACE,
                    fieldbackground=SURFACE,foreground=TEXT,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
    style.configure('Treeview.Heading',font=('Microsoft YaHei UI',10,'bold'),background='#303C4D',
                    foreground='#CDD6E5',padding=(7,5),relief='flat')
    style.map('Treeview',background=[('selected',SELECT)],foreground=[('selected','#FFF0D0')])
    style.map('Treeview.Heading',background=[('active','#3E4B5F')])
    style.configure('TNotebook',background=APP,borderwidth=0)
    style.configure('TNotebook.Tab',font=('Microsoft YaHei UI',10),padding=(9,5),background='#2F3A49',foreground=MUTED)
    style.map('TNotebook.Tab',background=[('selected',SURFACE)],foreground=[('selected',ACCENT)])
    style.configure('TLabelframe',background=SURFACE,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,relief='solid')
    style.configure('TLabelframe.Label',font=('Microsoft YaHei UI',10,'bold'),background=SURFACE,foreground='#CDD6E5')
    style.configure('TScrollbar',background='#4A586E',troughcolor=APP,bordercolor=SURFACE,
                    lightcolor='#4A586E',darkcolor='#4A586E',arrowsize=12)
    style.configure('TScale',background=ACCENT,troughcolor='#37465B',bordercolor=LINE)
    root.option_add('*TCombobox*Listbox.background',SURFACE)
    root.option_add('*TCombobox*Listbox.foreground',TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground',SELECT)
    root.option_add('*TCombobox*Listbox.selectForeground',TEXT)
    dark_titlebar(root)


def dark_titlebar(window):
    def paint():
        try:
            import ctypes as c
            from ctypes import wintypes as w
            user=c.WinDLL('user32');dwm=c.WinDLL('dwmapi')
            user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
            dwm.DwmSetWindowAttribute.argtypes=[w.HWND,w.DWORD,c.c_void_p,w.DWORD]
            hwnd=user.GetAncestor(window.winfo_id(),2);enabled=w.BOOL(True)
            dwm.DwmSetWindowAttribute(hwnd,20,c.byref(enabled),c.sizeof(enabled))
        except (OSError,AttributeError):pass
    window.after_idle(paint)


def tree_tags(tree):
    tree.tag_configure('alternate',background='#2B3543')
    tree.tag_configure('edited',foreground=SUCCESS)
    tree.tag_configure('confirmed',foreground=SUCCESS)


def detail_text(widget):
    widget.configure(background=SURFACE,foreground=TEXT,selectbackground=SELECT,selectforeground=TEXT,
                     padx=6,pady=4,highlightthickness=0,borderwidth=0)
