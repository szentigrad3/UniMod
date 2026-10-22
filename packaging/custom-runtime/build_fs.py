#!/usr/bin/env python3
"""Small SquashFS 4.0 writer for AppImage packaging; zlib and no fragments."""
import os, struct, zlib, sys, stat
from pathlib import Path
from dataclasses import dataclass, field
S=struct.Struct
U64MAX=0xffffffffffffffff
BLOCK=131072
@dataclass
class Node:
    path:Path
    name:str
    parent:object=None
    kids:list=field(default_factory=list)
    num:int=0
    index:int=0
    offset:int=0
    blob:bytes=b''
    data_offset:int=0
    data_len:int=0
    block_sizes:list=field(default_factory=list)
    dir_start:int=0
    dir_off:int=0
    dir_size:int=0
    mode:int=0
    kind:int=0

def metadata(data, compress=True):
    out=bytearray(); locations=[]
    for i in range(0,len(data),8192):
        locations.append(len(out))
        p=data[i:i+8192];z=zlib.compress(p,8)
        if compress and len(z)<len(p):out+=S('<H').pack(len(z))+z
        else:out+=S('<H').pack(len(p)|0x8000)+p
    return bytes(out),locations

def scan(root):
    nodes=[]
    def walk(path,parent):
        st=path.lstat();mode=stat.S_IMODE(st.st_mode)
        kind=1 if stat.S_ISDIR(st.st_mode) else 3 if stat.S_ISLNK(st.st_mode) else 2 if stat.S_ISREG(st.st_mode) else 0
        if not kind:raise ValueError('Not supported file kind '+str(path))
        n=Node(path,path.name,parent,mode=mode,kind=kind,num=len(nodes)+1)
        nodes.append(n)
        if kind==1:
            for p in sorted(path.iterdir(),key=lambda x:x.name):
                if p.name in ('.','..'):continue
                c=walk(p,n);n.kids.append(c)
        return n
    rootnode=walk(root,None)
    return rootnode,nodes

def pack(src,out_path):
    src=Path(src); root,nodes=scan(src)
    with open(out_path,'wb+') as out:
        out.write(b'\0'*96)
        # compression stores zlib streams per data block, with no fragments
        for n in nodes:
            if n.kind!=2:continue
            n.data_offset=out.tell(); n.data_len=n.path.stat().st_size
            with n.path.open('rb') as f:
                while chunk:=f.read(BLOCK):
                    z=zlib.compress(chunk,7)
                    if len(z)<len(chunk):b=z; size=len(z)
                    else:b=chunk;size=len(chunk)|0x1000000
                    out.write(b);n.block_sizes.append(size)
        # Allocate each inode's position in uncompressed metadata, then map to actual compressed block positions.
        offsets={};total=0
        for n in nodes:
            offsets[n.num]=total
            if n.kind==1:size=16+16
            elif n.kind==2:size=16+16+4*len(n.block_sizes)
            else:size=16+8+len(os.readlink(n.path).encode('utf-8'))
            total+=size
        # inode metadata block offsets require compressed inode bytes, and directory table contents use those.
        # The metadata block offsets depend on directory inode content; build repeatedly until stable.
        inode_block_locs=[0]*((total+8191)//8192)
        dirinfo={}
        for iteration in range(12):
            # Directory listing uses inode compressed block position & intra-block offset.
            listings={}
            for n in nodes:
                if n.kind!=1:continue
                content=bytearray()
                # Group children by the compressed inode-table metadata block holding their inode headers.
                groups=[]
                for c in n.kids:
                    idx=offsets[c.num]//8192
                    blk=inode_block_locs[idx]
                    if not groups or groups[-1][0]!=blk:groups.append((blk,[]))
                    groups[-1][1].append(c)
                for blk,children in groups:
                    content+=S('<III').pack(len(children)-1,blk,children[0].num)
                    for c in children:
                        name=c.name.encode('utf-8')
                        if len(name)>256:raise ValueError('Name too long: '+c.name)
                        off=offsets[c.num]%8192
                        delta=c.num-children[0].num
                        content+=S('<HhHH').pack(off,delta,c.kind,len(name)-1)+name
                listings[n.num]=bytes(content)
            # Treat directory listing as an uncompressed continuous stream; offsets are relative to table metadata blocks.
            # Full directory record spans metadata blocks naturally.
            dir_raw=bytearray();dir_offsets={}
            for n in nodes:
                if n.kind!=1:continue
                off=len(dir_raw)
                dir_offsets[n.num]=off
                dir_raw+=listings[n.num]
            dir_encoded,dir_block_locs=metadata(dir_raw)
            for n in nodes:
                if n.kind!=1:continue
                raw_off=dir_offsets[n.num]
                n.dir_start=dir_block_locs[raw_off//8192] if dir_block_locs else 0
                n.dir_off=raw_off%8192
                n.dir_size=len(listings[n.num])+3
                if n.dir_size>65535:raise ValueError('Directory exceeds max basic dir size: '+str(n.path))
            # Create inode metadata stream.
            inodes=bytearray()
            for n in nodes:
                parent=n.parent.num if n.parent else 0
                base=S('<HHHHII').pack(n.kind,n.mode,0,0,0,n.num)
                if n.kind==1:
                    ext=S('<IIHHI').pack(n.dir_start,len(n.kids)+2,n.dir_size,n.dir_off,parent)
                elif n.kind==2:
                    ext=S('<IIII').pack(n.data_offset,0xffffffff,0,n.data_len)+b''.join(S('<I').pack(sz) for sz in n.block_sizes)
                else:
                    target=os.readlink(n.path).encode('utf-8');ext=S('<II').pack(1,len(target))+target
                assert len(inodes)==offsets[n.num],(n.path,len(inodes),offsets[n.num])
                inodes+=base+ext
            inode_encoded,new_inode_locs=metadata(inodes,compress=False)
            if inode_block_locs==new_inode_locs:break
            inode_block_locs=new_inode_locs
        else:raise RuntimeError('inode location convergence failed')
        inode_start=out.tell();out.write(inode_encoded)
        dir_start=out.tell();out.write(dir_encoded)
        id_meta_start=out.tell();id_meta,locs=metadata(S('<I').pack(0));out.write(id_meta)
        id_pointer=out.tell();out.write(S('<Q').pack(id_meta_start))
        bytes_used=out.tell()
        out.write(b'\0'*(-out.tell()%4096))
        rootref=(inode_block_locs[offsets[root.num]//8192]<<16)|(offsets[root.num]%8192)
        superblock=S('<IIIIIHHHHHHQQQQQQQQ').pack(0x73717368,len(nodes),0,BLOCK,0,1,17,0x211,1,4,0,rootref,bytes_used,id_pointer,U64MAX,inode_start,dir_start,U64MAX,U64MAX)
        assert len(superblock)==96,len(superblock)
        out.seek(0);out.write(superblock)
    return len(nodes),os.path.getsize(out_path)

if __name__=='__main__':
    result=pack(sys.argv[1],sys.argv[2]);print('Packed SquashFS',result)
