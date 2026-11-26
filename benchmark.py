#!/usr/bin/env python3
"""Compare a human-annotated word JSON and studio audit JSON. Never invent a score."""
import argparse, json, statistics, sys, unicodedata
from pathlib import Path
from universal_engine import norm

def compare(ref,hyp,key=norm):
    # Levenshtein edit path; linear rows plus compact trace.
    a=[key(x['text']) for x in ref];b=[key(x['text']) for x in hyp];n,m=len(a),len(b)
    if n*m>30_000_000:raise ValueError('Benchmark long recordings in annotated segments (matrix limit).')
    prev=list(range(m+1));moves=[bytearray([2]*(m+1))]
    for i in range(1,n+1):
        curr=[i]+[0]*m;row=bytearray(m+1);row[0]=1
        for j in range(1,m+1):
            d=prev[j-1]+(a[i-1]!=b[j-1]);u=prev[j]+1;l=curr[j-1]+1
            k=min(d,u,l);curr[j]=k;row[j]=0 if d==k else 1 if u==k else 2
        moves.append(row);prev=curr
    i,j=n,m;subs=ins=dele=0;errors=[];end_errors=[];matches=[]
    while i or j:
        k=moves[i][j]
        if i and j and k==0:
            i-=1;j-=1
            if a[i]!=b[j]:subs+=1
            else:
                matches.append((i,j))
                try:errors.append(abs(float(ref[i]['start'])-float(hyp[j]['start'])));end_errors.append(abs(float(ref[i]['end'])-float(hyp[j]['end'])))
                except (KeyError,TypeError,ValueError):pass
        elif i and (not j or k==1):i-=1;dele+=1
        else:j-=1;ins+=1
    return {'reference_tokens':n,'substitutions':subs,'deletions':dele,'insertions':ins,'error_rate':(subs+dele+ins)/n if n else None,'matched_timed_tokens':len(errors),'mean_start_error_ms':statistics.mean(errors)*1000 if errors else None,'median_start_error_ms':statistics.median(errors)*1000 if errors else None,'mean_end_error_ms':statistics.mean(end_errors)*1000 if end_errors else None,'p95_start_error_ms':sorted(errors)[min(len(errors)-1,int(.95*(len(errors)-1)))]*1000 if errors else None}

def load(p):
    x=json.loads(Path(p).read_text(encoding='utf-8'));return x['words'] if isinstance(x,dict) else x

def chars(words):return [{'text':c} for c in ''.join(norm(w['text']) for w in words)]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference');p.add_argument('audit');p.add_argument('--output');a=p.parse_args();r,h=load(a.reference),load(a.audit)
    out={'word_metrics':compare(r,h),'character_metrics':compare(chars(r),chars(h)),'note':'Human reference must match the exact recording; language-specific tokenization may be required. Confidence calibration needs a labeled population.'}
    text=json.dumps(out,indent=2,ensure_ascii=False)
    if a.output:Path(a.output).write_text(text,encoding='utf-8')
    else:print(text)
if __name__=='__main__':main()
