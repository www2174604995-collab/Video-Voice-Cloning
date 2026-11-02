# BiliSimul · 视频同声传译 / 一键换声

把视频里的说话声换成**另一个人的音色**，并可选翻译成中文。

| 用法 | 说明 |
|---|---|
| **B 站实时同传** | 浏览器扩展抓当前标签页声音，边看边译边配音 |
| **上传视频换声** | 上传视频 + 参考音，输出配音版 MP4（适合课程、口播类长视频） |

## 效果（实测，RTX 3080 Ti 12 GB）

| 指标 | 数值 |
|---|---|
| 声纹相似度（单句，ECAPA） | **0.84**（>0.75 即判定为同一说话人） |
| 声纹相似度（9 分钟整片） | **0.81** |
| 9 分钟视频出片 | 10~30 分钟 |
| 实时同传延迟（IndexTTS-2） | 2~3 秒/句 |

> 诚实说明：**效果不如 B 站官方的 AI 配音**。官方用未公开的生产模型，本项目基于开源模型（VoxCPM2 / IndexTTS-2），
> 音色能达到"同一个人"级别，但自然度和情绪表达仍有差距。

## 流水线

```
视频音轨
   ├─ 有字幕 → OCR 硬字幕 / 读 SRT ─────────────┐
   └─ 无字幕 → VAD 切句 → Whisper → DeepSeek 翻译 ┴→ 中文文本
                                                     │
                              VoxCPM2 克隆配音（音色=参考音）
                                                     │
                          逐句校验（语音回听：语言 + 词一致性）
                                                     │
                        不合格句 → IndexTTS-2 重做（保证准确）
                                                     │
                    混音（48 kHz / 响度归一 / 交叠淡出）→ MP4
```

## 快速开始

### 方式 A：本机

```bat
install.bat        :: 装依赖 + 下模型
start.bat          :: 启动 http://127.0.0.1:8765
```

Chrome → `chrome://extensions` → 开发者模式 → 加载已解压的扩展 → 选 `extension/` 目录；
打开 B 站视频，点扩展图标开始同传。

### 方式 B：云 GPU（推荐）

```bash
bash scripts/setup_linux.sh
TTS=voxcpm bash scripts/run_server.sh
```

建隧道后访问 `http://127.0.0.1:8765/dub` 上传视频换声。详见 [`docs/云GPU部署.md`](docs/云GPU部署.md)。

## 上传视频换声

```bash
python tools/dub_video.py \
  --video input.mp4 \
  --ref   voice.wav \
  --srt   subs.srt \      # 可选：有字幕就不做识别和翻译
  --target zh \           # same=只换音色 / zh=翻成中文
  --tts voxcpm --bg 0 \
  --out  out.mp4
```

硬字幕先 OCR：

```bash
python tools/ocr_subs.py --video input.mp4 --out subs.srt
```

## 关键配置（`server/config.yaml`）

```yaml
tts: voxcpm              # voxcpm（最像）| indextts（最稳）| xtts | edge
voxcpm_dir: data/models/voxcpm2
voxcpm_mode: ref         # 纯参考音模式，跨语种最稳
ref_trim: 0              # 0 = 用完整参考音（实测截短会掉相似度）
voxcpm_timesteps: 12     # 12 与 20 音色无差别，12 更快
dub_candidates: 2        # 每句生成几个候选取最好
sub_merge_sec: 14        # 相邻字幕合并成整句（自然度的关键）
dub_max_speedup: 1.0     # 1.0 = 不变速（变速损伤音色）
repair_tts: indextts     # 校验失败的句子用它重做
```

## 已踩过的坑

| 坑 | 结论 |
|---|---|
| 参考音截成 15 秒 | 掉 0.04 相似度，**用完整的** |
| 参考音被重编码到 16 kHz | 声音发闷，**必须用原始文件** |
| `voxcpm_mode: both` | 会让模型顺着参考音语言走，**用 `ref`** |
| LoRA 微调（lr=1e-4, 40 epoch） | 训坏了（0.78 < 0.84），要训用 `lr=1e-5` |
| 每句变速对齐时间轴 | 相位声码器损伤音色，宁可溢出后淡出 |
| 字幕逐条喂给 TTS | 碎片输入导致语气平，**合并成 12~14 秒整句** |
| 校验用全局 `asr_language` | 中文会被判成外语，**校验必须显式传语言** |

## 目录

```
server/app/       服务端（FastAPI + WebSocket + 离线配音）
  backends/       ASR / MT / TTS 引擎适配
  dubbing.py      离线换声核心（切句→合成→校验→混音）
  subs.py         字幕解析 / 合并 / 拆分
  vc.py           Seed-VC 桥接（可选）
extension/        Chrome MV3 扩展
web/              浏览器界面
tools/            命令行工具（换声 / OCR / 评测 / 打包）
docs/             部署与引擎安装说明
```

## 合规

- 克隆他人声音需获得授权，本项目不附带任何人的音色模型。
- 请遵守 B 站等平台的服务条款。

## 许可

MIT
