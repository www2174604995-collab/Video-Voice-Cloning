# 装 CosyVoice2（中文/英文音色克隆，效果最好）

CosyVoice2-0.5B 支持跨语种零样本克隆，中英日韩粤都很自然，单句 0.5~1.2 秒。
代价是**依赖重**，尤其 Windows 上 `pynini` 不好装。两条路：

## 路线 A：WSL2 / Linux（推荐）

~~~bash
# 在 WSL 里（Ubuntu 22.04）
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
conda create -n cosy python=3.10 -y
conda activate cosy
pip install -r requirements.txt
conda install -y -c conda-forge pynini==2.1.5
pip install modelscope
modelscope download --model iic/CosyVoice2-0.5B --local_dir pretrained_models/CosyVoice2-0.5B
~~~

然后把仓库路径告诉服务端（Windows 侧用 \\wsl$ 路径）：

~~~bat
start.bat --tts cosyvoice --voice clone
~~~

~~~yaml
# server/config.yaml
cosyvoice_dir: "\\\\wsl$\\Ubuntu\\home\\you\\CosyVoice"
~~~

> 跨 WSL 跑 Python 不方便，更省事的做法是**把服务端整个放进 WSL**，Windows 只留浏览器扩展。
> 此时扩展里的「引擎地址」改成 `ws://127.0.0.1:8765/ws` 仍然可用（WSL2 会转发 localhost）。

## 路线 B：Windows 原生（能装，但折腾）

1. 装 Miniconda for Windows。
2. `conda create -n cosy python=3.10`，`conda activate cosy`。
3. `pip install -r requirements.txt`。
4. `pynini` 用 conda-forge 的 win-64 包；装不上就跳过 WeTextProcessing，只用 `inference_cross_lingual`（本项目只用这个）。
5. 下载模型到 `pretrained_models/CosyVoice2-0.5B`。

## 在本项目里启用

~~~yaml
# server/config.yaml
tts: cosyvoice
voice: clone
cosyvoice_dir: "D:/CosyVoice"
~~~

服务端启动日志里应该出现：

~~~
warmup done: tts: CosyVoice2-0.5B (D:/CosyVoice/pretrained_models/CosyVoice2-0.5B)
~~~

## 实测参考（RTX 3050 4G / i7）

| 项 | 值 |
|---|---|
| 显存占用 | 3.8~4.2 GB（fp16 关闭时偏紧） |
| 首句加载 | 12~25 s |
| 单句合成 | 0.5~1.2 s（5 秒译文） |
| 参考音最少 | 3 s（推荐 6~8 s） |
