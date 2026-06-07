"""Превращает results.json в site/data.js (window.RESULTS = {...}),
чтобы сайт открывался двойным кликом по index.html без локального сервера."""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(HERE, "results.json")
dst = os.path.join(HERE, "site", "data.js")

with open(src, encoding="utf-8") as f:
    data = f.read()

with open(dst, "w", encoding="utf-8") as f:
    f.write("window.RESULTS = ")
    f.write(data)
    f.write(";\n")

print(f"Записано {dst} ({os.path.getsize(dst)//1024} КБ)")
