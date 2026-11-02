
import json, time, urllib.request, mimetypes, os
B = "http://127.0.0.1:8815"

def post(path, fields, files):
    boundary = "----bili" + str(int(time.time()))
    body = b""
    for k, v in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode()
    for k, p in files.items():
        fn = os.path.basename(p)
        ctype = mimetypes.guess_type(fn)[0] or "application/octet-stream"
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n" % (boundary, k, fn, ctype)).encode()
        body += open(p, "rb").read() + b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(B + path, data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    return json.load(urllib.request.urlopen(req, timeout=120))

r = post("/api/dub", {"target": "same", "bg": "0"},
         {"video": "data/input/test_src.mp4", "ref": "data/samples/zh.wav"})
print("queued:", r)
jid = r["id"]
for _ in range(90):
    time.sleep(2)
    s = json.load(urllib.request.urlopen(B + "/api/dub/" + jid, timeout=30))
    print(s.get("state"), s.get("stage"), s.get("done"), "/", s.get("total"), s.get("message"))
    if s.get("state") in ("done", "error"):
        break
print("file:", os.path.exists("data/uploads/%s/dubbed.mp4" % jid))
