"""
Patches Streamlit's installed index.html so the app's manifest.json and
apple-touch-icon are linked in the page <head>. This makes "Add to Home
Screen" on phones pick up the MWDTS icon instead of the default Streamlit icon.

Run this once after installing/upgrading streamlit, e.g. at the end of your
Dockerfile or startup script:

    pip install streamlit
    python patch_head.py
    streamlit run app.py
"""

import os
import streamlit as st

streamlit_path = os.path.dirname(st.__file__)
index_path = os.path.join(streamlit_path, "static", "index.html")

with open(index_path, "r") as f:
    html = f.read()

tags = '''
<link rel="manifest" href="/app/static/manifest.json">
<link rel="apple-touch-icon" href="/app/static/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="MWDTS">
<meta name="theme-color" content="#0a1a3c">
'''

if 'rel="manifest"' not in html:
    html = html.replace("</head>", tags + "</head>")
    with open(index_path, "w") as f:
        f.write(html)
    print(f"Patched {index_path}")
else:
    print("Already patched — no changes made.")
  
