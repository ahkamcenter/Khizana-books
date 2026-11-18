import sys,re,os,json
F=set("من في على إلى عن أن التي الذي هذا ذلك ما لا هو كان قال مع بين كل ثم الله أو إن هذه قد وقد وفي ومن وهو كما بن عليه به له حتى بعد عند بل لم غير".split())
DIA=re.compile('[ً-ْـ]')
def score(t):
    t=DIA.sub('',t); toks=re.findall('[ء-ي]+',t)
    if not toks: return 0,0
    return sum(1 for x in toks if x in F)/len(toks), len(toks)
if __name__=='__main__':
    out={}
    for f in sorted(os.listdir(sys.argv[1])):
        t=open(os.path.join(sys.argv[1],f),encoding='utf8',errors='ignore').read()
        pages=t.split('\f'); s,n=score(t)
        out[f]=[round(s,3),n,len(pages)]
    json.dump(out,open(sys.argv[2],'w'))
    import collections
    b=collections.Counter()
    for k,(s,n,p) in out.items():
        b['empty' if n/p<20 else 'good' if s>=.12 else 'mid' if s>=.06 else 'bad']+=1
    print(b)
