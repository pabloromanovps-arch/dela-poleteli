import numpy as np, json, os, sys
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter1d, uniform_filter1d, gaussian_filter
W,H=1920,384; PITCH=12
def hexc(h): h=h.lstrip('#'); return np.array([int(h[i:i+2],16) for i in (0,2,4)],np.float32)/255
def s2l(x): return np.where(x<=0.04045,x/12.92,((x+0.055)/1.055)**2.4)
def l2s(x): x=np.clip(x,0,1); return np.where(x<=0.0031308,x*12.92,1.055*x**(1/2.4)-0.055)
def luma(im): return im@np.array([0.2126,0.7152,0.0722],np.float32)
TEAL=hexc('#002935'); DEEP=hexc('#00151C'); FROST=hexc('#7C9795'); FROSTHI=hexc('#A4B9B5'); GOLD=hexc('#C9A961'); FIRE=hexc('#F0D6A0'); TEXT=hexc('#F4EFE4')
PL_BG=[hexc(c) for c in ('#2F4348','#3A4A4A','#33474F','#3D4B47','#2C4046')]
FIG=[hexc(c) for c in ('#C79A7E','#D8D0BC','#7C8F93','#A9795F','#E6C9A8')]
rng=np.random.RandomState(26)
tone=[int(i) for i in np.random.RandomState(7).permutation(35)%5]
CX=[192,499.2,729.6,960,1190.4,1420.8,1728]
SECY=[0,-14,10,-6,14,-10,6]; SECX=[0,4,-5,0,5,-4,0]
def slots(w,h,pitch,tier_gap,top_up,top_lo):
    out=[]
    for s,cx in enumerate(CX):
        cx=cx+SECX[s]; dy=SECY[s]
        for k,dx in enumerate((-pitch,0,pitch)): out.append((cx+dx,top_lo+dy+(k%2)*5))
        for k,dx in enumerate((-pitch/2,pitch/2)): out.append((cx+dx,top_up+dy-(k%2)*6))
    return out  # centre x, top y
UW,UH=56,70           # underlay (shadow) size
UND=slots(UW,UH,62,0,66,168)
LW,LH=60,107          # final leaf 9:16
LEAF=slots(LW,LH,66,0,48,172)
def figure_plate(i,w,h,lampx=True):
    ww,hh=int(w),int(h); yy,xx=np.mgrid[0:hh,0:ww]; u=(xx+0.5)/ww*2-1; v=(yy+0.5)/hh
    bg=PL_BG[tone[i]][None,None,:]*(1.15-0.35*v)[...,None]
    off=((i*37)%11-5)/60
    head=((u-off)/0.20)**2+((v-0.34*(70/h if h<80 else 1)*(h/70 if h<80 else 1))/0.14)**2<1
    head=((u-off)/0.20)**2+((v-0.34)/0.14)**2<1
    body=(((u-off)/0.62)**2+((v-0.98)/0.52)**2<1)&(v>0.5)
    fig=gaussian_filter((head|body).astype(np.float32),0.7)[...,None]
    col=FIG[tone[i]][None,None,:]*(1.08-0.3*v)[...,None]
    return bg*(1-fig)+col*fig
def lamp_pos(i,x,top,w,h): return (x+w*0.30, top+h*0.26)
def draw_lamp(img,cx,cy,r=2.6,scale=1.0,col=None,strength=1.0):
    yy,xx=np.mgrid[0:H,0:W]
    d=np.sqrt((xx-cx)**2+(yy-cy)**2); m=np.clip(r+0.5-d,0,1)[...,None]*strength
    col=FIRE if col is None else col
    img[:]=img*(1-m)+col*m
def bg_world(sharp=False,w0=1.0,w1=0.5):
    y=np.linspace(0,1,H)[:,None,None]; x=np.linspace(0,1,W)[None,:,None]
    base=TEAL[None,None,:]*(0.5+0.9*np.exp(-((y-0.34)/0.30)**2))
    if sharp:
        n=gaussian_filter(np.random.RandomState(3).randn(H,W),(0.6,0.4)); base=base*(w0+w1*np.exp(-((y-0.34)/0.3)**2))*(1+0.05*n[...,None])
    return np.clip(base,0,1)
def underlay_lin(include_lamps=True):
    img=l2s(s2l(bg_world(False))); 
    layer=np.zeros((H,W,3),np.float32); a=np.zeros((H,W),np.float32)
    for i,(cx,top) in enumerate(UND):
        p=figure_plate(i,UW,UH); x0=int(round(cx-UW/2)); y0=int(round(top))
        layer[y0:y0+UH,x0:x0+UW]=p; a[y0:y0+UH,x0:x0+UW]=1
    base=img*(1-a[...,None])+layer*a[...,None]
    base=base.copy()
    lamps=[]
    for i,(cx,top) in enumerate(UND):
        lx,ly=lamp_pos(i,cx-UW/2,top,UW,UH); lamps.append((lx,ly))
    lin=s2l(base)
    if include_lamps:
        yy,xx=np.mgrid[0:H,0:W]
        for (lx,ly) in lamps:
            d=np.sqrt((xx-lx)**2+(yy-ly)**2); m=np.clip(3.0+0.5-d,0,1)[...,None]
            lin=lin*(1-m)+s2l(FIRE)[None,None,:]*LAMP*m
    return lin,lamps
