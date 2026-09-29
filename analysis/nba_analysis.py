"""NBA strategy tests ($10 per bet, bought at the ask, after Kalshi fees).
Run after nba_build.py:  python analysis/nba_analysis.py [data_dir] [results_dir]
Columns d/t = return in Oct-Feb and Mar-Jun."""
import os, sys
DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = sys.argv[2] if len(sys.argv) > 2 else "results"
os.makedirs(OUT, exist_ok=True)
import pandas as pd, numpy as np, math
def fee(p,c): return math.ceil(0.07*c*p*(1-p)*100)/100
def pnl(price,win,st=10):
    c=st/price; g=np.where(win,c-st,-st); f=np.array([fee(p,cc) for p,cc in zip(price,c)]); return g-f
def odds(p): return f"{-100*p/(1-p):+.0f}" if p>=0.5 else f"+{100*(1-p)/p:.0f}"
ROWS=[]
def R(df,price,win,label,grp):
    x=pd.DataFrame({'p':np.asarray(price,float),'w':np.asarray(win,bool),'date':df.date.values})
    x=x[(x.p>0.009)&(x.p<0.991)].copy()
    if len(x)<8: return
    x['n']=pnl(x.p.values,x.w.values)
    d=x[x.date<'2026-03-01'].n; t=x[x.date>='2026-03-01'].n
    both='✅' if (d.sum()>0 and t.sum()>0) else ('❌' if (d.sum()<0 and t.sum()<0) else 'mixed')
    ROWS.append(dict(grp=grp,label=label,n=len(x),won=x.w.mean(),odds=odds(x.p.median()),staked=10*len(x),net=x.n.sum(),roi=x.n.mean()/10,both=both,d=d.mean()/10 if len(d) else np.nan,t=t.mean()/10 if len(t) else np.nan))
