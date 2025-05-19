import subprocess
import urllib.request
from collections import defaultdict
import unicodedata
 
def detect_encoding(byte_str):
    encodings = ['utf-16','utf-8', 'gbk', 'ascii', 'iso-8859-1', 'cp1252']
    probs = defaultdict(int)
    for enc in encodings:
        try:
            decoded = byte_str.decode(enc, errors='ignore')
            if len(decoded) > 0 and unicodedata.category(decoded[0]) != 'Cc':  # 忽略控制字符的影响，仅为示例简化处理
                probs[enc] += 1  # 这里可以加入更复杂的逻辑来评估概率，例如基于解码后的文本内容等。
        except UnicodeDecodeError:
            continue
    max_prob = max(probs.values(), default=0)  # 如果没有任何有效的解码，则max为0
    if max_prob > 0:  # 可以设置一个阈值来决定是否返回结果，例如max_prob > len(byte_str) * 0.5等。
        return [k for k, v in probs.items() if v == max_prob]  # 返回概率最高的编码列表，可能有多个相同概率的编码。
    return None

# 执行命令并获取输出
result = subprocess.run(['pip', 'list'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
 
# 打印输出
# print(result.stdout)
whllist = result.stdout.split('\n')
whllist1 = []
for whl in whllist:
    whl = whl.split(' ')[0].lower()
    whllist1.append(whl)
    # print(whl)

# 如果有错误，也可以打印错误信息
if result.stderr:
    print(result.stderr)
    
# 获取返回码
exit_code = result.returncode

lacklist = []
with open('requirements.txt', "rb") as f:
    encoding = detect_encoding(f.read())[0]
    print(encoding)
with open('requirements.txt', 'r',encoding=encoding) as f:
    requirements = f.readlines()
    requirements = [x.strip() for x in requirements]
    # print(requirements)
    for i in requirements:
        if i not in whllist1:
            #print(i)
            #print('not install')
            lacklist.append(i)
        else:
            #print(i)
            #print('install')
            pass
# print(lacklist)

pysources=['https://pypi.tuna.tsinghua.edu.cn/simple','https://mirrors.aliyun.com/pypi/simple/']
pys_url=pysources[0]
for pys in pysources:
	# print(pys)
	try:
		status=urllib.request.urlopen(pys).status
		if status==200:
			pys_url=pys
			break
	except:
		continue
if len(lacklist) == 0:
    print('all requirements are installed')
else:
    for i in lacklist:
        subprocess.run(['pip', 'install', i, '-i', pys_url])
        print(i + ' install success')