def glass(lin,A=5,bh=5,bv=7,lift=0.03,gain=0.9,tri=0.65,seed=11):
    out=uniform_filter1d(lin,bh|1,axis=1,mode='nearest'); out=uniform_filter1d(out,bh|1,axis=1,mode='nearest')
    out=gaussian_filter1d(out,bv,axis=0,mode='nearest')
    xs=np.arange(W); u=(xs%PITCH)/PITCH; sh=A*np.sin(2*np.pi*u)
    src=np.clip(xs+sh,0,W-1); i0=np.floor(src).astype(int); i1=np.minimum(i0+1,W-1); f=(src-i0)[None,:,None]
    out=out[:,i0]*(1-f)+out[:,i1]*f
    s=l2s(out); l=luma(s)[...,None]
    tg=np.where(l<0.5,DEEP+(FROST-DEEP)*(l/0.5),FROST+(FROSTHI-FROST)*np.clip((l-0.5)/0.5,0,1))
    # keep warmth of fires: tritone weight reduced where warm
    warm=np.clip((s[...,0]-s[...,2])*4,0,1)[...,None]
    t=tri*(1-0.7*warm)
    o=s*(1-t)+tg*t*(0.5+l)
    o=o*gain+lift
    n=np.random.RandomState(seed).randn(H,W,1)*0.006
    return np.clip(o+n,0,1)
def bevel_window(img,content,x0,y0,x1,y1,wb,glow=1.0):
    X0,Y0,X1,Y1=[int(round(v)) for v in (x0,y0,x1,y1)]
    X0c,X1c=max(X0,0),min(X1,W); Y0c,Y1c=max(Y0,0),min(Y1,H)
    img[Y0c:Y1c,X0c:X1c]=content[Y0c:Y1c,X0c:X1c]
    yy,xx=np.mgrid[Y0c:Y1c,X0c:X1c]
    dl=xx-X0; dr=X1-1-xx; dt=yy-Y0; db=Y1-1-yy
    stack=np.stack([dl,dt,dr,db]); d=stack.min(0); which=stack.argmin(0)
    inb=d<wb; u=np.clip((wb-d)/wb,0,1)   # 1 outer edge
    # refraction: sample content mirrored across inner edge (edge shows compressed neighbour pixels)
    sx=np.where(which==0,X0+wb+(wb-dl)*0.8,np.where(which==2,X1-1-wb-(wb-dr)*0.8,xx)).astype(int)
    sy=np.where(which==1,Y0+wb+(wb-dt)*0.8,np.where(which==3,Y1-1-wb-(wb-db)*0.8,yy)).astype(int)
    sx=np.clip(sx,0,W-1); sy=np.clip(sy,0,H-1)
    refr=content[sy,sx]
    lit=np.where(which<2,1.0,0.0)
    gain=np.where(lit>0,1.0+0.55*np.clip(1-np.abs(u-0.3)/0.5,0,1),0.45-0.15*u)[...,None]
    warm=np.where(lit>0,0.22*np.clip(1-np.abs(u-0.3)/0.5,0,1),0)[...,None]
    fac=refr*gain*glow+FIRE*warm*glow
    # outer 1-2px crisp edge: a thin warm-light line only on lit facets
    edge=((d<=1)&(lit>0))[...,None]*0.5
    fac=fac+FIRE*edge
    reg=img[Y0c:Y1c,X0c:X1c]; reg[:]=np.where(inb[...,None],np.clip(fac,0,1),reg)
    gx=np.exp(-(((xx-(X0+wb*3))/(wb*5))**2))*np.exp(-(((yy-(Y0+wb*0.5))/(wb*0.6))**2))
    reg[:]=np.clip(reg+FIRE*gx[...,None]*0.40,0,1)
def stats(arr):
    l=luma(arr.astype(np.float32)); r,g,b=[arr[...,i].astype(np.float32) for i in range(3)]
    return dict(dark=round(float(np.mean(l<40))*100,1),mid=round(float(np.mean((l>=40)&(l<150)))*100,1),light=round(float(np.mean((l>=150)&(l<=235)))*100,2),peak=round(float(np.mean(l>235))*100,3),mean=round(float(l.mean()),1),warm=round(float(np.mean(r-b>=40))*100,2))
OUT='/home/user/dela-poleteli/projects/pz26_nagrazhdenie/03_style/thumbs/'
def save(name,img):
    a=(np.clip(img,0,1)*255+0.5).astype(np.uint8); Image.fromarray(a).save(OUT+name); return a
