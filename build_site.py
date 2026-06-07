"""Turn results.json into site/data.js (window.RESULTS = {...}),
so the site opens by double-clicking index.html without a local server."""
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

print(f"Wrote {dst} ({os.path.getsize(dst)//1024} KB)")
