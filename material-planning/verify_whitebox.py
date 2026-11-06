"""E4 reproducible white-box evidence; application source is never rewritten."""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
import core

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / 'core.py').read_text(encoding='utf-8')
SELECTED = {'allocate_stock', 'round_purchase_qty', '_integer'}
EVENTS = []
MANIFEST = {}

def hit(kind, key, value=None):
    EVENTS.append((kind, key, bool(value) if kind != 'S' else None))
    return value

class Observe(ast.NodeTransformer):
    """Instrument a temporary AST copy; preserve short-circuit evaluation."""
    def __init__(self):
        self.fn = ''
    def call(self, kind, node, value=None):
        key = f'{self.fn}:{node.lineno}:{node.col_offset}'
        MANIFEST[kind + ':' + key] = ast.get_source_segment(SOURCE, node)
        return ast.copy_location(ast.Call(ast.Name('_hit', ast.Load()),
            [ast.Constant(kind), ast.Constant(key), value or ast.Constant(None)], []), node)
    def atom(self, node):
        if isinstance(node, ast.BoolOp):
            return self.visit(node)
        return self.call('C', node, self.visit(node))
    def visit_BoolOp(self, node):
        node.values = [self.atom(v) for v in node.values]
        return node
    def visit_If(self, node):
        node.test = self.call('D', node.test, self.atom(node.test))
        node.body = self.block(node.body)
        node.orelse = self.block(node.orelse)
        return node
    def visit_For(self, node):
        node.iter = self.visit(node.iter)
        node.body = [ast.Expr(self.call('L', node, ast.Constant(True)))] + self.block(node.body)
        node.orelse = self.block(node.orelse) + [ast.Expr(self.call('L', node, ast.Constant(False)))]
        return node
    def block(self, nodes):
        result = []
        for node in nodes:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                result.append(node)
            else:
                result += [ast.copy_location(ast.Expr(self.call('S', node)), node), self.visit(node)]
        return result
    def visit_FunctionDef(self, node):
        if node.name not in SELECTED:
            return node
        self.fn = node.name
        node.body = self.block(node.body)
        return node

tree = Observe().visit(ast.parse(SOURCE))
ast.fix_missing_locations(tree)
ENV = {'_hit': hit}
exec(compile(tree, '<E4 observed core>', 'exec'), ENV)
CASES = []

def project(value):
    if isinstance(value, dict) and 'netted_demand' in value:
        d = value['netted_demand']
        return [d['allocated_qty'], d['net_qty'], value['new_balance']['available_qty'],
                [[x['origin_id'], x['allocated_qty'], x['residual_qty']] for x in d['source_allocations']]]
    return value

def execute(fn, args, full=False):
    try:
        value=fn(*args)
        return {'return': value if full else project(value)}
    except (ValueError, TypeError, KeyError) as exc:
        return {'error': type(exc).__name__, 'message': str(exc)}

def case(cid, module, fn, args, expected, note='', vector=None):
    original = deepcopy(args)
    actual_full = execute(getattr(core, fn), args, full=True)
    actual = {'return':project(actual_full['return'])} if 'return' in actual_full else actual_full
    immutable = args == original
    observed_args = deepcopy(original)
    EVENTS.clear()
    observed_full = execute(ENV[fn], observed_args, full=True)
    observed = {'return':project(observed_full['return'])} if 'return' in observed_full else observed_full
    shadow = None
    if cid.startswith('C'):
        origin = original[0]['origins'][0]
        oid, path = origin['origin_id'], origin['bom_path']
        shadow = (not isinstance(oid,str), not oid, not isinstance(path,list), not path,
                  any(not isinstance(part,str) or not part for part in path))
    elif cid.startswith('I'):
        part = original[0]['origins'][0]['bom_path'][0]
        shadow = (not isinstance(part,str), not part)
    elif cid.startswith('G'):
        shadow = (type(original[0]) is not int, original[0] < original[2])
    CASES.append(dict(id=cid, module=module, function=fn, inputs=original, input_literal=repr(original),
        origin_path_literal=repr(original[0]['origins'][0]['bom_path']) if cid.startswith('C') else None,
        expected=expected, actual=actual, full_original_result=actual_full, passed=actual == expected and observed_full == actual_full and immutable and observed_args == original and (vector is None or shadow == tuple(vector)),
        instrumented_matches=observed_full == actual_full, inputs_unchanged=immutable and observed_args == original,
        note=note, logical_vector=vector, independently_evaluated_vector=shadow, events=deepcopy(EVENTS)))

