# 云 GPU 部署（AutoDL / 任意 Linux + NVIDIA 显卡）

本地只有 4 GB 显存时，IndexTTS-2 跑不动（实测 84~110 秒/句）。
把**服务端**放到云 GPU 上，本地只留浏览器扩展，是性价比最高的做法：

~~~
你的 Chrome / Edge（抓音 + 播译音）
        │  ws://127.0.0.1:8765/ws   （SSH 隧道转发）
        ▼
本机 ssh -L 8765:127.0.0.1:8765 ──► 云 GPU:8765  (ASR + 翻译 + IndexTTS-2)
~~~

## 0. 选机器

| 卡 | 显存 | 参考价 | IndexTTS-2 单句 |
|---|---|---|---|
| RTX 4090 | 24 GB | 约 ¥2.0/小时 | 0.5~1.5 s |
| RTX 3090 | 24 GB | 约 ¥1.5/小时 | 0.8~2 s |
| A5000 | 24 GB | 约 ¥1.2/小时 | 1~2 s |

看一部 1 小时的番，大约 2 小时机时 ≈ ¥3~4。**关机不计 GPU 费**，只计存储（几毛钱/天）。

镜像选「PyTorch 2.x / CUDA 12.1 / Python 3.10~3.11」的基础镜像即可，不用自己装 CUDA。

## 1. 上传代码

### 方式 A（推荐）：直接在实例上 clone

~~~bash
cd /root/autodl-tmp
git clone https://github.com/www2174604995-collab/Video-Voice-Cloning.git bilisimul
cd bilisimul
~~~

> 私有仓库或网络不通时用下面的方式 B。

### 方式 B：本地打包再上传（Windows）

~~~bat
powershell -ExecutionPolicy Bypass -File tools\pack_code.ps1
~~~

生成 `bilisimul-code-<时间>.zip`（约 700 KB，**不含**模型和 `server/config.yaml`，所以不会带出你的 key）。

上传方式二选一：

~~~bat
:: A. scp（AutoDL 控制台给了 SSH 命令和端口）
scp -P 12345 bilisimul-code-1022-0928.zip root@region-1.autodl.com:/root/
~~~

B. 直接在 AutoDL 的 JupyterLab 里把 zip 拖进 `/root/autodl-tmp/`。

然后在实例终端（**建议解压到数据盘 `/root/autodl-tmp`，系统盘只有 30 GB**）：

~~~bash
mkdir -p /root/autodl-tmp && cd /root/autodl-tmp
unzip -q ~/bilisimul-code-*.zip -d bilisimul
cd bilisimul
~~~

> AutoDL 数据盘（`/root/autodl-tmp`）比系统盘大且便宜；模型权重会自动落在 `data/models`，跟着项目走，放对地方就不用担心系统盘满。

## 2. 装环境（约 10~15 分钟，主要在下权重）

~~~bash
bash scripts/setup_linux.sh
~~~

它做四件事：

1. 建 `.venv`、装 torch 2.5.1+cu121；
2. 装应用依赖（fastapi / faster-whisper / edge-tts …）；
3. 装 coqui-tts + 下 XTTS-v2 权重（1.7 GB，走 hf-mirror）；
4. 装 windextts + 下 IndexTTS-2 权重（3.2 GB，走 ModelScope）。

只想要 IndexTTS-2：`bash scripts/setup_linux.sh --no-xtts`（省 1.7 GB 和 10 分钟）。

## 3. 启动

~~~bash
BS_MT_API_KEY=sk-你的DeepSeekKey TTS=indextts bash scripts/run_server.sh
~~~

- `BS_MT_API_KEY` 会被服务端自动读成 `mt_api_key`（不用改文件）；
- `--host 0.0.0.0` 已经在脚本里，云上才能被隧道访问；
- 首次启动会加载模型 + 预热，**1~3 分钟**；看到 `Uvicorn running on http://0.0.0.0:8765` 就绪。

## 4. 本地建隧道（关键一步）

AutoDL 控制台 →「SSH 登录」，照抄它的命令，加上 `-L`：

~~~bat
ssh -L 8765:127.0.0.1:8765 -p 12345 root@region-1.autodl.com
~~~

（Windows 10+ 自带 ssh，直接在 PowerShell 里跑；密码在控制台复制）

**这个窗口不要关**，关掉隧道就断了。保持它开着，云上的 8765 就等于你本机的 8765。

## 5. 扩展端不用改

面板里的「引擎地址」保持 `ws://127.0.0.1:8765/ws` —— 隧道会把它送到云上。
点「开始同传」即可。

验证：本地浏览器打开 <http://127.0.0.1:8765/>，能打开测试台就说明隧道通了。

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 面板一直「引擎断开，重连中」 | 隧道没开 / ssh 窗口关了 / 云上服务没起 |
| 云上启动就 OOM | 选了 16 GB 以下的卡；IndexTTS-2 要 24 GB 最稳 |
| 第一句特别慢（10~30 s） | 模型预热 + 首次推理的 CUDA Graph 捕获，之后就快了 |
| 声音卡顿、断断续续 | 家宽上行不够（抓音要持续上传 16 kHz PCM，约 256 kbps），换网或降低 `asr_model` |
| 想换回本地 | `start.bat`（本地 XTTS）即可，扩展不用动 |

## 7. 省钱提醒

- 看完就**关机**（不是重启），GPU 计费停止；
- 模型权重放在 `/root/autodl-tmp` 或 `data/models`，关机保留（按存储计费）；
- 想更快出结果：`TTS=xtts` 在 4090 上是 0.2~0.4 秒/句，音质略逊于 IndexTTS-2。