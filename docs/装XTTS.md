# 装 XTTS-v2（音色克隆，Windows 推荐路线）

XTTS-v2 是 Coqui 的零样本克隆模型：给 6 秒参考音，就能用那个音色说 17 种语言。
4 GB 显存的笔记本显卡可以跑。

## 0. 一条命令（推荐）

~~~bat
install-xtts.bat            :: GPU 版（cu121，从交大镜像下载 torch）
install-xtts.bat -Cpu       :: 只有 CPU，装 PyPI 上的 CPU 版 torch
install-xtts.bat -SkipModel :: 只装依赖，不下载 1.9GB 权重
~~~

脚本支持断点续传：网络断了就重跑，会接着下。
装完会自动执行 `tools/check_xtts.py` 验证。

下面是手动步骤，供排查用。

## 1. 装 PyTorch（CUDA 版）

`download.pytorch.org` 在国内常常只有 0.3 MB/s（2.4 GB 要下两小时）。用交大镜像：

~~~bat
set W=https://mirror.sjtu.edu.cn/pytorch-wheels/cu121
curl.exe -L -C - -o torch.whl "%W%/torch-2.5.1%%2Bcu121-cp311-cp311-win_amd64.whl"
curl.exe -L -C - -o torchaudio.whl "%W%/torchaudio-2.5.1%%2Bcu121-cp311-cp311-win_amd64.whl"
.venv\Scripts\python.exe -m pip install torch.whl torchaudio.whl
~~~

没显卡就装 CPU 版（慢 5~10 倍，能用）：

~~~bat
.venv\Scripts\python.exe -m pip install torch==2.5.1 torchaudio==2.5.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
~~~

> 别装 2.6 以上，两个坑：
> 1. `torch.load` 默认改成 `weights_only=True`，XTTS 的 `model.pth` 会加载失败；
> 2. 2.9 起 `import TTS` 需要额外装 `torchcodec`（还要系统里有 FFmpeg）。
> 钉死 2.5.1 可以一次躲开这两个。

验证：

~~~bat
.venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
~~~

## 2. 装 coqui-tts

~~~bat
.venv\Scripts\python.exe -m pip install coqui-tts
~~~

> 注意是 `coqui-tts`（社区维护版），不是已停止维护的 `TTS`。两者导入名都是 `TTS`。

然后必须把 transformers 钉在 5 以下，否则 `import TTS` 直接报
`cannot import name 'TransformGetItemToIndex' from 'torch._dynamo...'`：

~~~bat
.venv\Scripts\python.exe -m pip install "transformers>=4.43,<5"
~~~

已验证组合记在 `server/requirements-xtts.txt` 里，想一次装齐可以直接：

~~~bat
.venv\Scripts\python.exe -m pip install -r server\requirements-xtts.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
~~~

## 3. 启动

~~~bat
start.bat --tts xtts --voice clone
~~~

权重放在 `data/models/xtts_v2/`（`config.json`、`model.pth`、`vocab.json`、`speakers_xtts.pth`、`dvae.pth`、`mel_stats.pth`）。
`XTTS(Config())` 会优先用这个目录，目录不完整才回退到按模型名从 HuggingFace 下。

手动拉权重（断点续传，可反复重跑）：

~~~bat
mkdir data\models\xtts_v2
set B=https://hf-mirror.com/coqui/XTTS-v2/resolve/main
for %f in (config.json vocab.json speakers_xtts.pth mel_stats.pth dvae.pth model.pth) do curl.exe -L -C - -o data\models\xtts_v2\%f %B%/%f
~~~

没有 curl 的环境（或想用 HuggingFace 的下载器）：

~~~bat
.venv\Scripts\python.exe tools\download_xtts.py
~~~

不管哪种方式，运行时都要保证 `COQUI_TOS_AGREED=1`（服务端代码里已经默认设置）：coqui 首次加载会调 `input()` 让你确认许可，服务端没有 stdin，会直接抛 `EOFError`。

## 4. 验证

~~~bat
.venv\Scripts\python.exe tests\e2e.py --real --tts xtts
~~~

看 `data/out/e2e.wav`：如果是一个「像原说话人」的英语声音，就装对了。

## 5. 已知限制

- 中文韵律偏平，长句偶尔吞字。想要更自然的中文，走 CosyVoice。
- 采样率 24 kHz，够用于视频。
- 首次推理慢（加载 + CUDA 编译），之后每句 0.8~2 秒。