def demand():
    return dict(demand_id='D1', task_id='T1', material_id='X', needed_date='2026-10-30',
        gross_qty=10, origins=[dict(origin_id='O1', bom_path=['P','X'], contribution_qty=10)])

def alloc(cid, d=None, stock=5, error=None, expected=None, note='', vector=None, material='X'):
    d = demand() if d is None else d
    result = {'error':'ValueError','message':error} if error else {'return':expected or [5,5,0,[['O1',5,5]]]}
    case(cid,'M33','allocate_stock',[d,dict(material_id=material,available_qty=stock)],result,note,vector)

# Independent, hand-worked expected quantities, not calls to the implementation.
for cid, stock, expected in [('A00',0,[0,10,0,[['O1',0,10]]]),('A01',5,[5,5,0,[['O1',5,5]]]),
                            ('A02',10,[10,0,0,[['O1',10,0]]]),('A03',11,[10,0,1,[['O1',10,0]]])]:
    alloc(cid,stock=stock,expected=expected,note='One origin; stock boundary')
two=demand();two['origins']=[dict(origin_id='O2',bom_path=['P','Z','X'],contribution_qty=6),dict(origin_id='O1',bom_path=['P','B','X'],contribution_qty=4)]
alloc('A04',two,expected=[5,5,0,[['O1',4,0],['O2',1,5]]],note='Two origins, reversed lexical order, partial second allocation')
three=demand();three['origins']=[dict(origin_id=f'O{i}',bom_path=['P',str(i),'X'],contribution_qty=q) for i,q in [(3,5),(1,2),(2,3)]]
alloc('A05',three,expected=[5,5,0,[['O1',2,0],['O2',3,0],['O3',0,5]]],note='Three origins; depletion before final origin')
alloc('A06',material='Y',error='material IDs must match')
d=demand();d['origins']=[];alloc('A07',d,error='a demand requires origins')
d=deepcopy(two);d['origins'][1]['origin_id']='O2';alloc('A08',d,error='origin IDs must be unique within a demand')
d=demand();d['gross_qty']=11;alloc('A09',d,error='origin quantities must sum to gross demand')
for cid,field,val,msg in [('A10','gross_qty',0,'gross_qty must be an integer >= 1'),('A11','gross_qty',True,'gross_qty must be an integer >= 1'),('A12','needed_date','2026-02-30','invalid calendar date')]:
    d=demand();d[field]=val;alloc(cid,d,error=msg)
alloc('A13',stock=-1,error='available_qty must be an integer >= 0')
d=demand();d['origins'][0]['contribution_qty']=0;alloc('A14',d,error='contribution_qty must be an integer >= 1')

# A=not str ID, B=empty ID, C=not list path, D=empty path, E=any invalid part.
# Four ID vectors x six realizable path vectors = 24. Empty path implies E=False.
ids=[('O1',(False,False)),('',(False,True)),(1,(True,False)),(0,(True,True))]
paths=[(['X'],(False,False,False)),([''],(False,False,True)),([],(False,True,False)),
       (('X',),(True,False,False)),(('',),(True,False,True)),((),(True,True,False))]