LAMP=7.0
KEYX=672
def key_layer(tipx,tipy,L=210):
    S=4; im=Image.new('L',(W*S,H*S),0); d=ImageDraw.Draw(im); ang=np.deg2rad(5); dx,dy=np.sin(ang),np.cos(ang)
    def pt(t,off): return ((tipx-dx*t+dy*off)*S,(tipy-dy*t-dx*off)*S)
    d.polygon([pt(10,-3),pt(L-30,-3),pt(L-30,3),pt(10,3)],fill=255)
    for (t0,t1,o) in ((0,9,6),(12,20,8),(24,30,5)): d.polygon([pt(t0,3),pt(t1,3),pt(t1,3+o),pt(t0,3+o)],fill=255)
    d.polygon([pt(0,-3),pt(0,9),pt(10,9),pt(10,-3)],fill=255)
    cx,cy=pt(L+8,0); d.ellipse([cx-22*S,cy-22*S,cx+22*S,cy+22*S],outline=255,width=7*S)
    return np.asarray(im.resize((W,H),Image.LANCZOS)).astype(np.float32)/255
def add_key(img,tipx,tipy):
    a=key_layer(tipx,tipy); yy=np.arange(H)[:,None]
    dist=np.clip((tipy-yy)/200,0,1); ab=gaussian_filter(a,(5,3)); aa=a*(1-dist)+ab*dist
    t=np.clip((tipy-yy)/215,0,1)[...,None]
    col=(GOLD*0.62)*(1-t)+np.array([0.05,0.12,0.14])*t; col=np.broadcast_to(col,(H,W,3)).copy()
    yy2,xx2=np.mgrid[0:H,0:W]; g=np.exp(-(((xx2-tipx)/5)**2+((yy2-tipy+3)/8)**2))[...,None]*a[...,None]
    col=col*(1-g)+hexc('#F6E4B8')*g
    img[:]=img*(1-aa[...,None]*0.95)+col*aa[...,None]*0.95
def k1(P):
    lin,l=underlay_lin(); img=glass(lin,**P); add_key(img,KEYX,150); return img
def k2(P):
    lin,l=underlay_lin(); img=glass(lin,**P)
    wx0,wx1,wy0,wy1=164,714,37,347
    # trail: weaker glass strip to the left of window
    weak=glass(lin,A=3,bh=3,bv=3.5,**{k:v for k,v in P.items() if k not in('A','bh','bv')})
    tr=np.zeros((H,W),np.float32)
    for k in range(200):
        xx=wx0-k; 
        if xx<0: break
        tr[wy0+30:wy1-30,xx]=0.9**(k/14)
    tr=gaussian_filter(tr,(4,3))[...,None]*0.85
    img=img*(1-tr)+weak*tr
    # content: neutral b-roll plate, wide continuous layer
    yy=np.linspace(0,1,H)[:,None,None]; xx=np.linspace(0,1,W)[None,:,None]
    plate=hexc('#85837A')[None,None,:]*(1.12-0.45*yy)*(1-0.15*((xx-0.2)/0.3)**2)+0*xx
    plate=np.broadcast_to(plate,(H,W,3)).copy()
    # warm lamp inside plate (b-roll detail: brass lamp glint) left-centre
    draw_lamp(plate,300,110,5,strength=1.0)
    # remaining fires
    bevel_window(img,plate,wx0,wy0,wx1,wy1,6)
    # label
    im=Image.fromarray((np.clip(img,0,1)*255).astype(np.uint8)); d=ImageDraw.Draw(im)
    f=ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-Medium.otf',9)
    d.text((wx0+16,wy1-24),'КАДР: ДЕТАЛЬ ОТЕЛЯ (ПЛЕЙСХОЛДЕР)',font=f,fill=(40,40,36))
    return np.asarray(im).astype(np.float32)/255
def k3(P):
    img=l2s(s2l(bg_world(True,P.get('w0',1.1),P.get('w1',0.7)))); out=img.copy()
    for i,(cx,top) in enumerate(LEAF):
        p=figure_plate(i,LW,LH); x0=int(round(cx-LW/2)); y0=int(round(top))
        # sharp content: full leaf plate (stretch of 4:5 plate downward: regenerate at 60x107)
        cont=out.copy(); cont[y0:y0+LH,x0:x0+LW]=p
        bevel_window(out,cont,x0,y0,x0+LW,y0+LH,3)
        # practical lamp inside the footage: sharp warm bead behind the shoulder
        lx=cx-LW/2+LW*0.30; ly=y0+LH*0.20
        draw_lamp(out,lx,ly,2.6)
        # warm spill on wall below (light from people)
    return out
if __name__=='__main__':
    P=dict(A=5,bh=5,bv=7,lift=0.03,gain=0.9,tri=0.65); P.update(json.loads(os.environ.get('PARAMS','{}')))
    for n,fn in (('k1',k1),('k2',k2),('k3',k3)):
        a=save(f'okno_calib_{n}.png',fn(P)); print(n,stats(a))
