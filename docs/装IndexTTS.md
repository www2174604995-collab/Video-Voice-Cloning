# 装 IndexTTS-2（中文音色克隆，B 站自家模型）

IndexTTS-2 是 B 站开源的零样本克隆模型，中文韵律明显好于 XTTS，日/英/粤等也支持。
本项目用的是社区版纯 Torch 实现 [windextts](https://pypi.org/project/windextts/)：
不需要编译、不需要 pynini、不用改官方仓库代码。

## 1. 装依赖

```bat
.venv\Scripts\python.exe -m pip install --no-deps windextts
.venv\Scripts\python.exe -m pip install jieba cn2an tiktoken safetensors wetext bitsandbytes
```

说明两件事：

- **torchcodec 不用装**：windextts 的 METADATA 里声明了它，但代码里并没有 import（那是给 torch>=2.9 的 torchaudio 用的）。用 `--no-deps` 跳过即可。
- **pynini 装不了也没关系**：windextts 的文本正则化优先用 `tn`（WeTextProcessing），失败会自动退到 `wetext`。`wetext` 在 Windows 上是纯 whl，一条 pip 就装好，所以这里不需要 conda。

## 2. 下权重（约 4.5 GB）

```bat
.venv\Scripts\python.exe -m windextts.download --out data\models\indextts2 --skip-qwen
```

- 源是 ModelScope（`baicai1145/WIndexTTS-Releases`），国内速度还行（实测 2~13 MB/s）。
- `--skip-qwen` 省掉 1.2 GB 的情感文本分支；本项目只用参考音克隆音色，用不到它。
- 中断了就重跑同一条命令，会跳过已完整的文件。

目录结构（本项目会自动找这里）：

```
data/models/indextts2/
├─ config.yaml
├─ gpt.pth
├─ s2mel.pth
├─ codec.pth
├─ bigvgan/
├─ w2v-bert-2.0/
├─ campplus_cn_common.bin
└─ multilingual_zh_ja_yue_char_del.tiktoken
```

## 3. 启动

```bat
start.bat --tts indextts
```

或者写进 `server/config.yaml`：

```yaml
tts: indextts
tts_device: cuda
voice: clone
indextts_dir: ""        # 留空 = data/models/indextts2
```

## 4. 显存不够怎么办

IndexTTS-2 官方建议 6~8 GB。4 GB 卡（比如 3050 笔记本）本项目会自动：

1. `low_vram=True`：wav2vec 编码器放 CPU，只把 GPT/声码器留显存；
2. 如果仍然 OOM，自动重建成 `enable_w4a16`（GPT 走 INT4），只重试一次。

日志里会看到：

```
indextts out of memory, retrying with int4: CUDA out of memory...
```

## 5. 验证

```bat
.venv\Scripts\python.exe tools\probe_indextts.py
```

会打印构造耗时、首句耗时、RTF 和显存峰值。


---

## 6. 4 GB 显卡实测（重要）

本机 RTX 3050 Laptop 4 GB，实测结论是**跑不动**：

| 配置 | 结果 |
|---|---|
| 默认 fp16 + low_vram | 构造 67 s，单句 84 s（峰值 6.77 GB，超显存后开始换页） |
| enable_w4a16（INT4）+ 小 token 预算 | 构造 62 s，单句 **110 s**（峰值降到 2.75 GB，但更慢） |

对比同机其他引擎（中文，2.6 s 译文）：

| 引擎 | 单句耗时 | 音质 |
|---|---|---|
| SAPI | 0.1 s | 机器人 |
| XTTS（CPU） | 7~9 s | 可用的克隆 |
| IndexTTS-2（本机 GPU） | 84~110 s | 好，但没法用 |

**建议**：4 GB 显存的机器不要上 IndexTTS-2，用 XTTS；想要 IndexTTS-2 的音质，
要么换 8 GB 以上的卡，要么走云端克隆 TTS（MiniMax / 火山 / ElevenLabs，按字计费）。