for i,((oid,ab),(path,cde)) in enumerate(itertools.product(ids,paths)):
    d=demand();d['origins'][0].update(origin_id=oid,bom_path=path)
    vector=ab+cde
    alloc(f'C{i:02}',d,error='invalid origin identifier or BOM path' if any(vector) else None,
          vector=vector,note='Outer origin predicate feasible logical vector; skipped atoms are not observed')
# Inner any predicate U=not str part; V=empty part. Include all four logical pairs.
for i,(part,vector) in enumerate([('X',(False,False)),('',(False,True)),(1,(True,False)),(0,(True,True))]):
    d=demand();d['origins'][0]['bom_path']=[part]
    alloc(f'I{i}',d,error='invalid origin identifier or BOM path' if any(vector) else None,vector=vector,note='Inner path-part predicate logical vector')
d=demand();d['origins'][0]['bom_path']=['P',0];alloc('A15',d,error='invalid origin identifier or BOM path',note='Generator valid prefix then invalid part')
d=deepcopy(two);d['origins'][1]['origin_id']='';alloc('A16',d,error='invalid origin identifier or BOM path',note='Outer validation loop accepts first origin then rejects second')

for cid,args,expected in [('P00',[0,100,10],0),('P01',[620,100,100],700),('P02',[1,25,10],30),('P03',[20,0,10],20),('P04',[1,0,1],1),('P05',[9007199254740993,0,10],9007199254741000)]:
    case(cid,'M43','round_purchase_qty',args,{'return':expected},'Independent integer rounding oracle')
for i,(position,value) in enumerate([(0,True),(0,-1),(1,False),(1,-1),(2,1.5),(2,0),(0,-1.5)]):
    args=[5,0,1];args[position]=value
    name=['remaining_gap','minimum_qty','purchase_multiple'][position]
    msg=f'{name} must be an integer >= {1 if position==2 else 0}'
    case(f'P{10+i}','M43','round_purchase_qty',args,{'error':'ValueError','message':msg},'One of six validator failure paths')
for i,(value,vector) in enumerate([(-1,(False,True)),(1,(False,False)),(-1.5,(True,True)),(1.5,(True,False))]):
    case(f'G{i}','guard','_integer',[value,'probe',0],{'error':'ValueError','message':'probe must be an integer >= 0'} if any(vector) else {'return':None},'Shared integer guard logical vector',vector)

def relevant(event,module):
    return event[1].startswith('allocate_stock:') if module=='M33' else event[1].startswith(('round_purchase_qty:','_integer:'))

def tokens(row, criterion):
    kinds={'statement':{'S'},'branch':{'D','L'},'condition':{'C'}}[criterion]
    return {tuple(e) for e in row['events'] if relevant(e,row['module']) and e[0] in kinds}

def minimum_cover(rows,criterion,universe):
    options={}
    for row in rows:
        covered=frozenset(tokens(row,criterion))
        if covered: options.setdefault(covered,row['id'])
    items=list(options.items());best=[v for k,v in items]
    def search(left,chosen):
        nonlocal best
        if not left:
            if len(chosen)<len(best):best=chosen
            return
        if len(chosen)>=len(best):return
        target=min(left,key=lambda t:(sum(t in s for s,_ in items),str(t)))
        for s,cid in sorted((x for x in items if target in x[0]),key=lambda x:-len(x[0]&left)):
            search(left-s,chosen+[cid])
    search(set(universe),[])
    return best

COVERAGE={}
for module,functions in [('M33',{'allocate_stock'}),('M43',{'round_purchase_qty','_integer'})]:
    rows=[r for r in CASES if r['module']==module]
    summary={}
    for criterion,kinds in [('statement',{'S'}),('branch',{'D','L'}),('condition',{'C'})]:
        universe=set()
        for key in MANIFEST:
            kind,func,*_=key.split(':')
            if kind in kinds and func in functions:
                identity=key[2:]
                universe.update({(kind,identity,None)} if kind=='S' else {(kind,identity,False),(kind,identity,True)})
        covered=set().union(*(tokens(r,criterion) for r in rows))
        summary[criterion]=dict(covered=len(covered&universe),total=len(universe),missing=sorted(universe-covered),minimum_cases=minimum_cover(rows,criterion,universe&covered))
    signatures={}
    for row in rows:
        sig=json.dumps([e for e in row['events'] if relevant(e,module)])
        signatures.setdefault(sig,[]).append(row['id'])
    summary['observed_paths']=[dict(representative=ids[0],cases=ids,events=json.loads(sig)) for sig,ids in signatures.items()]
    COVERAGE[module]=summary

