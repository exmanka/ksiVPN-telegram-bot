import json

arr = []
with open('obscene_words.txt', encoding='utf-8') as r:
    for word in r:
        n = word.lower().split('\n')[0]
        if n != '':
            arr.append(n)

with open('obscene_words.json', 'w', encoding='utf-8') as w:
    json.dump(arr, w)