#define _GNU_SOURCE
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <zlib.h>
#include <time.h>

/* Preserve this marker in the ELF, then patch the 16 hexadecimal digits when packaging. */
volatile char unimod_payload_offset[] = "UNI_APPIMAGE_OFFSET=0000000000000000";
static FILE *image;
static uint64_t start;
static uint32_t data_block_size;
static unsigned char *idata, *ddata;
static size_t ilen, dlen;
static uint64_t *ip, *dp;
static int inb, dnb;
static const char *outdir;
typedef struct {uint16_t type, mode;uint32_t num;uint32_t parent, dsz, off, block;uint32_t data, fsz, nblocks; uint32_t*blocks;char*target;} Inode;
static Inode *inodes;static unsigned inode_count;
static uint16_t r16(const void*p){const unsigned char*b=p;return b[0]|(b[1]<<8);}
static uint32_t r32(const void*p){const unsigned char*b=p;return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
static uint64_t r64(const void*p){return (uint64_t)r32(p)|((uint64_t)r32((const unsigned char*)p+4)<<32);}
static void die(const char*s){fprintf(stderr,"UniMod AppImage runtime: %s (%s)\n",s,strerror(errno));exit(3);}
static void seekat(uint64_t pos){if(fseeko(image,(off_t)(start+pos),SEEK_SET))die("Cannot seek AppImage payload");}
static void getat(uint64_t pos,void*ptr,size_t n){seekat(pos);if(fread(ptr,1,n,image)!=n)die("Cannot read AppImage payload");}
static int inflateblock(const unsigned char*src,size_t srcsz,unsigned char*dst,unsigned long*dstsz){return uncompress(dst,dstsz,src,srcsz);}
static unsigned char *readmeta(uint64_t from,uint64_t to,size_t *length,uint64_t **locations,int*count){
    unsigned char*out=NULL;size_t size=0,cap=0;uint64_t*loc=NULL;int n=0;
    while(from<to){
        unsigned char hd[2];getat(from,hd,2);uint16_t h=r16(hd);int raw=h&0x8000;size_t bs=h&0x7fff;
        if(bs==0||bs>8192||from+2+bs>to)die("Invalid SquashFS metadata block");
        unsigned char input[8192],unpacked[8192];getat(from+2,input,bs);
        unsigned long dstlen=8192;
        if(raw){memcpy(unpacked,input,bs);dstlen=bs;}
        else if(inflateblock(input,bs,unpacked,&dstlen)!=Z_OK)die("Corrupt SquashFS metadata compression");
        if(size+dstlen>cap){cap=(size+dstlen)*2+4096;out=realloc(out,cap);if(!out)die("Out of memory");}
        memcpy(out+size,unpacked,dstlen);size+=dstlen;
        loc=realloc(loc,(n+1)*sizeof(uint64_t));if(!loc)die("Out of memory");loc[n++]=from;
        from+=2+bs;
    }
    *length=size;*locations=loc;*count=n;return out;
}
static unsigned lookup_block(uint64_t*loc,int count,uint32_t ref){for(int i=0;i<count;i++)if((uint32_t)loc[i]==ref)return i;fprintf(stderr,"Block ref %u count=%d first=%llu\n",ref,count,(unsigned long long)(count?loc[0]:0));die("Invalid SquashFS inode or directory block reference");return 0;}
static void parse_inodes(void){
    inodes=calloc(inode_count+1,sizeof(Inode));if(!inodes)die("Out of memory");size_t at=0;
    for(unsigned i=1;i<=inode_count;i++){
        if(at+16>ilen)die("Short inode metadata");unsigned char*p=idata+at;
        Inode*n=&inodes[i];n->type=r16(p);n->mode=r16(p+2);n->num=r32(p+12);
        if(n->num!=i)die("Inode index mismatch");at+=16;
        if(n->type==1){
            if(at+16>ilen)die("Short directory inode");p=idata+at;n->block=r32(p);n->dsz=r16(p+8);n->off=r16(p+10);n->parent=r32(p+12);at+=16;
        }else if(n->type==2){
            if(at+16>ilen)die("Short file inode");p=idata+at;n->data=r32(p);if(r32(p+4)!=0xffffffff)die("Fragments unsupported");n->fsz=r32(p+12);at+=16;
            n->nblocks=(n->fsz+data_block_size-1)/data_block_size;
            if(at+4*(uint64_t)n->nblocks>ilen)die("Invalid file block count");
            n->blocks=calloc(n->nblocks?n->nblocks:1,4);if(!n->blocks)die("Out of memory");
            for(uint32_t j=0;j<n->nblocks;j++)n->blocks[j]=r32(idata+at+4*j);
            at+=4*n->nblocks;
        }else if(n->type==3){
            if(at+8>ilen)die("Short symlink inode");p=idata+at;uint32_t len=r32(p+4);at+=8;
            if(len>PATH_MAX||at+len>ilen)die("Invalid symlink");n->target=calloc(len+1,1);
            memcpy(n->target,idata+at,len);at+=len;
            if(n->target[0]=='/'||strstr(n->target,"../"))die("Unsafe symlink in AppImage");
        }else die("Unsupported SquashFS inode type");
    }
}
static void makedir(const char*p,mode_t mode){if(mkdir(p,mode) && errno!=EEXIST)die("Cannot create extraction directory");}
static void extractfile(Inode*n,const char*p){
    int fd=open(p,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,n->mode?n->mode:0644);if(fd<0)die("Cannot create extracted file");
    uint64_t offset=n->data;unsigned char packed[131072],raw[131072];size_t rest=n->fsz;
    for(unsigned j=0;j<n->nblocks;j++){
        uint32_t encoded=n->blocks[j];size_t sz=encoded&0xffffff;size_t want=rest<data_block_size?rest:data_block_size;
        if(sz==0||sz>data_block_size)die("Invalid data block size");
        getat(offset,packed,sz);offset+=sz;
        if(encoded&0x1000000){if(sz!=want)die("Bad uncompressed block length");memcpy(raw,packed,want);}
        else {unsigned long outlen=sizeof(raw);if(inflateblock(packed,sz,raw,&outlen)!=Z_OK||outlen!=want)die("Bad compressed data block");}
        if(write(fd,raw,want)!=(ssize_t)want)die("Could not write extracted block");rest-=want;
    }
    if(rest)die("Short data for file");close(fd);
}
static void unpack_directory(unsigned id,const char*path,unsigned depth){
    if(depth>50)die("Excessive directory depth");Inode*n=&inodes[id];
    if(n->type!=1)die("Expected directory");makedir(path,n->mode?n->mode:0755);
    if(n->dsz<=3)return;
    unsigned b=lookup_block(dp,dnb,n->block);size_t at=(size_t)b*8192+n->off;size_t stop=at+(size_t)n->dsz-3;
    if(stop>dlen)die("Invalid directory listing");
    while(at<stop){
        if(at+12>stop)die("Short directory header");uint32_t count=r32(ddata+at)+1;uint32_t blk=r32(ddata+at+4);uint32_t first=r32(ddata+at+8);at+=12;
        if(count>inode_count)die("Invalid directory entry count");
        for(uint32_t j=0;j<count;j++){
            if(at+8>stop)die("Short directory entry");uint16_t off=r16(ddata+at);int16_t delta=(int16_t)r16(ddata+at+2);uint16_t type=r16(ddata+at+4);uint16_t len=r16(ddata+at+6)+1;at+=8;
            if(len>255||at+len>stop)die("Invalid directory entry name");char name[260]={0};memcpy(name,ddata+at,len);at+=len;
            if(strchr(name,'/')||!strcmp(name,".")||!strcmp(name,".."))die("Unsafe directory entry");
            int id=(int)first+delta;
            if(id<1||id>(int)inode_count||inodes[id].type!=type)die("Directory entry references invalid inode");
            char outpath[PATH_MAX];if(snprintf(outpath,sizeof(outpath),"%s/%s",path,name)>=(int)sizeof(outpath))die("Path too long");
            Inode *child=&inodes[id];
            if(type==1)unpack_directory(id,outpath,depth+1);
            else if(type==2)extractfile(child,outpath);
            else if(type==3){if(symlink(child->target,outpath))die("Cannot create symlink");}
        }
    }
}
static void remove_tree(const char*dir){DIR*d=opendir(dir);if(!d)return;struct dirent*entry;
    while((entry=readdir(d))){if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
        char path[PATH_MAX];if(snprintf(path,sizeof(path),"%s/%s",dir,entry->d_name)>=(int)sizeof(path))continue;
        struct stat st;if(lstat(path,&st))continue;if(S_ISDIR(st.st_mode))remove_tree(path);else unlink(path);
    }closedir(d);rmdir(dir);
}

/* AppImage-local v0.43 overlay: two fixed, source-built application files. */
static void apply_source_overlay(const char *dest,uint64_t payload_used){
    const char *names[]={"unimod.py","smapi_catalogue.py"};
    unsigned char magic[16];
    if(fseeko(image,(off_t)(start+((payload_used+4095)&~4095ULL)),SEEK_SET))die("Missing overlay");
    if(fread(magic,1,16,image)!=16||memcmp(magic,"UNIMOD_OVERLAY43",16))die("Invalid v0.43 overlay");
    for(unsigned int i=0;i<2;i++){
        unsigned char n[4];if(fread(n,1,4,image)!=4)die("Truncated overlay header");
        uint32_t count=r32(n);
        if(count==0||count>1000000)die("Invalid overlay size");
        char filename[PATH_MAX];
        if(snprintf(filename,sizeof(filename),"%s/usr/share/unimod/%s",dest,names[i])>=(int)sizeof(filename))die("Overlay path too long");
        int fd=open(filename,O_CREAT|O_WRONLY|O_TRUNC|O_NOFOLLOW,0644);
        if(fd<0)die("Cannot install bundled overlay");
        unsigned char buf[32768];
        while(count){size_t chunk=count>sizeof(buf)?sizeof(buf):count;
            if(fread(buf,1,chunk,image)!=chunk||write(fd,buf,chunk)!=(ssize_t)chunk)die("Corrupt overlay");
            count-=chunk;}
        if(close(fd)!=0)die("Cannot finish bundled overlay");
    }
}

int main(int argc,char**argv){
    char *num=strchr((char*)unimod_payload_offset,'=');if(!num)die("Missing image offset marker");start=strtoull(num+1,NULL,16);
    if(start<4096)die("Unpatched AppImage runtime");
    image=fopen("/proc/self/exe","rb");if(!image)die("Cannot open executable image");
    unsigned char sb[96];getat(0,sb,sizeof sb);
    if(r32(sb)!=0x73717368||r16(sb+28)!=4||r16(sb+30)!=0)die("Invalid SquashFS superblock");
    inode_count=r32(sb+4);data_block_size=r32(sb+12);
    if(!inode_count||inode_count>100000||data_block_size!=131072)die("Unsupported filesystem configuration");
    uint64_t used=r64(sb+40),id_pointer=r64(sb+48),inode_start=r64(sb+64),dir_start=r64(sb+72);
    if(used<96||id_pointer<6||inode_start>=dir_start||dir_start>=id_pointer)die("Invalid filesystem section offsets");
    idata=readmeta(inode_start,dir_start,&ilen,&ip,&inb);
    ddata=readmeta(dir_start,id_pointer-6,&dlen,&dp,&dnb);
    for(int k=0;k<inb;k++)ip[k]-=inode_start;
    for(int k=0;k<dnb;k++)dp[k]-=dir_start;
    parse_inodes();
    int extract=0;for(int i=1;i<argc;i++){
        if(!strcmp(argv[i],"--appimage-offset")){printf("%llu\n",(unsigned long long)start);return 0;}
        if(!strcmp(argv[i],"--appimage-extract"))extract=1;
    }
    char path[PATH_MAX];
    if(extract){if(!getcwd(path,sizeof(path)))die("Cannot find current directory");strncat(path,"/squashfs-root",sizeof(path)-strlen(path)-1);
        if(access(path,F_OK)==0)die("squashfs-root already exists");
    } else {
        const char*tmp=getenv("TMPDIR");if(!tmp||!*tmp)tmp="/tmp";
        if(snprintf(path,sizeof(path),"%s/.mount_unimod_XXXXXX",tmp)>=(int)sizeof(path))die("TMPDIR path too long");
        if(!mkdtemp(path))die("Cannot create temporary directory");
        /* Unpack below into temporary directory. */
    }
    unpack_directory(1,path,0);apply_source_overlay(path,used);fclose(image);
    if(extract){puts("squashfs-root");return 0;}
    char runpath[PATH_MAX];snprintf(runpath,sizeof(runpath),"%s/AppRun",path);
    pid_t child=fork();if(child<0)die("Cannot fork");
    if(!child){setenv("APPDIR",path,1);char exe[PATH_MAX];ssize_t bytes=readlink("/proc/self/exe",exe,sizeof(exe)-1);if(bytes>0){exe[bytes]=0;setenv("APPIMAGE",exe,1);}
        char**args=calloc(argc+1,sizeof(char*));args[0]=runpath;for(int j=1;j<argc;j++)args[j]=argv[j];
        execv(runpath,args);die("Cannot launch bundled AppRun");
    }
    int status;while(waitpid(child,&status,0)<0){if(errno!=EINTR)die("Failed waiting for application");}
    remove_tree(path);if(WIFEXITED(status))return WEXITSTATUS(status);
    if(WIFSIGNALED(status))return 128+WTERMSIG(status);return 1;
}