checks=[dict(name='All original and instrumented cases match independent expectations without input mutations',passed=all(c['passed'] for c in CASES)),
        dict(name='Outer origin predicate has all 24 feasible logical vectors',passed=len({tuple(r['logical_vector']) for r in CASES if r['id'].startswith('C')})==24),
        dict(name='Inner generator has all four feasible logical vectors',passed=len({tuple(r['logical_vector']) for r in CASES if r['id'].startswith('I')})==4),
        dict(name='Integer guard has all four numeric logical vectors',passed=len({tuple(r['logical_vector']) for r in CASES if r['module']=='guard'})==4),
        dict(name='M43 with integer guards has eight distinct complete control paths',passed=len(COVERAGE['M43']['observed_paths'])==8)]
for m in COVERAGE:
    for criterion in ('statement','branch','condition'):
        checks.append(dict(name=f'{m} {criterion} scope complete',passed=not COVERAGE[m][criterion]['missing']))
mutations=[]
for label,old,new in [
    ('Zero gap incorrectly buys minimum','if remaining_gap == 0:\n        return 0','if remaining_gap == 0:\n        return minimum_qty'),
    ('Floor rounding loses a purchase lot','(target + purchase_multiple - 1) // purchase_multiple','target // purchase_multiple'),
    ('Minimum order ignored','target = max(remaining_gap, minimum_qty)','target = remaining_gap'),
    ('Origin quantity mismatch accepted','if sum(origin["contribution_qty"] for origin in origins) != gross:','if False:'),
    ('Duplicate origins accepted','if len({origin["origin_id"] for origin in origins}) != len(origins):','if False:'),
    ('Allocation overdraws balance','allocated = min(available, gross)','allocated = gross'),
]:
    assert SOURCE.count(old)==1
    namespace={}
    exec(compile(SOURCE.replace(old,new),'<E4 temporary mutation>','exec'),namespace)
    killed=[r['id'] for r in CASES if execute(namespace[r['function']],deepcopy(r['inputs']))!=r['expected']]
    mutations.append(dict(mutation=label,detected_by=killed,detected=bool(killed)))
checks.append(dict(name='Six targeted in-memory mutations detected by independent expected outputs',passed=all(m['detected'] for m in mutations)))
result=dict(executed_at=datetime.now().astimezone().isoformat(),python=sys.version,platform=platform.platform(),
    source_sha256=hashlib.sha256((ROOT/'core.py').read_bytes()).hexdigest(),
    harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='M33 function body and generator expressions, opaque standard library and _date/_integer callees; M43 includes _integer. Valid record shapes and built-in scalar/container values. M33 path sample is not exhaustive.',
    cases=CASES,passed=sum(c['passed'] for c in CASES),total=len(CASES),manifest=MANIFEST,coverage=COVERAGE,checks=checks,mutations=mutations)
target=ROOT/'results'/'whitebox-e4.json'
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f"E4 cases: {result['passed']}/{result['total']}; evidence checks: {sum(c['passed'] for c in checks)}/{len(checks)}")
for m,items in COVERAGE.items():
    print(m,json.dumps({k:v for k,v in items.items() if k!='observed_paths'}), 'observed paths',len(items['observed_paths']))
if result['passed']!=result['total'] or not all(c['passed'] for c in checks):
    print(json.dumps([c for c in CASES if not c['passed']],ensure_ascii=False))
    raise SystemExit(1)
