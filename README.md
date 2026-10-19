# torn-paper-assemble

当用户要求四块撕纸拼接、人物抠像拼合或 vlog 撕纸开场时，将同一帧拆成四片白边撕纸并错峰滑入，拼齐后接回视频。有人物时固定为完整人物一片加剩余背景三片；无人时按景物拆四片。不用于四张不同照片的拼贴或全程人物跟踪。

## 安装

```bash
npx -y skills add jacob6re/torn-paper-assemble -g --all
```

## 使用

安装后，可以这样开始：

> 使用 $torn-paper-assemble 制作四片撕纸开场：有人物先抠出完整人物一片、背景分三片，错峰入场拼齐后恢复原视频。

## 两种模式

- **有人物**：完整人物抠成第 1 片，人物以外的背景分成 3 片。背景不会重复出现人物，人物位于最上层。
- **无人物**：按景物轮廓划分 4 片。所有片段来自同一帧，拼齐后白边淡出，再从定格位置继续播放视频。

人物版的三块背景默认采用明显起伏、弯折且不对称的不规则撕裂轮廓，尤其避免把上方一片做成平切横条。细小锯齿仅用作纸边纹理，不能代替大尺度的不规则分区；人物遮挡之后仍可见的分界也要检查。

每片都带白色撕纸边缘，可分别设置入场方向、开始时间、时长和轻微旋转。照片拼齐后保持完整照片。

## 运行依赖与直接调用

- 支持 Agent Skills 的客户端。
- Python 3、Pillow（`python3 -m pip install Pillow`）。
- FFmpeg / FFprobe（视频抽帧与恢复片段）。
- Node.js 22+、HyperFrames（检查、预览、渲染）。工程命令固定使用 HyperFrames 0.8.161。
- 自动人物抠像使用 macOS 14+ 的 Vision 和本机 Swift。其他系统或需要修正轮廓时，提供与处理后定格帧等大的灰度人物遮罩。

Agent 先看图确定模式和背景分区，脚本负责抠像、扣除人物、生成图块与动画工程。自动抠像不等于无需检查，头发、手指和遮挡边缘可能需要修正。

按 [分区契约](skills/torn-paper-assemble/references/pieces.md) 创建 `pieces.json` 后：

```bash
python3 skills/torn-paper-assemble/scripts/build.py \
  --input /path/to/video.mp4 --frame 0 \
  --pieces /path/to/pieces.json --output /path/to/new-project
```

人物模式在非 macOS 系统上添加 `--person-mask /path/to/mask.png`；白色人物、黑色背景。输出目录必须尚不存在。然后进入工程：

```bash
npm run check
npm run preview -- --background
npm run render -- --output /path/to/result.mp4
```

本地验证分区、错误遮罩与无人模式回归：

```bash
python3 skills/torn-paper-assemble/scripts/test_build.py
```

冻结开场默认静音，恢复片段保留原声；不做全程人物跟踪、背景补画或自动踩点。

## 内容

本仓库只发布运行这个 Skill 所需的文件。本地评测样本、预期答案和运行记录不包含在公开包中。

人物抠像在本机运行。参考录屏、人物照片和用户视频不随本仓库发布。

`assets/gsap.min.js` 保留原作者版权声明，按其 [GSAP Standard License](https://gsap.com/standard-license/) 使用。
