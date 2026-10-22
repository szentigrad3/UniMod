#define _GNU_SOURCE
#define _XOPEN_SOURCE 700
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <string.h>
#include <errno.h>
#include <ftw.h>
#include <limits.h>
static int rm_cb(const char *path, const struct stat *st,int flag,struct FTW *ftwbuf){(void)st;(void)flag;(void)ftwbuf;return remove(path);}
static void cleanup(char *dir){if(dir)nftw(dir,rm_cb,20,FTW_DEPTH|FTW_PHYS);}
static int run(char *const args[]){pid_t pid=fork();if(pid<0)return -1;if(pid==0){execvp(args[0],args);_exit(127);}int status=0;if(waitpid(pid,&status,0)<0)return -1;return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);}
static void pathjoin(char *buf,size_t sz,const char *a,const char *b){if(snprintf(buf,sz,"%s/%s",a,b)>=(int)sz){fputs("UniMod: path too long\n",stderr);exit(2);}}
int main(int argc,char **argv){
    char self[PATH_MAX],dir[]="/tmp/.mount_unimod_T9_XXXXXX",gz[PATH_MAX],pyr[PATH_MAX],app[PATH_MAX],python[PATH_MAX],appfile[PATH_MAX],native[PATH_MAX],tl[PATH_MAX],tk[PATH_MAX];
    ssize_t n=readlink("/proc/self/exe",self,sizeof(self)-1);if(n<=0)return 2;self[n]=0;
    int fd=open(self,O_RDONLY);if(fd<0)return 2;
    off_t length=lseek(fd,0,SEEK_END);unsigned char tail[16];if(length<16 || lseek(fd,length-16,SEEK_SET)<0 || read(fd,tail,16)!=16 || memcmp(tail+8,"UniModT9",8)!=0){fputs("UniMod: missing payload\n",stderr);close(fd);return 2;}
    uint64_t amount=0;for(int k=0;k<8;k++)amount|=((uint64_t)tail[k])<<(k*8);
    if(amount<100||amount>120*1024*1024ULL||amount>(uint64_t)length-16){fputs("UniMod: invalid payload size\n",stderr);close(fd);return 2;}
    if(!mkdtemp(dir)){perror("mkdtemp");close(fd);return 2;}
    pathjoin(gz,sizeof(gz),dir,"payload.tar.gz");int target=open(gz,O_CREAT|O_EXCL|O_WRONLY,0600);if(target<0){close(fd);cleanup(dir);return 2;}
    if(lseek(fd,length-16-(off_t)amount,SEEK_SET)<0){close(fd);close(target);cleanup(dir);return 2;}
    uint64_t left=amount;char buf[131072];int err=0;
    while(left){size_t chunk=left>sizeof(buf)?sizeof(buf):(size_t)left;ssize_t x=read(fd,buf,chunk);if(x<=0){err=1;break;}size_t pos=0;while(pos<(size_t)x){ssize_t w=write(target,buf+pos,(size_t)x-pos);if(w<=0){err=1;break;}pos+=(size_t)w;}if(err)break;left-=(uint64_t)x;}
    close(fd);close(target);if(err){fputs("UniMod: failed to extract payload\n",stderr);cleanup(dir);return 2;}
    char *tarargs[]={"tar","--no-same-owner","--no-same-permissions","-xzf",gz,"-C",dir,NULL};
    int code=run(tarargs);unlink(gz);if(code!=0){fputs("UniMod: could not extract bundled runtime (tar required)\n",stderr);cleanup(dir);return 2;}
    pathjoin(pyr,sizeof(pyr),dir,"runtime");pathjoin(app,sizeof(app),dir,"app");pathjoin(python,sizeof(python),pyr,"bin/python3.13");pathjoin(appfile,sizeof(appfile),app,"unimod.py");pathjoin(native,sizeof(native),pyr,"libnative");
    pathjoin(tl,sizeof(tl),pyr,"share/tcltk/tcl8.6");pathjoin(tk,sizeof(tk),pyr,"share/tcltk/tk8.6");
    if(access(python,X_OK)!=0 || access(appfile,R_OK)!=0){cleanup(dir);fputs("UniMod: missing runtime files\n",stderr);return 2;}
    setenv("PYTHONHOME",pyr,1);setenv("PYTHONPATH",app,1);setenv("PYTHONNOUSERSITE","1",1);setenv("LD_LIBRARY_PATH",native,1);setenv("TCL_LIBRARY",tl,1);setenv("TK_LIBRARY",tk,1);
    if(!getenv("SSL_CERT_FILE")){
        const char *certs[]={"/etc/ssl/cert.pem","/etc/ssl/certs/ca-certificates.crt","/etc/pki/tls/certs/ca-bundle.crt"};
        for(int k=0;k<3;k++)if(access(certs[k],R_OK)==0){setenv("SSL_CERT_FILE",certs[k],1);break;}
    }
    if(chdir(app)<0){cleanup(dir);return 2;}
    char **cmd=calloc((size_t)argc+2,sizeof(char*));if(!cmd){cleanup(dir);return 2;}
    cmd[0]=python;cmd[1]=appfile;for(int i=1;i<argc;i++)cmd[i+1]=argv[i];cmd[argc+1]=NULL;
    code=run(cmd);free(cmd);cleanup(dir);return code;
}
