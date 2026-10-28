"""Tk presentation adapters keep canonical filter values and item data unchanged."""
import tkinter as native_tk
from tkinter import ttk as native_ttk
from types import SimpleNamespace
from localization import tr,register


class TextOptions:
    def __init__(self,master=None,**kwargs):
        self._raw_text=None;self._domain_var=None;self._view_var=None;self._trace=None
        if 'text' in kwargs:self._raw_text=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        variable=kwargs.get('textvariable')
        if isinstance(variable,native_tk.Variable):
            self._domain_var=variable;self._view_var=native_tk.StringVar(master=master,value=tr(variable.get()))
            self._trace=variable.trace_add('write',self._sync);kwargs['textvariable']=self._view_var
        super().__init__(master,**kwargs);register(self)

    def _sync(self,*_args):
        if self._view_var is not None:self._view_var.set(tr(self._domain_var.get()))

    def configure(self,cnf=None,**kwargs):
        if cnf and isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        if 'text' in kwargs:self._raw_text=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        return super().configure(cnf,**kwargs)
    config=configure

    def refresh_language(self):
        if self._raw_text is not None:super().configure(text=tr(self._raw_text))
        self._sync()

    def destroy(self):
        if self._trace:
            try:self._domain_var.trace_remove('write',self._trace)
            except native_tk.TclError:pass
            self._trace=None
        super().destroy()


class Label(TextOptions,native_ttk.Label):pass
class Button(TextOptions,native_ttk.Button):pass
class Checkbutton(TextOptions,native_ttk.Checkbutton):pass
class Radiobutton(TextOptions,native_ttk.Radiobutton):pass
class LabelFrame(TextOptions,native_ttk.LabelFrame):pass


class Combobox(native_ttk.Combobox):
    def __init__(self,master=None,**kwargs):
        self._guard=False;self._raw_values=tuple(kwargs.get('values',()))
        self._domain=kwargs.get('textvariable')
        if not isinstance(self._domain,native_tk.Variable):self._domain=native_tk.StringVar(master=master)
        self._display=native_tk.StringVar(master=master,value=tr(self._domain.get()))
        kwargs['textvariable']=self._display;kwargs['values']=tuple(tr(v) for v in self._raw_values)
        self._lookup={str(tr(v)):v for v in self._raw_values}
        super().__init__(master,**kwargs)
        self._domain_trace=self._domain.trace_add('write',self._sync)
        self._display_trace=self._display.trace_add('write',self._selected)
        register(self)

    def _sync(self,*_args):
        if self._guard:return
        self._guard=True
        try:self._display.set(tr(self._domain.get()))
        finally:self._guard=False

    def _selected(self,*_args):
        if self._guard:return
        value=self._display.get();self._guard=True
        try:self._domain.set(self._lookup.get(value,value))
        finally:self._guard=False

    def configure(self,cnf=None,**kwargs):
        if cnf and isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        if 'values' in kwargs:
            self._raw_values=tuple(kwargs['values']);self._lookup={str(tr(v)):v for v in self._raw_values}
            kwargs['values']=tuple(tr(v) for v in self._raw_values)
        return super().configure(cnf,**kwargs)
    config=configure
    def get(self):return self._domain.get()
    def set(self,value):self._domain.set(value)
    def refresh_language(self):
        self._lookup={str(tr(v)):v for v in self._raw_values}
        super().configure(values=tuple(tr(v) for v in self._raw_values));self._sync()
    def destroy(self):
        for variable,trace in [(self._domain,self._domain_trace),(self._display,self._display_trace)]:
            try:variable.trace_remove('write',trace)
            except native_tk.TclError:pass
        super().destroy()