S=pd.read_csv(f'{OUT}/nba_game_snapshots.csv'); D=pd.read_csv(f'{OUT}/nba_deficit_events.csv')
S['home_won']=S.home_won.astype(bool); D['won']=D.won.astype(bool)
d20=D[D.th==20]; d15=D[D.th==15]
G='Comeback'
R(d15,d15.price,d15.won,'Bet team down 15+',G)
R(d20,d20.price,d20.won,'Bet team down 20+',G)
x=d20[d20.period<=2]; R(x,x.price,x.won,'Down 20+ in 1st half',G)
x=d20[d20.period>=3]; R(x,x.price,x.won,'Down 20+ in 2nd half',G)
x=d20[d20.was_fav]; R(x,x.price,x.won,'Down 20+ but was pre-game favorite',G)
G='3-pointer hypothesis'
x=d20[d20.tpa>=4]; R(x,x.price,x.won,'Down 20+, took 4+ threes in last 10 min',G)
x=d20[d20.tpm>=2]; R(x,x.price,x.won,'Down 20+, made 2+ threes in last 10 min',G)
x=d20[d20.tpa>d20.opp_tpa]; R(x,x.price,x.won,'Down 20+, shooting more threes than leader',G)
x=d20[(d20.g3pct>=0.38)&(d20.g3pa>=10)]; R(x,x.price,x.won,'Down 20+, hitting 38%+ from three this game',G)
x=d20[(d20.g3pct<0.30)&(d20.g3pa>=10)]; R(x,x.price,x.won,'Down 20+, cold from three (<30%) this game',G)
x=d15[d15.tpa>=4]; R(x,x.price,x.won,'Down 15+, took 4+ threes in last 10 min',G)
G='Bet the leader'
R(d20,1-d20.price,~d20.won,'Bet leader when opponent down 20+',G)
x=d20[(d20.price>=0.03)&(d20.price<=0.10)]; R(x,1-x.price,~x.won,'Bet leader, trailer priced +900 to +3200',G)
x=S[S.m3.abs()>=16]; lh=x.m3>0; R(x,np.where(lh,x.ha3,1-x.hb3),np.where(lh,x.home_won,~x.home_won),'Bet leader up 16+ after Q3',G)
x=S[S.m1.abs()>=16]; lh=x.m1>0; R(x,np.where(lh,x.ha1,1-x.hb1),np.where(lh,x.home_won,~x.home_won),'Bet leader up 16+ after Q1',G)
G='Pre-game'
fh=S.pre_mid>=0.5
fp=np.where(fh,S.pre_ha,1-S.pre_hb); dp=np.where(fh,1-S.pre_hb,S.pre_ha); fw=np.where(fh,S.home_won,~S.home_won)
R(S,fp,fw,'Bet every favorite',G); R(S,dp,~fw,'Bet every underdog',G)
R(S,S.pre_ha,S.home_won,'Bet every home team',G); R(S,1-S.pre_hb,~S.home_won,'Bet every away team',G)
m=~fh; R(S[m],S.pre_ha[m],S.home_won[m],'Bet home underdogs',G)
m=fp>=0.8; R(S[m],fp[m],fw[m],'Bet heavy favorites (-400 or shorter)',G)
m=dp<=0.25; R(S[m],dp[m],~fw[m],'Bet big underdogs (+300 or longer)',G)
m=S.playoff; R(S[m],fp[m],fw[m],'Playoffs: bet favorite',G); R(S[m],dp[m],~fw[m],'Playoffs: bet underdog',G)
G='In-game'
S['fav_home']=fh
# fav trailing at half
ok=S.m2.notna()
fm=np.where(fh,S.m2,-S.m2)  # favorite's margin at half
m=ok&(fm<0); x=S[m]; R(x,np.where(x.fav_home,x.ha2,1-x.hb2),np.where(x.fav_home,x.home_won,~x.home_won),'Favorite trailing at halftime: bet favorite',G)
R(x,np.where(x.fav_home,1-x.hb2,x.ha2),np.where(x.fav_home,~x.home_won,x.home_won),'Underdog leading at halftime: bet underdog',G)
m=ok&(fm<=-10); x=S[m]; R(x,np.where(x.fav_home,x.ha2,1-x.hb2),np.where(x.fav_home,x.home_won,~x.home_won),'Favorite down 10+ at half: bet favorite',G)
m=S.m3.notna()&(S.m3.abs()<=5); x=S[m]; xf=x.pre_mid>=0.5
R(x,np.where(xf,x.ha3,1-x.hb3),np.where(xf,x.home_won,~x.home_won),'Within 5 after Q3: bet pre-game favorite',G)
R(x,np.where(xf,1-x.hb3,x.ha3),np.where(xf,~x.home_won,x.home_won),'Within 5 after Q3: bet pre-game underdog',G)
m=S.m3.notna()&(S.m3.abs()<=5); x=S[m]; R(x,x.ha3,x.home_won,'Within 5 after Q3: bet home team',G)
G='Back-to-back'
hb=(S.hr==1)&(S.ar>1); ab=(S.ar==1)&(S.hr>1)
x=S[hb]; R(x,1-x.pre_hb,~x.home_won,'Pre-game: bet rested away vs tired home',G)
x=S[ab]; R(x,x.pre_ha,x.home_won,'Pre-game: bet rested home vs tired away',G)
b2b=S[hb|ab].copy(); tired_home=(b2b.hr==1)
R(b2b,np.where(tired_home,1-b2b.pre_hb,b2b.pre_ha),np.where(tired_home,~b2b.home_won,b2b.home_won),'Pre-game: always bet against tired team',G)
x=b2b[b2b.m2.notna()]; th_=(x.hr==1)
R(x,np.where(th_,1-x.hb2,x.ha2),np.where(th_,~x.home_won,x.home_won),'Halftime: bet against tired team',G)
tl=np.where(th_,x.m2>0,x.m2<0); y=x[tl]; th2=(y.hr==1)
R(y,np.where(th2,1-y.hb2,y.ha2),np.where(th2,~y.home_won,y.home_won),'Halftime: tired team leading, bet against them',G)
tr=np.where(th_,x.m2<0,x.m2>0); y=x[tr]; th2=(y.hr==1)
R(y,np.where(th2,y.ha2,1-y.hb2),np.where(th2,y.home_won,~y.home_won),'Halftime: tired team trailing, bet on them',G)
out=pd.DataFrame(ROWS); out.to_csv(f'{OUT}/nba_strategies.csv',index=False)
pd.set_option('display.width',250)
print(out.assign(won=(out.won*100).round(1),roi=(out.roi*100).round(1),d=(out.d*100).round(1),t=(out.t*100).round(1),net=out.net.round(0)).to_string())
# B2B descriptive per half (score-based)
S2=S[(hb|ab)&S.m2.notna()].copy(); tired_home=S2.hr==1
S2['t1']=np.where(tired_home,S2.m2,-S2.m2); S2['t2']=np.where(tired_home,S2.final-S2.m2,-(S2.final-S2.m2))
print('B2B games',len(S2),'tired team avg 1H margin',S2.t1.mean().round(2),'2H margin',S2.t2.mean().round(2),'won 1H',(S2.t1>0).mean().round(3),'won 2H',(S2.t2>0).mean().round(3))
