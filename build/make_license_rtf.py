import sys

with open('LICENSE', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('\\', '\\\\').replace('{', r'\{').replace('}', r'\}')
lines = text.split('\n')
body = '\n'.join(line + r'\par' for line in lines)
rtf = r'{\rtf1\ansi\deff0 {\fonttbl {\f0 Courier New;}}' + '\n' + r'\f0\fs18' + '\n' + body + '\n}'

with open('LICENSE.rtf', 'w', encoding='ascii', errors='replace') as f:
    f.write(rtf)

print('LICENSE.rtf created')