class Treeview(native_ttk.Treeview):
    def __init__(self,*args,**kwargs):
        self._rows={};self._headings={};super().__init__(*args,**kwargs);register(self)
    def insert(self,parent,index,iid=None,**kwargs):
        original={k:kwargs[k] for k in ['values','text'] if k in kwargs}
        if 'values' in kwargs:kwargs['values']=tuple(tr(v) for v in kwargs['values'])
        if 'text' in kwargs:kwargs['text']=tr(kwargs['text'])
        result=super().insert(parent,index,iid,**kwargs);self._rows[result]=original;return result
    def delete(self,*items):
        for item in items:self._rows.pop(str(item),None)
        return super().delete(*items)
    def item(self,item,option=None,**kwargs):
        raw=self._rows.setdefault(str(item),{})
        for key in ['values','text']:
            if key in kwargs:
                raw[key]=kwargs[key];kwargs[key]=tuple(tr(v) for v in kwargs[key]) if key=='values' else tr(kwargs[key])
        result=super().item(item,option,**kwargs)
        if not kwargs:
            if option in raw:return raw[option]
            if option is None and isinstance(result,dict):result.update(raw)
        return result
    def set(self,item,column=None,value=None):
        columns=tuple(self.cget('columns'));raw=self._rows.get(str(item),{})
        if column in columns and 'values' in raw:
            values=list(raw['values']);index=columns.index(column)
            if value is None:return values[index] if index<len(values) else ''
            values.extend(['']*max(0,index+1-len(values)));values[index]=value;raw['values']=tuple(values)
            return super().set(item,column,tr(value))
        return super().set(item,column,value)
    def heading(self,column,option=None,**kwargs):
        if 'text' in kwargs:self._headings[column]=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        return super().heading(column,option,**kwargs)
    def refresh_language(self):
        for item,raw in self._rows.items():
            if self.exists(item):super().item(item,**{k:tuple(tr(v) for v in value) if k=='values' else tr(value) for k,value in raw.items()})
        for column,text in self._headings.items():super().heading(column,text=tr(text))


class Notebook(native_ttk.Notebook):
    def __init__(self,*args,**kwargs):self._labels={};super().__init__(*args,**kwargs);register(self)
    def add(self,child,**kwargs):
        if 'text' in kwargs:self._labels[str(child)]=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        return super().add(child,**kwargs)
    def insert(self,pos,child,**kwargs):
        if 'text' in kwargs:self._labels[str(child)]=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        return super().insert(pos,child,**kwargs)
    def tab(self,tab_id,option=None,**kwargs):
        if 'text' in kwargs:
            identity=self.tabs()[tab_id] if isinstance(tab_id,int) else str(tab_id)
            self._labels[identity]=kwargs['text'];kwargs['text']=tr(kwargs['text'])
        return super().tab(tab_id,option,**kwargs)
    def refresh_language(self):
        for child,text in self._labels.items():
            if child in self.tabs():super().tab(child,text=tr(text))


class Text(native_tk.Text):
    def __init__(self,*args,**kwargs):self._segments=[];super().__init__(*args,**kwargs);register(self)
    def insert(self,index,chars,*args):
        self._segments.append((chars,args));return super().insert(index,tr(chars),*args)
    def delete(self,index1,index2=None):self._segments=[];return super().delete(index1,index2)
    def refresh_language(self):
        state=self.cget('state');position=self.yview();super().configure(state='normal');super().delete('1.0','end')
        for chars,tags in self._segments:super().insert('end',tr(chars),*tags)
        super().configure(state=state)
        if position:self.yview_moveto(position[0])


class Canvas(native_tk.Canvas):
    def __init__(self,*args,**kwargs):self._texts={};super().__init__(*args,**kwargs);register(self)
    def create_text(self,*args,**kwargs):
        text=kwargs.get('text','');kwargs['text']=tr(text);item=super().create_text(*args,**kwargs);self._texts[item]=text;return item
    def delete(self,*args):
        if 'all' in args:self._texts={}
        else:
            for arg in args:self._texts.pop(arg,None)
        return super().delete(*args)
    def refresh_language(self):
        for item,text in self._texts.items():super().itemconfigure(item,text=tr(text))


class Toplevel(native_tk.Toplevel):
    def __init__(self,*args,**kwargs):
        self._raw_title='';super().__init__(*args,**kwargs);register(self)
    def title(self,string=None):
        if string is None:return super().title()
        self._raw_title=string;return super().title(tr(string))
    def refresh_language(self):super().title(tr(self._raw_title))


ttk=SimpleNamespace(**{k:getattr(native_ttk,k) for k in dir(native_ttk) if not k.startswith('__')})
for cls in [Label,Button,Checkbutton,Radiobutton,LabelFrame,Combobox,Treeview,Notebook]:setattr(ttk,cls.__name__,cls)
tk=SimpleNamespace(**{k:getattr(native_tk,k) for k in dir(native_tk) if not k.startswith('__')})
tk.Text=Text;tk.Canvas=Canvas
tk.Toplevel=Toplevel
