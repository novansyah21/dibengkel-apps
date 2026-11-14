"""Local-only MVP diagram uploads, safely normalized for manual visual review.

The six-fuse source-locked auto-tracing does NOT apply to uploaded diagrams.
No claim of automatic recognition, vehicle suitability or electrical verification.
"""
import base64
import hashlib
import io
from pathlib import Path
import re
import sqlite3
import uuid

MAX_UPLOAD_BYTES=8*1024*1024
MAX_PIXELS=15_000_000
MAX_EDGE=6000

def _clean_text(value,limit):
    text=" ".join(str(value or "").strip().split())
    if not text or len(text)>limit:raise ValueError("Diagram title/vehicle must be nonempty and within limit")
    if any(ord(c)<32 for c in text):raise ValueError("Invalid control character")
    return text

def upload(dbpath,assets_dir,data):
    if not isinstance(data,dict):raise ValueError("Invalid upload payload")
    title=_clean_text(data.get("title"),120)
    vehicle=" ".join(str(data.get("vehicle") or "Vehicle not specified").split())
    if len(vehicle)>120:raise ValueError("Vehicle description too long")
    encoded=data.get("image_base64")
    if not isinstance(encoded,str) or len(encoded)>(MAX_UPLOAD_BYTES*4//3+4096):
        raise ValueError("Image exceeds 8 MB upload limit")
    if encoded.startswith("data:"):
        mime,sep,encoded=encoded.partition(",")
        if not sep or mime.lower() not in (
            "data:image/png;base64","data:image/jpeg;base64","data:image/jpg;base64"):
            raise ValueError("PNG/JPEG base64 images only")
    try:
        binary=base64.b64decode(encoded,validate=True)
    except (ValueError,base64.binascii.Error):
        raise ValueError("Invalid base64 image")
    if not binary or len(binary)>MAX_UPLOAD_BYTES:
        raise ValueError("Image is empty or larger than 8 MB")
    try:
        from PIL import Image,ImageOps,UnidentifiedImageError
        Image.MAX_IMAGE_PIXELS=MAX_PIXELS
        with Image.open(io.BytesIO(binary)) as src:
            if src.format not in ("PNG","JPEG"):
                raise ValueError("Only PNG or JPEG diagram images are supported")
            width,height=src.size
            if (not 100<=width<=MAX_EDGE or not 100<=height<=MAX_EDGE
                    or width*height>MAX_PIXELS):
                raise ValueError("Invalid image dimensions (max 6000x6000 and 15 MP)")
            oriented=ImageOps.exif_transpose(src)
            normalized=oriented.convert("RGBA")
            background=Image.new("RGBA",normalized.size,(255,255,255,255))
            background.alpha_composite(normalized)
            rgb=background.convert("RGB")
            buffer=io.BytesIO()
            rgb.save(buffer,format="PNG",optimize=True)
            raw=buffer.getvalue()
    except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid or unsafe image: "+str(exc))
    ident="upload_"+uuid.uuid4().hex
    filename=ident+".png"
    folder=Path(assets_dir);folder.mkdir(parents=True,exist_ok=True)
    # Generated basename only; never accept a user-controlled local filename.
    target=folder/filename
    tmp=folder/(ident+".tmp")
    try:
        with tmp.open("xb") as f:f.write(raw)
        tmp.replace(target)
        digest=hashlib.sha256(raw).hexdigest()
        with sqlite3.connect(dbpath) as db:
            db.execute("""INSERT INTO viewer_diagrams
                (id,title,image_file,width,height,source_url,vehicle,verification)
                VALUES(?,?,?,?,?,?,?,?)""",
                (ident,title,filename,rgb.width,rgb.height,
                 "local_upload_sha256:"+digest,vehicle,"manual_visual_review_only"))
            db.commit()
    except Exception:
        tmp.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    return {"id":ident,"title":title,"image_file":filename,
            "width":rgb.width,"height":rgb.height,
            "sha256":digest,"vehicle":vehicle,
            "verification":"manual_visual_review_only",
            "scope":"manual annotation, path tracing and connector/terminal mapping; no automatic electrical netlist"}
