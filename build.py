import json, sys
data = json.load(open(sys.argv[1]))
tpl = open(sys.argv[2]).read()
blob = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
eng = open(sys.argv[4] if len(sys.argv) > 4 else 'engine.js').read().replace('</', '<\\/')
open(sys.argv[3], 'w').write(tpl.replace('__DATA__', blob).replace('__ENGINE__', eng))
print('built', sys.argv[3])
