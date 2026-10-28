import json, sys
data = json.load(open(sys.argv[1]))
tpl = open(sys.argv[2]).read()
blob = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
open(sys.argv[3], 'w').write(tpl.replace('__DATA__', blob))
print('built', sys.argv[3])
