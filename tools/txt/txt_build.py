"""نص الكتب (نظام TXT) للقراءة داخل التطبيق
الاستعمال: python3 tools/txt_build.py <ملف PDF أو أكثر> --out <مجلد> [--min good|mid] [--ocr]
مع --ocr: الكتاب الذي لا تصلح طبقته النصية يُقرأ بالتعرف الضوئي (tesseract بالعربية) صفحةً صفحة
لكل كتاب طبقته النصية سليمة يُكتب <out>/<اسم الملف دون .pdf>.json فيه {"q":جودة, "p":[نص كل صفحة]}
ويُحدَّث <out>/index.json بأسماء الكتب التي لها نص وعدد صفحاتها، ويقرؤه التطبيق ليُظهر زر «نص»
- الصفحات بترتيب صفحات ملف PDF نفسه، فينتقل القارئ بين النص والأصل على الصفحة نفسها
- لا يُحذف التشكيل، وتُصلح أخطاء الطبقة النصية الشائعة (الحروف المقلوبة في «يف» و«عىل» ونحوها)
- النص للقراءة والنسخ داخل التطبيق وحده، ولا يُتاح تنزيله"""
import sys, os, re, json
import pymupdf, subprocess, tempfile
from multiprocessing import Pool
_d = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(_d, 'ft')); sys.path.insert(0, _d)
import norm, score as S

FIX = dict(norm.FIX)
PRE = norm.PRE
LIG = {'ﻻ': 'لا', 'ﻷ': 'لأ', 'ﻹ': 'لإ', 'ﻵ': 'لآ', 'ﻼ': 'لا', 'ﻸ': 'لأ', 'ﻺ': 'لإ', 'ﻶ': 'لآ'}
DIA = re.compile('[ً-ْٰـ]')

def clean(t):
    """إصلاح الطبقة النصية مع إبقاء التشكيل"""
    for a, b in LIG.items(): t = t.replace(a, b)
    for a, b in PRE: t = t.replace(a, b)
    t = re.sub('[ء-يً-ْٰ]+', lambda m: FIX.get(DIA.sub('', m.group(0)), m.group(0)) if DIA.sub('', m.group(0)) in FIX else m.group(0), t)
    t = re.sub('[ \t ]+', ' ', t)
    t = re.sub(' *\n *', '\n', t)
    t = re.sub('\n{3,}', '\n\n', t)
    return t.strip()

BIDI = re.compile('[\u200e\u200f\u202a-\u202e\u2066-\u2069]')

def page_lines(pg):
    """يعيد بناء الأسطر من مواضع الكلمات: تُجمع الكلمات المتقاربة في الارتفاع، وتُرتَّب من اليمين إلى اليسار
    (أدق من pdftotext في كتب كثيرة طبقتها كلمات منفصلة)"""
    w = sorted(pg.get_text('words'), key=lambda a: (a[1] + a[3]) / 2)
    lines = []
    for a in w:
        yc, h = (a[1] + a[3]) / 2, a[3] - a[1]
        if lines and abs(lines[-1][0] - yc) < max(3, h * .45): lines[-1][1].append(a)
        else: lines.append([yc, [a]])
    out, prev = [], None
    for yc, ws in lines:
        if prev is not None and yc - prev > 2.2 * max(8, ws[0][3] - ws[0][1]): out.append('')   # فراغ كبير = فقرة جديدة
        out.append(' '.join(x[4] for x in sorted(ws, key=lambda a: -a[2]))); prev = yc
    return BIDI.sub('', '\n'.join(out))

def _ocr(args):
    pdf, i = args
    try:
        pg = pymupdf.open(pdf)[i]
        with tempfile.NamedTemporaryFile(suffix='.png') as f:
            pg.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY).save(f.name)
            return subprocess.run(['tesseract', f.name, '-', '-l', 'ara'], capture_output=True, timeout=300, env={**os.environ, 'OMP_THREAD_LIMIT': '1'}).stdout.decode('utf8', 'ignore')
    except Exception: return ''

def ocr_pages(pdf, n, pool):
    return [BIDI.sub('', t).replace('\f', '') for t in pool.map(_ocr, [(pdf, i) for i in range(n)], chunksize=1)]

def quality(text):
    pages = max(1, text.count('\f'))
    toks = re.findall('[ء-ي]+', norm.fix(text))
    if len(toks) / pages < 20: return 'empty'
    sc = S.score(norm.fix(text))[0]; one = sum(len(x) == 1 for x in toks) / len(toks)
    return 'good' if sc >= .11 and one < .12 else 'mid' if sc >= .07 and one < .2 else 'bad'

def main():
    args = sys.argv[1:]; out = args[args.index('--out') + 1]; args = [a for a in args if a not in ('--out', out)]
    mn = 'good'
    if '--min' in args: mn = args[args.index('--min') + 1]; args = [a for a in args if a not in ('--min', mn)]
    ok = {'good'} if mn == 'good' else {'good', 'mid'}
    use_ocr = '--ocr' in args; args = [a for a in args if a != '--ocr']
    pool = Pool(os.cpu_count() or 2) if use_ocr else None
    os.makedirs(out, exist_ok=True)
    ix_p = os.path.join(out, 'index.json')
    ix = json.load(open(ix_p)) if os.path.exists(ix_p) else {}
    skip = '--skip-done' in args; args = [a for a in args if a != '--skip-done']
    done = 0
    for pdf in args:
        name = os.path.basename(pdf)[:-4]
        if skip and os.path.exists(os.path.join(out, name + '.json')): continue
        try:
            doc = pymupdf.open(pdf); pages = [page_lines(pg) for pg in doc]
        except Exception as e: print(name, 'error', e); continue
        q = quality('\f'.join(pages))
        if q not in ok and use_ocr:
            pages = ocr_pages(pdf, len(pages), pool); q2 = quality('\f'.join(pages))
            q = 'ocr' if q2 in ('good', 'mid') else q2
        if q not in ok and q != 'ocr': ix.pop(name, None); print(name, q); continue
        pages = [clean(p) for p in pages]
        json.dump({'q': q, 'p': pages}, open(os.path.join(out, name + '.json'), 'w', encoding='utf8'), ensure_ascii=False, separators=(',', ':'))
        ix[name] = len(pages); done += 1; print(name, q, len(pages))
    json.dump(ix, open(ix_p, 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    print('done', done, 'total', len(ix))

if __name__ == '__main__': main()
