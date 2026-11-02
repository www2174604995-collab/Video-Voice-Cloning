
import os, time
os.chdir(r"D:\dshwork\bili-simul")
t0 = time.time()
from modelscope import snapshot_download
p = snapshot_download("openbmb/VoxCPM-0.5B", local_dir="data/models/voxcpm")
print("done %.1fs -> %s" % (time.time()-t0, p), flush=True)
