"""Read UE object and property metadata using independently verified session globals.

No write, allocation, injection, function invocation, or network capability.
Addresses are specific to the observed running process and validated on entry.
"""
import ctypes as c
import argparse
from ctypes import wintypes as w
import json
from pathlib import Path
import re
import struct
import time

ROOT=Path(__file__).resolve().parent


class ReadOnlyUE:
    def __init__(self,calibration=None):
        self.k=c.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];self.k.OpenProcess.restype=w.HANDLE
        self.k.ReadProcessMemory.argtypes=[w.HANDLE,c.c_void_p,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
        self.k.ReadProcessMemory.restype=w.BOOL
        self.k.CloseHandle.argtypes=[w.HANDLE]
        calibration_path=ROOT/'runtime_calibration.json'
        if calibration is None and calibration_path.exists():
            calibration=json.loads(calibration_path.read_bytes())
        self.pid=calibration['pid'] if calibration else json.loads((ROOT/'live_scan_01.json').read_bytes())['pid']
        self.h=self.k.OpenProcess(0x410,False,self.pid)
        if not self.h:raise c.WinError(c.get_last_error())
        try:
            if calibration:
                self.pool=int(calibration['fname_blocks'],16)
                self.array=int(calibration['object_array'],16)
                self.k.GetProcessTimes.argtypes=[w.HANDLE]+[c.POINTER(c.c_uint64)]*4
                self.k.GetProcessTimes.restype=w.BOOL
                times=[c.c_uint64() for _ in range(4)]
                if not self.k.GetProcessTimes(self.h,*[c.byref(t) for t in times]):raise c.WinError(c.get_last_error())
                if str(times[0].value)!=calibration['process_creation_id']:raise RuntimeError('Runtime calibration belongs to a different process generation')
            else:
                pools=json.loads((ROOT/'fname_pool_candidates.json').read_bytes())
                self.pool=int(pools[0]['possible_block_arrays'][0]['array_address'],16)
                arrays=json.loads((ROOT/'uobject_array_candidates.json').read_bytes())
                self.array=int(next(x['array'] for x in arrays if x['verified']),16)
            self.name_cache={};self.class_cache={}
            if self.name(0)!='None':raise RuntimeError('Name pool validation failed')
        except Exception:
            self.close();raise

    def close(self):self.k.CloseHandle(self.h)

    def read(self,addr,n):
        if not 0x10000<addr<0x7fffffffffff or not 0<n<16*1024*1024:return b''
        buf=c.create_string_buffer(n);got=c.c_size_t()
        self.k.ReadProcessMemory(self.h,c.c_void_p(addr),buf,n,c.byref(got))
        return buf.raw[:got.value]

    def ptr(self,addr):
        b=self.read(addr,8)
        return struct.unpack('<Q',b)[0] if len(b)==8 else 0

    def name(self,index,number=0):
        if index not in self.name_cache:
            block=self.ptr(self.pool+(index>>16)*8)
            raw=self.read(block+(index&65535)*2,2)
            if len(raw)!=2:return '<unreadable>'
            header=struct.unpack('<H',raw)[0];length=header>>6
            if not 0<length<=1024:return '<invalid>'
            b=self.read(block+(index&65535)*2+2,length*(2 if header&1 else 1))
            self.name_cache[index]=b.decode('utf-16le' if header&1 else 'utf-8',errors='replace')
        return self.name_cache[index]+('_'+str(number-1) if number else '')

    def object(self,ptr):
        b=self.read(ptr,40)
        if len(b)!=40:return None
        vt,flags,index,cls,ni,nn,outer=struct.unpack('<QIiQIIQ',b)
        if cls not in self.class_cache:
            cb=self.read(cls,32)
            self.class_cache[cls]=self.name(*struct.unpack_from('<II',cb,24)) if len(cb)==32 else '<unreadable>'
        return {'address':hex(ptr),'vtable':hex(vt),'flags':hex(flags),'object_index':index,
                'name':self.name(ni,nn),'class':self.class_cache[cls],
                'class_address':hex(cls),'outer':hex(outer)}

    def properties(self,cls):
        classes=set();out=[]
        while cls and cls not in classes:
            classes.add(cls);b=self.read(cls,0x60)
            if len(b)<0x60:break
            ni,nn=struct.unpack_from('<II',b,0x18);clsname=self.name(ni,nn)
            sup,children,fields=struct.unpack_from('<QQQ',b,0x40)
            size=struct.unpack_from('<i',b,0x58)[0]
            seen=set();field=fields
            while field and field not in seen and len(seen)<2048:
                seen.add(field);f=self.read(field,0x58)
                if len(f)<0x58:break
                fieldclass=struct.unpack_from('<Q',f,8)[0]
                nxt=struct.unpack_from('<Q',f,0x20)[0]
                ni,nn=struct.unpack_from('<II',f,0x28)
                arraydim,elementsize=struct.unpack_from('<ii',f,0x38)
                offset=struct.unpack_from('<i',f,0x4c)[0]
                typ=self.read(fieldclass,8)
                typename=self.name(*struct.unpack('<II',typ)) if len(typ)==8 else '<unreadable>'
                if 0<=offset<size and 0<elementsize<1024*1024 and 0<arraydim<65536:
                    out.append({'declaring_class':clsname,'property':self.name(ni,nn),'type':typename,
                                'offset':offset,'element_size':elementsize,'array_dim':arraydim,
                                'metadata_address':hex(field)})
                field=nxt
            cls=sup
        return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,default=ROOT/'ue_runtime_objects_after_swap.json')
    ap.add_argument('--summary-only',action='store_true')
    args=ap.parse_args()
    ue=ReadOnlyUE();started=time.monotonic();found=[];props={}
    try:
        raw=ue.read(ue.array,32);chunks,pre,maxe,nume,maxc,numc=struct.unpack('<QQiiii',raw)
        ptrs=ue.read(chunks,numc*8)
        relevant=re.compile(r'Arsenal|Boar|SilvermanePrime|PlayerSession|APInventory|APEquipment|APAttributeSet|PlayerController|PlayerCharacter|BP_PlayerState|APLoadout|TrainingDummy|Training_Dummy')
        for ci in range(numc):
            chunk=struct.unpack_from('<Q',ptrs,ci*8)[0]
            count=min(65536,nume-ci*65536)
            items=ue.read(chunk,count*24)
            for i in range(count):
                ptr=struct.unpack_from('<Q',items,i*24)[0]
                if not ptr:continue
                b=ue.read(ptr,40)
                if len(b)!=40:continue
                cls=struct.unpack_from('<Q',b,16)[0]
                if cls not in ue.class_cache:
                    cb=ue.read(cls,32)
                    ue.class_cache[cls]=ue.name(*struct.unpack_from('<II',cb,24)) if len(cb)==32 else '<unreadable>'
                classname=ue.class_cache[cls]
                if not relevant.search(classname):continue
                obj=ue.object(ptr)
                if not obj or obj['object_index']!=ci*65536+i:continue
                if cls not in props:props[cls]=ue.properties(cls)
                obj['values']=[]
                for p in props[cls]:
                    if re.search(r'APAttributeSet|PlayerSession|Boar|Arsenal|SilvermanePrime',classname) and p['declaring_class'] not in ['Object','Actor','ActorComponent','SceneComponent','PrimitiveComponent','Pawn','Character']:
                        n=min(p['element_size']*p['array_dim'],64)
                        b=ue.read(ptr+p['offset'],n)
                        v={k:p[k] for k in ['declaring_class','property','type','offset','element_size']}
                        v['bytes_hex']=b.hex()
                        if len(b)%4==0 and b:
                            floats=struct.unpack('<'+'f'*(len(b)//4),b)
                            v['float32_values']=[x if abs(x)<1e15 else None for x in floats]
                        obj['values'].append(v)
                found.append(obj)
            print(json.dumps({'event':'chunk_complete','chunk':ci,'objects_considered':min((ci+1)*65536,nume),'found':len(found)}),flush=True)
        result={'pid':ue.pid,'access':'QUERY_INFORMATION | VM_READ only','elapsed_seconds':round(time.monotonic()-started,2),
                'object_count':nume,'objects':found,'class_properties':{hex(k):v for k,v in props.items()},
                'limitation':'Reflection fields and values are observations. No editing or effect validation performed.'}
        args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({'found':len(found),'classes':len(props),'elapsed_seconds':result['elapsed_seconds']}),flush=True)
        for obj in ([] if args.summary_only else found):
            if not obj['name'].startswith('Default__'):
                print(json.dumps({k:v for k,v in obj.items() if k!='values'},ensure_ascii=True))
    finally:ue.close()


if __name__=='__main__':main()
