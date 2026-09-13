# A.V.I.D. legacy Python application

This is the validated Python reference implementation preserved for manual comparison during the native rewrite. It remains intentionally independent of the Rust/native application and does not share or migrate settings.

```bash
cd legacy-python
python3 -m pip install -r requirements.txt
python3 avid_gui.py
python3 -m unittest discover -s tests -v
```

The historical packaging workflow and release artifacts are preserved beside the source. Do not remove this directory until the replacement has received explicit manual approval.
