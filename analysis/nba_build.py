"""Build NBA analysis tables: match Kalshi game markets to ESPN play-by-play, then record
prices at key moments (pre-game, end of each quarter, first time a team trails by 15/20).
Run from the repo root:  python analysis/nba_build.py [data_dir] [results_dir]"""
import os, sys
DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = sys.argv[2] if len(sys.argv) > 2 else "results"
os.makedirs(OUT, exist_ok=True)
import pandas as pd, numpy as np, math
m=pd.read_csv(f'{DATA}/nba/nba_markets.csv'); p=pd.read_csv(f'{DATA}/nba/nba_prices.csv'); g=pd.read_csv(f'{DATA}/nba/nba_games.csv'); pl=pd.read_csv(f'{DATA}/nba/nba_plays.csv')
mp={'GSW':'GS','NYK':'NY','SAS':'SA','NOP':'NO','UTA':'UTAH','WAS':'WSH'}
seg=m.ticker.str.split('-')
m['date']=pd.to_datetime(seg.str[1].str[:7],format='%y%b%d').dt.date.astype(str)
m['away']=seg.str[1].str[7:10].map(lambda x:mp.get(x,x)); m['home']=seg.str[1].str[10:13].map(lambda x:mp.get(x,x))
m['yes']=seg.str[2].map(lambda x:mp.get(x,x))
g['date']=g.date.astype(str)
mg=m.merge(g,on=['date','home','away'],how='inner')
print('matched',len(mg),'of',len(m))
mg['home_won']=mg.home_pts>mg.away_pts
mg['yes_is_home']=mg.yes==mg.home
# sanity: yes result vs espn
chk=np.where(mg.yes_is_home,mg.home_won,~mg.home_won)==(mg.result=='yes')
print('result agreement',chk.mean())
pl['ts']=pd.to_datetime(pl.wallclock).astype('datetime64[s, UTC]').astype('int64')
pl=pl.sort_values(['gid','ts'])
g2=g.copy(); g2['date']=pd.to_datetime(g2.date)
lg=pd.concat([g2[['gid','date','home']].rename(columns={'home':'team'}),g2[['gid','date','away']].rename(columns={'away':'team'})]).sort_values(['team','date'])
lg['rest']=lg.groupby('team').date.diff().dt.days
rest=lg.set_index(['gid','team']).rest.to_dict()
pg=dict(tuple(p.groupby('ticker'))); plg=dict(tuple(pl.groupby('gid')))
S=[];D=[]
for _,r in mg.iterrows():
    if r.ticker not in pg or r.gid not in plg: continue
    pr=pg[r.ticker].sort_values('ts').copy()
    if r.yes_is_home: pr['hb'],pr['ha']=pr.bid,pr.ask
    else: pr['hb'],pr['ha']=1-pr.ask,1-pr.bid
    q=plg[r.gid].copy(); q['margin']=q.home-q.away; tip=q.ts.min()
    b=pr[pr.ts<=tip-300]
    if not len(b): continue
    x=b.iloc[-1]; prem=(x.ha+x.hb)/2
    base=dict(gid=r.gid,date=r.date,home_won=r.home_won,pre_mid=prem,pre_ha=x.ha,pre_hb=x.hb,
              hr=rest.get((r.gid,r.home)),ar=rest.get((r.gid,r.away)),playoff=r.title.startswith('Game'),
              h1=None,h2=None)
    # half margins
    ht=q[q.period<=2]
    base['h1']=ht.margin.iloc[-1] if len(ht) else np.nan
    base['final']=r.home_pts-r.away_pts
    def at(t):
        a=pr[(pr.ts>=t+60)&(pr.ts<=t+300)]; return a.iloc[0] if len(a) else None
    snaps={}
    for per in [1,2,3]:
        qq=q[q.period==per]
        if len(qq):
            e=qq.iloc[-1]; a=at(e.ts)
            if a is not None: snaps[per]=(e.margin,a.ha,a.hb,e.ts)
    base.update({f'm{k}':v[0] for k,v in snaps.items()}); base.update({f'ha{k}':v[1] for k,v in snaps.items()}); base.update({f'hb{k}':v[2] for k,v in snaps.items()})
    S.append(base)
    # deficit events (first time down 20) with 3pt features
    for side,sign,tid in [('home',1,r.home_id),('away',-1,r.away_id)]:
        tm=(q.margin*sign).values
        for th in [15,20]:
            idx=np.where(tm<=-th)[0]
            if not len(idx): continue
            i=idx[0]; e=q.iloc[i]; t=e.ts; a=at(t)
            if a is None: continue
            w=q[(q.ts>t-600)&(q.ts<=t)]; mine=w[w.team_id==tid]; opp=w[(w.team_id!=tid)&w.team_id.notna()]
            sofar=q[(q.ts<=t)&(q.team_id==tid)]
            D.append(dict(gid=r.gid,date=r.date,th=th,period=int(e.period),
                price=a.ha if side=='home' else 1-a.hb, won=(r.home_won if side=='home' else not r.home_won),
                tpa=int(mine.is3.sum()), tpm=int((mine.is3&mine.made).sum()), opp_tpa=int(opp.is3.sum()),
                g3pct=(sofar.is3&sofar.made).sum()/max(1,sofar.is3.sum()), g3pa=int(sofar.is3.sum()),
                was_fav=(prem>=0.5) if side=='home' else (prem<0.5)))
pd.DataFrame(S).to_csv(f'{OUT}/nba_game_snapshots.csv',index=False); pd.DataFrame(D).to_csv(f'{OUT}/nba_deficit_events.csv',index=False)
print(len(S),len(D))
